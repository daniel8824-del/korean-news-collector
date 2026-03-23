"""clean_news_body 함수 테스트"""

import pytest
from knews.clean import clean_news_body


def test_empty_input():
    """빈 입력은 빈 문자열 반환."""
    assert clean_news_body("") == ""
    assert clean_news_body(None) == ""


def test_short_input_passthrough():
    """50자 미만 짧은 입력은 그대로 반환."""
    short = "짧은 텍스트입니다."
    assert clean_news_body(short) == short


def test_firewall_page_detected():
    """방화벽/차단 페이지는 빈 문자열 반환."""
    firewall_text = (
        "Hold tight! We're checking your connection. "
        "This security service protects against online attack. " * 5
    )
    assert clean_news_body(firewall_text) == ""


def test_reporter_info_removed():
    """기자 이름+이메일 패턴이 제거되는지 확인."""
    raw = (
        "서울시가 새로운 교통 정책을 발표했다. "
        "이번 정책은 대중교통 이용을 촉진하기 위한 것으로, "
        "버스 노선 확대와 지하철 연장이 핵심이다. "
        "시민들의 반응은 대체로 긍정적이다.\n"
        "홍길동 기자 hong@chosun.com"
    )
    result = clean_news_body(raw)
    assert "hong@chosun.com" not in result
    assert "홍길동 기자" not in result
    assert "교통 정책" in result


def test_copyright_footer_removed():
    """저작권/무단전재 문구가 제거되는지 확인."""
    raw = (
        "인공지능 기술이 빠르게 발전하고 있다. "
        "특히 생성형 AI는 다양한 산업에서 활용되고 있으며, "
        "향후 더 많은 변화가 예상된다고 전문가들은 말했다.\n"
        "Copyright ⓒ 2024 All Rights Reserved 무단 전재 및 재배포 금지"
    )
    result = clean_news_body(raw)
    assert "Copyright" not in result
    assert "무단 전재" not in result
    assert "인공지능" in result


def test_markdown_links_removed():
    """마크다운 링크 문법이 제거되는지 확인."""
    raw = (
        "경제 성장률이 예상을 웃돌았다는 분석이 나왔다. "
        "한국은행은 올해 성장률 전망치를 상향 조정했다고 밝혔다. "
        "이에 따라 금리 인하 기대감도 커지고 있는 상황이다.\n"
        "* [관련 기사 보기](https://example.com/news)\n"
        "* [더 알아보기](https://example.com/more)"
    )
    result = clean_news_body(raw)
    assert "example.com" not in result
    assert "경제 성장률" in result


def test_news1_reporter_cleaned():
    """뉴스1 기자 서명 패턴 제거."""
    raw = (
        "(서울=뉴스1) 김철수 기자 = "
        "정부가 새로운 부동산 대책을 발표했다. "
        "이번 대책은 주택 공급 확대에 초점을 맞추고 있으며, "
        "수도권 신규 택지 개발이 핵심이라고 관계자는 설명했다."
    )
    result = clean_news_body(raw, url="https://www.news1.kr/article/123")
    assert "뉴스1" not in result
    assert "김철수 기자" not in result
    assert "부동산 대책" in result


def test_ad_taboola_removed():
    """광고(Taboola 등) 패턴이 제거되는지 확인."""
    raw = (
        "반도체 산업이 회복세를 보이고 있다. "
        "삼성전자와 SK하이닉스는 올해 실적 개선이 기대된다고 밝혔다. "
        "AI 수요 증가가 메모리 반도체 시장을 견인하고 있다는 분석이다.\n"
        "[By Taboola] You May Like These Sponsored Stories\n"
        "[AD] Shop Now for Best Deals"
    )
    result = clean_news_body(raw)
    assert "Taboola" not in result
    assert "[AD]" not in result
    assert "반도체" in result
