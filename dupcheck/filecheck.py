# -*- coding: utf-8 -*-
"""파일 단위 동일성 검사 (SHA-256)."""
import os

from .config import CAT_FILE, CATEGORY_LABELS
from .models import CategoryResult, DupItem
from .util import file_sha256, human_bytes, rel


def run(ctx, cfg, train_files, test_files, train_root, test_root):
    """train_files/test_files: [(path, size, cat)] 전체 파일 목록"""
    res = CategoryResult(key=CAT_FILE, label=CATEGORY_LABELS[CAT_FILE], unit_name="파일")
    res.ran = True
    res.train_files = len(train_files)
    res.test_files = len(test_files)
    res.train_units = len(train_files)
    res.test_units = len(test_files)
    if not train_files or not test_files:
        return res

    # 크기가 같은 파일만 해시 (성능)
    train_by_size = {}
    for p, s, _ in train_files:
        train_by_size.setdefault(s, []).append(p)

    hashed = {}
    cap = cfg.max_samples_in_report
    name_only = 0

    train_names = {}
    for p, s, _ in train_files:
        train_names.setdefault(os.path.basename(p).lower(), []).append(p)

    for p, s, _ in test_files:
        ctx.check()
        cands = train_by_size.get(s)
        matched = False
        if cands:
            try:
                th = file_sha256(p)
                for c in cands:
                    if c not in hashed:
                        hashed[c] = file_sha256(c)
                    if hashed[c] == th:
                        res.exact_units += 1
                        res.add_item(DupItem("exact", rel(c, train_root), rel(p, test_root), 1.0,
                                             human_bytes(s), human_bytes(s),
                                             "SHA-256 동일 (%s…)" % th[:12]), cap)
                        matched = True
                        break
            except Exception as e:
                res.add_read_error("%s 해시 실패: %s" % (rel(p, test_root), e))
        if not matched and os.path.basename(p).lower() in train_names:
            name_only += 1
        ctx.step()

    if name_only:
        res.notes.append("파일명은 같지만 내용이 다른 파일이 %d건 있습니다(버전 차이 가능성)." % name_only)
    return res
