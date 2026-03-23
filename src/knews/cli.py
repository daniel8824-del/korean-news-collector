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


def cmd_search(args):
    """뉴스 검색 + 본문 추출."""
    from knews.search import search_news
    from knews.extract import extract_article_with_options
    from knews.output import print_results, to_csv, to_json, to_markdown, to_excel

    query = " ".join(args.query)
    console.print(f"\n[bold blue]뉴스 검색 중...[/bold blue] '{query}'")
    console.print(f"  최근 {args.days}일 / 최대 {args.count}건 / 백엔드: {args.backend}", style="dim")

    # 1단계: 검색 (Tavily 또는 SerpAPI)
    try:
        results = search_news(
            query=query,
            max_results=args.count,
            days=args.days,
            include_content=True,
            site=args.site,
            backend=args.backend,
        )
    except SystemExit as e:
        console.print(str(e))
        return

    if not results:
        console.print("[yellow]검색 결과가 없습니다.[/yellow]")
        return

    console.print(f"  [green]{len(results)}건 검색 완료[/green]")

    # 2단계: 본문이 부족한 기사는 Playwright/httpx로 추출
    articles = []
    for i, r in enumerate(results, 1):
        article_data = {
            "title": r.title,
            "url": r.url,
            "content": r.content,
            "content_length": len(r.content),
            "source": r.source,
            "published_date": r.published_date,
            "method": "tavily",
            "success": True,
        }

        # Tavily 본문이 짧거나 브라우저 우선 모드면 직접 추출
        if (len(r.content) < 200 or args.prefer_browser) and not args.fast:
            console.print(f"  [{i}/{len(results)}] [dim]본문 추출 중: {r.title[:40]}...[/dim]")
            extracted = asyncio.run(
                extract_article_with_options(
                    r.url,
                    prefer_browser=args.prefer_browser,
                )
            )
            if extracted.success and len(extracted.content) > len(r.content):
                article_data["content"] = extracted.content
                article_data["content_length"] = extracted.content_length
                article_data["method"] = extracted.method
                article_data["thumbnail"] = extracted.thumbnail
            elif not extracted.success and len(r.content) < 50:
                article_data["success"] = False
                article_data["error"] = extracted.error
        elif len(r.content) < 50:
            article_data["success"] = False
            article_data["error"] = "본문이 너무 짧습니다"

        articles.append(article_data)

    # 3단계: 출력
    fmt = args.output.lower()
    save_path = args.save

    if fmt == "csv":
        if not save_path:
            save_path = f"news_{query.replace(' ', '_')[:20]}.csv"
        to_csv(articles, save_path)
        print_results(articles, query)
    elif fmt == "json":
        if not save_path:
            save_path = f"news_{query.replace(' ', '_')[:20]}.json"
        to_json(articles, save_path)
        print_results(articles, query)
    elif fmt == "md":
        if not save_path:
            save_path = f"news_{query.replace(' ', '_')[:20]}.md"
        to_markdown(articles, query, save_path)
        print_results(articles, query)
    elif fmt in ("excel", "xlsx"):
        if not save_path:
            save_path = f"news_{query.replace(' ', '_')[:20]}.xlsx"
        to_excel(articles, save_path, query)
        print_results(articles, query)
    else:
        # 터미널 출력만
        print_results(articles, query)
        if save_path:
            to_json(articles, save_path)


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
    """Playwright 브라우저 설치."""
    console.print("\n[bold blue]Playwright Chromium 설치 중...[/bold blue]")
    console.print("  (JTBC, 조선일보 등 JS 사이트 추출에 필요합니다)\n")

    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=False,
    )
    if result.returncode == 0:
        console.print("\n[green]설치 완료! 이제 모든 뉴스 사이트를 추출할 수 있습니다.[/green]")
    else:
        console.print("\n[red]설치 실패. 아래 명령어를 직접 실행해보세요:[/red]")
        console.print("  playwright install chromium")


