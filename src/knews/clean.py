"""
뉴스 본문 텍스트 클리닝 - n8n Google News Scraper 워크플로우에서 포팅.

한국 뉴스 사이트별 노이즈 제거:
- 기자 정보, 저작권 푸터, 광고, UI 요소
- 언론사별 특화 패턴 (채널A, 뉴스1, 맥스무비, 보그코리아 등)
- 마크다운 링크, 이모지, 특수문자 정리
"""

import re
from urllib.parse import urlparse


def clean_news_body(raw_content: str, url: str = "") -> str:
    """
    뉴스 본문 텍스트를 정제합니다.

    Args:
        raw_content: 원본 텍스트 (Tavily, Playwright, httpx 등에서 추출)
        url: 기사 URL (언론사별 특화 처리에 사용)

    Returns:
        정제된 본문 텍스트
    """
    if not raw_content:
        return ""
    if not isinstance(raw_content, str):
        return ""
    if len(raw_content) < 50:
        return raw_content

    original_length = len(raw_content)

    # URL 기반 언론사 판별
    is_news1 = "news1.kr" in url
    is_maxmovie = "maxmovie.com" in url
    is_channela = "ichannela.com" in url
    is_vogue = "vogue.co.kr" in url

    # ── Firewall / 차단 페이지 감지 ──
    firewall_pattern = re.compile(
        r"The request.*?contrary to the Web firewall|Hold tight|secure connection|"
        r"security service|protect.*?online attack|잠시만 기다려|보안 검사|CAPTCHA|"
        r"서버 접속.*?보안",
        re.IGNORECASE,
    )
    if firewall_pattern.search(raw_content):
        return ""

    # ══════════════════════════════════════
    # 1단계: 마크다운 링크 제거
    # ══════════════════════════════════════
    raw_content = re.sub(r"^\*\s+\[.*?\]\(.*?\)\s*$", "", raw_content, flags=re.MULTILINE)
    raw_content = re.sub(r"^\d+\.\s+\[.*?\]\(.*?\)\s*$", "", raw_content, flags=re.MULTILINE)
    raw_content = re.sub(r"\[[^\]]+\]\([^\)]+\)", "", raw_content)
    raw_content = re.sub(r"\[\]\(\)", "", raw_content)
    raw_content = re.sub(r"!\[.*?\]\(.*?\)", "", raw_content)

    # ══════════════════════════════════════
    # 2단계: 보그 코리아 전용 전처리
    # ══════════════════════════════════════
    if is_vogue:
        raw_content = re.sub(r"^[\s\S]*?===+\n", "", raw_content, count=1)
        raw_content = re.sub(
            r"\[(FASHION|BEAUTY|LIVING|CULTURE|VIDEO)\][\s\S]*?(?=\n\n[가-힣])",
            "", raw_content, flags=re.IGNORECASE,
        )
        raw_content = re.sub(
            r"korea\n\*\s+\[Adria\][\s\S]*?(?=\n\n[가-힣])", "", raw_content, flags=re.IGNORECASE
        )
        raw_content = re.sub(
            r"\[(구독하기|정기구독|회사소개|광고/제휴|공지사항|MASTHEAD|개인정보 처리방침)\]", "", raw_content
        )

    # ══════════════════════════════════════
    # 3단계: 기자 정보 제거
    # ══════════════════════════════════════

    # 뉴스1 기자 서명
    if is_news1:
        raw_content = re.sub(r"\([가-힣]+=뉴스1\)\s*[가-힣]{2,4}\s*기자\s*=\s*", "", raw_content)
        raw_content = re.sub(r"^[가-힣]{2,4}\s*기자\s*=\s*", "", raw_content, flags=re.MULTILINE)

    # 기자명 이메일 패턴
    raw_content = re.sub(r"\n?/?[가-힣]{2,4}\s*기자\s*[a-zA-Z0-9._-]+@[^\s\n]+", "", raw_content)
    raw_content = re.sub(r"\n?/?[가-힣]+\s*[가-힣]{2,4}기자\s*[a-zA-Z0-9._-]+@[^\s\n]+", "", raw_content)

    # 언론사 기자 태그
    raw_content = re.sub(r"\[[가-힣]+(?:데일리|투데이|뉴스|타임즈|경제|일보|신문)\s*[가-힣]*(?:기자|리포터|AI리포터)\]", "", raw_content)
    raw_content = re.sub(r"\[디지털데일리\s*[가-힣]+기자\]", "", raw_content)
    raw_content = re.sub(r"\[디지털투데이\s*AI\s*리포터\]", "", raw_content)

    # 연합뉴스 등 괄호 기자 패턴
    raw_content = re.sub(r"\([\s가-힣]*=\s*연합뉴스\)\s*[가-힣\s]+기자\s*[=]*\s*", "", raw_content)
    raw_content = re.sub(r"\([^)]*=\s*[^)]+\)\s*[가-힣\s]+기자\s*[=]*\s*", "", raw_content)
    raw_content = re.sub(r"[가-힣]+기자\s+구독\s+구독중", "", raw_content)
    raw_content = re.sub(r"\[[^\]]*기자\]", "", raw_content)
    raw_content = re.sub(r"\[[^\]]*AI\s*리포터\]", "", raw_content)

    # 뉴시스 스타일
    raw_content = re.sub(r"\[[^\]]+=[^\]]+\][가-힣\s]+기자\s*=\s*", "", raw_content)
    raw_content = re.sub(r"◎공감언론\s*뉴시스", "", raw_content)

    # iMBC연예 패턴
    raw_content = re.sub(r"iMBC연예\s+[가-힣]{2,4}\s*\|\s*사진출처[^\n]*", "", raw_content)
    raw_content = re.sub(r"iMBC연예\s+[가-힣]{2,4}", "", raw_content)

    # 빈 괄호 기자 / 언론사명 단독 라인
    raw_content = re.sub(r"[가-힣]{2,4}\s*기자\s*\(\s*\)", "", raw_content)
    raw_content = re.sub(r"\nOSEN\s*(DB)?\s*$", "", raw_content, flags=re.MULTILINE)

    # 일반 이메일 주소 단독 라인 또는 꼬리
    raw_content = re.sub(r"\n?[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+\.(co\.kr|com|net)\s*$", "", raw_content, flags=re.MULTILINE)

    # 인라인 날짜 패턴
    raw_content = re.sub(r"입력\s*\d{4}\.\d{2}\.\d{2}\.\s*\d{2}:\d{2}", "", raw_content)
    raw_content = re.sub(r"업데이트\s*\d{4}\.\d{2}\.\d{2}\.\s*\d{2}:\d{2}", "", raw_content)

    # 광고 패턴
    raw_content = re.sub(r"\[By Taboola\][^\n]*", "", raw_content)
    raw_content = re.sub(r"\[AD\][^\n]*", "", raw_content)

    # 블로그 헤더 제거
    is_blog = bool(re.search(r"루빵루나|URL 복사|본문 기타 기능", raw_content))
    has_share = bool(re.search(r"공유하기\s*신고하기", raw_content))
    if is_blog and has_share:
        share_match = re.search(r"공유하기\s*신고하기", raw_content)
        if share_match and share_match.start() < len(raw_content) * 0.3:
            raw_content = re.sub(r"^[\s\S]*?공유하기\s*신고하기\s*", "", raw_content, count=1)

    # 매체명 제거
    for outlet in ["채널A 뉴스", "MBC 뉴스", "KBS 뉴스", "SBS 뉴스", "YTN"]:
        raw_content = re.sub(rf"\s+{re.escape(outlet)}\s*$", "", raw_content, flags=re.MULTILINE)

    # ══════════════════════════════════════
    # 4단계: 라인 단위 처리
    # ══════════════════════════════════════
    lines = [line.strip() for line in raw_content.split("\n") if line.strip()]

    # 본문 시작점 찾기
    start_idx = _find_start_index(lines, is_channela, is_news1, is_maxmovie)

    # 본문 끝점 찾기
    end_idx = _find_end_index(lines, start_idx, is_channela, is_news1, is_maxmovie)

    lines = lines[start_idx:end_idx]

    # ══════════════════════════════════════
    # 5단계: 라인 필터링
    # ══════════════════════════════════════
    lines = _filter_lines(lines, is_channela, is_news1, is_maxmovie)

    # ══════════════════════════════════════
    # 6단계: 최종 후처리
    # ══════════════════════════════════════
    text = "\n".join(lines)
    text = _final_cleanup(text)

    # 최종 검증
    min_length = 20 if is_channela else 30
    if not text or len(text) < min_length:
        return ""

    return text


