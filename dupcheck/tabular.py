# -*- coding: utf-8 -*-
"""정형 테이블(행 단위) 중복 검사.

메모리 효율을 위해 행 키를 64bit 해시로 만들고, 학습셋 해시를 정렬된
numpy 배열로 보관한 뒤 searchsorted 로 시험셋을 대조한다.
"""
import numpy as np
import pandas as pd

from .config import CAT_TABULAR, CATEGORY_LABELS
from .loaders import iter_frames
from .models import CategoryResult, DupItem
from .util import norm_text, rel, safe_str

NA_TOKEN = "\x00NA"
ROW_BITS = 38
MAX_ROWS = (1 << ROW_BITS) - 1


def _pack(table_idx, row_no):
    return (np.uint64(table_idx) << np.uint64(ROW_BITS)) | np.uint64(min(row_no, MAX_ROWS))


def _unpack(v):
    v = int(v)
    return v >> ROW_BITS, v & MAX_ROWS


def _norm_cell(x):
    s = str(x)
    return norm_text(s, strip_punct=False)


def canon_column(s: pd.Series, near: bool, decimals: int, normalize_text: bool):
    """컬럼을 정규화된 문자열 object 배열로 변환."""
    n = len(s)
    out = np.empty(n, dtype=object)
    if n == 0:
        return out
    num = pd.to_numeric(s, errors="coerce")
    isnum = num.notna().to_numpy()
    if isnum.any():
        vals = num.to_numpy(dtype="float64")[isnum]
        if near:
            vals = np.round(vals, decimals)
            fmt = "%%.%df" % max(0, decimals)
        else:
            fmt = "%.12g"
        out[isnum] = np.char.mod(fmt, vals).astype(object)
    other = ~isnum
    if other.any():
        rest = s[other]
        nullmask = rest.isna().to_numpy()
        raw = rest.to_numpy(dtype=object)
        if near and normalize_text:
            conv = np.array([_norm_cell(x) for x in raw], dtype=object)
        else:
            conv = np.array([str(x).strip() for x in raw], dtype=object)
        if nullmask.any():
            conv[nullmask] = NA_TOKEN
        out[other] = conv
    return out


def _dedup_columns(cols):
    seen, res = {}, []
    for c in cols:
        c = str(c).strip()
        if c in seen:
            seen[c] += 1
            c = "%s.%d" % (c, seen[c])
        else:
            seen[c] = 0
        res.append(c)
    return res


def select_columns(df, cfg):
    cols = _dedup_columns(list(df.columns))
    df = df.copy()
    df.columns = cols
    low = {c.lower(): c for c in cols}
    if cfg.key_columns:
        want = [low[k.strip().lower()] for k in cfg.key_columns if k.strip().lower() in low]
        use = want
    else:
        excl = {k.strip().lower() for k in cfg.exclude_columns if k.strip()}
        use = [c for c in cols if c.lower() not in excl]
    if cfg.ignore_column_order:
        use = sorted(use)
    return df, use


def row_hashes(df, use_cols, near, cfg):
    """행 키 문자열 → uint64 해시 배열."""
    if not use_cols or len(df) == 0:
        return np.empty(0, dtype=np.uint64)
    key = None
    for c in use_cols:
        col = canon_column(df[c], near, cfg.float_decimals, cfg.text_cell_normalize)
        part = pd.Series(col, dtype=object).fillna("").astype(str)
        piece = (str(c) + "\x1e") + part
        key = piece if key is None else (key + "\x1f" + piece)
    return pd.util.hash_pandas_object(key, index=False).to_numpy(dtype=np.uint64)


class _Tables:
    """(파일, 시트) 단위 테이블 목록."""

    def __init__(self):
        self.items = []          # (path, sheet_label)

    def add(self, path, sheet):
        self.items.append((path, sheet))
        return len(self.items) - 1

    def label(self, idx, root):
        path, sheet = self.items[idx]
        s = rel(path, root)
        return s + (" [%s]" % sheet if sheet else "")


