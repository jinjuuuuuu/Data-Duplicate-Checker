# -*- coding: utf-8 -*-
"""배포용 icon.ico 생성 (개발용 스크립트)."""
import os

from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icon.ico")
S = 512
NAVY = (23, 42, 74, 255)
BLUE = (37, 99, 235, 255)
WHITE = (255, 255, 255, 255)
GRAY = (203, 213, 225, 255)
RED = (220, 38, 38, 255)


def page(d, x, y, w, h, fill, outline):
    d.rounded_rectangle([x, y, x + w, y + h], radius=18, fill=fill, outline=outline, width=8)


def main():
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([8, 8, S - 8, S - 8], radius=96, fill=NAVY)

    # 뒤쪽 문서
    page(d, 96, 96, 210, 270, WHITE, GRAY)
    for i in range(4):
        d.rounded_rectangle([126, 140 + i * 40, 276, 152 + i * 40], radius=6, fill=GRAY)
    # 앞쪽 문서
    page(d, 186, 156, 210, 270, WHITE, BLUE)
    for i in range(4):
        d.rounded_rectangle([216, 200 + i * 40, 366, 212 + i * 40], radius=6, fill=(147, 197, 253, 255))

    # 돋보기
    d.ellipse([236, 226, 396, 386], outline=BLUE, width=26)
    d.line([386, 376, 452, 442], fill=BLUE, width=30)
    # 중복(=) 표시
    d.line([282, 288, 350, 288], fill=RED, width=20)
    d.line([282, 324, 350, 324], fill=RED, width=20)

    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    im.resize((256, 256), Image.LANCZOS).save(OUT, format="ICO", sizes=sizes)
    print("생성:", OUT)


if __name__ == "__main__":
    main()