def _find_start_index(lines: list[str], is_channela: bool, is_news1: bool, is_maxmovie: bool) -> int:
    """본문 시작 위치를 찾습니다."""
    if is_channela:
        for i, line in enumerate(lines):
            if re.match(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}", line):
                return i + 1
        for i, line in enumerate(lines):
            if len(line) > 10 and re.search(r"[가-힣]", line) and not re.match(r"^[#\[!]|^Image|^•", line):
                return i
        return 0

    if is_news1:
        for i, line in enumerate(lines):
            if (len(line) > 20 and not re.match(r"^[#\[!]|^[가-힣]{2,4}\s*기자$", line)
                    and re.search(r"[가-힣]", line)):
                return i
        return 0

    # 일반 사이트: 본문 첫 문장 패턴
    for i, line in enumerate(lines):
        if re.match(r"^[가-힣]{2,4}\s+[가-힣]+시가", line) or re.match(r"^경북\s+[가-힣]+시", line):
            return i

    for i, line in enumerate(lines):
        if re.match(r"^넷플릭스|^<블룸버그>|^<[가-힣]+>", line):
            return i
        # 한국어 문장으로 시작하고 20자+ 이면 본문 시작
        if re.match(r"^[가-힣].{20,}[가-힣]다\.\s*$", line):
            return i
        if len(line) > 25 and re.search(r"[이가]라고|[이가]며|밝혔다|말했다|전했다|설명했다|강조했다", line):
            return i

    # 첫 줄이 매우 짧으면 (메뉴/카테고리) 다음 줄부터
    if (not is_maxmovie and not is_news1 and not is_channela
            and lines and len(lines[0]) < 15 and len(lines) > 1):
        return 1

    return 0


