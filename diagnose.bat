@echo off
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

set PY=%~1
if not defined PY call :TRYPY py -3
if not defined PY call :TRYPY python
if not defined PY call :TRYPY python3
if not defined PY call :TRYPY py
if not defined PY goto NONE

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

:TRYPY
call %* -c "import sys" 1>nul 2>nul
if not errorlevel 1 set PY=%*
goto :eof
