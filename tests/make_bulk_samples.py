# -*- coding: utf-8 -*-
"""확장자별로 검사 단위 1000개짜리 시험 데이터를 만든다.

tests/make_format_samples.py 가 '포맷마다 최소한의 사례'를 만든다면, 이쪽은
'포맷마다 충분한 양'을 만든다. 폴더 구조와 기대값 파일 형식은 같다.

    <ROOT>/train/<확장자>/...
    <ROOT>/test/<확장자>/...
    <ROOT>/expected.json
    <ROOT>/기대결과.md

확장자마다 검사 단위 1000개(학습 700 + 시험 300)를 만들고, 시험 쪽 300개 중
30개는 완전일치, 20개는 근사중복이 되도록 심는다. 나머지 250개는 새 것이다.
'단위'는 형식에 따라 파일 한 개, 표의 한 행, 배열의 한 샘플을 뜻한다.

    python tests/make_bulk_samples.py <ROOT>
    python tests/verify_format_samples.py <ROOT>      (검증은 같은 것을 쓴다)
"""
import argparse
import hashlib
import json
import os
import pickle
import shutil
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from dupcheck.imagecheck import image_hashes                       # noqa: E402
from dupcheck.textcheck import shingles                            # noqa: E402

from make_format_samples import (                                   # noqa: E402
    IMAGE_SPECS, _has, _save_img, _synth, _table, _write_table,
    rmtree_retry, write_text,
)

MARKER = "_생성정보.json"
CAT_LABEL = {"file": "파일 단위 동일성", "tabular": "정형 테이블(행)",
             "image": "이미지(장)", "text": "텍스트/JSON(문서)", "array": "배열/PKL(샘플)"}

# ── 규모 ──────────────────────────────────────────────────────────────
UNITS = 1000            # 확장자당 검사 단위 수
N_TRAIN = 700
N_TEST = UNITS - N_TRAIN        # 300
N_EXACT = 30                    # 시험 쪽에 심는 완전일치
N_NEAR = 20                     # 시험 쪽에 심는 근사중복
N_NEW = N_TEST - N_EXACT - N_NEAR   # 250

EXPECT = {}
EXPECT_FOLDERS = []
WARN = []


def tr(root, folder):
    p = os.path.join(root, "train", folder)
    os.makedirs(p, exist_ok=True)
    return p


def te(root, folder):
    p = os.path.join(root, "test", folder)
    os.makedirs(p, exist_ok=True)
    return p


def expect(folder, cat, exact=0, near=0):
    d = EXPECT.setdefault(folder, {})
    cur = d.setdefault(cat, {"exact": 0, "near": 0})
    cur["exact"] += exact
    cur["near"] += near
    if folder not in EXPECT_FOLDERS:
        EXPECT_FOLDERS.append(folder)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _spread(n, total):
    """0..total-1 에서 n 개를 고르게 흩뿌린다."""
    if n <= 0:
        return []
    if n == 1:
        return [0]
    return [int(round(i * (total - 1) / float(n - 1))) for i in range(n)]


def _pick(n_exact, n_near, total):
    """완전일치용·근사중복용 번호를 겹치지 않게 고른다.

    고르게 흩뿌린 번호끼리 부딪히면 남은 번호에서 차례로 채운다.
    (반드시 끝나야 한다. 직전 값만 보고 다음 후보를 만들면 부딪히는 순간
    상태가 변하지 않아 영원히 돈다.)
    """
    ex, used = [], set()
    for x in _spread(n_exact, total):
        if x not in used:
            ex.append(x)
            used.add(x)
    near = []
    for x in _spread(n_near, total):
        if x not in used:
            near.append(x)
            used.add(x)
    i = 0
    while (len(ex) < n_exact or len(near) < n_near) and i < total:
        if i not in used:
            used.add(i)
            (ex if len(ex) < n_exact else near).append(i)
        i += 1
    return sorted(ex), sorted(near)


# ─────────────────────────────────────────────────────────── 이미지