def _find_end_index(lines: list[str], start_idx: int, is_channela: bool, is_news1: bool, is_maxmovie: bool) -> int:
    """본문 끝 위치를 찾습니다."""
    for i, line in enumerate(lines):
        if i <= start_idx:
            continue

        # 채널A 특화
        if is_channela:
            if (re.match(r"^•\s*\[채널A 뉴스\]", line)
                    or "구독하기" in line
                    or "Copyright Ⓒ 채널A" in line
                    or line == "재생목록"):
                return i

        # 뉴스1 특화
        if is_news1:
            if (line == "관련 키워드"
                    or re.match(r"^[a-z0-9]+@news1\.kr$", line)
                    or "대표이사/발행인" in line):
                return i

        # 맥스무비 특화
        if is_maxmovie:
            if (line == "댓글0" or line == "관련 기사"
                    or re.match(r"^[a-z0-9]+@maxmovie\.com$", line)
                    or "<저작권자(c) 맥스무비" in line):
                return i

        # 공통 종료 패턴
        if re.match(r"^많이 본 (뉴스|기사|콘텐츠)\s*(\d+/\d+)?$", line):
            return i
        if re.match(r"^(관련기사|최신기사|추천기사|인기기사|주요 기사|많이 본 기사|이시각 주요뉴스)", line, re.IGNORECASE):
            return i
        if re.match(r"^(SNS 공유하기|함께 볼만한|이 시각|top|댓글|Copyright|AD$)", line, re.IGNORECASE):
            return i
        if re.match(r"^(꼭 봐야 할|함께 보면 좋은|놓칠 수 없는|당신을 위한|오늘의 추천|오늘의 인기)", line):
            return i
        if re.match(r"^(Advertisement|by Dable|View English)", line, re.IGNORECASE):
            return i
        if re.match(r"^[가-힣]{2,4}\s*기자\s+[a-zA-Z0-9]+@[a-zA-Z]+\.(co\.kr|com)$", line):
            return i
        if "[[한겨레 후원하기]" in line:
            return i

        # edaily 푸터
        if "케이지타워" in line or "이데일리 대표전화" in line:
            return i

    return len(lines)


