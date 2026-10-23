# -*- coding: utf-8 -*-
"""파일 → DataFrame 청크 로더."""
import csv
import os
import pickle
import warnings

import pandas as pd

# 손상된 CSV 를 관대하게 읽을 때 나오는 경고는 리포트의 오류 목록으로 대체한다.
warnings.filterwarnings("ignore", category=pd.errors.ParserWarning)
warnings.filterwarnings("ignore", category=pd.errors.DtypeWarning)

CHUNK = 200_000
ENCODINGS = ("utf-8-sig", "cp949", "utf-8", "euc-kr", "latin-1")


def _sniff_sep(path, forced=""):
    if forced:
        return {"\\t": "\t", "tab": "\t", "TAB": "\t"}.get(forced, forced)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".tsv":
        return "\t"
    try:
        with open(path, "rb") as f:
            head = f.read(65536)
        for enc in ENCODINGS:
            try:
                text = head.decode(enc)
                break
            except Exception:
                continue
        else:
            return ","
        try:
            return csv.Sniffer().sniff(text, delimiters=",;\t|").delimiter
        except Exception:
            first = text.splitlines()[0] if text.splitlines() else ""
            counts = {d: first.count(d) for d in (",", ";", "\t", "|")}
            best = max(counts, key=counts.get)
            return best if counts[best] > 0 else ","
    except Exception:
        return ","


def _read_csv_chunks(path, cfg):
    sep = _sniff_sep(path, cfg.csv_sep)
    last_err = None
    for enc in ENCODINGS:
        try:
            reader = pd.read_csv(
                path, sep=sep, dtype=str, chunksize=CHUNK, encoding=enc,
                engine="c", on_bad_lines="skip", keep_default_na=True,
                skip_blank_lines=True, index_col=False,
            )
            got = False
            for chunk in reader:
                got = True
                yield "", chunk
            if not got:
                yield "", pd.DataFrame()
            return
        except UnicodeDecodeError as e:
            last_err = e
            continue
        except pd.errors.EmptyDataError:
            yield "", pd.DataFrame()      # 빈 파일은 조용히 건너뜀
            return
        except Exception as e:
            # 따옴표 불일치 등 손상된 CSV → 관대한 파서로 재시도
            last_err = e
            try:
                reader = pd.read_csv(
                    path, sep=sep, dtype=str, chunksize=CHUNK, encoding=enc,
                    engine="python", on_bad_lines="skip", keep_default_na=True,
                    skip_blank_lines=True, quoting=csv.QUOTE_NONE, index_col=False,
                )
                for chunk in reader:
                    yield "", chunk
                return
            except UnicodeDecodeError:
                continue
            except Exception:
                raise last_err
    raise last_err or RuntimeError("CSV 인코딩을 판별할 수 없습니다")


def iter_frames(path, cfg):
    """(sheet_label, DataFrame) 제너레이터. 실패 시 예외."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".csv", ".tsv"):
        for lbl, df in _read_csv_chunks(path, cfg):
            yield lbl, df
    elif ext in (".xlsx", ".xlsm", ".xls"):
        sheets = pd.read_excel(path, sheet_name=None, dtype=str)
        for name, df in sheets.items():
            yield str(name), df
    elif ext == ".parquet":
        yield "", pd.read_parquet(path)
    else:
        obj = load_pickle(path)
        for lbl, df in frames_from_object(obj):
            yield lbl, df


def load_pickle(path):
    try:
        return pd.read_pickle(path)
    except Exception:
        with open(path, "rb") as f:
            return pickle.load(f)


def frames_from_object(obj, prefix=""):
    """PKL 등에서 얻은 객체에서 DataFrame 후보를 추출."""
    if isinstance(obj, pd.DataFrame):
        yield prefix, obj
    elif isinstance(obj, pd.Series):
        yield prefix, obj.to_frame(name=obj.name or "value")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (pd.DataFrame, pd.Series)):
                for lbl, df in frames_from_object(v, str(k)):
                    yield lbl, df
    elif isinstance(obj, (list, tuple)) and obj and all(isinstance(x, dict) for x in obj):
        yield prefix, pd.DataFrame(list(obj))
