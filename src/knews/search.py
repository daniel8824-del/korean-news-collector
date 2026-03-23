"""뉴스 검색 - SerpAPI (구글 뉴스) + Tavily (범용)"""

import os
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx


# 뉴스 포털/애그리게이터 (자동요약만 제공, 원본 아님)
EXCLUDED_DOMAINS = {
    "news.nate.com",
    "nate.com",
    "msn.com",
    "www.msn.com",
}


@dataclass
class NewsResult:
    """검색 결과 하나"""
    title: str
    url: str
    snippet: str = ""
    content: str = ""
    source: str = ""
    published_date: str = ""
    score: float = 0.0


# ─── SerpAPI (구글 뉴스 전용) ───


def _search_serpapi(
    query: str,
    max_results: int = 10,
    days: int = 7,
    site: str | None = None,
) -> list[NewsResult]:
    """SerpAPI google_news 엔진으로 구글 뉴스 검색."""
    api_key = os.getenv("SERPAPI_API_KEY", "")
    if not api_key:
        raise SystemExit(
            "\n[오류] SERPAPI_API_KEY가 설정되지 않았습니다.\n\n"
            "설정 방법 (택 1):\n"
            "  1) 환경변수:  export SERPAPI_API_KEY=...\n"
            "  2) .env 파일: SERPAPI_API_KEY=...\n\n"
            "API 키 발급: https://serpapi.com  (무료 100회/월)\n"
        )

    # 기간 매핑: days → tbs 파라미터
    tbs_map = {1: "qdr:d", 3: "qdr:d3", 7: "qdr:w", 30: "qdr:m"}
    tbs = "qdr:w"  # 기본 1주
    for threshold in sorted(tbs_map.keys()):
        if days <= threshold:
            tbs = tbs_map[threshold]
            break

    search_query = query
    if site:
        search_query = f"site:{site} {query}"

    params = {
        "engine": "google_news",
        "q": search_query,
        "gl": "kr",
        "hl": "ko",
        "num": str(min(max_results, 100)),
        "tbs": tbs,
        "api_key": api_key,
    }

    resp = httpx.get("https://serpapi.com/search", params=params, timeout=15.0)
    resp.raise_for_status()
    data = resp.json()

    results = []
    for item in data.get("news_results", []):
        url = item.get("link", "")
        source = ""
        if url:
            source = urlparse(url).netloc.replace("www.", "")

        # SerpAPI는 본문을 제공하지 않음 → snippet만
        snippet = item.get("snippet", "")
        date = item.get("date", "")

        # 하위 기사(stories) 처리
        if not url and "stories" in item:
            for story in item["stories"][:1]:
                url = story.get("link", "")
                snippet = story.get("snippet", snippet)
                source = story.get("source", {}).get("name", "")
                break

        if url and not any(d in url for d in EXCLUDED_DOMAINS):
            results.append(NewsResult(
                title=item.get("title", ""),
                url=url,
                snippet=snippet[:300],
                content="",  # SerpAPI는 본문 없음 → 이후 extract로 보충
                source=source or item.get("source", {}).get("name", ""),
                published_date=date,
            ))

    return results[:max_results]


# ─── Tavily (범용 검색) ───


def _search_tavily(
    query: str,
    max_results: int = 10,
    days: int = 7,
    include_content: bool = True,
    site: str | None = None,
) -> list[NewsResult]:
    """Tavily API로 뉴스 검색."""
    from tavily import TavilyClient

    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        raise SystemExit(
            "\n[오류] TAVILY_API_KEY가 설정되지 않았습니다.\n\n"
            "설정 방법 (택 1):\n"
            "  1) 환경변수:  export TAVILY_API_KEY=tvly-xxxxxxxx\n"
            "  2) .env 파일: TAVILY_API_KEY=tvly-xxxxxxxx\n\n"
            "API 키 발급: https://app.tavily.com  (무료 1,000회/월)\n"
        )

    client = TavilyClient(api_key=api_key)

    include_domains = [site] if site else None

    response = client.search(
        query=query,
        search_depth="advanced",
        topic="news",
        days=days,
        max_results=min(max_results, 20),
        include_raw_content=include_content,
        include_domains=include_domains,
    )

    from knews.clean import clean_news_body

    results = []
    for item in response.get("results", []):
        raw = item.get("raw_content", "") or item.get("content", "")
        item_url = item.get("url", "")
        content = clean_news_body(raw, item_url) if raw else ""

        source = ""
        if item_url:
            source = urlparse(item_url).netloc.replace("www.", "")

        if any(d in item_url for d in EXCLUDED_DOMAINS):
            continue

        results.append(NewsResult(
            title=item.get("title", ""),
            url=item_url,
            snippet=item.get("content", "")[:300],
            content=content,
            source=source,
            published_date=item.get("published_date", ""),
            score=item.get("score", 0.0),
        ))

    return results


# ─── 통합 인터페이스 ───


def search_news(
    query: str,
    max_results: int = 10,
    days: int = 7,
    include_content: bool = True,
    site: str | None = None,
    backend: str = "auto",
) -> list[NewsResult]:
    """
    뉴스 검색 통합 인터페이스.

    Args:
        query: 검색어
        max_results: 최대 결과 수
        days: 최근 N일 이내
        include_content: 본문 포함 여부 (Tavily만 해당)
        site: 특정 사이트 제한
        backend: "auto" | "serpapi" | "tavily"
            auto: SERPAPI_API_KEY 있으면 serpapi, 없으면 tavily
    """
    if backend == "auto":
        backend = "serpapi" if os.getenv("SERPAPI_API_KEY") else "tavily"

    if backend == "serpapi":
        return _search_serpapi(query, max_results, days, site)
    elif backend == "tavily":
        return _search_tavily(query, max_results, days, include_content, site)
    else:
        raise SystemExit(f"\n[오류] 지원하지 않는 백엔드: {backend}\n사용 가능: auto, serpapi, tavily\n")