def make_images(root):
    try:
        from PIL import Image, ImageDraw
    except Exception:
        WARN.append("Pillow 가 없어 이미지 폴더를 만들지 못했습니다.")
        return

    for k, (folder, ext, kw, rekw) in enumerate(IMAGE_SPECS):
        seed_base = 500000 + 20000 * k      # 폴더마다 겹치지 않는 시드 구간
        trd, ted = tr(root, folder), te(root, folder)

        for i in range(N_TRAIN):
            _save_img(Image, _synth(Image, ImageDraw, seed_base + i),
                      os.path.join(trd, "tr_%04d%s" % (i, ext)), kw)
        for i in range(N_NEW):
            _save_img(Image, _synth(Image, ImageDraw, seed_base + 10000 + i),
                      os.path.join(ted, "new_%04d%s" % (i, ext)), kw)

        ex_src, nr_src = _pick(N_EXACT, N_NEAR, N_TRAIN)
        # 완전일치 — 재압축을 지원하는 형식은 절반을 '픽셀만 같은' 사례로
        n_recompress = N_EXACT // 2 if rekw is not None else 0
        for j, i in enumerate(ex_src):
            src = os.path.join(trd, "tr_%04d%s" % (i, ext))
            if j < n_recompress:
                with Image.open(src) as t:
                    t.load()
                    t.save(os.path.join(ted, "exact_recompressed_of_tr%04d%s" % (i, ext)), **rekw)
            else:
                shutil.copy(src, os.path.join(ted, "exact_bytecopy_of_tr%04d%s" % (i, ext)))
        # 근사중복 — 1.5배로 키웠다가 저장
        for i in nr_src:
            with Image.open(os.path.join(trd, "tr_%04d%s" % (i, ext))) as t:
                t.load()
                _save_img(Image, t.convert("RGB").resize((192, 192), Image.BILINEAR),
                          os.path.join(ted, "near_resized_of_tr%04d%s" % (i, ext)), kw)

        expect(folder, "image", exact=len(ex_src), near=len(nr_src))
        _check_images(Image, folder, trd, ted, ext, ex_src, nr_src)
        print("  %-7s 이미지 %d장" % (folder, N_TRAIN + N_TEST))


def _check_images(Image, folder, trd, ted, ext, ex_src, nr_src):
    """심은 것이 기본 임계값(해밍 5)에 실제로 걸리는지 본다."""
    bad_exact = bad_near = 0
    for i in ex_src:
        a = image_hashes(Image, os.path.join(trd, "tr_%04d%s" % (i, ext)))[0]
        for name in ("exact_recompressed_of_tr%04d%s" % (i, ext),
                     "exact_bytecopy_of_tr%04d%s" % (i, ext)):
            p = os.path.join(ted, name)
            if os.path.exists(p) and image_hashes(Image, p)[0] != a:
                bad_exact += 1
    for i in nr_src:
        # image_hashes 는 (픽셀해시, dhash 정수, 크기) 를 돌려준다.
        # 완전일치는 픽셀해시로 보고, 근사중복은 dhash 해밍거리로 본다.
        a = image_hashes(Image, os.path.join(trd, "tr_%04d%s" % (i, ext)))[1]
        b = image_hashes(Image, os.path.join(ted, "near_resized_of_tr%04d%s" % (i, ext)))[1]
        if bin(a ^ b).count("1") > 5:
            bad_near += 1
    if bad_exact or bad_near:
        WARN.append("[%s] 이미지: 완전일치 어긋남 %d건 · 근사중복 임계 초과 %d건"
                    % (folder, bad_exact, bad_near))


# ─────────────────────────────────────────────────────────── 문서

_VOCAB = ["검증", "모형", "표본", "지표", "경계", "잔차", "편향", "분산", "군집", "회귀",
          "분류", "추론", "학습", "시험", "보정", "가중", "임계", "누적", "분포", "상관",
          "신뢰", "구간", "측정", "오차", "정밀", "재현", "조화", "평균", "중앙", "최빈",
          "변환", "정규", "표준", "축소", "확장", "선택", "제거", "결측", "이상", "잡음",
          "주기", "추세", "계절", "적합", "과적", "일반", "규제", "희소", "밀집", "직교"]
_SUFFIX = ["값", "률", "도", "량", "수", "역", "면", "축", "항", "군"]
DOC_WORDS = 120


def _lines(toks):
    out, line = [], []
    for t in toks:
        line.append(t)
        if len(line) >= 10:
            out.append(" ".join(line) + ".")
            line = []
    if line:
        out.append(" ".join(line) + ".")
    return "\n".join(out)


