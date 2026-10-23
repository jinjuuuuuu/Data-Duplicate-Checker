# -*- coding: utf-8 -*-
"""대량 시험 데이터를 검사기로 돌리고 결과를 문서로 정리한다.

EXE 가 화면에서 하는 일과 같은 경로를 탄다. app.py 의 기본 설정을 그대로
Config 에 담아 run_check 를 부르고 write_report 로 리포트를 만든다.
다른 점은 창이 없다는 것뿐이다.

확장자 폴더를 하나씩 돌리고 마지막에 전체를 한 번 돌린 뒤,
기대값(expected.json)과 나란히 놓은 표를 만든다.

    python tests/run_bulk_report.py <ROOT>
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from dupcheck.config import Config                              # noqa: E402
from dupcheck.engine import run_check                           # noqa: E402
from dupcheck.report import write_report                        # noqa: E402

CATS = ["file", "tabular", "image", "text", "array"]
LABEL = {"file": "파일 단위", "tabular": "정형 테이블(행)", "image": "이미지(장)",
         "text": "텍스트/JSON(문서)", "array": "배열/PKL(샘플)"}


def default_config(train, test, out):
    """app.py 가 아무것도 건드리지 않았을 때 만드는 설정과 같게 맞춘다."""
    return Config(
        train_dir=train, test_dir=test, out_dir=out,
        check_file=True, check_tabular=True, check_image=True,
        check_text=True, check_array=True,
        exact=True, near=True,
        exclude_columns=[], key_columns=[],
        ignore_column_order=True,
        float_decimals=4,
        text_cell_normalize=True,
        text_similarity=0.80,
        image_hamming=5,
        max_rows_per_file=0,
        max_samples_in_report=300,
    )


def run_one(train, test, out=None):
    t0 = time.time()
    res = run_check(default_config(train, test, out or ""))
    got = {}
    for c in res.categories:
        if c.ran and (c.train_units or c.test_units):
            got[c.key] = {"exact": c.exact_units, "near": c.near_units,
                          "train": c.train_units, "test": c.test_units,
                          "read_fail": c.read_fail}
    return res, got, time.time() - t0


ZERO = {"exact": 0, "near": 0}


def pair(d):
    """기대값 파일은 0건인 카테고리를 적지 않는다. 없으면 0으로 본다."""
    d = d or ZERO
    return d["exact"], d["near"]


def fmt(d):
    return "%d + %d" % pair(d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    exp = json.load(open(os.path.join(root, "expected.json"), encoding="utf-8"))
    folders = sorted(exp["folders"])

    rows, all_ok = [], True
    for f in folders:
        trd = os.path.join(root, "train", f)
        ted = os.path.join(root, "test", f)
        if not (os.path.isdir(trd) and os.path.isdir(ted)):
            continue
        _res, got, sec = run_one(trd, ted)
        want = exp["folders"][f]
        ok = all(pair(want.get(cat)) == pair(got.get(cat)) for cat in CATS)
        rows.append((f, want, got, sec, ok))
        all_ok &= ok
        print("  %-9s %s  %.1f초" % (f, "OK" if ok else "불일치", sec))
        sys.stdout.flush()

    print("\n전체 한 번에…")
    sys.stdout.flush()
    out_dir = os.path.join(root, "검사리포트")
    res, got_all, sec_all = run_one(os.path.join(root, "train"),
                                    os.path.join(root, "test"), out_dir)
    report = write_report(res, out_dir)
    want_all = exp["total"]
    total_ok = all(pair(want_all.get(c)) == pair(got_all.get(c)) for c in CATS)
    all_ok &= total_ok
    print("  전체      %s  %.1f초 · 판정 %s" % ("OK" if total_ok else "불일치", sec_all, res.verdict))

    # ── 문서 ──────────────────────────────────────────────────────────
    L = []
    L.append("# 대량 시험 데이터 검사 결과")
    L.append("")
    L.append("| 항목 | 값 |")
    L.append("|---|---|")
    L.append("| 데이터 | `%s` |" % root)
    L.append("| 검사일 | %s |" % time.strftime("%Y-%m-%d %H:%M"))
    L.append("| 확장자 | %d종, 각 1000단위 (학습 700 + 시험 300) |" % len(rows))
    L.append("| 전체 소요 | %.1f초 |" % sec_all)
    L.append("| 전체 판정 | %s |" % res.verdict)
    L.append("| 기대값 대조 | %s |" % ("전부 일치" if all_ok else "불일치 있음"))
    L.append("")
    L.append("표기는 `완전일치 + 근사중복` 이다.")
    L.append("")
    L.append("## 확장자별")
    L.append("")
    L.append("0건으로 나온 검사 항목도 모두 적었다. 0건은 '검사하지 않았다'가 아니라")
    L.append("'검사했고 중복이 없었다'는 뜻이다. 돌아가지 않은 항목은 아예 줄이 없다.")
    L.append("")
    L.append("| 확장자 | 검사 항목 | 비교한 학습 | 비교한 시험 | 기대 | 실제 | 결과 | 읽기 실패 | 소요 |")
    L.append("|---|---|---:|---:|---|---|---|---:|---:|")
    for f, want, got, sec, ok in rows:
        first = True
        for cat in CATS:
            w, g = want.get(cat), got.get(cat)
            if g is None:
                continue                       # 이 폴더에서 돌지 않은 검사
            mark = "OK" if pair(w) == pair(g) else "불일치"
            L.append("| %s | %s | %s | %s | %s | %s | %s | %d | %s |" % (
                f if first else "", LABEL[cat],
                "{:,}".format(g.get("train", 0)), "{:,}".format(g.get("test", 0)),
                fmt(w), fmt(g), mark, g.get("read_fail", 0),
                "%.1f초" % sec if first else ""))
            first = False
    L.append("")
    L.append("## 전체를 한 번에")
    L.append("")
    L.append("`train` 과 `test` 폴더를 통째로 넣었을 때다. 폴더별 기대값의 합과 같아야 한다.")
    L.append("")
    L.append("| 검사 항목 | 학습 단위 | 시험 단위 | 기대 | 실제 | 결과 | 읽기 실패 |")
    L.append("|---|---:|---:|---|---|---|---:|")
    for cat in CATS:
        w, g = want_all.get(cat), got_all.get(cat)
        if not (w or g):
            continue
        mark = "OK" if pair(w) == pair(g) else "불일치"
        L.append("| %s | %s | %s | %s | %s | %s | %d |" % (
            LABEL[cat], "{:,}".format((g or {}).get("train", 0)),
            "{:,}".format((g or {}).get("test", 0)),
            fmt(w), fmt(g), mark, (g or {}).get("read_fail", 0)))
    L.append("")
    L.append("HTML 리포트: `%s`" % report)
    L.append("")
    L.append("## 읽는 법")
    L.append("")
    L.append("- **완전일치** — 내용이 같은 단위. 한 건이라도 있으면 전체 판정은 FAIL")
    L.append("- **근사중복** — 임계값(수치 4자리 · 텍스트 0.80 · 이미지 해밍 5) 안에서 유사한 단위")
    L.append("- **읽기 실패** — 파일을 열지 못해 그 검사에서 빠진 파일 수. 0이어야 전부 검사된 것")
    L.append("- 이미지 완전일치 30건 중 절반은 **재압축본**이라 픽셀은 같고 바이트가 다르다.")
    L.append("  그래서 png·tif·tiff·webp 는 파일 단위가 30이 아니라 15로 잡힌다.")
    L.append("")

    # 다른 형식(엑셀 등)으로 옮길 때 쓰도록 구조화해서도 남긴다
    with open(os.path.join(root, "검사결과.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "root": root,
            "checked_at": time.strftime("%Y-%m-%d %H:%M"),
            "total_sec": round(sec_all, 1),
            "verdict": res.verdict,
            "all_ok": all_ok,
            "report": report,
            "folders": [{"folder": f, "sec": round(s, 1), "ok": ok,
                         "want": w, "got": g} for f, w, g, s, ok in rows],
            "overall": {"want": want_all, "got": got_all},
        }, fh, ensure_ascii=False, indent=2)

    doc = os.path.join(root, "검사결과.md")
    with open(doc, "w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(L))
    print("\n문서: %s" % doc)
    print("리포트: %s" % report)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
