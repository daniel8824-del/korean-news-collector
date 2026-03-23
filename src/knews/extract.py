"""기사 본문 추출 - Playwright (JS 사이트) + httpx (경량 fallback)"""

import asyncio
import re
from dataclasses import dataclass
from urllib.parse import urlparse

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
    "news1.kr",
    "mk.co.kr",
    "news.kbs.co.kr",
    "etnews.com",
    "nocutnews.co.kr",
    "joongang.co.kr",
    "donga.com",
    "khan.co.kr",
    "hani.co.kr",
    "sedaily.com",
    "mt.co.kr",
    "biz.heraldcorp.com",
    "edaily.co.kr",
    "asiae.co.kr",
    "fnnews.com",
    "newsis.com",
    "ddaily.co.kr",
    "inews24.com",
    "mbn.co.kr",
    "yna.co.kr",
    "maxmovie.com",
}

PLAYWRIGHT_UPGRADE_HINTS = (
    "articleview",
    "/news/view",
    "view.html",
    "view.do",
    "endpage.do",
    "/article/",
)


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
    domain = urlparse(url).netloc.replace("www.", "")
    return any(site in domain for site in JS_RENDER_SITES)


def _looks_like_news_article(url: str) -> bool:
    """URL이 뉴스 기사 페이지처럼 보이는지 판별."""
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "")
    path = f"{parsed.path}?{parsed.query}".lower()
    if _needs_playwright(url):
        return True
    if domain.endswith(".kr") and any(hint in path for hint in PLAYWRIGHT_UPGRADE_HINTS):
        return True
    newsy_domains = (
        "news", "chosun", "joongang", "donga", "hani", "khan",
        "etnews", "nocut", "mk.co.kr", "imbc", "sbs", "ytn",
    )
    return any(token in domain for token in newsy_domains)


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
    for el in soup.find_all(class_=re.compile(r"\bad\b|advertisement|banner|sidebar|related|comment|share|social", re.I)):
        el.decompose()
    # 뉴스 사이트 공통 노이즈 컨테이너 제거
    noise_classes = re.compile(
        r"txt-bx|recommend|popular|most_read|hot_news|rank|"
        r"more_news|aside_|widget|promo|dable|taboola|outbrain",
        re.I,
    )
    for el in soup.find_all(class_=noise_classes):
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
            ".article_txt", ".newsct_article", ".viewer_article",
            ".article_view", ".articleView", ".view_con",
            "#articleTxt", "#article-view-content-div",
            "#newsText", ".news_txt", ".articleContent",
            ".news_view",
        ]
        for sel in selectors:
            el = soup.select_one(sel)
            if el:
                paragraphs = el.find_all("p")
                if paragraphs:
                    texts = [p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20]
                    if texts:
                        content = "\n\n".join(texts)
                if len(content) < 100:
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

    # nate.com 자동 요약 감지: 실제 본문 아님
    if "기사 제목과 본문 내용을 자동 요약한 내용입니다" in content:
        content = ""

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
        from playwright_stealth import Stealth

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
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

            # Stealth 적용 (봇 감지 우회)
            stealth = Stealth()
            await stealth.apply_stealth_async(page)

            # 이미지/폰트 차단 (속도 향상)
            await page.route(
                "**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,eot}",
                lambda route: route.abort(),
            )

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(3000)
                try:
                    await page.wait_for_selector(
                        "article, main, #articleBodyContents, #newsEndContents, "
                        ".article-body, .article-content, .news-body, "
                        ".news_cnt_detail_wrap, .article_txt, .viewer_article, "
                        ".article_view, #articleTxt, #article-view-content-div, "
                        "[itemprop='articleBody']",
                        timeout=5000,
                    )
                except Exception:
                    pass
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


def extract_with_newspaper(url: str) -> Article:
    """newspaper3k로 정적 사이트 추출 (가장 빠름, n8n 원본 방식)."""
    try:
        from newspaper import Article as NArticle

        article = NArticle(url, language="ko")
        article.download()
        article.parse()

        title = article.title or ""
        raw_content = article.text or ""
        thumbnail = article.top_image or ""

        # 클리닝 적용
        from knews.clean import clean_news_body
        content = clean_news_body(raw_content, url)
        content_length = len(content)

        if content_length < 100:
            return Article(
                title=title, url=url, content=content,
                content_length=content_length, method="newspaper3k",
                thumbnail=thumbnail, success=False,
                error=f"본문이 너무 짧습니다 ({content_length}자). JS 렌더링이 필요할 수 있습니다.",
            )

        return Article(
            title=title, url=url, content=content,
            content_length=content_length, method="newspaper3k",
            thumbnail=thumbnail,
        )

    except Exception as e:
        return Article(
            title="", url=url, content="", content_length=0,
            method="newspaper3k", success=False, error=str(e),
        )


async def extract_with_httpx(url: str) -> Article:
    """httpx + BeautifulSoup으로 추출 (newspaper3k 실패 시 fallback)."""
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
    return await extract_article_with_options(url)


async def extract_article_with_options(url: str, prefer_browser: bool = False) -> Article:
    """
    URL에서 기사 본문 추출.
    우선순위: Playwright(stealth) → newspaper3k → (Tavily 본문은 cli에서 처리)
    한국 뉴스는 JS 렌더링이 대부분이라 Playwright 먼저.
    """
    # 1단계: Playwright + Stealth (가장 확실)
    result = await extract_with_playwright(url)
    if result.success and result.content_length >= 200:
        return result

    # 2단계: newspaper3k fallback (방화벽 차단 시)
    np_result = extract_with_newspaper(url)
    if np_result.success and np_result.content_length > (result.content_length or 0):
        return np_result

    # 둘 다 실패 시 더 나은 결과 반환
    return result if result.success else np_result


def extract_article_sync(url: str, prefer_browser: bool = False) -> Article:
    """동기 래퍼."""
    return asyncio.run(extract_article_with_options(url, prefer_browser=prefer_browser))