def gen_doc(folder, idx):
    """폴더·번호마다 어휘 조합이 거의 겹치지 않는 문서.

    낱말마다 네 자리 수를 붙여 만들어, 서로 다른 번호의 문서끼리는 3낱말
    셰이글이 사실상 겹치지 않는다(우연한 근사중복을 막는다).
    """
    seed = int(hashlib.md5(("bulk|%s|%d" % (folder, idx)).encode("utf-8")).hexdigest()[:8], 16)
    rng = np.random.RandomState(seed)
    return _lines(["%s%s%d" % (_VOCAB[rng.randint(len(_VOCAB))],
                               _SUFFIX[rng.randint(len(_SUFFIX))],
                               rng.randint(10000)) for _ in range(DOC_WORDS)])


def near_doc(text, n_change=3):
    """낱말 몇 개만 바꾼 변형.

    셰이글이 3낱말 단위라 낱말 하나를 바꾸면 셰이글 세 개가 깨진다.
    낱말 n개를 바꾸면 유사도가 대략 (N-3n)/(N+3n) 이 되므로, 기본 임계값
    0.80 위에 남기려면 120낱말에서 3개쯤만 건드려야 한다(약 0.86).
    """
    rng = np.random.RandomState(
        int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16))
    toks = text.replace("\n", " ").replace(".", "").split()
    for i in rng.permutation(len(toks))[:max(1, min(n_change, len(toks)))]:
        toks[i] = "%s%s%d" % (_VOCAB[rng.randint(len(_VOCAB))],
                              _SUFFIX[rng.randint(len(_SUFFIX))], rng.randint(10000))
    return _lines(toks)


def _jacc(a, b):
    sa, sb = set(shingles(a)), set(shingles(b))
    return len(sa & sb) / float(len(sa | sb)) if (sa or sb) else 0.0


def _check_docs(folder, pairs, others, sample=24):
    """심은 근사중복이 임계값을 넘는지, 남남끼리 우연히 겹치지 않는지 본다."""
    lo = min((_jacc(a, b) for a, b in pairs), default=1.0)
    if lo < 0.80:
        WARN.append("[%s] 근사중복 유사도 최저 %.2f 로 기준 0.80 미달" % (folder, lo))
    hi = 0.0
    s = others[:sample]
    for i in range(len(s)):
        for j in range(i + 1, len(s)):
            hi = max(hi, _jacc(s[i], s[j]))
    if hi >= 0.80:
        WARN.append("[%s] 서로 다른 문서끼리 유사도가 %.2f 로 우연히 겹칩니다" % (folder, hi))
    return lo, hi


def make_text_files(root):
    """txt / text / md — 파일 하나가 문서 하나."""
    for folder, ext in (("txt", ".txt"), ("text", ".text"), ("md", ".md")):
        trd, ted = tr(root, folder), te(root, folder)
        head = (lambda i: "# 표본 문서 %d\n\n" % i) if ext == ".md" else (lambda i: "")
        docs = [gen_doc(folder, i) for i in range(N_TRAIN)]
        for i, t in enumerate(docs):
            write_text(os.path.join(trd, "doc_%04d%s" % (i, ext)), head(i) + t)
        news = [gen_doc(folder, 100000 + i) for i in range(N_NEW)]
        for i, t in enumerate(news):
            write_text(os.path.join(ted, "new_%04d%s" % (i, ext)), head(100000 + i) + t)

        ex_src, nr_src = _pick(N_EXACT, N_NEAR, N_TRAIN)
        for i in ex_src:
            write_text(os.path.join(ted, "exact_copy_of_doc%04d%s" % (i, ext)),
                       head(i) + docs[i])
        pairs = []
        for i in nr_src:
            v = near_doc(docs[i])
            write_text(os.path.join(ted, "near_variant_of_doc%04d%s" % (i, ext)), head(i) + v)
            pairs.append((docs[i], v))

        expect(folder, "text", exact=len(ex_src), near=len(nr_src))
        lo, hi = _check_docs(folder, pairs, news)
        print("  %-7s 문서 %d개  (근사중복 최저 %.2f · 남남 최고 %.2f)"
              % (folder, N_TRAIN + N_TEST, lo, hi))


def _record(folder, idx, text):
    return {"doc_id": "%s-%05d" % (folder, idx), "label": idx % 3, "text": text}


