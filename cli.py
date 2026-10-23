# -*- coding: utf-8 -*-
"""명령행 실행 (자동화/검증용).

예) python cli.py --train ./train --test ./test --out ./report
"""
import argparse
import os
import sys

from dupcheck.config import Config
from dupcheck.engine import run_check
from dupcheck.report import write_report


def main(argv=None):
    p = argparse.ArgumentParser(description="AI 학습/시험 데이터 중복성 검사")
    p.add_argument("--train", required=True)
    p.add_argument("--test", required=True)
    p.add_argument("--out", default="")
    p.add_argument("--exclude", default="", help="제외 컬럼(콤마 구분)")
    p.add_argument("--keys", default="", help="기준 컬럼(콤마 구분)")
    p.add_argument("--decimals", type=int, default=4)
    p.add_argument("--text-sim", type=float, default=0.80)
    p.add_argument("--image-hamming", type=int, default=5)
    p.add_argument("--no-exact", action="store_true")
    p.add_argument("--no-near", action="store_true")
    p.add_argument("--no-file", action="store_true")
    p.add_argument("--quiet", action="store_true")
    a = p.parse_args(argv)

    cfg = Config(
        train_dir=os.path.abspath(a.train),
        test_dir=os.path.abspath(a.test),
        out_dir=os.path.abspath(a.out) if a.out else "",
        exclude_columns=[s for s in a.exclude.split(",") if s.strip()],
        key_columns=[s for s in a.keys.split(",") if s.strip()],
        float_decimals=a.decimals,
        text_similarity=a.text_sim,
        image_hamming=a.image_hamming,
        exact=not a.no_exact,
        near=not a.no_near,
        check_file=not a.no_file,
    )
    log = (lambda m: None) if a.quiet else (lambda m: print(m, flush=True))
    res = run_check(cfg, log=log)
    out_dir = cfg.out_dir or os.path.join(os.path.dirname(cfg.test_dir.rstrip("/\\")) or ".", "중복성검사_결과")
    path = write_report(res, out_dir)

    print("\n==== 요약 ====")
    for c in res.categories:
        print("%-22s 학습 %8d / 시험 %8d / 완전일치 %6d / 근사 %6d"
              % (c.label, c.train_units, c.test_units, c.exact_units, c.near_units))
    print("판정: %s" % res.verdict)
    print("리포트: %s" % path)
    return 0 if res.verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