def cmd_init(args):
    """학습자용 초기 설정 파일 생성."""
    target = Path(args.path).expanduser() if args.path else Path.home() / ".env"
    example = Path(__file__).resolve().parents[2] / ".env.example"

    if target.exists() and not args.force:
        console.print(f"[yellow]이미 파일이 있습니다:[/yellow] {target}")
        console.print("덮어쓰려면 `knews init --force` 를 사용하세요.")
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(example, target)

    console.print(f"\n[green]환경설정 파일 생성:[/green] {target}")
    console.print("1. 파일을 열고 `TAVILY_API_KEY=tvly-...` 값을 넣으세요.")
    console.print("2. 확인은 `knews doctor`")
    console.print("3. 검색은 `knews collect \"반도체 뉴스\"`")
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
    console.print("  knews search \"AI 인공지능\"")
    console.print("  knews search \"경제 뉴스\" -n 5 -d 3 -o csv")
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
        prog="knews",
        description="구글 뉴스 감각의 수집기 - Tavily 검색 + Playwright 추출",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  knews init                               ~/.env 설정 파일 생성
  knews search "AI 인공지능"              검색 후 터미널 출력
  knews search "경제 뉴스" -n 5 -d 3      최근 3일, 5건
  knews search "JTBC" -o csv              CSV로 저장
  knews search "정치" --site chosun.com   특정 사이트만

  knews extract https://news.jtbc.co.kr/...  단일 URL 추출
  knews extract --file urls.txt              파일에서 일괄 추출
  knews extract URL --prefer-browser         브라우저 우선 추출
  knews collect "반도체 뉴스"                 search와 동일한 별칭

  knews setup                             Playwright 브라우저 설치
  knews doctor                            API 키/브라우저 상태 점검
  knews sites                             지원 사이트 목록

환경변수:
  TAVILY_API_KEY    Tavily API 키 (필수, https://app.tavily.com)
        """,
    )
    parser.add_argument("-v", "--version", action="version", version="knews 0.4.0")

    sub = parser.add_subparsers(dest="command", help="명령어")

    # search
    p_search = sub.add_parser("search", help="뉴스 검색 + 본문 추출")
    p_search.add_argument("query", nargs="+", help="검색어")
    p_search.add_argument("-n", "--count", type=int, default=10, help="결과 수 (기본: 10)")
    p_search.add_argument("-d", "--days", type=int, default=7, help="최근 N일 (기본: 7)")
    p_search.add_argument("-o", "--output", default="terminal", choices=["terminal", "csv", "json", "md", "excel"], help="출력 형식 (excel=xlsx)")
    p_search.add_argument("-s", "--save", help="저장 파일 경로")
    p_search.add_argument("--site", help="특정 사이트 제한 (예: jtbc.co.kr)")
    p_search.add_argument("--backend", default="tavily", choices=["tavily"], help="검색 백엔드 (기본: tavily)")
    p_search.add_argument("--fast", action="store_true", help="Tavily 결과만 사용 (추가 추출 안 함)")
    p_search.add_argument("--prefer-browser", action="store_true", help="모든 기사에 대해 Playwright를 우선 사용")
    p_search.set_defaults(func=cmd_search)

    # extract
    p_extract = sub.add_parser("extract", help="URL에서 기사 본문 추출")
    p_extract.add_argument("url", nargs="?", help="추출할 URL")
    p_extract.add_argument("-f", "--file", help="URL 목록 파일 (한 줄에 하나)")
    p_extract.add_argument("-s", "--save", help="저장 파일 경로 (.csv 또는 .json)")
    p_extract.add_argument("--prefer-browser", action="store_true", help="httpx보다 Playwright를 먼저 사용")
    p_extract.set_defaults(func=cmd_extract)

    # collect
    p_collect = sub.add_parser("collect", help="search와 동일한 학습자용 별칭")
    p_collect.add_argument("query", nargs="+", help="검색어")
    p_collect.add_argument("-n", "--count", type=int, default=10, help="결과 수 (기본: 10)")
    p_collect.add_argument("-d", "--days", type=int, default=7, help="최근 N일 (기본: 7)")
    p_collect.add_argument("-o", "--output", default="terminal", choices=["terminal", "csv", "json", "md", "excel"], help="출력 형식 (excel=xlsx)")
    p_collect.add_argument("-s", "--save", help="저장 파일 경로")
    p_collect.add_argument("--site", help="특정 사이트 제한 (예: jtbc.co.kr)")
    p_collect.add_argument("--backend", default="tavily", choices=["tavily"], help="검색 백엔드 (기본: tavily)")
    p_collect.add_argument("--fast", action="store_true", help="Tavily 결과만 사용 (추가 추출 안 함)")
    p_collect.add_argument("--prefer-browser", action="store_true", help="모든 기사에 대해 Playwright를 우선 사용")
    p_collect.set_defaults(func=cmd_search)

    # setup
    p_setup = sub.add_parser("setup", help="Playwright 브라우저 설치")
    p_setup.set_defaults(func=cmd_setup)

    # init
    p_init = sub.add_parser("init", help="~/.env 설정 파일 생성")
    p_init.add_argument("--path", help="생성할 .env 경로 (기본: ~/.env)")
    p_init.add_argument("--force", action="store_true", help="기존 파일 덮어쓰기")
    p_init.set_defaults(func=cmd_init)

    # doctor
    p_doctor = sub.add_parser("doctor", help="API 키와 Playwright 상태 점검")
    p_doctor.set_defaults(func=cmd_doctor)

    # sites
    p_sites = sub.add_parser("sites", help="지원 뉴스 사이트 목록")
    p_sites.set_defaults(func=cmd_sites)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
