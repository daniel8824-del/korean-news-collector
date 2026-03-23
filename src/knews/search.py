"""Tavily API 기반 뉴스 검색"""

import os
from dataclasses import dataclass, field
from tavily import TavilyClient


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


def get_client() -> TavilyClient:
    """Tavily 클라이언트 생성. API 키가 없으면 안내 메시지 출력."""
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        raise SystemExit(
            "\n[오류] TAVILY_API_KEY가 설정되지 않았습니다.\n\n"
            "설정 방법 (택 1):\n"
            "  1) 환경변수:  export TAVILY_API_KEY=tvly-xxxxxxxx\n"
            "  2) .env 파일: 프로젝트 폴더에 .env 파일 생성 후\n"
            "     TAVILY_API_KEY=tvly-xxxxxxxx\n\n"
            "API 키 발급: https://app.tavily.com  (무료 1,000회/월)\n"
        )
    return TavilyClient(api_key=api_key)


def search_news(
    query: str,
    max_results: int = 10,
    days: int = 7,
    include_content: bool = True,
    site: str | None = None,
) -> list[NewsResult]:
    """
    Tavily로 뉴스 검색.

    Args:
        query: 검색어 (예: "AI 인공지능", "JTBC 경제 뉴스")
        max_results: 최대 결과 수 (1-20)
        days: 최근 N일 이내
        include_content: Tavily에서 본문도 함께 가져올지
        site: 특정 사이트 제한 (예: "jtbc.co.kr")

    Returns:
        NewsResult 리스트
    """
    client = get_client()

    # 사이트 제한이 있으면 쿼리에 추가
    search_query = query
    include_domains = []
    if site:
        include_domains = [site]

    response = client.search(
        query=search_query,
        search_depth="advanced",
        topic="news",
        days=days,
        max_results=min(max_results, 20),
        include_raw_content=include_content,
        include_domains=include_domains if include_domains else None,
    )

    results = []
    for item in response.get("results", []):
        # Tavily raw_content가 있으면 사용, 없으면 content 사용
        from knews.clean import clean_news_body
        raw = item.get("raw_content", "") or item.get("content", "")
        item_url = item.get("url", "")
        content = clean_news_body(raw, item_url) if raw else ""

        # 소스 도메인 추출
        url = item.get("url", "")
        source = ""
        if url:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            source = parsed.netloc.replace("www.", "")

        results.append(NewsResult(
            title=item.get("title", ""),
            url=url,
            snippet=item.get("content", "")[:300],
            content=content,
            source=source,
            published_date=item.get("published_date", ""),
            score=item.get("score", 0.0),
        ))

    return results