def _filter_lines(lines: list[str], is_channela: bool, is_news1: bool, is_maxmovie: bool) -> list[str]:
    """노이즈 라인을 필터링합니다."""
    filtered = []
    for i, line in enumerate(lines):
        if not line or len(line) < 2:
            continue

        # 채널A 특화 제거
        if is_channela:
            if re.match(r"^Image \d+", line):
                continue
            if re.match(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}", line):
                continue
            if re.match(r"^문화,국제$|^정치,사회$|^경제,국제$", line):
                continue
            if re.match(r"^•\s*\[채널A", line):
                continue
            if line in ("재생목록", "동영상 FAQ"):
                continue
            if re.match(r"^\d+/\d+\s+연속재생", line):
                continue

        # 뉴스1 특화 제거
        if is_news1:
            if re.match(r"^#", line):
                continue
            if re.match(r"^[가-힣]{2,4}\s*기자\s*$", line):
                continue
            if re.match(r"^!\[", line):
                continue
            if re.match(r"^#{2,6}\s*\[", line):
                continue

        # 맥스무비 특화 제거
        if is_maxmovie:
            if i == 0 and re.match(r"^###", line):
                continue
            if re.match(r"^\[맥스무비=", line):
                continue
            if re.match(r"^```", line):
                continue

        # ── 공통 필터 ──

        # 단일 문자
        if len(line) == 1 and line != ".":
            continue
        if line == "가":
            continue

        # 빈 마크다운
        if re.match(r"^\[\]|\(\)$|^!$", line):
            continue

        # 숫자만
        if re.match(r"^\d+\.?\s*$", line):
            continue

        # 날짜/시간만
        if re.match(r"^\d{4}[-./년]\d{1,2}[-./월]\d{1,2}[일\s\d:]*$", line):
            continue
        if re.match(r"^(오전|오후)\s+\d{1,2}:\d{2}$", line):
            continue

        # 지역명만
        if re.match(r"^(서울|부산|대구|인천|광주|대전|울산|강릉|제주|경기|강원|충북|충남|전북|전남|경북|경남|세종)$", line):
            continue

        # 메뉴 항목
        if re.match(
            r"^(정치|사회|경제|국제|전국|외교|북한|금융|산업|부동산|IT|과학|바이오|생활|문화|연예|스포츠|오피니언|피플|포토|TV|Now|리뷰)$",
            line, re.IGNORECASE,
        ):
            continue

        # 숫자+특수문자만
        if re.match(r"^[\d\s./\-]+$", line):
            continue

        # 이미지 설명
        if re.match(r"^(갈무리|제공|캡처|사진|출처|포스터)\s*[:=]?\s*[^\w가-힣]*$", line, re.IGNORECASE):
            continue
        if re.search(r"ⓒ\s*(AFP|뉴스1|맥스무비|채널A)", line):
            continue

        # 주식 위젯 노이즈
        if re.search(r"(KOSPI|KOSDAQ|현재가|전일대비|등락률|증권정보)", line) and re.search(r"\d{3,}", line):
            continue

        # 광고
        if re.search(r"Taboola|Sponsored|You May Like|Read More|Shop Now|Buy Now", line, re.IGNORECASE):
            continue

        # 푸터 패턴 (언론사별)
        if _is_footer_line(line, is_channela, is_news1, is_maxmovie):
            continue

        # edaily 푸터 주소/사업자 정보
        if re.search(r"서울시 중구 통일로|사업자번호", line):
            continue

        # Copyright / 저작권 패턴
        if re.match(r"^Copyright", line, re.IGNORECASE):
            continue
        if re.search(r"저작권자|무단\s*(전재|복제|배포)|All Rights Reserved", line, re.IGNORECASE):
            continue

        # 기타 노이즈
        if re.match(
            r"^(복사|공유|top|korea|가|돌아가기|Previous|Next|이전|다음|목록|로그인|헤더 바로가기|푸터 바로가기)$",
            line, re.IGNORECASE,
        ):
            continue

        filtered.append(line)

    return filtered


def _is_footer_line(line: str, is_channela: bool, is_news1: bool, is_maxmovie: bool) -> bool:
    """푸터 라인인지 확인합니다."""
    # 채널A 푸터
    if is_channela:
        footer_keywords = [
            "Copyright Ⓒ 채널A", "무단 전재, 재배포 및 AI학습",
            "CHANNEL A ALL RIGHTS RESERVED", "사업자등록번호",
            "부가통신사업신고", "청소년보호책임자",
        ]
        if any(kw in line for kw in footer_keywords):
            return True

    # 뉴스1 푸터
    news1_footers = [
        "newsok@news1.kr", "webmaster@news1.kr", "대표이사",
        "편집인", "SC빌딩", "Copyright ⓒ 뉴스1",
    ]
    if any(kw in line for kw in news1_footers):
        return True

    # 맥스무비 푸터
    if is_maxmovie:
        maxmovie_footers = [
            "tadada@maxmovie.com", "maxpress@maxmovie.com",
            "<저작권자(c) 맥스무비", "ⓒ MediaYunseul",
        ]
        if any(kw in line for kw in maxmovie_footers):
            return True

    # 한겨레 푸터
    if "한겨레 후원" in line or line in (";)", "SNS에 동시등록"):
        return True

    # 공통 저작권/사업자 정보
    if re.search(r"사업자등록번호|등록번호|무단\s*(전재|복제|배포)", line):
        return True

    return False


def _final_cleanup(text: str) -> str:
    """최종 텍스트 후처리."""
    # URL 제거
    text = re.sub(r"https?://[^\s)]+", "", text)
    # 특수 기호 제거
    text = re.sub(r"[▶▷●◆■★※▲▼→←↑↓#♥♡✓✔☞◎]", "", text)
    text = re.sub(r"[|│┃]+", "", text)
    # 마크다운 잔재
    text = re.sub(r"\*\*", "", text)
    text = re.sub(r"={4,}", "", text)
    text = re.sub(r"-{4,}", "", text)
    text = re.sub(r"```", "", text)
    # 이모지 제거
    text = re.sub(r"[\U0001F300-\U0001F9FF]", "", text)
    text = re.sub(r"[\u2600-\u26FF]", "", text)
    text = re.sub(r"[\u2700-\u27BF]", "", text)
    # 공백 정리
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"^\s+$", "", text, flags=re.MULTILINE)
    text = text.strip()
    # "돌아가기" 잔재
    text = text.replace("돌아가기", "")

    return text
