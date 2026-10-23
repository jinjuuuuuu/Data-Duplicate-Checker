# -*- coding: utf-8 -*-
"""검사 설정 정의."""
from dataclasses import dataclass, field, asdict
from typing import List

APP_NAME = "AI 학습/시험 데이터 중복성 검사기"
APP_VERSION = "1.0.2"

# 카테고리 키
CAT_TABULAR = "tabular"
CAT_IMAGE = "image"
CAT_TEXT = "text"
CAT_ARRAY = "array"
CAT_FILE = "file"

CATEGORY_LABELS = {
    CAT_FILE: "파일 단위 동일성",
    CAT_TABULAR: "정형 테이블(행 단위)",
    CAT_IMAGE: "이미지(샘플 단위)",
    CAT_TEXT: "텍스트/JSON(문서 단위)",
    CAT_ARRAY: "NumPy 배열/PKL(샘플 단위)",
}

CATEGORY_ORDER = [CAT_FILE, CAT_TABULAR, CAT_IMAGE, CAT_TEXT, CAT_ARRAY]

TABULAR_EXT = {".csv", ".tsv", ".xlsx", ".xlsm", ".xls", ".parquet"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp", ".ppm"}
TEXT_EXT = {".txt", ".json", ".jsonl", ".ndjson", ".md", ".text"}
ARRAY_EXT = {".npy", ".npz"}
PICKLE_EXT = {".pkl", ".pickle"}


@dataclass
class Config:
    """검사 옵션. GUI/CLI 모두 이 객체를 채워서 엔진에 넘긴다."""

    train_dir: str = ""
    test_dir: str = ""
    out_dir: str = ""              # 비우면 시험데이터 폴더 옆에 생성

    # 검사할 카테고리
    check_file: bool = True
    check_tabular: bool = True
    check_image: bool = True
    check_text: bool = True
    check_array: bool = True

    # 판정 기준
    exact: bool = True             # 완전 일치
    near: bool = True              # 근사 중복

    # 정형 테이블 옵션
    exclude_columns: List[str] = field(default_factory=list)   # 정답(라벨) 컬럼 등 제외
    key_columns: List[str] = field(default_factory=list)       # 지정 시 이 컬럼들만으로 판정
    ignore_column_order: bool = True
    float_decimals: int = 4        # 근사 판정 시 소수점 자리수
    text_cell_normalize: bool = True  # 근사 판정 시 공백/대소문자 무시
    max_rows_per_file: int = 0     # 0 = 제한 없음
    csv_sep: str = ""              # 비우면 자동 추정

    # 텍스트 옵션
    text_similarity: float = 0.80  # Jaccard 임계값
    text_min_chars: int = 20       # 이보다 짧은 문서는 근사 검사 제외(오탐 방지)

    # 이미지 옵션
    image_hamming: int = 5         # dHash 해밍거리 임계값(0~64), 작을수록 엄격

    # 배열 옵션
    array_max_samples: int = 2_000_000   # 파일당 샘플 상한

    # 리포트
    max_samples_in_report: int = 300
    open_report: bool = True

    def enabled_categories(self) -> List[str]:
        m = {
            CAT_FILE: self.check_file,
            CAT_TABULAR: self.check_tabular,
            CAT_IMAGE: self.check_image,
            CAT_TEXT: self.check_text,
            CAT_ARRAY: self.check_array,
        }
        return [c for c in CATEGORY_ORDER if m.get(c)]

    def to_dict(self):
        return asdict(self)
