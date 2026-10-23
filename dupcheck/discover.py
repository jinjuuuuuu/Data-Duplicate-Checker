# -*- coding: utf-8 -*-
"""폴더 스캔 및 파일 분류."""
import os

from .config import (ARRAY_EXT, CAT_ARRAY, CAT_IMAGE, CAT_TABULAR, CAT_TEXT,
                     IMAGE_EXT, PICKLE_EXT, TABULAR_EXT, TEXT_EXT)

SKIP_DIRS = {".git", ".svn", "__pycache__", ".ipynb_checkpoints", "$RECYCLE.BIN",
             "System Volume Information", ".DS_Store", "node_modules"}


def classify(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in TABULAR_EXT:
        return CAT_TABULAR
    if ext in IMAGE_EXT:
        return CAT_IMAGE
    if ext in TEXT_EXT:
        return CAT_TEXT
    if ext in ARRAY_EXT:
        return CAT_ARRAY
    if ext in PICKLE_EXT:
        return "pickle"      # 내용에 따라 나중에 재분류
    return "other"


def scan(root):
    """(files, by_cat) 반환. files=[(abspath, size, cat)]"""
    files = []
    by_cat = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith("~$")]
        for name in filenames:
            if name.startswith("~$") or name in SKIP_DIRS:
                continue
            p = os.path.join(dirpath, name)
            try:
                size = os.path.getsize(p)
            except OSError:
                continue
            cat = classify(p)
            files.append((p, size, cat))
            by_cat.setdefault(cat, []).append(p)
    files.sort(key=lambda t: t[0])
    for k in by_cat:
        by_cat[k].sort()
    return files, by_cat
