# -*- coding: utf-8 -*-
"""검사 오케스트레이션."""
import os
import time
from datetime import datetime

from . import arraycheck, discover, filecheck, imagecheck, tabular, textcheck
from .config import (APP_VERSION, CAT_ARRAY, CAT_FILE, CAT_IMAGE, CAT_TABULAR,
                     CAT_TEXT, CATEGORY_LABELS)
from .models import RunResult
from .util import Cancelled, Ctx


def classify_pickle(path):
    """PKL 내용을 보고 tabular / array 로 분류."""
    try:
        import numpy as np
        import pandas as pd
        from .loaders import load_pickle
        obj = load_pickle(path)
        if isinstance(obj, (pd.DataFrame, pd.Series)):
            return CAT_TABULAR
        if isinstance(obj, np.ndarray):
            return CAT_ARRAY
        if isinstance(obj, dict):
            if any(isinstance(v, (pd.DataFrame, pd.Series)) for v in obj.values()):
                return CAT_TABULAR
            if any(isinstance(v, np.ndarray) for v in obj.values()):
                return CAT_ARRAY
        if isinstance(obj, (list, tuple)) and obj:
            if all(isinstance(x, dict) for x in obj):
                return CAT_TABULAR
            return CAT_ARRAY
    except Exception:
        pass
    return None


def run_check(cfg, log=None, progress=None, cancel_check=None):
    ctx = Ctx(log, progress, cancel_check)
    result = RunResult()
    result.train_dir = cfg.train_dir
    result.test_dir = cfg.test_dir
    result.config = cfg.to_dict()
    result.started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    t0 = time.time()

    for label, path in (("학습데이터", cfg.train_dir), ("시험데이터", cfg.test_dir)):
        if not path or not os.path.isdir(path):
            raise ValueError("%s 폴더 경로가 올바르지 않습니다: %s" % (label, path))
    if os.path.abspath(cfg.train_dir) == os.path.abspath(cfg.test_dir):
        result.global_notes.append("경고: 학습/시험 폴더 경로가 동일합니다. 모든 데이터가 중복으로 보고됩니다.")

    try:
        ctx.log("폴더 스캔 중…")
        tr_files, tr_cat = discover.scan(cfg.train_dir)
        te_files, te_cat = discover.scan(cfg.test_dir)
        ctx.log("학습 %d개 파일 / 시험 %d개 파일 발견" % (len(tr_files), len(te_files)))

        # PKL 재분류
        for side, cats in (("train", tr_cat), ("test", te_cat)):
            for p in list(cats.get("pickle", [])):
                c = classify_pickle(p)
                if c:
                    cats.setdefault(c, []).append(p)
                    cats["pickle"].remove(p)
            if cats.get("pickle"):
                result.global_notes.append(
                    "내용을 해석할 수 없는 PKL %d개는 파일 단위 검사만 적용했습니다." % len(cats["pickle"]))

        enabled = cfg.enabled_categories()
        total = 0
        if CAT_FILE in enabled:
            total += len(te_files)
        for cat in (CAT_TABULAR, CAT_IMAGE, CAT_TEXT, CAT_ARRAY):
            if cat in enabled:
                total += len(tr_cat.get(cat, [])) + len(te_cat.get(cat, []))
        ctx.set_total(max(1, total))

        runners = [
            (CAT_FILE, filecheck.run, None),
            (CAT_TABULAR, tabular.run, CAT_TABULAR),
            (CAT_IMAGE, imagecheck.run, CAT_IMAGE),
            (CAT_TEXT, textcheck.run, CAT_TEXT),
            (CAT_ARRAY, arraycheck.run, CAT_ARRAY),
        ]
        for cat, fn, key in runners:
            if cat not in enabled:
                continue
            ctx.check()
            if key is None:
                a, b = tr_files, te_files
            else:
                a = sorted(tr_cat.get(key, []))
                b = sorted(te_cat.get(key, []))
                if not a and not b:
                    continue
            ctx.log("── %s 검사 시작" % CATEGORY_LABELS.get(cat, cat))
            cr = fn(ctx, cfg, a, b, cfg.train_dir, cfg.test_dir)
            result.categories.append(cr)
            ctx.log("   완료: 중복 %s건 / 시험 %s%s" % (f"{cr.dup_units:,}", f"{cr.test_units:,}", cr.unit_name))
    except Cancelled:
        result.cancelled = True
        ctx.log("사용자에 의해 중지되었습니다.")

    result.elapsed_sec = time.time() - t0
    result.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    result.config["_version"] = APP_VERSION
    return result