def _flat(rec):
    return json.dumps(rec, ensure_ascii=False, sort_keys=True)


def make_json_like(root):
    """json / jsonl / ndjson — 레코드 하나가 문서 하나."""
    for folder, ext in (("json", ".json"), ("jsonl", ".jsonl"), ("ndjson", ".ndjson")):
        trd, ted = tr(root, folder), te(root, folder)
        docs = [gen_doc(folder, i) for i in range(N_TRAIN)]
        recs = [_record(folder, i, t) for i, t in enumerate(docs)]
        news = [_record(folder, 100000 + i, gen_doc(folder, 100000 + i)) for i in range(N_NEW)]

        ex_src, nr_src = _pick(N_EXACT, N_NEAR, N_TRAIN)
        exacts = [dict(recs[i]) for i in ex_src]
        nears, pairs = [], []
        for i in nr_src:
            r = dict(recs[i])
            r["text"] = near_doc(docs[i])
            nears.append(r)
            pairs.append((_flat(recs[i]), _flat(r)))
        test_recs = news + exacts + nears

        if ext == ".json":
            write_text(os.path.join(trd, "train_docs.json"),
                       json.dumps(recs, ensure_ascii=False, indent=2))
            write_text(os.path.join(ted, "test_docs.json"),
                       json.dumps(test_recs, ensure_ascii=False, indent=2))
        else:
            write_text(os.path.join(trd, "train_docs" + ext),
                       "".join(_flat(r) + "\n" for r in recs))
            write_text(os.path.join(ted, "test_docs" + ext),
                       "".join(_flat(r) + "\n" for r in test_recs))

        expect(folder, "text", exact=len(ex_src), near=len(nr_src))
        lo, hi = _check_docs(folder, pairs, [_flat(r) for r in news])
        print("  %-7s 레코드 %d개  (근사중복 최저 %.2f · 남남 최고 %.2f)"
              % (folder, N_TRAIN + N_TEST, lo, hi))


# ─────────────────────────────────────────────────────────── 정형 테이블

def _jitter(a):
    """4자리로 반올림하면 원래와 같아지는, 그러나 값은 다른 수를 만든다.

    그냥 1e-7 을 더하면 원래 값이 반올림 경계(…5)에 걸려 있을 때 넷째 자리가
    바뀌어 버린다. 먼저 4자리에 딱 맞춰 놓고 흔들면 경계를 넘지 않는다.
    """
    return np.round(np.asarray(a, dtype=float), 4) + 1e-7


def _plant(train_df, new_df, ex_idx, nr_idx):
    exact = train_df.iloc[ex_idx].copy()
    near = train_df.iloc[nr_idx].copy()
    near["f1"] = _jitter(near["f1"].to_numpy())                  # 4자리 반올림 시 동일
    near["name"] = near["name"].str.lower().str.replace(" ", "  ", regex=False)
    return pd.concat([new_df, exact, near], ignore_index=True)


TAB_SPECS = [("csv", ".csv"), ("tsv", ".tsv"), ("xlsx", ".xlsx"),
             ("xlsm", ".xlsm"), ("xls", ".xls"), ("parquet", ".parquet")]


def make_tabular(root):
    for k, (folder, ext) in enumerate(TAB_SPECS):
        if ext == ".xls" and not _has("xlwt"):
            WARN.append("xlwt 가 없어 xls 폴더를 만들지 못했습니다 (pip install xlwt).")
            continue
        if ext == ".parquet" and not _has("pyarrow"):
            WARN.append("pyarrow 가 없어 parquet 폴더를 만들지 못했습니다.")
            continue
        base = 700000 + 50000 * k
        trd, ted = tr(root, folder), te(root, folder)
        train = _table(900 + k, N_TRAIN, base)
        new = _table(950 + k, N_NEW, base + 20000)
        ex_idx, nr_idx = _pick(N_EXACT, N_NEAR, N_TRAIN)
        test = _plant(train, new, ex_idx, nr_idx)

        # 학습은 파일 둘로 나눠, 여러 파일이 합쳐지는 경로도 태운다
        half = N_TRAIN // 2
        _write_table(train.iloc[:half], os.path.join(trd, "train_part1" + ext))
        _write_table(train.iloc[half:], os.path.join(trd, "train_part2" + ext))
        _write_table(test, os.path.join(ted, "test_main" + ext))

        expect(folder, "tabular", exact=len(ex_idx), near=len(nr_idx))
        print("  %-7s 행 %d개 (학습 %d + 시험 %d)" % (folder, UNITS, N_TRAIN, N_TEST))


