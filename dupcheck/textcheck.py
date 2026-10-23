# -*- coding: utf-8 -*-
"""텍스트/JSON/JSONL 문서 단위 중복 검사.

- 완전 일치: 개행/BOM 정규화 후 해시
- 근사 중복: MinHash(128 perm) + LSH 밴딩으로 후보 추출 후 Jaccard 추정
"""
import json
import os

import numpy as np

from .config import CAT_TEXT, CATEGORY_LABELS
from .models import CategoryResult, DupItem
from .util import h_text, norm_text, norm_newlines, read_text_file, rel, safe_str

PERMS = 128
BANDS = 32          # rows = 4 → 후보 임계 ≈ 0.5
ROWS = PERMS // BANDS
SHINGLE_WORDS = 3
SHINGLE_CHARS = 4
MAX_DOC_CHARS = 200_000

# 순열 해시 시드. (a*x+b) mod p 형태의 선형 해시는 x 와 a 가 p 에 비해
# 작을 때 순열로서 심하게 편향되므로(추정 표준편차 0.3 수준), 시드별
# splitmix64 믹싱 함수를 사용한다.
_rng = np.random.RandomState(20250820)
_SEEDS = _rng.randint(0, 1 << 63, size=PERMS, dtype=np.int64).astype(np.uint64)

_M1 = np.uint64(0xBF58476D1CE4E5B9)
_M2 = np.uint64(0x94D049BB133111EB)
_S30 = np.uint64(30)
_S27 = np.uint64(27)
_S31 = np.uint64(31)
_GAMMA = np.uint64(0x9E3779B97F4A7C15)


def _splitmix(z):
    """splitmix64 finalizer (uint64 배열, 오버플로는 wrap-around)."""
    z = (z + _GAMMA).astype(np.uint64)
    z = (z ^ (z >> _S30)) * _M1
    z = (z ^ (z >> _S27)) * _M2
    return z ^ (z >> _S31)


def iter_documents(path, root):
    """(doc_id, text) 제너레이터."""
    ext = os.path.splitext(path)[1].lower()
    label = rel(path, root)
    if ext in (".jsonl", ".ndjson"):
        text = read_text_file(path)
        for i, line in enumerate(text.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                yield "%s %d번째" % (label, i + 1), _flatten_json(obj)
            except Exception:
                yield "%s %d번째" % (label, i + 1), line
    elif ext == ".json":
        text = read_text_file(path)
        try:
            obj = json.loads(text)
        except Exception:
            yield label, text
            return
        if isinstance(obj, list) and len(obj) > 1:
            for i, el in enumerate(obj):
                yield "%s [%d]" % (label, i), _flatten_json(el)
        else:
            yield label, _flatten_json(obj)
    else:
        yield label, read_text_file(path)


def _flatten_json(obj):
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (int, float, bool)) or obj is None:
        return str(obj)
    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(obj)


def shingles(text):
    t = norm_text(text)[:MAX_DOC_CHARS]
    words = t.split()
    if len(words) >= SHINGLE_WORDS + 1:
        grams = [" ".join(words[i:i + SHINGLE_WORDS]) for i in range(len(words) - SHINGLE_WORDS + 1)]
    else:
        s = t.replace(" ", "")
        if len(s) < SHINGLE_CHARS:
            grams = [s] if s else []
        else:
            grams = [s[i:i + SHINGLE_CHARS] for i in range(len(s) - SHINGLE_CHARS + 1)]
    if not grams:
        return np.empty(0, dtype=np.uint64)
    arr = np.array([int.from_bytes(h_text(g)[:8], "big") for g in set(grams)], dtype=np.uint64)
    return arr


def signature(sh):
    """MinHash 서명 (PERMS,) uint64."""
    if len(sh) == 0:
        return None
    with np.errstate(over="ignore"):
        hv = _splitmix(sh.reshape(-1, 1) ^ _SEEDS.reshape(1, -1))
    return hv.min(axis=0)


def band_keys(sig):
    out = []
    for b in range(BANDS):
        part = sig[b * ROWS:(b + 1) * ROWS].tobytes()
        out.append(h_text(str(b)) + part)
    return out


def run(ctx, cfg, train_files, test_files, train_root, test_root):
    res = CategoryResult(key=CAT_TEXT, label=CATEGORY_LABELS[CAT_TEXT], unit_name="문서")
    res.ran = True
    res.train_files = len(train_files)
    res.test_files = len(test_files)
    if not train_files or not test_files:
        if train_files or test_files:
            res.notes.append("한쪽 폴더에만 텍스트 파일이 있어 문서 단위 비교를 건너뜁니다.")
        return res

    exact_map = {}          # hash → doc_id
    sig_store = []          # (doc_id, sig)
    lsh = {}                # band key → [sig_index]

    for path in train_files:
        ctx.check()
        ctx.log("  [학습] %s" % rel(path, train_root))
        try:
            for doc_id, text in iter_documents(path, train_root):
                res.train_units += 1
                norm = norm_newlines(text)
                if cfg.exact:
                    exact_map.setdefault(h_text(norm), (doc_id, safe_str(norm, 300)))
                if cfg.near and len(norm_text(norm)) >= cfg.text_min_chars:
                    sig = signature(shingles(norm))
                    if sig is None:
                        continue
                    i = len(sig_store)
                    sig_store.append((doc_id, sig, safe_str(norm, 300)))
                    for k in band_keys(sig):
                        lsh.setdefault(k, []).append(i)
        except Exception as e:
            res.add_read_error("%s 읽기 실패: %s" % (rel(path, train_root), e))
        ctx.step()

    cap = cfg.max_samples_in_report
    for path in test_files:
        ctx.check()
        ctx.log("  [시험] %s" % rel(path, test_root))
        try:
            for doc_id, text in iter_documents(path, test_root):
                res.test_units += 1
                norm = norm_newlines(text)
                hit = exact_map.get(h_text(norm)) if cfg.exact else None
                if hit:
                    res.exact_units += 1
                    res.add_item(DupItem("exact", hit[0], doc_id, 1.0,
                                         safe_str(hit[1], 200), safe_str(norm, 200)), cap)
                    continue
                if not cfg.near or not sig_store:
                    continue
                if len(norm_text(norm)) < cfg.text_min_chars:
                    continue
                sig = signature(shingles(norm))
                if sig is None:
                    continue
                cand = set()
                for k in band_keys(sig):
                    cand.update(lsh.get(k, ()))
                best, best_sim = None, 0.0
                for i in cand:
                    sim = float((sig_store[i][1] == sig).mean())
                    if sim > best_sim:
                        best, best_sim = i, sim
                if best is not None and best_sim >= cfg.text_similarity:
                    res.near_units += 1
                    res.add_item(DupItem("near", sig_store[best][0], doc_id, best_sim,
                                         safe_str(sig_store[best][2], 200), safe_str(norm, 200),
                                         "Jaccard 유사도 추정 %.2f" % best_sim), cap)
        except Exception as e:
            res.add_read_error("%s 읽기 실패: %s" % (rel(path, test_root), e))
        ctx.step()

    if cfg.near:
        res.notes.append("근사 중복은 MinHash(%d개 순열) 기반 추정치이며, 임계값 %.2f 이상만 보고합니다."
                         % (PERMS, cfg.text_similarity))
    return res
