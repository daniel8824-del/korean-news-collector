@echo off
setlocal enabledelayedexpansion

echo ======================================================
echo   knews - 한국 뉴스 수집기 원클릭 설치 스크립트
echo ======================================================
echo.

:: 1. uv 설치 확인
echo [1/4] uv 설치 상태를 확인하는 중...
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] 'uv'가 설치되어 있지 않습니다.
    echo.
    echo 설치를 위해 다음 명령어를 PowerShell에서 실행해 주세요:
    echo powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    echo.
    echo 설치를 마친 후 이 스크립트를 다시 실행해 주세요.
    pause
    exit /b 1
)
echo [OK] uv가 설치되어 있습니다.
echo.

:: 2. knews 설치
echo [2/4] knews 프로그램을 설치하는 중...
uv tool install git+https://github.com/daniel8824/korean-news-collector --force
if %errorlevel% neq 0 (
    echo [!] 설치 중 오류가 발생했습니다. 네트워크 연결을 확인해 주세요.
    pause
    exit /b 1
)
echo [OK] knews 설치 완료!
echo.

:: 3. TAVILY_API_KEY 설정 안내
echo [3/4] Tavily API 키 설정 안내
echo ------------------------------------------------------
echo 1. https://app.tavily.com 에서 무료 가입
echo 2. API Key (tvly-...) 복사
echo 3. 아래 방법 중 하나로 설정:
echo    - 시스템 환경 변수에 TAVILY_API_KEY 등록
echo    - 또는 현재 폴더에 .env 파일 생성 후 TAVILY_API_KEY=값 입력
echo ------------------------------------------------------
echo.

:: 4. 상태 확인 (knews doctor)
echo [4/4] 설치 상태를 점검합니다 (knews doctor)...
echo.
call knews doctor

echo.
echo ======================================================
echo   설치 시도가 완료되었습니다!
echo   'knews search "검색어"' 명령어로 시작해 보세요.
echo ======================================================
echo.
pause
