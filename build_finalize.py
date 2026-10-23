# -*- coding: utf-8 -*-
"""빌드 후처리: 산출물 이름을 한글로 바꾸고 문서를 함께 넣는다.

배치파일에서 한글 파일명을 직접 다루면 시스템 로캘(코드페이지)에 따라
이름이 깨질 수 있으므로, PyInstaller 는 ASCII 이름으로 빌드하고
이 스크립트가 최종 이름으로 정리한다.
"""
import os
import shutil
import sys

ASCII_NAME = "DataDupChecker.exe"
FINAL_NAME = "데이터중복성검사기.exe"
DOCS = ("사용설명서.md", "먼저읽어주세요.txt")


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    here = os.path.dirname(os.path.abspath(__file__))
    os.chdir(here)
    dist = os.path.join(here, "dist")
    src = os.path.join(dist, ASCII_NAME)
    dst = os.path.join(dist, FINAL_NAME)

    if not os.path.exists(src):
        # onedir 방식으로 빌드한 경우
        alt = os.path.join(dist, "DataDupChecker", ASCII_NAME)
        if os.path.exists(alt):
            src, dst = alt, os.path.join(os.path.dirname(alt), FINAL_NAME)
        else:
            print("[오류] 빌드 산출물을 찾을 수 없습니다: %s" % src)
            return 1

    try:
        if os.path.exists(dst):
            os.remove(dst)
        os.replace(src, dst)
    except OSError as e:
        print("[오류] 파일 이름 변경 실패: %s" % e)
        print("       실행 중인 프로그램이 있으면 종료한 뒤 다시 시도하세요.")
        return 1

    for name in DOCS:
        p = os.path.join(here, name)
        if os.path.exists(p):
            try:
                shutil.copy2(p, os.path.join(dist, name))
            except OSError:
                pass

    mb = os.path.getsize(dst) / 1024.0 / 1024.0
    print("생성 완료: %s (%.0f MB)" % (dst, mb))
    return 0


if __name__ == "__main__":
    sys.exit(main())
