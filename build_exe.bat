@echo off
title AI 학습/시험 데이터 중복성 검사기 - 실행파일 빌드
cd /d "%~dp0"
cls
echo ============================================================
echo   AI 학습/시험 데이터 중복성 검사기
echo   Windows 실행파일(EXE) 만들기
echo ============================================================
echo.
echo 이 배치파일은 인터넷 연결이 되는 Windows PC 에서 한 번만 실행하면 됩니다.
echo 완료되면 dist 폴더에 EXE 파일 하나가 만들어지고,
echo 그 파일만 USB 나 이메일로 옮겨 더블클릭하면 실행됩니다.
echo.
echo [0/3] Python 을 찾습니다...

set PY=%~1
if not defined PY call :TRYPY py -3
if not defined PY call :TRYPY python
if not defined PY call :TRYPY python3
if not defined PY call :TRYPY py
if not defined PY goto NOPY

echo       사용할 Python: %PY%
call %PY% -V
call %PY% -c "import sys;sys.exit(0 if min(sys.version_info[:2],(3,9))==(3,9) else 1)"
if errorlevel 1 goto OLDPY

echo.
echo 지원하는 모든 파일 형식을 포함합니다 (parquet, 구형 xls 포함).
echo   - EXE 크기 약 70MB (USB 전달 권장)
echo   - 일부 형식을 빼면 그 형식이 검사에서 조용히 빠져
echo     중복 0건처럼 보이므로 항상 포함합니다.
set PARQUET=1

echo.
echo [1/3] 필요한 패키지를 설치합니다. (수 분 소요)
call %PY% -m pip install --upgrade pip
call %PY% -m pip install pandas numpy pillow openpyxl xlrd tkinterdnd2 pyinstaller
if errorlevel 1 goto PIPFAIL
call %PY% -m pip install pyarrow

echo.
echo [2/3] 실행파일을 만듭니다. (수 분 소요)
set OPTS=--noconfirm --clean --onefile --windowed --name DataDupChecker --icon "icon.ico"
set OPTS=%OPTS% --collect-all openpyxl --collect-all xlrd --collect-all tkinterdnd2
set OPTS=%OPTS% --add-data "logo.jpg;."
set OPTS=%OPTS% --exclude-module matplotlib --exclude-module scipy --exclude-module sklearn
set OPTS=%OPTS% --exclude-module IPython --exclude-module notebook --exclude-module pytest
set OPTS=%OPTS% --exclude-module PyQt5 --exclude-module PySide2 --exclude-module torch
set OPTS=%OPTS% --exclude-module tensorflow --exclude-module numba --exclude-module sqlalchemy
set OPTS=%OPTS% --collect-all pyarrow
call %PY% -m PyInstaller %OPTS% app.py
if errorlevel 1 goto BUILDFAIL

echo.
echo [3/3] 마무리 (파일 이름 정리)
call %PY% build_finalize.py
if errorlevel 1 goto BUILDFAIL
echo.
echo ============================================================
echo  완료되었습니다.
echo  만들어진 파일은 dist 폴더에 있습니다 (데이터중복성검사기.exe)
echo  이 파일 하나만 복사해서 배포하면 됩니다.
echo ============================================================
echo.
start "" "%CD%\dist"
pause
exit /b 0

:NOPY
echo.
echo [오류] 실행 가능한 Python 을 찾지 못했습니다.
echo.
echo  아래 진단 정보를 확인하세요.
echo  ------------------------------------------------------------
echo  [where py]
where py 2>nul
echo  [where python]
where python 2>nul
echo  [python -V]
call python -V 2>nul
echo  ------------------------------------------------------------
echo.
echo  해결 방법
echo   1) Python 이 없다면: https://www.python.org/downloads/windows/ 에서 설치
echo      설치 화면에서 "Add python.exe to PATH" 를 반드시 체크하세요.
echo   2) 설치했는데도 찾지 못한다면 Microsoft Store 앨리어스가 가로채는 경우입니다.
echo      설정 - 앱 - 앱 실행 별칭 에서 python.exe / python3.exe 를 끄고 다시 실행하세요.
echo   3) 명령 프롬프트를 새로 열어 다시 실행하세요. (PATH 변경은 새 창에만 적용됩니다)
echo   4) 경로를 직접 지정해서 실행할 수도 있습니다.
echo      예) %~nx0 "C:\Users\사용자\AppData\Local\Programs\Python\Python313\python.exe"
echo   5) diagnose.bat 을 실행하면 설치된 Python 목록을 확인할 수 있습니다.
pause
exit /b 1

:OLDPY
echo.
echo [오류] Python 3.9 이상이 필요합니다. 선택된 실행기(%PY%)의 버전:
call %PY% -V
echo.
echo  다른 Python 이 설치되어 있다면 경로를 직접 지정해서 실행할 수 있습니다.
echo    예) %~nx0 "C:\Users\사용자\AppData\Local\Programs\Python\Python313\python.exe"
echo  설치된 Python 목록은 diagnose.bat 을 실행하면 확인할 수 있습니다.
pause
exit /b 1

:PIPFAIL
echo.
echo [오류] 패키지 설치에 실패했습니다. 인터넷 연결 또는 사내 프록시 설정을 확인하세요.
echo        프록시 환경이라면 아래처럼 실행해 보세요.
echo        %PY% -m pip install --proxy http://아이디:비밀번호@프록시주소:포트 pandas numpy pillow openpyxl xlrd tkinterdnd2 pyinstaller
pause
exit /b 1

:BUILDFAIL
echo.
echo [오류] 실행파일 생성에 실패했습니다. 위의 메시지를 확인하세요.
echo        백신 프로그램이 차단하는 경우가 많으므로, 실시간 검사를 잠시 끄고 다시 시도해 보세요.
pause
exit /b 1

:TRYPY
call %* -c "import sys" 1>nul 2>nul
if not errorlevel 1 set PY=%*
goto :eof
