"""knews CLI - 구글 뉴스 수집기 명령줄 인터페이스"""

import argparse
import asyncio
import sys
import os
import subprocess
import shutil
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

console = Console()


def _parse_queries(args) -> tuple[list[str], int]:
    """쿼리와 건수를 파싱. 'A,B,C' 10 또는 'A,B,C' -n 10 모두 지원."""
    raw_parts = args.query  # nargs="+" 로 받은 리스트
    count = args.count  # -n 값 또는 기본값

    # 마지막 인자가 숫자면 건수로 사용 (positional count)
    if len(raw_parts) > 1 and raw_parts[-1].isdigit():
        count = int(raw_parts[-1])
        raw_parts = raw_parts[:-1]

    # 콤마 구분 키워드 분리
    query_text = " ".join(raw_parts)
    queries = [q.strip() for q in query_text.split(",") if q.strip()]

    return queries, count


def cmd_search(args):
    """뉴스 검색 + 본문 추출. 콤마로 여러 키워드 동시 검색 가능."""
    from knews.search import search_news
    from knews.extract import extract_article_with_options
    from knews.output import print_results, to_csv, to_json, to_markdown, to_excel

    queries, count = _parse_queries(args)

    if len(queries) > 1:
        console.print(f"\n[bold blue]멀티 키워드 검색[/bold blue] {len(queries)}개: {', '.join(queries)}")
    else:
        console.print(f"\n[bold blue]뉴스 검색 중...[/bold blue] '{queries[0]}'")
    console.print(f"  최근 {args.days}일 / 키워드당 {count}건 / 백엔드: {args.backend}", style="dim")

    # 1단계: 검색 (키워드별 실행 후 병합)
    results = []
    seen_urls = set()
    for qi, query in enumerate(queries, 1):
        if len(queries) > 1:
            console.print(f"\n  [cyan][{qi}/{len(queries)}][/cyan] '{query}' 검색 중...")
        try:
            hits = search_news(
                query=query,
                max_results=count,
                days=args.days,
                include_content=True,
                site=args.site,
                backend=args.backend,
            )
        except SystemExit as e:
            console.print(str(e))
            return

        # URL 중복 제거 + 키워드 태깅
        for r in hits:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                r._keyword = query
                results.append(r)

        if len(queries) > 1:
            console.print(f"    [green]{len(hits)}건[/green]")

    if not results:
        console.print("[yellow]검색 결과가 없습니다.[/yellow]")
        return

    console.print(f"\n  [green]총 {len(results)}건 검색 완료[/green] (중복 제거 후)")

    # 2단계: 본문이 부족한 기사는 Playwright/httpx로 추출 (병렬)
    articles = []
    # 추출이 필요한 인덱스와 URL 수집
    extraction_tasks = []  # (index, result) 튜플
    for i, r in enumerate(results):
        article_data = {
            "keyword": getattr(r, "_keyword", queries[0]),
            "title": r.title,
            "url": r.url,
            "content": r.content,
            "content_length": len(r.content),
            "source": r.source,
            "published_date": r.published_date,
            "method": "tavily",
            "success": True,
        }
        prefer = getattr(args, "deep", False) or getattr(args, "prefer_browser", False)
        if (len(r.content) < 200 or prefer) and not args.fast:
            extraction_tasks.append((i, r))
            console.print(f"  [{i+1}/{len(results)}] [dim]본문 추출 예정: {r.title[:40]}...[/dim]")
        elif len(r.content) < 50:
            article_data["success"] = False
            article_data["error"] = "본문이 너무 짧습니다"
        articles.append(article_data)

    # 병렬 추출
    if extraction_tasks:
        console.print(f"  [cyan]{len(extraction_tasks)}건 병렬 추출 중...[/cyan]")

        async def _extract_all():
            sem = asyncio.Semaphore(5)

            async def _extract_one(url):
                async with sem:
                    return await extract_article_with_options(
                        url, prefer_browser=prefer,
                    )

            return await asyncio.gather(
                *[_extract_one(r.url) for _, r in extraction_tasks]
            )

        extracted_results = asyncio.run(_extract_all())

        for (idx, r), extracted in zip(extraction_tasks, extracted_results):
            if extracted.success and len(extracted.content) > len(r.content):
                articles[idx]["content"] = extracted.content
                articles[idx]["content_length"] = extracted.content_length
                articles[idx]["method"] = extracted.method
                articles[idx]["thumbnail"] = extracted.thumbnail
            elif not extracted.success and len(r.content) >= 50:
                # 직접 추출 실패했지만 Tavily 본문이 있으면 폴백
                articles[idx]["method"] = "tavily"
            elif not extracted.success and len(r.content) < 50:
                articles[idx]["success"] = False
                articles[idx]["error"] = extracted.error

    # 최신순 정렬
    if getattr(args, "latest", False):
        articles.sort(key=lambda a: a.get("published_date", ""), reverse=True)

    # 3단계: CSV 자동 저장 + 터미널 출력
    query_label = queries[0] if len(queries) == 1 else ",".join(queries)
    slug = query_label.replace(" ", "_").replace(",", "_")[:20]
    save_path = getattr(args, "file", None) or f"news_{slug}.csv"
    if not save_path.endswith(".csv"):
        save_path += ".csv"

    to_csv(articles, save_path)
    print_results(articles, query_label)


