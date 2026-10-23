# -*- coding: utf-8 -*-
"""Windows 배치 파일 생성 (한글 표시를 위해 CP949로 저장).

주의: 배치 파일 안의 파이썬 한 줄 코드에는 '>' 문자를 쓰지 않는다.
cmd 의 리다이렉션과 혼동되는 사례가 있어 min() 비교로 대체한다.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 파이썬 실행기 자동 탐지 (py 런처 우선 → Microsoft Store 스텁 회피)
# 첫 번째 인수로 python.exe 경로를 직접 지정할 수도 있다.
DETECT = r'''
set PY=%~1
if not defined PY call :TRYPY py -3
if not defined PY call :TRYPY python
if not defined PY call :TRYPY python3
if not defined PY call :TRYPY py
if not defined PY goto NOPY
'''

TRYPY_SUB = r'''
:TRYPY
call %* -c "import sys" 1>nul 2>nul
if not errorlevel 1 set PY=%*
goto :eof
'''

BUILD = r'''@echo off
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
''' + DETECT + r'''
echo       사용할 Python: %PY%
call %PY% -V
call %PY% -c "import sys;sys.exit(0 if min(sys.version_info[:2],(3,9))==(3,9) else 1)"
if errorlevel 1 goto OLDPY

echo.
echo Parquet(.parquet) 형식 지원을 포함하시겠습니까?
echo   - 포함하지 않으면 EXE 크기 약 60~90MB (이메일 첨부 가능)
echo   - 포함하면 약 200MB 이상 (USB 전달 권장)
set ANS=N
set /p ANS=포함하려면 Y, 제외하려면 N 을 입력하세요 [N]:
set PARQUET=
if /i "%ANS%"=="Y" set PARQUET=1

echo.
echo [1/3] 필요한 패키지를 설치합니다. (수 분 소요)
call %PY% -m pip install --upgrade pip
call %PY% -m pip install pandas numpy pillow openpyxl pyinstaller
if errorlevel 1 goto PIPFAIL
if defined PARQUET call %PY% -m pip install pyarrow

echo.
echo [2/3] 실행파일을 만듭니다. (수 분 소요)
set OPTS=--noconfirm --clean --onefile --windowed --name DataDupChecker --icon "icon.ico"
set OPTS=%OPTS% --collect-all openpyxl
set OPTS=%OPTS% --exclude-module matplotlib --exclude-module scipy --exclude-module sklearn
set OPTS=%OPTS% --exclude-module IPython --exclude-module notebook --exclude-module pytest
set OPTS=%OPTS% --exclude-module PyQt5 --exclude-module PySide2 --exclude-module torch
set OPTS=%OPTS% --exclude-module tensorflow --exclude-module numba --exclude-module sqlalchemy
if defined PARQUET (
  set OPTS=%OPTS% --collect-all pyarrow
) else (
  set OPTS=%OPTS% --exclude-module pyarrow
)
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
echo        %PY% -m pip install --proxy http://아이디:비밀번호@프록시주소:포트 pandas numpy pillow openpyxl pyinstaller
pause
exit /b 1

:BUILDFAIL
echo.
echo [오류] 실행파일 생성에 실패했습니다. 위의 메시지를 확인하세요.
echo        백신 프로그램이 차단하는 경우가 많으므로, 실시간 검사를 잠시 끄고 다시 시도해 보세요.
pause
exit /b 1
''' + TRYPY_SUB

RUN = r'''@echo off
title AI 학습/시험 데이터 중복성 검사기
cd /d "%~dp0"
''' + DETECT + r'''
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
''' + TRYPY_SUB

DIAG = r'''@echo off
title Python 환경 진단
cd /d "%~dp0"
cls
echo ============================================================
echo   Python 환경 진단 (빌드가 안 될 때 이 결과를 알려주세요)
echo ============================================================
echo.
echo [1] PATH 에서 찾은 실행기
echo --- where py ---
where py 2>nul
echo --- where python ---
where python 2>nul
echo --- where python3 ---
where python3 2>nul
echo --- where pythonw ---
where pythonw 2>nul
echo.
echo [2] 각 실행기 버전
echo --- py -3 -V ---
call py -3 -V 2>nul
echo --- python -V ---
call python -V 2>nul
echo --- python3 -V ---
call python3 -V 2>nul
echo.
echo [3] py 런처가 인식하는 설치 목록
call py -0p 2>nul
echo.
echo [4] 이 프로그램이 사용할 실행기 자동 선택 결과
''' + DETECT.replace("goto NOPY", "goto NONE") + r'''
echo       선택됨: %PY%
call %PY% -V
echo.
echo [5] 필요한 패키지 설치 상태
call %PY% -c "import pandas,numpy,PIL,openpyxl;print('pandas/numpy/pillow/openpyxl 모두 설치됨')" 2>nul
if errorlevel 1 echo   일부 패키지가 없습니다. build_exe.bat 또는 run.bat 이 자동 설치합니다.
echo.
pause
exit /b 0

:NONE
echo       선택된 실행기 없음 - Python 을 설치하거나 앱 실행 별칭을 확인하세요.
pause
exit /b 1
''' + TRYPY_SUB

if __name__ == "__main__":
    for name, text in (("build_exe.bat", BUILD), ("run.bat", RUN), ("diagnose.bat", DIAG)):
        p = os.path.join(ROOT, name)
        with open(p, "w", encoding="cp949", newline="\r\n") as f:
            f.write(text)
        print("생성:", p)