def _row_preview(df, pos, use_cols):
    try:
        row = df.iloc[pos]
    except Exception:
        return ""
    cols = use_cols if use_cols else list(df.columns)
    parts = []
    for c in cols[:12]:
        parts.append("%s=%s" % (c, safe_str(row.get(c, ""), 40)))
    if len(cols) > 12:
        parts.append("… (+%d)" % (len(cols) - 12))
    return " | ".join(parts)


def run(ctx, cfg, train_files, test_files, train_root, test_root):
    res = CategoryResult(key=CAT_TABULAR, label=CATEGORY_LABELS[CAT_TABULAR], unit_name="행")
    res.ran = True
    res.train_files = len(train_files)
    res.test_files = len(test_files)
    if not train_files or not test_files:
        if train_files or test_files:
            res.notes.append("한쪽 폴더에만 테이블 파일이 있어 행 단위 비교를 건너뜁니다.")
        return res

    tables = _Tables()
    ex_h, ex_loc, nr_h, nr_loc = [], [], [], []
    train_cols_seen = set()

    # ---------- 1) 학습셋 인덱싱 ----------
    for path in train_files:
        ctx.check()
        ctx.log("  [학습] %s" % rel(path, train_root))
        try:
            tidx_map, offset_map = {}, {}
            for sheet, df in iter_frames(path, cfg):
                if df is None or len(df) == 0:
                    continue
                sheet = sheet or ""
                if sheet not in tidx_map:
                    tidx_map[sheet] = tables.add(path, sheet)
                    offset_map[sheet] = 0
                tidx, offset = tidx_map[sheet], offset_map[sheet]
                df, use = select_columns(df, cfg)
                if not use:
                    res.errors.append("%s: 비교할 컬럼이 없습니다(제외 설정 확인)." % rel(path, train_root))
                    continue
                train_cols_seen.update(use)
                if cfg.max_rows_per_file and offset >= cfg.max_rows_per_file:
                    continue
                if cfg.max_rows_per_file and offset + len(df) > cfg.max_rows_per_file:
                    df = df.iloc[: cfg.max_rows_per_file - offset]
                    res.notes.append("%s: 상한(%s행)까지만 검사" % (rel(path, train_root), f"{cfg.max_rows_per_file:,}"))
                n = len(df)
                res.train_units += n
                offset_map[sheet] = offset + n
                locs = _pack(tidx, offset) + np.arange(n, dtype=np.uint64)
                if cfg.exact:
                    ex_h.append(row_hashes(df, use, False, cfg))
                    ex_loc.append(locs)
                if cfg.near:
                    nr_h.append(row_hashes(df, use, True, cfg))
                    nr_loc.append(locs)
        except Exception as e:
            res.add_read_error("%s 읽기 실패: %s" % (rel(path, train_root), e))
        ctx.step()

    def build(hl, ll):
        if not hl:
            return None, None
        h = np.concatenate(hl)
        l = np.concatenate(ll)
        order = np.lexsort((l, h))
        return h[order], l[order]

    ex_sorted, ex_locs = build(ex_h, ex_loc)
    nr_sorted, nr_locs = build(nr_h, nr_loc)
    del ex_h, ex_loc, nr_h, nr_loc

    if res.train_units == 0:
        res.notes.append("학습셋에서 읽을 수 있는 행이 없습니다.")
        return res
    if res.train_units > 5_000_000:
        res.notes.append("학습셋 행 수가 매우 많습니다(%s행). 메모리 사용량에 유의하세요." % f"{res.train_units:,}")

    def lookup(sorted_h, sorted_l, q):
        if sorted_h is None or len(q) == 0:
            return np.zeros(len(q), dtype=bool), np.zeros(len(q), dtype=np.uint64)
        idx = np.searchsorted(sorted_h, q, side="left")
        idx_c = np.clip(idx, 0, len(sorted_h) - 1)
        hit = sorted_h[idx_c] == q
        return hit, sorted_l[idx_c]

    # ---------- 2) 시험셋 대조 ----------
    cap = cfg.max_samples_in_report
    need_preview = []     # (table_idx, row_no, item)
    test_cols_seen = set()

    for path in test_files:
        ctx.check()
        ctx.log("  [시험] %s" % rel(path, test_root))
        try:
            offset_map = {}
            for sheet, df in iter_frames(path, cfg):
                if df is None or len(df) == 0:
                    continue
                sheet = sheet or ""
                offset = offset_map.get(sheet, 0)
                df, use = select_columns(df, cfg)
                if not use:
                    res.errors.append("%s: 비교할 컬럼이 없습니다." % rel(path, test_root))
                    continue
                test_cols_seen.update(use)
                if cfg.max_rows_per_file and offset >= cfg.max_rows_per_file:
                    continue
                if cfg.max_rows_per_file and offset + len(df) > cfg.max_rows_per_file:
                    df = df.iloc[: cfg.max_rows_per_file - offset]
                n = len(df)
                res.test_units += n
                offset_map[sheet] = offset + n
                base_label = rel(path, test_root) + (" [%s]" % sheet if sheet else "")

                exact_hit = np.zeros(n, dtype=bool)
                exact_loc = np.zeros(n, dtype=np.uint64)
                if cfg.exact:
                    q = row_hashes(df, use, False, cfg)
                    exact_hit, exact_loc = lookup(ex_sorted, ex_locs, q)
                    res.exact_units += int(exact_hit.sum())

                near_hit = np.zeros(n, dtype=bool)
                near_loc = np.zeros(n, dtype=np.uint64)
                if cfg.near:
                    q2 = row_hashes(df, use, True, cfg)
                    nh, nl = lookup(nr_sorted, nr_locs, q2)
                    near_hit = nh & (~exact_hit)
                    near_loc = nl
                    res.near_units += int(near_hit.sum())

                for kind, mask, locarr in (("exact", exact_hit, exact_loc), ("near", near_hit, near_loc)):
                    if not mask.any():
                        continue
                    pos_list = np.nonzero(mask)[0]
                    for pos in pos_list:
                        if len(res.items) >= cap:
                            res.truncated = True
                            break
                        tidx, rno = _unpack(locarr[pos])
                        item = DupItem(
                            kind=kind,
                            train_ref="%s %d행" % (tables.label(tidx, train_root), rno + 2),
                            test_ref="%s %d행" % (base_label, offset + int(pos) + 2),
                            similarity=1.0 if kind == "exact" else 0.99,
                            test_preview=_row_preview(df, int(pos), use),
                            note="" if kind == "exact" else "허용오차 %d자리/공백·대소문자 정규화 후 일치" % cfg.float_decimals,
                        )
                        res.items.append(item)
                        need_preview.append((tidx, rno, item))
        except Exception as e:
            res.add_read_error("%s 읽기 실패: %s" % (rel(path, test_root), e))
        ctx.step()

    if train_cols_seen and test_cols_seen and not (train_cols_seen & test_cols_seen):
        res.notes.append("학습셋과 시험셋의 컬럼명이 전혀 겹치지 않습니다. 컬럼 구성을 확인하세요.")

    # ---------- 3) 학습셋 원문 미리보기 채우기 ----------
    if need_preview:
        try:
            _fill_train_previews(ctx, cfg, tables, need_preview, train_root)
        except Exception as e:
            res.notes.append("학습셋 미리보기 생성 생략: %s" % e)
    return res


def _fill_train_previews(ctx, cfg, tables, need_preview, train_root):
    by_table = {}
    for tidx, rno, item in need_preview:
        by_table.setdefault(tidx, []).append((rno, item))
    for tidx, wants in by_table.items():
        ctx.check()
        path, sheet = tables.items[tidx]
        wanted = {}
        for rno, item in wants:
            wanted.setdefault(rno, []).append(item)
        target_max = max(wanted)
        offset = 0
        try:
            for lbl, df in iter_frames(path, cfg):
                if (sheet or "") != (lbl or ""):
                    continue
                if df is None or len(df) == 0:
                    continue
                dfc, use = select_columns(df, cfg)
                for rno in list(wanted):
                    pos = rno - offset
                    if 0 <= pos < len(dfc):
                        prev = _row_preview(dfc, pos, use)
                        for it in wanted.pop(rno):
                            it.train_preview = prev
                offset += len(df)
                if not wanted or offset > target_max:
                    break
        except Exception:
            continue
