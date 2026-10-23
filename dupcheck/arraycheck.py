# -*- coding: utf-8 -*-
"""NumPy 배열(.npy/.npz) 및 PKL 내부 배열의 샘플 단위 중복 검사."""
import os

import numpy as np

from .config import CAT_ARRAY, CATEGORY_LABELS
from .loaders import load_pickle
from .models import CategoryResult, DupItem
from .util import h_bytes, rel, safe_str

MAX_UNITS_PER_FILE_DEFAULT = 2_000_000


def iter_arrays(path):
    """(label, ndarray) 제너레이터."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".npy":
        yield "", np.load(path, allow_pickle=True)
    elif ext == ".npz":
        with np.load(path, allow_pickle=True) as z:
            for k in z.files:
                yield str(k), z[k]
    else:
        obj = load_pickle(path)
        for lbl, arr in _arrays_from_obj(obj):
            yield lbl, arr


def _arrays_from_obj(obj, prefix=""):
    if isinstance(obj, np.ndarray):
        yield prefix, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, np.ndarray):
                yield str(k), v
    elif isinstance(obj, (list, tuple)):
        allnum = obj and all(isinstance(x, (int, float, bool)) for x in obj)
        if allnum:
            yield prefix, np.asarray(obj)
        else:
            for i, v in enumerate(obj):
                if isinstance(v, np.ndarray):
                    yield "%s[%d]" % (prefix, i), v


def is_label_vector(arr):
    """샘플당 값이 1개뿐인 수치 배열(정답/라벨 벡터)인지 판정.

    라벨 벡터는 값의 종류가 몇 개뿐이라 서로 다른 샘플도 전부 '중복'으로
    잡히므로, 표 검사에서 라벨 컬럼을 제외하는 것과 같은 이유로 제외한다.
    """
    if not isinstance(arr, np.ndarray) or arr.dtype == object:
        return False
    if not (np.issubdtype(arr.dtype, np.number) or arr.dtype == bool):
        return False
    if arr.ndim == 0:
        return False
    if arr.ndim == 1:
        return True
    return int(np.prod(arr.shape[1:])) == 1


def sample_hashes(arr, near, decimals, limit):
    """(hashes, n_units, unit_shape). 첫 축을 샘플 축으로 본다."""
    a = arr
    if a.dtype == object:
        flat = a.ravel()
        vals = [h_bytes(repr(x).encode("utf-8", "replace")) for x in flat[:limit]]
        return vals, len(vals), "object"
    if np.issubdtype(a.dtype, np.floating) or np.issubdtype(a.dtype, np.integer) or a.dtype == bool:
        a = a.astype(np.float64, copy=False)
        if near:
            a = np.round(a, decimals)
    if a.ndim == 0:
        return [h_bytes(np.ascontiguousarray(a).tobytes())], 1, "scalar"
    n = min(a.shape[0], limit)
    if a.ndim == 1:
        rows = a[:n].reshape(n, 1)
    else:
        rows = a[:n].reshape(n, -1)
    rows = np.ascontiguousarray(rows)
    itemsize = rows.dtype.itemsize
    stride = rows.shape[1] * itemsize
    buf = rows.tobytes()
    hs = [h_bytes(buf[i * stride:(i + 1) * stride]) for i in range(n)]
    return hs, n, "x".join(str(d) for d in a.shape[1:]) or "scalar"


def run(ctx, cfg, train_files, test_files, train_root, test_root):
    res = CategoryResult(key=CAT_ARRAY, label=CATEGORY_LABELS[CAT_ARRAY], unit_name="샘플")
    res.ran = True
    res.train_files = len(train_files)
    res.test_files = len(test_files)
    if not train_files or not test_files:
        if train_files or test_files:
            res.notes.append("한쪽 폴더에만 배열 파일이 있어 샘플 단위 비교를 건너뜁니다.")
        return res

    limit = cfg.array_max_samples or MAX_UNITS_PER_FILE_DEFAULT
    ex_map, nr_map = {}, {}
    skipped = []

    for path in train_files:
        ctx.check()
        ctx.log("  [학습] %s" % rel(path, train_root))
        try:
            for key, arr in iter_arrays(path):
                base = rel(path, train_root) + (" [%s]" % key if key else "")
                if is_label_vector(arr):
                    skipped.append(base)
                    continue
                if cfg.exact:
                    hs, n, shape = sample_hashes(arr, False, cfg.float_decimals, limit)
                    res.train_units += n
                    for i, h in enumerate(hs):
                        ex_map.setdefault(h, ("%s #%d" % (base, i), shape))
                if cfg.near:
                    hs2, n2, shape2 = sample_hashes(arr, True, cfg.float_decimals, limit)
                    if not cfg.exact:
                        res.train_units += n2
                    for i, h in enumerate(hs2):
                        nr_map.setdefault(h, ("%s #%d" % (base, i), shape2))
        except Exception as e:
            res.add_read_error("%s 읽기 실패: %s" % (rel(path, train_root), e))
        ctx.step()

    cap = cfg.max_samples_in_report
    for path in test_files:
        ctx.check()
        ctx.log("  [시험] %s" % rel(path, test_root))
        try:
            for key, arr in iter_arrays(path):
                base = rel(path, test_root) + (" [%s]" % key if key else "")
                if is_label_vector(arr):
                    skipped.append(base)
                    continue
                hs, n, shape = ([], 0, "")
                if cfg.exact:
                    hs, n, shape = sample_hashes(arr, False, cfg.float_decimals, limit)
                hs2, n2, shape2 = ([], 0, "")
                if cfg.near:
                    hs2, n2, shape2 = sample_hashes(arr, True, cfg.float_decimals, limit)
                res.test_units += max(n, n2)
                count = max(n, n2)
                for i in range(count):
                    hit = ex_map.get(hs[i]) if (cfg.exact and i < len(hs)) else None
                    if hit:
                        res.exact_units += 1
                        res.add_item(DupItem("exact", hit[0], "%s #%d" % (base, i), 1.0,
                                             "shape=" + safe_str(hit[1], 30),
                                             "shape=" + safe_str(shape, 30)), cap)
                        continue
                    if cfg.near and i < len(hs2):
                        hit2 = nr_map.get(hs2[i])
                        if hit2:
                            res.near_units += 1
                            res.add_item(DupItem("near", hit2[0], "%s #%d" % (base, i), 0.99,
                                                 "shape=" + safe_str(hit2[1], 30),
                                                 "shape=" + safe_str(shape2, 30),
                                                 "소수점 %d자리 반올림 후 동일" % cfg.float_decimals), cap)
        except Exception as e:
            res.add_read_error("%s 읽기 실패: %s" % (rel(path, test_root), e))
        ctx.step()

    res.notes.append("배열은 첫 번째 축을 샘플 축으로 보고 샘플별로 비교합니다. 수치형은 float64로 변환 후 비교합니다.")
    if skipped:
        uniq = sorted(set(skipped))
        res.notes.append(
            "샘플당 값이 1개인 수치 배열 %d개는 정답(라벨) 벡터로 판단해 비교에서 제외했습니다"
            " (라벨은 값의 종류가 적어 서로 다른 샘플도 중복으로 잡히기 때문입니다): %s"
            % (len(uniq), ", ".join(uniq[:10]) + (" 외 %d개" % (len(uniq) - 10) if len(uniq) > 10 else "")))
    return res