def cmd_extract(args):
    """단일 URL 또는 파일에서 기사 추출."""
    from knews.extract import extract_article_with_options
    from knews.output import print_results, to_csv, to_json

    urls = []

    if args.file:
        # 파일에서 URL 목록 읽기
        filepath = Path(args.file)
        if not filepath.exists():
            console.print(f"[red]파일을 찾을 수 없습니다: {args.file}[/red]")
            return
        for line in filepath.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and line.startswith("http"):
                urls.append(line)
    elif args.url:
        urls = [args.url]
    else:
        console.print("[red]URL 또는 --file을 지정하세요.[/red]")
        return

    if not urls:
        console.print("[yellow]추출할 URL이 없습니다.[/yellow]")
        return

    console.print(f"\n[bold blue]기사 추출 중...[/bold blue] {len(urls)}건")

    articles = []
    for i, url in enumerate(urls, 1):
        console.print(f"  [{i}/{len(urls)}] {url[:60]}...")
        result = asyncio.run(
            extract_article_with_options(
                url,
                prefer_browser=args.prefer_browser,
            )
        )
        articles.append({
            "title": result.title,
            "url": result.url,
            "content": result.content,
            "content_length": result.content_length,
            "method": result.method,
            "thumbnail": result.thumbnail,
            "success": result.success,
            "error": result.error,
        })

    print_results(articles, "URL 추출")

    if args.save:
        ext = Path(args.save).suffix.lower()
        if ext == ".csv":
            to_csv(articles, args.save)
        elif ext == ".xlsx":
            from knews.output import to_excel
            to_excel(articles, args.save)
        else:
            to_json(articles, args.save)


def cmd_setup(args):
    """초기 설정: API 키 입력 + Playwright 브라우저 설치."""
    console.print("\n[bold blue]news 초기 설정[/bold blue]\n")

    # ── 1. API 키 설정 ──
    target = Path.home() / ".env"
    existing = {}
    if target.exists():
        for line in target.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                existing[k.strip()] = v.strip()

    # Tavily
    console.print("[bold]1. Tavily API 키[/bold] (필수, 무료 1,000회/월)")
    console.print("   발급: https://app.tavily.com")
    current_tavily = existing.get("TAVILY_API_KEY", "")
    if current_tavily and not current_tavily.startswith("tvly-여기"):
        masked = f"{current_tavily[:7]}...{current_tavily[-4:]}"
        console.print(f"   현재: {masked}")
        tavily_input = input("   새 키 (Enter=유지): ").strip()
        tavily_key = tavily_input if tavily_input else current_tavily
    else:
        tavily_key = input("   키 입력: ").strip()

    # SerpAPI
    console.print("\n[bold]2. SerpAPI 키[/bold] (선택, 구글 뉴스 직접 검색)")
    console.print("   발급: https://serpapi.com")
    current_serp = existing.get("SERPAPI_API_KEY", "")
    if current_serp:
        masked = f"{current_serp[:7]}...{current_serp[-4:]}"
        console.print(f"   현재: {masked}")
        serp_input = input("   새 키 (Enter=유지, skip=건너뛰기): ").strip()
        serp_key = "" if serp_input.lower() == "skip" else (serp_input if serp_input else current_serp)
    else:
        serp_key = input("   키 입력 (Enter=건너뛰기): ").strip()

    # 저장
    lines = []
    if tavily_key:
        lines.append(f"TAVILY_API_KEY={tavily_key}")
    if serp_key:
        lines.append(f"SERPAPI_API_KEY={serp_key}")
    for k, v in existing.items():
        if k not in ("TAVILY_API_KEY", "SERPAPI_API_KEY"):
            lines.append(f"{k}={v}")

    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if tavily_key:
        console.print(f"\n[green]OK[/green] Tavily 키 저장됨")
    if serp_key:
        console.print(f"[green]OK[/green] SerpAPI 키 저장됨")

    # ── 2. Playwright 브라우저 설치 ──
    console.print(f"\n[bold]3. Playwright Chromium 설치[/bold]")
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=False,
    )
    if result.returncode == 0:
        console.print("[green]OK[/green] 브라우저 설치 완료")
    else:
        console.print("[red]FAIL[/red] 브라우저 설치 실패. 직접 실행: playwright install chromium")

    console.print("\n[bold]설정 완료! 바로 사용하세요:[/bold]")
    console.print("  news search \"AI 반도체\" 10")
    console.print()


