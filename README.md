# knews - 한국 뉴스 수집기 (Python Learn Friendly)

파이썬 설치나 복잡한 환경 설정 없이, **한 줄의 명령어로 한국 뉴스 기사를 완벽하게 수집**하고 싶으신가요?  
`knews`는 최신 검색 엔진(Tavily)과 웹 브라우저 자동화(Playwright) 기술을 결합하여, 누구나 손쉽게 뉴스 데이터를 모을 수 있도록 설계된 도구입니다.

---

## 🌟 주요 특징

- **스마트 검색:** Tavily API를 사용하여 구글 뉴스 등의 최신 정보를 정확하게 필터링합니다. (월 1,000회 무료)
- **강력한 본문 추출:** JTBC, 조선일보, MBC 등 자바스크립트가 필요한 까다로운 사이트도 Playwright를 통해 완벽하게 읽어옵니다.
- **깨끗한 데이터:** 광고, 메뉴, 기자 정보 등 불필요한 요소를 제거하고 본문 핵심 내용만 추출합니다.
- **다양한 저장 포맷:** 수집한 결과를 CSV, JSON, Markdown 파일로 즉시 저장하여 데이터 분석이나 블로그 초안 작성에 활용할 수 있습니다.

---

## 🚀 5분 완성! 단계별 설치 및 설정 가이드

스크린샷 없이도 따라 할 수 있도록 차근차근 안내해 드립니다.

### 1단계: 'uv' 도구 설치
`uv`는 파이썬 버전을 자동으로 관리해 주는 가장 빠르고 편리한 도구입니다. 터미널(또는 CMD/PowerShell)을 열고 아래 명령어를 입력하세요.

- **Mac/Linux:**
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Windows (PowerShell):**
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```
*(설치 후 터미널을 껐다가 다시 켜야 `uv` 명령어가 인식될 수 있습니다.)*

### 2단계: `knews` 프로그램 설치
이제 `uv`를 이용해 `knews`를 시스템에 등록합니다.

```bash
# 최신 버전 바로 설치
uv tool install git+https://github.com/daniel8824/korean-news-collector
```

### 3단계: Tavily 무료 API 키 발급 받기
뉴스 검색 기능을 사용하려면 API 키가 필요합니다.

1. [Tavily 공식 홈페이지](https://app.tavily.com)에 접속합니다.
2. **Sign Up** 버튼을 눌러 가입합니다. (구글이나 깃허브 계정으로 1초 만에 가입 가능)
3. 대시보드 메인 화면에 보이는 **'Your API Key'** (예: `tvly-abc123...`)를 복사합니다.

### 4단계: API 키 환경 설정 (매우 중요!)
복사한 키를 프로그램이 인식할 수 있도록 설정해야 합니다. 가장 추천하는 방법은 **'.env'** 파일을 만드는 것입니다.

```bash
# 홈 디렉토리에 .env 파일 생성 (tvly- 부분에 본인의 키를 입력하세요)
echo "TAVILY_API_KEY=tvly-본인의키" > ~/.env
```

또는 터미널 세션에서 바로 등록할 수도 있습니다:
- **Mac/Linux:** `export TAVILY_API_KEY=tvly-본인의키`
- **Windows:** `$env:TAVILY_API_KEY="tvly-본인의키"`

### 5단계: 브라우저 환경 구축 (최초 1회)
까다로운 뉴스 사이트(JTBC, 조선일보 등)에서 본문을 읽어오려면 가상 브라우저가 필요합니다.

```bash
knews setup
```
*(설치가 완료되면 이제 준비 끝입니다!)*

---

## 💡 실전 사용법

### 1. 뉴스 검색하고 터미널에서 보기
가장 기본적인 검색 방법입니다.
```bash
# "AI 인공지능" 관련 뉴스 10건 검색
knews search "AI 인공지능"

# 최근 3일 동안의 "경제 뉴스" 5건 검색
knews search "경제 뉴스" -n 5 -d 3
```

### 2. 특정 사이트 뉴스만 모아보기
`--site` 옵션을 사용하면 원하는 언론사의 뉴스만 타겟팅할 수 있습니다.
```bash
knews search "반도체" --site chosun.com
```

### 3. 파일로 깔끔하게 저장하기
엑셀(CSV)이나 문서(Markdown)로 저장하여 나중에 활용해 보세요.
```bash
# CSV로 저장 (엑셀용)
knews search "스타트업 뉴스" -o csv

# Markdown으로 저장 (옵시디언, 노션, 블로그용)
knews search "건강 정보" -o md -s healthy.md
```

### 4. 이미 알고 있는 뉴스 URL에서 본문만 추출하기
```bash
knews extract https://news.jtbc.co.kr/article/example-url
```

---

## ❓ 자주 묻는 질문 (FAQ)

**Q: "TAVILY_API_KEY가 설정되지 않았습니다"라고 떠요.**
A: 4단계를 다시 확인해 주세요. `.env` 파일에 오타가 있거나, 환경변수 설정이 제대로 되지 않았을 때 발생합니다. `echo $TAVILY_API_KEY`로 값이 나오는지 확인해 보세요.

**Q: 특정 사이트 본문이 빈 칸으로 나와요.**
A: 해당 사이트의 구조가 특이하거나 방화벽이 있을 수 있습니다. `knews setup`을 완료했는지 확인하고, 그래도 안 된다면 해당 URL을 알려주시면 개선에 큰 도움이 됩니다.

**Q: 무료 사용량이 다 떨어지면 어떻게 되나요?**
A: Tavily 무료 플랜은 월 1,000회입니다. 초과 시 다음 달까지 기다리거나 유료 플랜을 고려해야 합니다. 학습용으로는 1,000회면 충분합니다!

---

## 🛠 지원하는 주요 뉴스 사이트
아래 사이트들은 자동으로 Playwright(브라우저 렌더링)를 사용하여 정확하게 수집합니다.
- **방송사:** JTBC, MBC, SBS, YTN, TV조선, 채널A
- **포털/신문:** 네이버뉴스, 다음뉴스, 조선일보, ZUM 등

---
**Happy News Collecting!** 🚀
