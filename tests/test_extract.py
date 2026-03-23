"""extract 모듈의 비네트워크 판별 로직 테스트."""

from knews.extract import _looks_like_news_article, _needs_playwright


def test_known_browser_priority_sites():
    """샘플 수집에서 자주 막히는 언론사는 Playwright 우선."""
    assert _needs_playwright("https://www.sedaily.com/NewsView/123456")
    assert _needs_playwright("https://news.mt.co.kr/mtview.php?no=202603231200")
    assert _needs_playwright("https://www.fnnews.com/news/202603231200123456")


def test_article_path_upgrades_browser_fallback():
    """일반 도메인도 기사형 URL이면 보강 대상으로 본다."""
    assert _looks_like_news_article("https://example.kr/news/view?idxno=1234")
    assert _looks_like_news_article("https://somepaper.kr/article/2026/03/23/12345")


def test_non_article_page_not_treated_as_news():
    """일반 소개 페이지는 뉴스 기사로 오인하지 않는다."""
    assert not _looks_like_news_article("https://example.com/about")