def cmd_init(args):
    """학습자용 초기 설정 - 대화형 API 키 입력."""
    target = Path(args.path).expanduser() if args.path else Path.home() / ".env"

    console.print("\n[bold blue]knews 초기 설정[/bold blue]\n")

    # 기존 값 로드
    existing = {}
    if target.exists():
        for line in target.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                existing[k.strip()] = v.strip()

    # Tavily
    console.print("[bold]1. Tavily API 키[/bold] (필수, 무료 1,000회/월)")
    console.print("   발급: [link=https://app.tavily.com]https://app.tavily.com[/link]")
    current_tavily = existing.get("TAVILY_API_KEY", "")
    if current_tavily and current_tavily != "tvly-여기에_API_키를_넣으세요":
        masked = f"{current_tavily[:7]}...{current_tavily[-4:]}"
        console.print(f"   현재: {masked}")
        tavily_input = input("   새 키 (Enter=유지): ").strip()
        tavily_key = tavily_input if tavily_input else current_tavily
    else:
        tavily_key = input("   키 입력: ").strip()

    # SerpAPI
    console.print("\n[bold]2. SerpAPI 키[/bold] (선택, 구글 뉴스 직접 검색)")
    console.print("   발급: [link=https://serpapi.com]https://serpapi.com[/link]")
    current_serp = existing.get("SERPAPI_API_KEY", "")
    if current_serp:
        masked = f"{current_serp[:7]}...{current_serp[-4:]}"
        console.print(f"   현재: {masked}")
        serp_input = input("   새 키 (Enter=유지, 'skip'=건너뛰기): ").strip()
        serp_key = "" if serp_input.lower() == "skip" else (serp_input if serp_input else current_serp)
    else:
        serp_key = input("   키 입력 (Enter=건너뛰기): ").strip()

    # 저장
    lines = []
    if tavily_key:
        lines.append(f"TAVILY_API_KEY={tavily_key}")
    if serp_key:
        lines.append(f"SERPAPI_API_KEY={serp_key}")

    # 기존 다른 키 보존
    for k, v in existing.items():
        if k not in ("TAVILY_API_KEY", "SERPAPI_API_KEY"):
            lines.append(f"{k}={v}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")

    console.print(f"\n[green]저장 완료:[/green] {target}")
    if tavily_key:
        console.print("[green]OK[/green] Tavily 설정됨")
    if serp_key:
        console.print("[green]OK[/green] SerpAPI 설정됨")
    console.print("\n다음 단계:")
    console.print("  knews setup       # 브라우저 설치")
    console.print("  knews doctor      # 환경 점검")
    console.print("  knews news \"AI\"   # 뉴스 수집 시작!")
    console.print()


def cmd_doctor(args):
    """환경 설정 상태 점검."""
    from knews import __version__

    console.print(f"\n[bold blue]knews 환경 점검[/bold blue] [dim]v{__version__}[/dim]\n")

    # Tavily
    api_key = os.getenv("TAVILY_API_KEY", "")
    if api_key:
        masked = f"{api_key[:7]}...{api_key[-4:]}" if len(api_key) > 11 else "(설정됨)"
        console.print(f"[green]OK[/green] TAVILY_API_KEY: {masked}")
    else:
        console.print("[red]FAIL[/red] TAVILY_API_KEY: 설정되지 않음 (Tavily 사용 불가)")

    # SerpAPI
    serp_key = os.getenv("SERPAPI_API_KEY", "")
    if serp_key:
        masked = f"{serp_key[:7]}...{serp_key[-4:]}" if len(serp_key) > 11 else "(설정됨)"
        console.print(f"[green]OK[/green] SERPAPI_API_KEY: {masked}")
    else:
        console.print("[yellow]WARN[/yellow] SERPAPI_API_KEY: 설정되지 않음 (SerpAPI 사용 불가)")

    playwright_ok = False
    browser_ok = False
    browser_path = ""

    try:
        from playwright.sync_api import sync_playwright

        playwright_ok = True
        console.print("[green]OK[/green] playwright 패키지: 설치됨")

        with sync_playwright() as p:
            browser_path = p.chromium.executable_path
        browser_ok = bool(browser_path) and Path(browser_path).exists()
    except ImportError:
        console.print("[red]FAIL[/red] playwright 패키지: 가져올 수 없음")
    except Exception:
        browser_ok = False

    if playwright_ok and browser_ok:
        console.print(f"[green]OK[/green] Chromium 브라우저: 설치됨 [dim]({browser_path})[/dim]")
    elif playwright_ok:
        console.print("[yellow]WARN[/yellow] Chromium 브라우저: 아직 설치되지 않음")
        console.print("      해결: knews setup")

    console.print("\n[bold]추천 시작 명령[/bold]")
    console.print("  knews init")
    console.print("  knews news \"AI 인공지능\"")
    console.print("  knews news \"경제 뉴스\" 5 -d 3 -csv")
    console.print("  knews extract https://news.jtbc.co.kr/article/...")
    console.print()


