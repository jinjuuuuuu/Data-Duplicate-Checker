# -*- coding: utf-8 -*-
"""공용 유틸: 해시, 정규화, 취소/로그 컨텍스트."""
import hashlib
import os
import re
import unicodedata

DIGEST_SIZE = 12  # 96bit. 충돌확률 무시 가능 수준이면서 메모리 절약


class Cancelled(Exception):
    """사용자가 검사를 중지했을 때."""


class Ctx:
    """엔진 전체가 공유하는 로그/진행률/취소 컨텍스트."""

    def __init__(self, log=None, progress=None, cancel_check=None):
        self._log = log or (lambda msg: None)
        self._progress = progress or (lambda done, total, msg="": None)
        self._cancel = cancel_check or (lambda: False)
        self.done = 0
        self.total = 0

    def log(self, msg):
        self._log(str(msg))

    def set_total(self, n):
        self.total = max(0, int(n))
        self._progress(self.done, self.total, "")

    def step(self, msg=""):
        self.done += 1
        self._progress(self.done, self.total, msg)

    def check(self):
        if self._cancel():
            raise Cancelled()


def h_bytes(data: bytes) -> bytes:
    return hashlib.blake2b(data, digest_size=DIGEST_SIZE).digest()


def h_text(s: str) -> bytes:
    return h_bytes(s.encode("utf-8", "surrogatepass"))


def file_sha256(path, chunk=1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def norm_text(s: str, strip_punct=True) -> str:
    """근사 비교용 텍스트 정규화."""
    s = unicodedata.normalize("NFKC", s)
    s = s.lower()
    if strip_punct:
        s = _PUNCT.sub(" ", s)
    return _WS.sub(" ", s).strip()


def norm_newlines(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n").strip("﻿").strip()


def human_bytes(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return "%.1f %s" % (n, u) if u != "B" else "%d B" % n
        n /= 1024.0


def rel(path, root):
    try:
        return os.path.relpath(path, root)
    except Exception:
        return path


def safe_str(v, limit=160):
    s = "" if v is None else str(v)
    s = s.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    if len(s) > limit:
        s = s[: limit - 1] + "…"
    return s


def read_text_file(path, limit_bytes=0):
    """인코딩 자동 추정 텍스트 읽기 (한국어 CP949 대응)."""
    with open(path, "rb") as f:
        raw = f.read() if limit_bytes <= 0 else f.read(limit_bytes)
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr", "utf-16", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "replace")
