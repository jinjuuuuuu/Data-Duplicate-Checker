@echo off
title AI 학습/시험 데이터 중복성 검사기
cd /d "%~dp0"

set PY=%~1
if not defined PY call :TRYPY py -3
if not defined PY call :TRYPY python
if not defined PY call :TRYPY python3
if not defined PY call :TRYPY py
if not defined PY goto NOPY

call %PY% -c "import sys;sys.exit(0 if min(sys.version_info[:2],(3,9))==(3,9) else 1)"
if errorlevel 1 goto OLDPY

call %PY% -c "import pandas,numpy,PIL,openpyxl" 1>nul 2>nul
if errorlevel 1 (
  echo 처음 실행을 위해 필요한 패키지를 설치합니다. 잠시만 기다려 주세요.
  call %PY% -m pip install pandas numpy pillow openpyxl
  if errorlevel 1 goto PIPFAIL
)

rem 콘솔 창 없이 실행 (pythonw / pyw 우선)
call pyw -3 -c "import sys" 1>nul 2>nul
if not errorlevel 1 (
  start "" pyw -3 app.py
  exit /b 0
)
call pythonw -c "import sys" 1>nul 2>nul
if not errorlevel 1 (
  start "" pythonw app.py
  exit /b 0
)
call %PY% app.py
exit /b 0

:NOPY
echo [오류] 실행 가능한 Python 을 찾지 못했습니다.
echo.
echo  [where py]
where py 2>nul
echo  [where python]
where python 2>nul
echo.
echo  Python 이 없는 PC 에서는 build_exe.bat 로 만든 EXE 파일을 사용하세요.
echo  Python 을 설치했는데도 인식되지 않으면
echo  설정 - 앱 - 앱 실행 별칭 에서 python.exe 별칭을 끄고 다시 시도하세요.
pause
exit /b 1

:OLDPY
echo [오류] Python 3.9 이상이 필요합니다. 현재 버전:
call %PY% -V
pause
exit /b 1

:PIPFAIL
echo [오류] 패키지 설치에 실패했습니다. 인터넷 연결 또는 사내 프록시 설정을 확인하세요.
pause
exit /b 1

:TRYPY
call %* -c "import sys" 1>nul 2>nul
if not errorlevel 1 set PY=%*
goto :eof
