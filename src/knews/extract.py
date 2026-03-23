"""기사 본문 추출 - Playwright (JS 사이트) + httpx (경량 fallback)"""

import asyncio
import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup


# JS 렌더링이 필요한 한국 뉴스 사이트
JS_RENDER_SITES = {
    "jtbc.co.kr",
    "news.jtbc.co.kr",
    "chosun.com",
    "biz.chosun.com",
    "ichannela.com",
    "mbc.co.kr",
    "imnews.imbc.com",
    "sbs.co.kr",
    "news.sbs.co.kr",
    "tvchosun.com",
    "ytn.co.kr",
    "news.zum.com",
    "v.daum.net",
    "n.news.naver.com",
    "vogue.co.kr",
}


@dataclass
class Article:
    """추출된 기사"""
    title: str
    url: str
    content: str
    content_length: int
    method: str  # "playwright" | "httpx" | "tavily"
    thumbnail: str = ""
    success: bool = True
    error: str = ""


def _needs_playwright(url: str) -> bool:
    """URL이 JS 렌더링이 필요한 사이트인지 판별."""
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.replace("www.", "")
    return any(site in domain for site in JS_RENDER_SITES)


def _extract_thumbnail(soup: BeautifulSoup, base_url: str) -> str:
    """HTML에서 썸네일 URL 추출."""
    from urllib.parse import urljoin

    # og:image
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        img = og["content"]
        if img.startswith("http"):
            return img
        if img.startswith("//"):
            return "https:" + img
        return urljoin(base_url, img)

    # twitter:image
    tw = soup.find("meta", attrs={"name": "twitter:image"}) or soup.find(
        "meta", attrs={"property": "twitter:image"}
    )
    if tw and tw.get("content"):
        img = tw["content"]
        return img if img.startswith("http") else urljoin(base_url, img)

    return ""


def _parse_article_html(html: str, url: str) -> tuple[str, str, str]:
    """HTML에서 제목, 본문, 썸네일 추출."""
    soup = BeautifulSoup(html, "lxml")

    # 불필요한 태그 제거
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "iframe", "noscript"]):
        tag.decompose()
    for el in soup.find_all(class_=re.compile(r"ad|advertisement|banner|sidebar|related|comment|share|social", re.I)):
        el.decompose()

    # 제목
    title = ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"]
    if not title:
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""

    # 썸네일
    thumbnail = _extract_thumbnail(soup, url)

    # 본문 추출 (우선순위)
    content = ""

    # 1. article 태그
    article = soup.find("article")
    if article:
        paragraphs = article.find_all("p")
        texts = [p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20]
        content = "\n\n".join(texts)

    # 2. 본문 class 검색
    if len(content) < 100:
        selectors = [
            ".article-body", ".article-content", ".post-content",
            ".entry-content", ".content", ".article_body",
            ".story-body", ".news-body", '[data-t="article-body"]',
            'div[itemprop="articleBody"]', ".articleBody",
            "#articleBodyContents", "#newsEndContents",
            ".news_cnt_detail_wrap", "#articeBody",
        ]
        for sel in selectors:
            el = soup.select_one(sel)
            if el:
                paragraphs = el.find_all("p")
                if paragraphs:
                    texts = [p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20]
                    if texts:
                        content = "\n\n".join(texts)
                else:
                    content = el.get_text(separator="\n", strip=True)
                if len(content) > 100:
                    break

    # 3. main 태그
    if len(content) < 100:
        main = soup.find("main")
        if main:
            paragraphs = main.find_all("p")
            texts = [p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20]
            content = "\n\n".join(texts)

    # 4. 모든 p 태그 (최후 수단)
    if len(content) < 100:
        paragraphs = soup.find_all("p")
        noise = {"cookie", "로그인", "copyright", "저작권", "구독", "댓글"}
        texts = []
        for p in paragraphs:
            text = p.get_text(strip=True)
            if len(text) > 30 and not any(k in text.lower() for k in noise):
                texts.append(text)
        content = "\n\n".join(texts)

    # 후처리: 연속 빈 줄 제거
    content = re.sub(r"\n\s*\n+", "\n\n", content).strip()

    # n8n 클리닝 적용
    from knews.clean import clean_news_body
    content = clean_news_body(content, url)

    return title, content, thumbnail


async def extract_with_playwright(url: str) -> Article:
    """Playwright로 JS 렌더링 후 본문 추출."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return Article(
            title="", url=url, content="", content_length=0,
            method="playwright", success=False,
            error="playwright가 설치되지 않았습니다. 'knews setup' 을 실행하세요.",
        )

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                locale="ko-KR",
                timezone_id="Asia/Seoul",
            )
            page = await context.new_page()

            # 이미지/폰트 차단 (속도 향상)
            await page.route(
                "**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,eot}",
                lambda route: route.abort(),
            )

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(3000)
            except Exception:
                pass  # 타임아웃이어도 현재 HTML 사용

            html = await page.content()
            await browser.close()

        title, content, thumbnail = _parse_article_html(html, url)

        if len(content) < 50:
            return Article(
                title=title, url=url, content=content,
                content_length=len(content), method="playwright",
                thumbnail=thumbnail, success=False,
                error=f"본문이 너무 짧습니다 ({len(content)}자)",
            )

        return Article(
            title=title, url=url, content=content,
            content_length=len(content), method="playwright",
            thumbnail=thumbnail,
        )

    except Exception as e:
        return Article(
            title="", url=url, content="", content_length=0,
            method="playwright", success=False, error=str(e),
        )


async def extract_with_httpx(url: str) -> Article:
    """httpx로 정적 페이지 추출 (빠름)."""
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=15.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "ko-KR,ko;q=0.9",
            },
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text

        title, content, thumbnail = _parse_article_html(html, url)

        if len(content) < 50:
            return Article(
                title=title, url=url, content=content,
                content_length=len(content), method="httpx",
                thumbnail=thumbnail, success=False,
                error=f"본문이 너무 짧습니다 ({len(content)}자). JS 렌더링이 필요할 수 있습니다.",
            )

        return Article(
            title=title, url=url, content=content,
            content_length=len(content), method="httpx",
            thumbnail=thumbnail,
        )

    except Exception as e:
        return Article(
            title="", url=url, content="", content_length=0,
            method="httpx", success=False, error=str(e),
        )


async def extract_article(url: str) -> Article:
    """
    URL에서 기사 본문 추출.
    JS 사이트 → Playwright, 나머지 → httpx 시도 후 실패 시 Playwright fallback.
    """
    if _needs_playwright(url):
        return await extract_with_playwright(url)

    # httpx 먼저 시도 (빠름)
    result = await extract_with_httpx(url)
    if result.success:
        return result

    # httpx 실패 → Playwright fallback
    return await extract_with_playwright(url)


def extract_article_sync(url: str) -> Article:
    """동기 래퍼."""
    return asyncio.run(extract_article(url))