# ─────────────────────────────────────────────────────────── 배열 / PKL

def _arrays(seed):
    """학습 700샘플, 시험 300샘플. 시험 쪽에 완전일치 30 · 근사중복 20을 심는다."""
    rng = np.random.RandomState(seed)
    xtr = rng.rand(N_TRAIN, 8)
    ytr = rng.randint(0, 3, N_TRAIN)
    xte = rng.rand(N_TEST, 8)
    ex_idx, nr_idx = _pick(N_EXACT, N_NEAR, N_TRAIN)
    for j, i in enumerate(ex_idx):
        xte[j] = xtr[i]                                  # 바이트까지 동일
    for j, i in enumerate(nr_idx):
        xte[len(ex_idx) + j] = _jitter(xtr[i])           # 4자리 반올림 시 동일
    return xtr, ytr, xte, rng.randint(0, 3, N_TEST)


def _check_arrays(folder, xtr, xte):
    exact = sum(1 for r in xte if any(np.array_equal(r, t) for t in xtr))
    rtr = {np.round(t, 4).tobytes() for t in xtr}
    near = sum(1 for r in xte if np.round(r, 4).tobytes() in rtr
               and not any(np.array_equal(r, t) for t in xtr))
    if (exact, near) != (N_EXACT, N_NEAR):
        WARN.append("[%s] 배열 완전일치 %d·근사중복 %d 를 의도했으나 %d·%d 입니다."
                    % (folder, N_EXACT, N_NEAR, exact, near))
    return exact, near


def make_arrays(root):
    for folder, seed in (("npy", 4021), ("npz", 4022)):
        xtr, ytr, xte, yte = _arrays(seed)
        trd, ted = tr(root, folder), te(root, folder)
        if folder == "npy":
            np.save(os.path.join(trd, "X_train.npy"), xtr)
            np.save(os.path.join(trd, "y_train.npy"), ytr)
            np.save(os.path.join(ted, "X_test.npy"), xte)
            np.save(os.path.join(ted, "y_test.npy"), yte)
        else:
            np.savez(os.path.join(trd, "train_data.npz"), X=xtr, y=ytr)
            np.savez(os.path.join(ted, "test_data.npz"), X=xte, y=yte)
        e, n = _check_arrays(folder, xtr, xte)
        expect(folder, "array", exact=e, near=n)
        print("  %-7s 샘플 %d개 (완전 %d · 근사 %d)" % (folder, UNITS, e, n))


def make_pickles(root):
    # pkl — DataFrame(표 1000행)
    folder = "pkl"
    trd, ted = tr(root, folder), te(root, folder)
    train = _table(4031, N_TRAIN, 900000)
    new = _table(4032, N_NEW, 960000)
    ex_idx, nr_idx = _pick(N_EXACT, N_NEAR, N_TRAIN)
    train.to_pickle(os.path.join(trd, "train_table.pkl"))
    _plant(train, new, ex_idx, nr_idx).to_pickle(os.path.join(ted, "test_table.pkl"))
    expect(folder, "tabular", exact=len(ex_idx), near=len(nr_idx))
    print("  %-7s 행 %d개" % (folder, UNITS))

    # pickle — 배열 묶음(샘플 1000개)
    folder = "pickle"
    trd, ted = tr(root, folder), te(root, folder)
    xtr, ytr, xte, yte = _arrays(4033)
    with open(os.path.join(trd, "train_bundle.pickle"), "wb") as f:
        pickle.dump({"X": xtr, "y": ytr}, f)
    with open(os.path.join(ted, "test_bundle.pickle"), "wb") as f:
        pickle.dump({"X": xte, "y": yte}, f)
    e, n = _check_arrays(folder, xtr, xte)
    expect(folder, "array", exact=e, near=n)
    print("  %-7s 샘플 %d개 (완전 %d · 근사 %d)" % (folder, UNITS, e, n))


# ─────────────────────────────────────────────────────────── 마무리

