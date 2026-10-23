# -*- coding: utf-8 -*-
"""이미지 중복 검사.

- 완전 일치: 디코딩된 픽셀 해시 (파일 포맷/메타데이터가 달라도 동일 이미지면 탐지)
- 근사 중복: dHash 64bit + 해밍거리 (리사이즈/재압축/약한 편집 탐지)
"""
from .config import CAT_IMAGE, CATEGORY_LABELS
from .models import CategoryResult, DupItem
from .util import h_bytes, rel

BANDS = 8
BAND_BITS = 8


def _load_pil():
    try:
        from PIL import Image
        return Image
    except Exception:
        return None


def image_hashes(Image, path):
    """(pixel_hash, dhash_int, size_text) 반환."""
    with Image.open(path) as im:
        im.load()
        w, h = im.size
        rgb = im.convert("RGB")
        px = h_bytes(rgb.tobytes() + b"|%dx%d" % (w, h))
        small = im.convert("L").resize((9, 8), Image.BILINEAR)
        data = list(small.getdata())
        bits = 0
        for row in range(8):
            base = row * 9
            for col in range(8):
                bits <<= 1
                if data[base + col] > data[base + col + 1]:
                    bits |= 1
    return px, bits, "%dx%d" % (w, h)


def _bands(bits):
    return [(b, (bits >> (b * BAND_BITS)) & ((1 << BAND_BITS) - 1)) for b in range(BANDS)]


def run(ctx, cfg, train_files, test_files, train_root, test_root):
    res = CategoryResult(key=CAT_IMAGE, label=CATEGORY_LABELS[CAT_IMAGE], unit_name="장")
    res.ran = True
    res.train_files = len(train_files)
    res.test_files = len(test_files)
    if not train_files or not test_files:
        if train_files or test_files:
            res.notes.append("한쪽 폴더에만 이미지가 있어 이미지 비교를 건너뜁니다.")
        return res

    Image = _load_pil()
    if Image is None:
        res.errors.append("Pillow 라이브러리가 없어 이미지 검사를 수행할 수 없습니다.")
        return res

    exact_map = {}
    lsh = {}
    dstore = []      # (label, dhash, size)

    for path in train_files:
        ctx.check()
        try:
            px, bits, size = image_hashes(Image, path)
            label = rel(path, train_root)
            res.train_units += 1
            if cfg.exact:
                exact_map.setdefault(px, (label, size))
            if cfg.near:
                i = len(dstore)
                dstore.append((label, bits, size))
                for k in _bands(bits):
                    lsh.setdefault(k, []).append(i)
        except Exception as e:
            res.add_read_error("%s 읽기 실패: %s" % (rel(path, train_root), e))
        ctx.step()

    cap = cfg.max_samples_in_report
    thr = max(0, min(64, cfg.image_hamming))
    for path in test_files:
        ctx.check()
        try:
            px, bits, size = image_hashes(Image, path)
            label = rel(path, test_root)
            res.test_units += 1
            hit = exact_map.get(px) if cfg.exact else None
            if hit:
                res.exact_units += 1
                res.add_item(DupItem("exact", hit[0], label, 1.0, hit[1], size,
                                     "픽셀 데이터가 완전히 동일"), cap)
                ctx.step()
                continue
            if cfg.near and dstore:
                cand = set()
                for k in _bands(bits):
                    cand.update(lsh.get(k, ()))
                best, best_d = None, 65
                for i in cand:
                    d = bin(dstore[i][1] ^ bits).count("1")
                    if d < best_d:
                        best, best_d = i, d
                if best is not None and best_d <= thr:
                    res.near_units += 1
                    res.add_item(DupItem("near", dstore[best][0], label,
                                         1.0 - best_d / 64.0, dstore[best][2], size,
                                         "dHash 해밍거리 %d (임계 %d)" % (best_d, thr)), cap)
        except Exception as e:
            res.add_read_error("%s 읽기 실패: %s" % (rel(path, test_root), e))
        ctx.step()

    if cfg.near and thr > 7:
        res.notes.append("해밍거리 임계값이 7보다 크면 후보 탐색 과정에서 일부 유사쌍을 놓칠 수 있습니다.")
    return res