def cmd_sites(args):
    """지원하는 뉴스 사이트 목록."""
    from knews.extract import JS_RENDER_SITES

    console.print("\n[bold blue]JS 렌더링 사이트 (Playwright 사용)[/bold blue]")
    for site in sorted(JS_RENDER_SITES):
        console.print(f"  - {site}")

    console.print("\n[dim]위 사이트는 자동으로 Playwright로 추출됩니다.[/dim]")
    console.print("[dim]그 외 사이트는 httpx(빠름)로 먼저 시도 후 실패 시 Playwright를 사용합니다.[/dim]\n")


def main():
    """CLI 진입점."""
    # .env 파일 로드 (현재 디렉토리 또는 홈)
    load_dotenv()
    home_env = Path.home() / ".env"
    if home_env.exists():
        load_dotenv(home_env)

    parser = argparse.ArgumentParser(
        prog="news",
        description="한국 뉴스 수집기 - 검색 + 본문 추출 + 저장",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  news setup                             최초 설정 (API 키 + 브라우저)
  news search "AI 반도체"                검색 + CSV 자동 저장
  news search "케데헌,BTS" 5             멀티 키워드, 5건
  news search "경제" -d 3 -latest        최근 3일, 최신순
  news extract https://news.jtbc.co.kr/...  단일 URL 본문 추출
        """,
    )
    parser.add_argument("-v", "--version", action="version", version="knews 0.5.0")

    sub = parser.add_subparsers(dest="command", help="명령어")

    # news (메인 명령)
    def _add_news_args(p):
        """news/search/collect 공통 인자."""
        p.add_argument("query", nargs="+", help="검색어 (콤마로 멀티 키워드, 마지막 숫자는 건수)")
        p.add_argument("-d", type=int, default=7, dest="days", help="최근 N일 (기본: 7)")
        p.add_argument("-latest", action="store_true", help=argparse.SUPPRESS)
        # 내부용 (숨김)
        p.add_argument("-n", "--count", type=int, default=10, help=argparse.SUPPRESS)
        p.add_argument("-f", dest="file", help=argparse.SUPPRESS)
        p.add_argument("-s", dest="site", help=argparse.SUPPRESS)
        p.add_argument("-csv", action="store_true", help=argparse.SUPPRESS)
        p.add_argument("-excel", action="store_true", help=argparse.SUPPRESS)
        p.add_argument("-json", action="store_true", help=argparse.SUPPRESS)
        p.add_argument("-md", action="store_true", help=argparse.SUPPRESS)
        p.add_argument("-fast", action="store_true", help=argparse.SUPPRESS)
        p.add_argument("-deep", action="store_true", help=argparse.SUPPRESS)
        p.add_argument("--backend", default="auto", help=argparse.SUPPRESS)
        p.add_argument("-o", "--output", default="terminal", help=argparse.SUPPRESS)
        p.set_defaults(func=cmd_search)

    p_search = sub.add_parser("search", help="뉴스 검색 + 본문 추출 + 저장")
    _add_news_args(p_search)

    # collect (별칭)
    p_collect = sub.add_parser("collect", help="search와 동일")
    _add_news_args(p_collect)

    # extract
    p_extract = sub.add_parser("extract", help="URL에서 기사 본문 추출")
    p_extract.add_argument("url", nargs="?", help="추출할 URL")
    p_extract.add_argument("-f", "--file", help="URL 목록 파일 (한 줄에 하나)")
    p_extract.add_argument("-s", "--save", help="저장 파일 경로")
    p_extract.add_argument("--prefer-browser", action="store_true", help="브라우저 우선 추출")
    p_extract.set_defaults(func=cmd_extract)

    # setup
    p_setup = sub.add_parser("setup", help="Playwright 브라우저 설치")
    p_setup.set_defaults(func=cmd_setup)


    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
