# -*- coding: utf-8 -*-
"""결과 데이터 모델."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DupItem:
    kind: str                  # 'exact' | 'near'
    train_ref: str             # 예: train/a.csv 12행
    test_ref: str
    similarity: float = 1.0
    train_preview: str = ""
    test_preview: str = ""
    note: str = ""


@dataclass
class CategoryResult:
    key: str
    label: str
    unit_name: str = "건"
    train_files: int = 0
    test_files: int = 0
    train_units: int = 0
    test_units: int = 0
    exact_units: int = 0       # 학습셋과 완전 일치한 시험셋 단위 수
    near_units: int = 0        # (완전일치 제외) 근사 중복인 시험셋 단위 수
    items: List[DupItem] = field(default_factory=list)
    truncated: bool = False    # 리포트 샘플 상한 초과
    notes: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    read_fail: int = 0         # 읽지 못해 이 검사에서 빠진 파일 수
    ran: bool = False

    def add_read_error(self, msg):
        """읽지 못한 파일 하나를 기록한다.

        errors 에만 쌓으면 요약에서 보이지 않아 '중복 0건'과 구분되지 않는다.
        그래서 건수를 따로 센다.
        """
        self.read_fail += 1
        self.errors.append(msg)

    @property
    def dup_units(self):
        return self.exact_units + self.near_units

    @property
    def leak_rate(self):
        if not self.test_units:
            return 0.0
        return 100.0 * self.dup_units / self.test_units

    def add_item(self, item: DupItem, cap: int):
        if len(self.items) < cap:
            self.items.append(item)
        else:
            self.truncated = True


@dataclass
class RunResult:
    started_at: str = ""
    finished_at: str = ""
    elapsed_sec: float = 0.0
    train_dir: str = ""
    test_dir: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
    categories: List[CategoryResult] = field(default_factory=list)
    global_notes: List[str] = field(default_factory=list)
    cancelled: bool = False
    report_path: Optional[str] = None

    @property
    def total_dup(self):
        return sum(c.dup_units for c in self.categories)

    @property
    def verdict(self):
        """전체 판정."""
        if self.total_dup == 0:
            return "PASS"
        exact = sum(c.exact_units for c in self.categories)
        return "FAIL" if exact > 0 else "WARN"
