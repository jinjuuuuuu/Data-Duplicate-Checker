# -*- coding: utf-8 -*-
"""포맷별 검증용 샘플 데이터 생성.

지원 확장자마다 폴더를 따로 만들고, 폴더 안에 완전일치/근사중복을 의도적으로
심는다. 폴더 구조는 다음과 같다.

    <ROOT>/train/<확장자>/...
    <ROOT>/test/<확장자>/...
    <ROOT>/expected.json      기계 판독용 기대 결과
    <ROOT>/기대결과.md         사람이 읽는 기대 결과표

폴더별로 학습/시험 경로를 지정해 한 포맷씩 검사할 수도 있고, <ROOT>/train 과
<ROOT>/test 를 그대로 넣어 전체를 한 번에 검사할 수도 있다(포맷별 기대값의
단순 합이 전체 기대값이 되도록 폴더마다 내용을 겹치지 않게 만든다).

    python tests/make_format_samples.py <ROOT>
    python tests/verify_format_samples.py <ROOT>
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import zipfile

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dupcheck.imagecheck import image_hashes                       # noqa: E402
from dupcheck.textcheck import shingles, signature                 # noqa: E402
from dupcheck.util import h_text, norm_newlines                    # noqa: E402

MARKER = "_생성정보.json"

# 기대 결과: {폴더명: {카테고리: {"exact": n, "near": n}}}
EXPECT = {}
EXPECT_FOLDERS = []
# 자기검증 경고 목록(설계 의도가 임계값 안에 들어오지 않은 경우)
WARN = []

CAT_LABEL = {"file": "파일 단위 동일성", "tabular": "정형 테이블(행)",
             "image": "이미지(장)", "text": "텍스트/JSON(문서)", "array": "배열/PKL(샘플)"}


# ─────────────────────────────────────────────────────────── 공통 유틸

def tr(root, folder):
    p = os.path.join(root, "train", folder)
    os.makedirs(p, exist_ok=True)
    return p


def te(root, folder):
    p = os.path.join(root, "test", folder)
    os.makedirs(p, exist_ok=True)
    return p


def expect(folder, cat, exact=0, near=0):
    d = EXPECT.setdefault(folder, {}).setdefault(cat, {"exact": 0, "near": 0})
    d["exact"] += exact
    d["near"] += near


def write_text(path, text, encoding="utf-8", newline="\n"):
    with open(path, "w", encoding=encoding, newline=newline) as f:
        f.write(text)


def rmtree_retry(path, tries=3):
    """폴더 삭제. OneDrive 동기화 폴더에서 실패하는 경우까지 처리한다.

    OneDrive 가 폴더 핸들을 붙잡고 있으면 파일은 지워지지만 빈 디렉터리를
    지우는 os.rmdir 이 WinError 5 로 실패한다. 재시도로도 안 풀리므로
    이때는 rd /s /q 로 넘긴다(같은 상황에서 성공한다).
    """
    import subprocess
    import time
    for i in range(tries):
        try:
            shutil.rmtree(path)
            return
        except OSError:
            if i < tries - 1:
                time.sleep(0.5 * (i + 1))
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "rd", "/s", "/q", path],
                       capture_output=True, check=False)
    if os.path.exists(path):
        raise OSError("폴더를 지울 수 없습니다: %s (탐색기에서 닫은 뒤 다시 실행하세요)" % path)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# ─────────────────────────────────────────────────────────── 정형 테이블

TAB_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _table(seed, n, id_base):
    rng = np.random.RandomState(seed)
    return pd.DataFrame({
        "id": np.arange(id_base, id_base + n),
        "name": ["Sample-%s %d" % (TAB_LETTERS[i % 26], id_base + i) for i in range(n)],
        "f1": rng.rand(n).round(6),
        "f2": rng.randint(0, 1000, n),
        "label": rng.randint(0, 3, n),
    })


def _plant_rows(train_df, new_df, exact_idx, near_idx):
    """new_df 뒤에 완전일치 행과 근사중복 행을 붙인다.

    - 완전일치: 학습 행을 그대로 복사
    - 근사중복: f1 을 소수 7째 자리에서 흔들고(4자리 반올림하면 같아짐)
      name 을 소문자·공백중복으로 바꿔(공백/대소문자 무시하면 같아짐) 만든다
    """
    exact = train_df.iloc[exact_idx].copy()
    near = train_df.iloc[near_idx].copy()
    near["f1"] = np.round(near["f1"].to_numpy() + 1e-7, 7)
    near["name"] = near["name"].str.lower().str.replace(" ", "  ", regex=False)
    return pd.concat([new_df, exact, near], ignore_index=True)


def _write_xls(df, path):
    """구형 .xls(BIFF) 쓰기. pandas 2.x 는 xls 쓰기 엔진을 지원하지 않으므로 직접 쓴다."""
    import xlwt
    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet("Sheet1")
    for j, c in enumerate(df.columns):
        ws.write(0, j, str(c))
    for i, row in enumerate(df.itertuples(index=False), start=1):
        for j, v in enumerate(row):
            ws.write(i, j, v.item() if hasattr(v, "item") else v)   # numpy 스칼라 → 파이썬 값
    wb.save(path)


def _write_table(df, path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        df.to_csv(path, index=False, encoding="utf-8-sig")
    elif ext == ".tsv":
        df.to_csv(path, index=False, sep="\t", encoding="utf-8-sig")
    elif ext in (".xlsx", ".xlsm"):
        df.to_excel(path, index=False)
    elif ext == ".xls":
        _write_xls(df, path)
    elif ext == ".parquet":
        df.to_parquet(path, index=False)
    else:
        raise ValueError(ext)


def _has(*mods):
    for m in mods:
        try:
            __import__(m)
            return True
        except Exception:
            continue
    return False


def make_tabular(root):
    """csv / tsv / xlsm / parquet / xls — 행 단위 완전일치 5건, 근사중복 3건."""
    specs = [("csv", ".csv", 10), ("tsv", ".tsv", 11), ("xlsm", ".xlsm", 13)]
    if _has("pyarrow", "fastparquet"):
        specs.append(("parquet", ".parquet", 14))
    else:
        WARN.append("pyarrow 가 없어 parquet 폴더를 만들지 못했습니다 "
                    "(pip install pyarrow 후 재실행하면 생성됩니다).")
    if _has("xlwt"):
        specs.append(("xls", ".xls", 15))
        if not _has("xlrd"):
            WARN.append("xls 폴더는 만들었지만 xlrd 가 없어 검사기가 읽지 못합니다 "
                        "(pip install xlrd).")
    else:
        WARN.append("xlwt 가 없어 xls 폴더를 만들지 못했습니다 (pip install xlwt xlrd).")

    for k, (folder, ext, seed) in enumerate(specs):
        id_base = 100000 * (k + 1)
        train = _table(seed, 200, id_base)
        new = _table(seed + 500, 40, id_base + 90000)
        test = _plant_rows(train, new, list(range(20, 25)), [60, 61, 62])
        _write_table(train, os.path.join(tr(root, folder), "train_main" + ext))
        _write_table(test, os.path.join(te(root, folder), "test_main" + ext))
        expect(folder, "tabular", exact=5, near=3)

    make_xlsx(root)


def make_xlsx(root):
    """xlsx — 시트가 여러 개인 경우까지 확인한다 (완전일치 7건, 근사중복 3건)."""
    folder, id_base = "xlsx", 900000
    a = _table(12, 200, id_base)                  # 시트 "학습A"
    b = _table(112, 50, id_base + 50000)          # 시트 "학습B"
    new = _table(512, 40, id_base + 90000)
    test = _plant_rows(a, new, list(range(20, 25)), [60, 61, 62])
    test = pd.concat([test, b.iloc[[5, 6]]], ignore_index=True)   # 다른 시트에서 2건

    with pd.ExcelWriter(os.path.join(tr(root, folder), "train_main.xlsx")) as w:
        a.to_excel(w, sheet_name="학습A", index=False)
        b.to_excel(w, sheet_name="학습B", index=False)
    test.to_excel(os.path.join(te(root, folder), "test_main.xlsx"), index=False)
    expect(folder, "tabular", exact=7, near=3)


# ─────────────────────────────────────────────────────────── 이미지

# (폴더, 확장자, 저장옵션, 재압축옵션)
#   재압축옵션이 None 이면 "픽셀은 같은데 바이트만 다른" 파일을 만들 수 없는 포맷.
IMAGE_SPECS = [
    ("png",  ".png",  dict(compress_level=6), dict(compress_level=1)),
    ("jpg",  ".jpg",  dict(quality=92), None),
    ("jpeg", ".jpeg", dict(quality=92), None),
    ("bmp",  ".bmp",  dict(), None),
    ("gif",  ".gif",  dict(), None),
    ("tif",  ".tif",  dict(), dict(compression="tiff_lzw")),
    ("tiff", ".tiff", dict(), dict(compression="tiff_lzw")),
    ("webp", ".webp", dict(lossless=True, method=4), dict(lossless=True, method=0)),
    ("ppm",  ".ppm",  dict(), None),
]
N_TRAIN_IMG = 8
IMG_EXACT_SRC, IMG_NEAR_SRC = 3, 5


def _synth(Image, ImageDraw, seed, size=128):
    """도형이 무작위로 얹힌 128x128 합성 이미지. 시드가 다르면 충분히 달라진다."""
    rng = np.random.RandomState(seed)
    base = (rng.rand(8, 8, 3) * 255).astype("uint8")
    im = Image.fromarray(base).resize((size, size), Image.BILINEAR)
    d = ImageDraw.Draw(im)
    for _ in range(6):
        x, y = rng.randint(0, 100, 2)
        w, h = rng.randint(10, 40, 2)
        col = tuple(int(c) for c in rng.randint(0, 256, 3))
        (d.rectangle if rng.rand() < 0.5 else d.ellipse)([x, y, x + w, y + h], fill=col)
    return im


def _save_img(Image, im, path, kw):
    """GIF 는 팔레트 이미지로 저장해야 포맷 특성이 살아난다."""
    if path.lower().endswith(".gif"):
        im = im.convert("P", palette=Image.ADAPTIVE)
    im.save(path, **kw)


def make_images(root):
    try:
        from PIL import Image, ImageDraw
    except Exception:
        WARN.append("Pillow 가 없어 이미지 폴더를 만들지 못했습니다.")
        return

    for k, (folder, ext, kw, rekw) in enumerate(IMAGE_SPECS):
        seed_base = 1000 + 100 * k          # 폴더마다 다른 시드 → 폴더 간 내용 겹침 없음
        trd, ted = tr(root, folder), te(root, folder)
        for i in range(N_TRAIN_IMG):
            _save_img(Image, _synth(Image, ImageDraw, seed_base + i),
                      os.path.join(trd, "tr_%02d%s" % (i, ext)), kw)
        for i in range(3):
            _save_img(Image, _synth(Image, ImageDraw, seed_base + 50 + i),
                      os.path.join(ted, "new_%02d%s" % (i, ext)), kw)

        src = os.path.join(trd, "tr_%02d%s" % (IMG_EXACT_SRC, ext))
        # ① 완전일치: 바이트 복사 → 이미지 검사와 파일 단위 검사 양쪽에서 잡힌다
        shutil.copy(src, os.path.join(ted, "exact_bytecopy_of_tr%02d%s" % (IMG_EXACT_SRC, ext)))
        n_exact = 1
        # ② 완전일치: 픽셀은 같고 바이트만 다르게 재압축
        #    → SHA-256(파일 단위)으로는 못 잡고 이미지 검사만 잡아내는 핵심 케이스
        if rekw is not None:
            with Image.open(src) as t:
                t.load()
                t.save(os.path.join(ted, "exact_recompressed_of_tr%02d%s"
                                    % (IMG_EXACT_SRC, ext)), **rekw)
            n_exact += 1
        # ③ 근사중복: 1.5배 확대 후 재저장
        nsrc = os.path.join(trd, "tr_%02d%s" % (IMG_NEAR_SRC, ext))
        with Image.open(nsrc) as t:
            t.load()
            _save_img(Image, t.convert("RGB").resize((192, 192), Image.BILINEAR),
                      os.path.join(ted, "near_resized_of_tr%02d%s" % (IMG_NEAR_SRC, ext)), kw)

        expect(folder, "image", exact=n_exact, near=1)
        _selfcheck_images(Image, folder, trd, ted, ext, n_exact)


def _selfcheck_images(Image, folder, trd, ted, ext, n_exact):
    """심어둔 중복이 실제로 기본 임계값(해밍 5)에 걸리는지 확인."""
    trh = {i: image_hashes(Image, os.path.join(trd, "tr_%02d%s" % (i, ext)))
           for i in range(N_TRAIN_IMG)}
    mn = min(bin(trh[a][1] ^ trh[b][1]).count("1") for a in trh for b in trh if a < b)
    if mn <= 5:
        WARN.append("[%s] 학습 이미지끼리 해밍거리가 %d 로 가까워 오탐이 날 수 있습니다." % (folder, mn))

    px_ok = 0
    for name in sorted(os.listdir(ted)):
        px, bits, _ = image_hashes(Image, os.path.join(ted, name))
        if name.startswith("exact_"):
            if px == trh[IMG_EXACT_SRC][0]:
                px_ok += 1
            else:
                WARN.append("[%s] %s 의 픽셀 해시가 원본과 달라 완전일치로 잡히지 않습니다."
                            % (folder, name))
        elif name.startswith("near_"):
            d = bin(bits ^ trh[IMG_NEAR_SRC][1]).count("1")
            if px == trh[IMG_NEAR_SRC][0]:
                WARN.append("[%s] %s 가 픽셀까지 동일해 근사중복이 아니라 완전일치가 됩니다."
                            % (folder, name))
            elif d > 5:
                WARN.append("[%s] %s 의 해밍거리가 %d 로 임계값 5를 넘습니다." % (folder, name, d))
        else:
            best = min(bin(bits ^ trh[i][1]).count("1") for i in trh)
            if best <= 5 or px in {v[0] for v in trh.values()}:
                WARN.append("[%s] %s 는 중복이 아니어야 하는데 학습 이미지와 해밍거리 %d 입니다."
                            % (folder, name, best))
    if px_ok != n_exact:
        WARN.append("[%s] 완전일치 이미지 %d건을 의도했으나 %d건만 성립합니다."
                    % (folder, n_exact, px_ok))


# ─────────────────────────────────────────────────────────── 텍스트

_DOMAIN = ["의료영상", "금융거래", "제조공정", "교통흐름", "농작물생육", "음성명령", "보안로그",
           "전력수요", "물류배송", "고객상담", "위성사진", "지진파형", "수질측정", "축산질병",
           "산업안전", "폐기물분류", "실내소음", "지하매설물", "산불감시", "어획량"]
_ARTIFACT = ["학습데이터셋", "시험데이터셋", "검증계획서", "라벨링지침", "품질보고서", "성능시험표",
             "전처리기록", "표본설계서", "오류사례집", "메타데이터목록", "반출승인서", "결함이력"]
_METRIC = ["정확도", "재현율", "정밀도", "종합점수", "오탐률", "미탐률", "일관성지수", "결측률",
           "중복률", "편향도", "해상도편차", "라벨불일치율"]
_ACTION = ["추가수집", "재라벨링", "표본재분할", "임계값조정", "규칙보완", "이상치제거",
           "교차검증확대", "지침개정", "재시험", "원인분석", "익명화강화", "출처재확인"]
_ORG = ["품질관리팀", "데이터운영팀", "시험평가팀", "현업부서", "외부감리인", "표준화분과",
        "정보보호담당", "사업관리자"]

_TPL = [
    "{domain} 관련 {artifact}를 점검한 결과 {metric}이 기준치를 벗어나 {action}이 필요하다.",
    "{org}은 {domain} {artifact}의 {metric} 항목을 재산출하고 {action} 계획을 회신하였다.",
    "{domain} 표본에서 {metric}이 특히 낮게 관측되어 {org}과 협의해 {action}을 우선 수행한다.",
    "{artifact} 검토회의에서는 {domain} 데이터의 {metric} 산출기준을 명확히 하고 {action} 시점을 확정했다.",
    "{action} 이후 {domain} {artifact}의 {metric}을 다시 측정하여 {org}에 보고하도록 한다.",
    "{org}이 제출한 {domain} {artifact}에는 {metric} 산출 근거가 빠져 있어 {action}을 요청했다.",
    "{domain} 수집 단계에서 누락이 발견되었으므로 {artifact}의 {metric}을 {action}과 함께 재정리한다.",
    "{metric} 기준을 상향하면 {domain} {artifact}의 {action} 물량이 늘어난다는 {org} 의견이 있었다.",
]

# 문장 수가 적으면 단어 한 곳만 바꿔도 Jaccard 가 0.80 밑으로 떨어져
# 근사중복본이 탐지되지 않는다. 6문장이면 수정 한 곳의 영향도가 충분히 작다.
DOC_SENTENCES = 6
N_TRAIN_DOCS = 12
DOC_EXACT_SRC, DOC_NEAR_SRC = 3, 7
TEXT_SPECS = [("txt", ".txt"), ("text", ".text"), ("md", ".md")]


def gen_doc(folder, idx):
    """폴더·번호마다 어휘가 거의 겹치지 않는 문서.

    문장 골격은 공유하지만 빈칸이 모두 달라지므로 3단어 셰이글이 거의 겹치지
    않는다(같은 문장을 번호만 바꿔 찍으면 Jaccard 0.86 수준으로 서로 중복이 된다).
    """
    rng = np.random.RandomState(int(hashlib.md5(
        ("dlc|%s|%d" % (folder, idx)).encode("utf-8")).hexdigest()[:8], 16))
    lines = []
    for t in rng.permutation(len(_TPL))[:DOC_SENTENCES]:
        lines.append(_TPL[t].format(
            domain=_DOMAIN[rng.randint(len(_DOMAIN))],
            artifact=_ARTIFACT[rng.randint(len(_ARTIFACT))],
            metric=_METRIC[rng.randint(len(_METRIC))],
            action=_ACTION[rng.randint(len(_ACTION))],
            org=_ORG[rng.randint(len(_ORG))]))
    return " ".join(lines)


def near_doc(text):
    """단어 한 곳을 바꾸고 짧은 문장을 덧붙인 근사중복본 (Jaccard 0.80 이상)."""
    out = text
    for a, b in (("점검한", "확인한"), ("재산출하고", "다시 산출하고"),
                 ("관측되어", "확인되어"), ("검토회의에서는", "검토 회의에서"),
                 ("보고하도록", "보고하게")):
        if a in out:
            out = out.replace(a, b, 1)
            break
    return out + " 본 문서는 재검토 대상으로 분류되었다."


def _md_head(kind, i):
    return "# %s %02d\n\n" % (kind, i)


def make_text(root):
    """txt / text / md — 문서 단위 완전일치 1건, 근사중복 1건."""
    for folder, ext in TEXT_SPECS:
        trd, ted = tr(root, folder), te(root, folder)
        docs = [gen_doc(folder, i) for i in range(N_TRAIN_DOCS)]
        head = (lambda kind, i: _md_head(kind, i)) if ext == ".md" else (lambda kind, i: "")
        for i, t in enumerate(docs):
            write_text(os.path.join(trd, "doc_%02d%s" % (i, ext)), head("검증용 표본 문서", i) + t)
        for i in range(3):
            write_text(os.path.join(ted, "new_%02d%s" % (i, ext)),
                       head("신규 시험 문서", i) + gen_doc(folder, 100 + i))
        write_text(os.path.join(ted, "exact_copy_of_doc%02d%s" % (DOC_EXACT_SRC, ext)),
                   head("검증용 표본 문서", DOC_EXACT_SRC) + docs[DOC_EXACT_SRC])
        write_text(os.path.join(ted, "near_variant_of_doc%02d%s" % (DOC_NEAR_SRC, ext)),
                   head("검증용 표본 문서", DOC_NEAR_SRC) + near_doc(docs[DOC_NEAR_SRC]))

        expect(folder, "text", exact=1, near=1)
        _selfcheck_text(folder, docs, [gen_doc(folder, 100 + i) for i in range(3)],
                        [near_doc(docs[DOC_NEAR_SRC])])


def _record(folder, idx, text):
    return {"doc_id": "%s-%03d" % (folder, idx), "label": idx % 3, "text": text}


def _flat(rec):
    """textcheck 가 JSON 객체를 문서 문자열로 평탄화하는 방식과 동일."""
    return json.dumps(rec, ensure_ascii=False, sort_keys=True)


def make_json(root):
    """json — 배열 JSON(원소 1개가 문서 1건)과 단일 객체 JSON 둘 다."""
    folder = "json"
    trd, ted = tr(root, folder), te(root, folder)
    recs = [_record(folder, i, gen_doc(folder, i)) for i in range(N_TRAIN_DOCS)]
    write_text(os.path.join(trd, "train_docs.json"),
               json.dumps(recs, ensure_ascii=False, indent=2))
    single = _record(folder, 900, gen_doc(folder, 900))
    write_text(os.path.join(trd, "train_single.json"),
               json.dumps(single, ensure_ascii=False, indent=2))

    news = [_record(folder, 100 + i, gen_doc(folder, 100 + i)) for i in range(3)]
    exact = dict(recs[DOC_EXACT_SRC])
    near = dict(recs[DOC_NEAR_SRC])
    near["text"] = near_doc(near["text"])
    write_text(os.path.join(ted, "test_docs.json"),
               json.dumps(news + [exact, near], ensure_ascii=False, indent=2))
    # 들여쓰기를 없애도 평탄화 결과는 같으므로 문서 완전일치로 잡혀야 한다
    write_text(os.path.join(ted, "test_single.json"),
               json.dumps(single, ensure_ascii=False))

    expect(folder, "text", exact=2, near=1)
    _selfcheck_text(folder, [_flat(r) for r in recs] + [_flat(single)],
                    [_flat(r) for r in news], [_flat(near)])


def make_jsonl(root):
    """jsonl / ndjson — 한 줄이 문서 1건."""
    for folder, ext in (("jsonl", ".jsonl"), ("ndjson", ".ndjson")):
        trd, ted = tr(root, folder), te(root, folder)
        recs = [_record(folder, i, gen_doc(folder, i)) for i in range(N_TRAIN_DOCS)]
        write_text(os.path.join(trd, "train_docs" + ext),
                   "".join(_flat(r) + "\n" for r in recs))

        news = [_record(folder, 100 + i, gen_doc(folder, 100 + i)) for i in range(3)]
        exact = dict(recs[DOC_EXACT_SRC])
        near = dict(recs[DOC_NEAR_SRC])
        near["text"] = near_doc(near["text"])
        write_text(os.path.join(ted, "test_docs" + ext),
                   "".join(_flat(r) + "\n" for r in news + [exact, near]))

        expect(folder, "text", exact=1, near=1)
        _selfcheck_text(folder, [_flat(r) for r in recs],
                        [_flat(r) for r in news], [_flat(near)])


def _sig(text):
    return signature(shingles(norm_newlines(text)))


def _selfcheck_text(folder, train_docs, new_docs, near_docs, thr=0.80):
    """학습 문서끼리·신규 문서는 임계값 미만, 근사중복본은 임계값 이상이어야 한다."""
    sigs = [_sig(t) for t in train_docs]
    for i in range(len(sigs)):
        for j in range(i + 1, len(sigs)):
            s = float((sigs[i] == sigs[j]).mean())
            if s >= thr:
                WARN.append("[%s] 학습 문서 %d·%d 의 유사도가 %.2f 로 서로 중복입니다."
                            % (folder, i, j, s))
    for k, t in enumerate(new_docs):
        best = max(float((s == _sig(t)).mean()) for s in sigs)
        if best >= thr:
            WARN.append("[%s] 신규 문서 %d 가 학습 문서와 유사도 %.2f 로 오탐 대상입니다."
                        % (folder, k, best))
    hashes = {h_text(norm_newlines(t)) for t in train_docs}
    for k, t in enumerate(near_docs):
        best = max(float((s == _sig(t)).mean()) for s in sigs)
        if h_text(norm_newlines(t)) in hashes:
            WARN.append("[%s] 근사중복본 %d 이 완전일치로 잡힙니다." % (folder, k))
        elif best < thr:
            WARN.append("[%s] 근사중복본 %d 의 유사도가 %.2f 로 임계값 %.2f 미만입니다."
                        % (folder, k, best, thr))


# ─────────────────────────────────────────────────────────── 배열

ARR_EXACT_SRC, ARR_NEAR_SRC = 7, 50


def _arrays(seed):
    """(학습X, 학습y, 시험X, 시험y). 시험X 3번=완전일치, 9번=근사중복."""
    rng = np.random.RandomState(seed)
    xtr = rng.rand(60, 8)
    ytr = rng.randint(0, 3, 60)
    xte = rng.rand(12, 8)
    xte[3] = xtr[ARR_EXACT_SRC]                    # 바이트까지 동일 → 완전일치
    xte[9] = xtr[ARR_NEAR_SRC] + 1e-7              # 4자리 반올림 시 동일 → 근사중복
    yte = rng.randint(0, 3, 12)
    return xtr, ytr, xte, yte


def _selfcheck_arrays(folder, xtr, xte):
    exact = sum(1 for r in xte if any(np.array_equal(r, t) for t in xtr))
    rtr = {np.round(t, 4).tobytes() for t in xtr}
    near = sum(1 for r in xte if np.round(r, 4).tobytes() in rtr
               and not any(np.array_equal(r, t) for t in xtr))
    if (exact, near) != (1, 1):
        WARN.append("[%s] 배열 완전일치 1·근사중복 1을 의도했으나 %d·%d 입니다."
                    % (folder, exact, near))


def make_arrays(root):
    # npy — 1차원 라벨 벡터가 검사에서 제외되는지도 함께 확인한다
    xtr, ytr, xte, yte = _arrays(21)
    np.save(os.path.join(tr(root, "npy"), "X_train.npy"), xtr)
    np.save(os.path.join(tr(root, "npy"), "y_train.npy"), ytr)
    np.save(os.path.join(te(root, "npy"), "X_test.npy"), xte)
    np.save(os.path.join(te(root, "npy"), "y_test.npy"), yte)
    expect("npy", "array", exact=1, near=1)
    _selfcheck_arrays("npy", xtr, xte)

    # npz — 한 파일에 배열 여러 개
    xtr, ytr, xte, yte = _arrays(22)
    np.savez(os.path.join(tr(root, "npz"), "train_data.npz"), X=xtr, y=ytr)
    np.savez(os.path.join(te(root, "npz"), "test_data.npz"), X=xte, y=yte)
    expect("npz", "array", exact=1, near=1)
    _selfcheck_arrays("npz", xtr, xte)


# ─────────────────────────────────────────────────────────── PKL / PICKLE

def make_pickles(root):
    """PKL 내용에 따라 tabular / array 로 재분류되는 경로를 모두 태운다."""
    import pickle

    # pkl — DataFrame(표) + ndarray(배열)
    folder = "pkl"
    trd, ted = tr(root, folder), te(root, folder)
    train = _table(31, 200, 300000)
    new = _table(531, 40, 390000)
    test = _plant_rows(train, new, list(range(20, 25)), [60, 61, 62])
    train.to_pickle(os.path.join(trd, "train_table.pkl"))
    test.to_pickle(os.path.join(ted, "test_table.pkl"))
    expect(folder, "tabular", exact=5, near=3)

    xtr, ytr, xte, yte = _arrays(32)
    with open(os.path.join(trd, "train_array.pkl"), "wb") as f:
        pickle.dump(xtr, f)
    with open(os.path.join(ted, "test_array.pkl"), "wb") as f:
        pickle.dump(xte, f)
    expect(folder, "array", exact=1, near=1)
    _selfcheck_arrays(folder, xtr, xte)

    # pickle — dict(배열 묶음) + list of dict(레코드)
    folder = "pickle"
    trd, ted = tr(root, folder), te(root, folder)
    xtr, ytr, xte, yte = _arrays(33)
    with open(os.path.join(trd, "train_bundle.pickle"), "wb") as f:
        pickle.dump({"X": xtr, "y": ytr}, f)
    with open(os.path.join(ted, "test_bundle.pickle"), "wb") as f:
        pickle.dump({"X": xte, "y": yte}, f)
    expect(folder, "array", exact=1, near=1)
    _selfcheck_arrays(folder, xtr, xte)

    rtr = _table(34, 100, 400000)
    rnew = _table(534, 20, 490000)
    rtest = pd.concat([rnew, rtr.iloc[[10, 11, 12, 13]]], ignore_index=True)
    with open(os.path.join(trd, "train_records.pickle"), "wb") as f:
        pickle.dump(rtr.to_dict("records"), f)
    with open(os.path.join(ted, "test_records.pickle"), "wb") as f:
        pickle.dump(rtest.to_dict("records"), f)
    expect(folder, "tabular", exact=4)


# ─────────────────────────────────────────────────────────── 미지원 확장자

def make_other_ext(root):
    """지원 목록에 없는 확장자 — 파일 단위 검사만 적용되고 오류 없이 지나가야 한다."""
    folder = "other_ext"
    trd, ted = tr(root, folder), te(root, folder)
    write_text(os.path.join(trd, "runtime.log"), "2026-08-27 10:00:00 학습 시작\n" * 20)
    with open(os.path.join(trd, "weights.dat"), "wb") as f:
        f.write(np.random.RandomState(41).bytes(4096))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("inside.txt", "압축파일 안의 내용")
    with open(os.path.join(trd, "bundle.zip"), "wb") as f:
        f.write(buf.getvalue())

    shutil.copy(os.path.join(trd, "runtime.log"), os.path.join(ted, "runtime_copy.log"))
    with open(os.path.join(ted, "weights.dat"), "wb") as f:
        f.write(np.random.RandomState(42).bytes(4096))


# ─────────────────────────────────────────────────────────── 예외/경계

def make_edge_cases(root):
    """인코딩·개행·BOM 만 다른 같은 내용, 손상 파일, 빈 파일."""
    folder = "edge_cases"
    trd, ted = tr(root, folder), te(root, folder)
    a, b, c = gen_doc(folder, 1), gen_doc(folder, 2), gen_doc(folder, 3)

    write_text(os.path.join(trd, "enc_utf8.txt"), a)
    write_text(os.path.join(ted, "enc_cp949.txt"), a, encoding="cp949")        # 인코딩만 다름
    write_text(os.path.join(trd, "nl_lf.txt"), b, newline="\n")
    write_text(os.path.join(ted, "nl_crlf.txt"), b, newline="\r\n")            # 개행만 다름
    write_text(os.path.join(trd, "bom_none.txt"), c)
    write_text(os.path.join(ted, "bom_utf8sig.txt"), c, encoding="utf-8-sig")  # BOM만 다름
    expect(folder, "text", exact=3)

    # 빈 파일(시험 쪽에만) — 중복으로 잡히지 않아야 한다
    open(os.path.join(ted, "empty.txt"), "wb").close()

    # 손상 파일 — 오류 목록에 기록되고 검사가 중단되지 않아야 한다
    try:
        from PIL import Image, ImageDraw
        ok = os.path.join(trd, "img_ok.png")
        _synth(Image, ImageDraw, 4100).save(ok)
        with open(ok, "rb") as f:
            head = f.read(220)
        with open(os.path.join(ted, "img_truncated.png"), "wb") as f:
            f.write(head)
    except Exception:
        WARN.append("[edge_cases] Pillow 가 없어 손상 이미지 케이스를 만들지 못했습니다.")
    write_text(os.path.join(ted, "broken_quotes.csv"),
               'id,name,memo\n1,"열린 따옴표,메모\n2,정상,두번째 행\n')

    _selfcheck_text(folder, [a, b, c], [], [])


# ─────────────────────────────────────────────────────────── 기대결과 산출

def count_file_dups(root):
    """폴더별로 학습·시험에 바이트까지 같은 파일이 몇 개인지 센다."""
    for folder in EXPECT_FOLDERS:
        trd = os.path.join(root, "train", folder)
        ted = os.path.join(root, "test", folder)
        if not (os.path.isdir(trd) and os.path.isdir(ted)):
            continue
        train_hashes = {sha256(os.path.join(trd, n)) for n in os.listdir(trd)}
        n = sum(1 for name in os.listdir(ted)
                if sha256(os.path.join(ted, name)) in train_hashes)
        if n:
            expect(folder, "file", exact=n)


def totals():
    agg = {}
    for cats in EXPECT.values():
        for cat, v in cats.items():
            d = agg.setdefault(cat, {"exact": 0, "near": 0})
            d["exact"] += v["exact"]
            d["near"] += v["near"]
    return agg


def write_expected(root):
    agg = totals()
    with open(os.path.join(root, "expected.json"), "w", encoding="utf-8") as f:
        json.dump({"version": 1, "folders": EXPECT, "total": agg, "warnings": WARN},
                  f, ensure_ascii=False, indent=2)

    lines = ["# 포맷별 기대 결과", "",
             "기본 옵션(완전일치+근사중복, 소수 4자리, 텍스트 유사도 0.80, 이미지 해밍 5)에서",
             "아래 값이 나와야 정상이다.", "",
             "```bash",
             "python tests/verify_format_samples.py \"%s\"" % root,
             "```", "",
             "## 폴더별", "",
             "| 폴더 | 카테고리 | 완전일치 | 근사중복 |", "|---|---|---:|---:|"]
    for folder in sorted(EXPECT):
        cats = EXPECT[folder]
        if not cats:
            lines.append("| %s | (중복 없음 — 오류처리·미지원 확장자 확인용) | 0 | 0 |" % folder)
            continue
        for cat in ("file", "tabular", "image", "text", "array"):
            if cat in cats:
                v = cats[cat]
                lines.append("| %s | %s | %d | %d |"
                             % (folder, CAT_LABEL[cat], v["exact"], v["near"]))
    lines += ["", "## 전체 (train ↔ test 를 통째로 검사할 때)", "",
              "| 카테고리 | 완전일치 | 근사중복 |", "|---|---:|---:|"]
    for cat in ("file", "tabular", "image", "text", "array"):
        if cat in agg:
            lines.append("| %s | %d | %d |" % (CAT_LABEL[cat], agg[cat]["exact"], agg[cat]["near"]))
    lines += ["", "## 심어둔 중복의 종류", "",
              "- `exact_bytecopy_*` : 바이트까지 같은 복사본 → 파일 단위 + 카테고리 검사 양쪽에서 잡힘",
              "- `exact_recompressed_*` : 픽셀은 같고 바이트만 다름 → SHA-256으로는 못 잡고 이미지 검사만 잡음",
              "  (png / tif / tiff / webp 에만 존재. jpg·jpeg·bmp·gif·ppm 은 같은 픽셀이면 바이트도 같아짐)",
              "- `near_resized_*` : 1.5배 확대 재저장 → dHash 해밍거리 5 이내",
              "- `exact_copy_of_doc*` : 문서 내용 동일",
              "- `near_variant_of_doc*` : 단어 하나 수정 + 문장 하나 추가 → Jaccard 0.80 이상",
              "- 표 근사중복 : f1 을 소수 7째 자리에서 흔들고 name 을 소문자·공백중복으로 변형",
              "- 배열 근사중복 : 값에 1e-7 을 더해 소수 4자리 반올림 시 동일",
              "- `y_*.npy` 등 1차원 라벨 벡터 : 검사 제외 대상(리포트 비고에 안내가 떠야 함)",
              "- `edge_cases` : 인코딩(cp949)·개행(CRLF)·BOM 만 다른 같은 문서 3건 →",
              "  파일 단위로는 다르지만 문서 단위 완전일치로 잡혀야 함",
              "- `edge_cases/img_truncated.png`, `broken_quotes.csv`, `empty.txt` :",
              "  중복이 아니라 오류 목록에 기록되고 검사가 계속되어야 하는 케이스",
              "- `other_ext` : 지원하지 않는 확장자(.log/.dat/.zip) → 파일 단위 검사만 적용",
              ""]
    if WARN:
        lines += ["## 생성 시 경고", ""] + ["- " + w for w in WARN] + [""]
    with open(os.path.join(root, "기대결과.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ─────────────────────────────────────────────────────────── 진입점

def main(argv=None):
    p = argparse.ArgumentParser(description="포맷별 검증용 샘플 데이터 생성")
    p.add_argument("root", nargs="?", default=os.path.join(os.getcwd(), "dlc_format_testdata"))
    p.add_argument("--force", action="store_true", help="기존 폴더를 지우고 다시 만든다")
    a = p.parse_args(argv)
    root = os.path.abspath(a.root)

    if os.path.isdir(root) and os.listdir(root):
        if os.path.exists(os.path.join(root, MARKER)) or a.force:
            rmtree_retry(root)
        else:
            print("중단: %s 은 비어 있지 않고 이 스크립트가 만든 폴더도 아닙니다.\n"
                  "      다른 경로를 지정하거나 --force 를 주세요." % root, file=sys.stderr)
            return 2
    os.makedirs(root, exist_ok=True)

    make_tabular(root)
    make_images(root)
    make_text(root)
    make_json(root)
    make_jsonl(root)
    make_arrays(root)
    make_pickles(root)
    make_other_ext(root)
    make_edge_cases(root)

    EXPECT_FOLDERS[:] = sorted(set(os.listdir(os.path.join(root, "train"))) |
                               set(os.listdir(os.path.join(root, "test"))))
    for f in EXPECT_FOLDERS:
        EXPECT.setdefault(f, {})
    count_file_dups(root)
    write_expected(root)

    n_files = sum(len(fs) for _, _, fs in os.walk(root))
    with open(os.path.join(root, MARKER), "w", encoding="utf-8") as f:
        json.dump({"generator": "tests/make_format_samples.py", "folders": EXPECT_FOLDERS},
                  f, ensure_ascii=False, indent=2)

    print("생성 완료: %s" % root)
    print("포맷 폴더 %d개 / 파일 %d개\n" % (len(EXPECT_FOLDERS), n_files))
    print("%-12s %-18s %8s %8s" % ("폴더", "카테고리", "완전일치", "근사중복"))
    for folder in sorted(EXPECT):
        for cat in ("file", "tabular", "image", "text", "array"):
            v = EXPECT[folder].get(cat)
            if v:
                print("%-12s %-18s %8d %8d" % (folder, CAT_LABEL[cat], v["exact"], v["near"]))
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
