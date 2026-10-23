# -*- coding: utf-8 -*-
"""make_format_samples.py 로 만든 데이터를 실제 엔진으로 검사해 기대값과 대조한다.

포맷 폴더마다 학습/시험 경로를 넣어 한 번씩 돌리고, 마지막에 train ↔ test 전체를
한 번 더 돌려 포맷별 기대값의 합과 맞는지 확인한다.

    python tests/verify_format_samples.py <ROOT>
    python tests/verify_format_samples.py <ROOT> --only png,csv
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dupcheck.config import Config                     # noqa: E402
from dupcheck.engine import run_check                  # noqa: E402

CATS = ("file", "tabular", "image", "text", "array")
LABEL = {"file": "파일단위", "tabular": "표(행)", "image": "이미지(장)",
         "text": "텍스트(문서)", "array": "배열(샘플)"}


def actual(train_dir, test_dir):
    cfg = Config(train_dir=train_dir, test_dir=test_dir)
    res = run_check(cfg, log=lambda m: None)
    got = {}
    errors, notes = [], []
    for c in res.categories:
        if c.exact_units or c.near_units:
            got[c.key] = {"exact": c.exact_units, "near": c.near_units}
        errors += ["[%s] %s" % (LABEL.get(c.key, c.key), e) for e in c.errors]
        notes += ["[%s] %s" % (LABEL.get(c.key, c.key), n) for n in c.notes]
    return got, errors, notes, res


def diff(exp, got):
    """기대값과 실측값 차이. 반환값이 빈 리스트면 일치."""
    out = []
    for cat in CATS:
        e = exp.get(cat, {"exact": 0, "near": 0})
        g = got.get(cat, {"exact": 0, "near": 0})
        for kind in ("exact", "near"):
            if e[kind] != g[kind]:
                out.append("%s %s 기대 %d → 실측 %d"
                           % (LABEL[cat], "완전일치" if kind == "exact" else "근사중복",
                              e[kind], g[kind]))
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description="포맷별 샘플 데이터 검증")
    p.add_argument("root")
    p.add_argument("--only", default="", help="검사할 폴더만 콤마로 지정")
    p.add_argument("--skip-total", action="store_true", help="전체 통합 검사를 건너뛴다")
    p.add_argument("--show-notes", action="store_true", help="카테고리 비고까지 출력")
    a = p.parse_args(argv)
    root = os.path.abspath(a.root)

    with open(os.path.join(root, "expected.json"), encoding="utf-8") as f:
        exp = json.load(f)
    only = {s.strip() for s in a.only.split(",") if s.strip()}

    folders = [f for f in sorted(exp["folders"]) if not only or f in only]
    print("검증 대상: %s" % root)
    print("=" * 78)
    print("%-12s %-6s %s" % ("폴더", "결과", "내용"))
    print("-" * 78)

    failed, all_errors = [], []
    for folder in folders:
        trd = os.path.join(root, "train", folder)
        ted = os.path.join(root, "test", folder)
        if not (os.path.isdir(trd) and os.path.isdir(ted)):
            print("%-12s %-6s 폴더 없음 → 건너뜀" % (folder, "SKIP"))
            continue
        got, errors, notes, _ = actual(trd, ted)
        bad = diff(exp["folders"][folder], got)
        summary = " / ".join("%s %d+%d" % (LABEL[c], got[c]["exact"], got[c]["near"])
                             for c in CATS if c in got) or "중복 없음"
        print("%-12s %-6s %s" % (folder, "FAIL" if bad else "OK", summary))
        for m in bad:
            print("%-12s        ✗ %s" % ("", m))
        if bad:
            failed.append(folder)
        for e in errors:
            all_errors.append("%s: %s" % (folder, e))
        if a.show_notes:
            for n in notes:
                print("%-12s        · %s" % ("", n))

    if not a.skip_total and not only:
        print("-" * 78)
        got, errors, notes, res = actual(os.path.join(root, "train"),
                                        os.path.join(root, "test"))
        bad = diff(exp["total"], got)
        summary = " / ".join("%s %d+%d" % (LABEL[c], got[c]["exact"], got[c]["near"])
                             for c in CATS if c in got)
        print("%-12s %-6s %s" % ("전체", "FAIL" if bad else "OK", summary))
        for m in bad:
            print("%-12s        ✗ %s" % ("", m))
        if bad:
            failed.append("전체")
        print("%-12s        판정 %s / 소요 %.1f초" % ("", res.verdict, res.elapsed_sec))

    print("=" * 78)
    if all_errors:
        print("\n엔진이 기록한 읽기 오류 (edge_cases 는 의도된 것):")
        for e in all_errors:
            print("  - " + e)
    if exp.get("warnings"):
        print("\n데이터 생성 시 경고:")
        for w in exp["warnings"]:
            print("  - " + w)

    if failed:
        print("\n결과: 실패 %d건 → %s" % (len(failed), ", ".join(failed)))
        return 1
    print("\n결과: 검사한 %d개 항목 모두 기대값과 일치" % (len(folders) + (0 if only else 1)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
