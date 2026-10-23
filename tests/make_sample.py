# -*- coding: utf-8 -*-
"""검증용 합성 데이터 생성 (의도적으로 중복을 심는다)."""
import os
import shutil
import sys

import numpy as np
import pandas as pd

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/dlc_sample"
TR = os.path.join(ROOT, "train")
TE = os.path.join(ROOT, "test")

EXPECT = {}


def reset():
    shutil.rmtree(ROOT, ignore_errors=True)
    for d in (TR, TE, os.path.join(TR, "docs"), os.path.join(TE, "docs"),
              os.path.join(TR, "img"), os.path.join(TE, "img")):
        os.makedirs(d, exist_ok=True)


def make_tabular():
    rng = np.random.RandomState(0)
    n = 1000
    df = pd.DataFrame({
        "id": np.arange(n),
        "name": ["샘플 %d" % i for i in range(n)],
        "f1": rng.rand(n).round(6),
        "f2": rng.randint(0, 100, n),
        "label": rng.randint(0, 2, n),
    })
    df.to_csv(os.path.join(TR, "train_main.csv"), index=False, encoding="utf-8-sig")

    test = pd.DataFrame({
        "id": np.arange(10000, 10200),
        "name": ["시험 %d" % i for i in range(200)],
        "f1": rng.rand(200).round(6),
        "f2": rng.randint(0, 100, 200),
        "label": rng.randint(0, 2, 200),
    })
    # 완전 일치 10건
    exact = df.iloc[100:110].copy()
    # 근사 중복 5건: f1 소수점 6자리 → 미세 변동, 이름 대소문자/공백 변형
    near = df.iloc[500:505].copy()
    near["f1"] = near["f1"] + 1e-7
    near["name"] = near["name"].str.upper() + "  "
    out = pd.concat([test, exact, near], ignore_index=True)
    out.to_csv(os.path.join(TE, "test_main.csv"), index=False, encoding="utf-8-sig")
    EXPECT["tabular_exact"] = 10
    EXPECT["tabular_near"] = 5

    # PKL DataFrame (완전 일치 3건)
    dtr = df.iloc[:200].reset_index(drop=True)
    dtr.to_pickle(os.path.join(TR, "train_extra.pkl"))
    dte = pd.concat([test.iloc[:20], df.iloc[10:13]], ignore_index=True)
    dte.to_pickle(os.path.join(TE, "test_extra.pkl"))
    EXPECT["tabular_exact"] += 3

    # Excel (완전 일치 2건)
    df.iloc[:50].to_excel(os.path.join(TR, "train_sheet.xlsx"), index=False)
    pd.concat([test.iloc[:5], df.iloc[20:22]], ignore_index=True).to_excel(
        os.path.join(TE, "test_sheet.xlsx"), index=False)
    EXPECT["tabular_exact"] += 2


def make_arrays():
    rng = np.random.RandomState(1)
    xtr = rng.rand(100, 5)
    np.save(os.path.join(TR, "x_train.npy"), xtr)
    xte = rng.rand(20, 5)
    xte[3] = xtr[7]                      # 완전 일치
    xte[9] = xtr[50] + 1e-7              # 근사 중복
    np.save(os.path.join(TE, "x_test.npy"), xte)
    EXPECT["array_exact"] = 1
    EXPECT["array_near"] = 1


def make_text():
    base = ("인공지능 모델의 성능시험에서 학습 데이터와 시험 데이터가 중복되면 "
            "시험 결과가 과대평가될 수 있으므로 사전에 중복성을 반드시 확인해야 한다. "
            "문서 번호 %d 에 대한 설명이다.")
    for i in range(20):
        with open(os.path.join(TR, "docs", "doc_%02d.txt" % i), "w", encoding="utf-8") as f:
            f.write(base % i)
    # 시험셋: 신규 3건
    for i in range(3):
        with open(os.path.join(TE, "docs", "new_%02d.txt" % i), "w", encoding="utf-8") as f:
            f.write("완전히 새로운 시험 문서 %d 입니다. 서로 다른 내용을 담고 있으며 중복이 아닙니다. "
                    "임의 토큰 %s" % (i, "가나다라마바사"[i:i + 3] * 5))
    # 완전 일치 1건
    with open(os.path.join(TE, "docs", "copy_of_doc05.txt"), "w", encoding="utf-8") as f:
        f.write(base % 5)
    # 근사 중복 1건 (일부 단어 변경)
    with open(os.path.join(TE, "docs", "similar_to_doc07.txt"), "w", encoding="utf-8") as f:
        f.write((base % 7).replace("과대평가될", "부풀려질").replace("반드시", ""))
    EXPECT["text_exact"] = 1
    EXPECT["text_near"] = 1

    # JSONL (완전 일치 2건)
    import json
    recs = [{"text": "질의 %d 에 대한 응답 문장입니다." % i, "label": i % 3} for i in range(30)]
    with open(os.path.join(TR, "qa_train.jsonl"), "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(TE, "qa_test.jsonl"), "w", encoding="utf-8") as f:
        for r in [{"text": "새로운 질의 %d 문장입니다." % i, "label": 0} for i in range(5)]:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        for r in recs[3:5]:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    EXPECT["text_exact"] += 2


def make_images():
    try:
        from PIL import Image
    except Exception:
        print("Pillow 없음 → 이미지 샘플 생략")
        return
    from PIL import ImageDraw

    def synth(seed):
        rng = np.random.RandomState(seed)
        base = (rng.rand(8, 8, 3) * 255).astype("uint8")
        im = Image.fromarray(base).resize((128, 128), Image.BILINEAR)
        d = ImageDraw.Draw(im)
        for _ in range(6):
            x, y = rng.randint(0, 100, 2)
            w, h = rng.randint(10, 40, 2)
            col = tuple(int(c) for c in rng.randint(0, 256, 3))
            if rng.rand() < 0.5:
                d.rectangle([x, y, x + w, y + h], fill=col)
            else:
                d.ellipse([x, y, x + w, y + h], fill=col)
        return im

    imgs = []
    for i in range(10):
        im = synth(100 + i)
        im.save(os.path.join(TR, "img", "tr_%02d.png" % i))
        imgs.append(im)
    for i in range(3):
        synth(900 + i).save(os.path.join(TE, "img", "te_%02d.png" % i))
    # 완전 일치(픽셀 동일, 파일명 다름)
    imgs[4].save(os.path.join(TE, "img", "copy_of_tr04.png"))
    # 근사 중복(2배 확대 후 재저장)
    imgs[6].resize((200, 200)).save(os.path.join(TE, "img", "resized_tr06.png"))
    EXPECT["image_exact"] = 1
    EXPECT["image_near"] = 1


def make_same_file():
    shutil.copy(os.path.join(TR, "x_train.npy"), os.path.join(TE, "x_train_COPY.npy"))
    EXPECT["file_exact"] = 1
    # 파일 단위 동일이면 배열 샘플 100건도 모두 중복으로 잡힘
    EXPECT["array_exact"] = EXPECT.get("array_exact", 0) + 100
    EXPECT["array_near"] = EXPECT.get("array_near", 0)


if __name__ == "__main__":
    reset()
    make_tabular()
    make_arrays()
    make_text()
    make_images()
    make_same_file()
    print("생성 완료:", ROOT)
    for k in sorted(EXPECT):
        print("  기대 %-16s %d" % (k, EXPECT[k]))