def count_file_dups(root):
    """바이트까지 같은 파일이 양쪽에 있는 경우를 세어 파일 단위 기대값으로 넣는다."""
    for folder in list(EXPECT_FOLDERS):
        trd = os.path.join(root, "train", folder)
        ted = os.path.join(root, "test", folder)
        if not (os.path.isdir(trd) and os.path.isdir(ted)):
            continue
        tr_h = {sha256(os.path.join(trd, n)) for n in os.listdir(trd)}
        n = sum(1 for name in os.listdir(ted) if sha256(os.path.join(ted, name)) in tr_h)
        if n:
            expect(folder, "file", exact=n)


def totals():
    out = {}
    for d in EXPECT.values():
        for cat, v in d.items():
            c = out.setdefault(cat, {"exact": 0, "near": 0})
            c["exact"] += v["exact"]
            c["near"] += v["near"]
    return out


def write_expected(root):
    with open(os.path.join(root, "expected.json"), "w", encoding="utf-8") as f:
        json.dump({"folders": EXPECT, "total": totals()}, f, ensure_ascii=False, indent=2)
    L = ["# 기대 결과 (확장자별 %d단위)" % UNITS, "",
         "확장자마다 검사 단위 %d개(학습 %d + 시험 %d)." % (UNITS, N_TRAIN, N_TEST),
         "시험 %d개 중 완전일치 %d · 근사중복 %d 를 심었다." % (N_TEST, N_EXACT, N_NEAR), "",
         "| 폴더 | 카테고리 | 완전일치 | 근사중복 |", "|---|---|---:|---:|"]
    for folder in sorted(EXPECT):
        for cat in ("file", "tabular", "image", "text", "array"):
            v = EXPECT[folder].get(cat)
            if v:
                L.append("| %s | %s | %d | %d |" % (folder, CAT_LABEL[cat], v["exact"], v["near"]))
    L += ["", "| 전체 | 완전일치 | 근사중복 |", "|---|---:|---:|"]
    for cat in ("file", "tabular", "image", "text", "array"):
        v = totals().get(cat)
        if v:
            L.append("| %s | %d | %d |" % (CAT_LABEL[cat], v["exact"], v["near"]))
    write_text(os.path.join(root, "기대결과.md"), "\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description="확장자별 1000단위 시험 데이터 생성")
    ap.add_argument("root")
    ap.add_argument("--keep", action="store_true", help="기존 폴더를 지우지 않는다")
    a = ap.parse_args()
    root = os.path.abspath(a.root)

    if os.path.exists(root) and not a.keep:
        if os.path.exists(os.path.join(root, MARKER)) or not os.listdir(root):
            rmtree_retry(root)
        else:
            print("[중단] %s 는 이 스크립트가 만든 폴더가 아닙니다. 다른 경로를 쓰세요." % root)
            return 2
    os.makedirs(root, exist_ok=True)

    print("생성 중 — 확장자마다 %d단위 (학습 %d / 시험 %d, 완전 %d · 근사 %d)\n"
          % (UNITS, N_TRAIN, N_TEST, N_EXACT, N_NEAR))
    sys.stdout.flush()
    make_tabular(root)
    make_arrays(root)
    make_pickles(root)
    make_text_files(root)
    make_json_like(root)
    make_images(root)
    count_file_dups(root)
    write_expected(root)

    with open(os.path.join(root, MARKER), "w", encoding="utf-8") as f:
        json.dump({"generator": "tests/make_bulk_samples.py", "units": UNITS,
                   "folders": EXPECT_FOLDERS}, f, ensure_ascii=False, indent=2)

    n_files = sum(len(fs) for _, _, fs in os.walk(root))
    size = sum(os.path.getsize(os.path.join(d, n))
               for d, _, fs in os.walk(root) for n in fs)
    print("\n완료: %s" % root)
    print("폴더 %d개 · 파일 %d개 · %.0f MB" % (len(EXPECT_FOLDERS), n_files, size / 1e6))
    print()
    for cat in ("file", "tabular", "image", "text", "array"):
        v = totals().get(cat)
        if v:
            print("전체 %-18s 완전일치 %5d / 근사중복 %5d" % (CAT_LABEL[cat], v["exact"], v["near"]))
    if WARN:
        print("\n경고:")
        for w in WARN:
            print("  - " + w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
