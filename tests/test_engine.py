# -*- coding: utf-8 -*-
"""엔진 검증: 의도적으로 심어둔 중복을 정확히 찾아내는지 확인.

실행: python tests/test_engine.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dupcheck.config import (CAT_ARRAY, CAT_FILE, CAT_IMAGE, CAT_TABULAR,
                             CAT_TEXT, Config)
from dupcheck.engine import run_check
from dupcheck.report import build_html

# (카테고리, 기대 완전일치, 기대 근사중복)
EXPECT = [
    (CAT_FILE, 3, 0),        # doc_05 사본, tr_04 사본, x_train 사본
    (CAT_TABULAR, 15, 5),    # csv 10 + pkl 3 + xlsx 2 / 근사 5
    (CAT_IMAGE, 1, 1),       # 픽셀 동일 1 / 확대본 1
    (CAT_TEXT, 3, 1),        # txt 1 + jsonl 2 / 유사문서 1
    (CAT_ARRAY, 101, 1),     # x_test 1 + 파일 사본 100 / 근사 1
]

FAILS = []


def check(label, got, want):
    ok = got == want
    print("%-34s 기대 %-5s 실측 %-5s %s" % (label, want, got, "OK" if ok else "*** 불일치 ***"))
    if not ok:
        FAILS.append(label)


def main():
    root = tempfile.mkdtemp(prefix="dlc_test_")
    here = os.path.dirname(os.path.abspath(__file__))
    subprocess.check_call([sys.executable, os.path.join(here, "make_sample.py"), root],
                          stdout=subprocess.DEVNULL)
    cfg = Config(train_dir=os.path.join(root, "train"),
                 test_dir=os.path.join(root, "test"),
                 text_similarity=0.55)   # 이 샘플의 유사문서는 실제 Jaccard 0.59
    res = run_check(cfg)
    by = {c.key: c for c in res.categories}

    print("\n--- 탐지 결과 검증 ---")
    for key, ex, nr in EXPECT:
        c = by.get(key)
        if c is None:
            check(key, "없음", "%d/%d" % (ex, nr))
            continue
        check("%s 완전일치" % c.label, c.exact_units, ex)
        check("%s 근사중복" % c.label, c.near_units, nr)

    print("\n--- 오탐 검증 (동일 폴더를 두 번 지정하지 않은 신규 데이터) ---")
    # 시험셋만으로 자기 자신과 비교하면 전부 중복이어야 한다 (민감도 확인)
    cfg2 = Config(train_dir=os.path.join(root, "test"), test_dir=os.path.join(root, "test"))
    res2 = run_check(cfg2)
    t2 = {c.key: c for c in res2.categories}
    check("자기비교 테이블 완전일치 = 전체행", t2[CAT_TABULAR].exact_units, t2[CAT_TABULAR].test_units)
    check("자기비교 텍스트 완전일치 = 전체문서", t2[CAT_TEXT].exact_units, t2[CAT_TEXT].test_units)
    check("자기비교 이미지 완전일치 = 전체장수", t2[CAT_IMAGE].exact_units, t2[CAT_IMAGE].test_units)

    print("\n--- 무중복 검증 (겹치지 않는 데이터) ---")
    clean = tempfile.mkdtemp(prefix="dlc_clean_")
    os.makedirs(os.path.join(clean, "train"))
    os.makedirs(os.path.join(clean, "test"))
    import numpy as np
    import pandas as pd
    rng = np.random.RandomState(7)
    pd.DataFrame({"a": rng.rand(500), "b": rng.randint(0, 5, 500)}).to_csv(
        os.path.join(clean, "train", "t.csv"), index=False)
    pd.DataFrame({"a": rng.rand(100) + 10, "b": rng.randint(5, 9, 100)}).to_csv(
        os.path.join(clean, "test", "t.csv"), index=False)
    res3 = run_check(Config(train_dir=os.path.join(clean, "train"),
                            test_dir=os.path.join(clean, "test")))
    dup3 = sum(c.dup_units for c in res3.categories)
    check("무중복 데이터 총 중복 건수", dup3, 0)
    check("무중복 판정", res3.verdict, "PASS")

    print("\n--- MinHash 유사도 추정 정확도 ---")
    import numpy as np
    from dupcheck.textcheck import signature
    rng = np.random.RandomState(0)
    for target in (0.9, 0.6, 0.3):
        errs = []
        for _ in range(30):
            n = 200
            base = rng.randint(0, 2 ** 63, n, dtype=np.uint64)
            k = int(round(n * target))
            other = np.concatenate([base[:k], rng.randint(0, 2 ** 63, n - k, dtype=np.uint64)])
            A, B = set(base.tolist()), set(other.tolist())
            j = len(A & B) / len(A | B)
            errs.append(float((signature(base) == signature(other)).mean()) - j)
        bias, sd = float(np.mean(errs)), float(np.std(errs))
        print("  실제J≈%.1f  편향 %+.3f  표준편차 %.3f" % (target, bias, sd))
        check("  편향 0.03 이내 (J≈%.1f)" % target, abs(bias) < 0.03, True)
        check("  표준편차 0.08 이내 (J≈%.1f)" % target, sd < 0.08, True)

    print("\n--- 라벨 벡터 제외 확인 ---")
    from dupcheck.arraycheck import is_label_vector
    check("1차원 정수 배열(라벨) 제외", is_label_vector(np.arange(10)), True)
    check("(N,1) 배열 제외", is_label_vector(np.zeros((10, 1))), True)
    check("(N,5) 특징 배열은 유지", is_label_vector(np.zeros((10, 5))), False)
    check("문자열 배열은 유지", is_label_vector(np.array(["a", "b"], dtype=object)), False)

    print("\n--- 리포트 생성 검증 ---")
    html = build_html(res)
    check("HTML 종료 태그", html.strip().endswith("</html>"), True)
    check("HTML 최소 길이", len(html) > 5000, True)

    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(clean, ignore_errors=True)

    print("\n" + ("모든 검증 통과" if not FAILS else "실패 항목: %s" % ", ".join(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
