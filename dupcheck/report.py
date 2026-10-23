# -*- coding: utf-8 -*-
"""단일 파일 HTML 리포트 생성."""
import html
import os
from datetime import datetime

from .config import APP_NAME, APP_VERSION

VERDICT_TEXT = {
    "PASS": ("중복 없음", "학습셋과 시험셋에서 중복 데이터가 발견되지 않았습니다."),
    "WARN": ("근사 중복 발견", "완전 일치는 없으나 유사(근사 중복) 데이터가 발견되었습니다. 검토가 필요합니다."),
    "FAIL": ("중복 발견", "학습셋과 시험셋에 동일한 데이터가 존재합니다. 시험 결과의 신뢰성이 훼손될 수 있습니다."),
}

CSS = """
:root{--bd:#e3e6ea;--mut:#5f6b7a;--bg:#f7f8fa;--ok:#127c4a;--warn:#8a5a00;--bad:#b3261e}
*{box-sizing:border-box}
body{margin:0;padding:32px 28px 64px;background:#fff;color:#1a1f26;
 font-family:"Malgun Gothic","맑은 고딕","Apple SD Gothic Neo","Noto Sans KR",sans-serif;
 font-size:14px;line-height:1.6}
.wrap{max-width:1100px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:17px;margin:34px 0 10px;padding-bottom:6px;border-bottom:2px solid #1a1f26}
h3{font-size:15px;margin:20px 0 8px}
.sub{color:var(--mut);font-size:13px;margin-bottom:18px}
.badge{display:inline-block;padding:5px 14px;border-radius:999px;font-weight:700;font-size:13px;color:#fff}
.b-PASS{background:var(--ok)}.b-WARN{background:var(--warn)}.b-FAIL{background:var(--bad)}
.verdict{border:1px solid var(--bd);border-left:5px solid #1a1f26;background:var(--bg);
 padding:14px 16px;border-radius:6px;margin:12px 0 8px}
.verdict.v-PASS{border-left-color:var(--ok)}.verdict.v-WARN{border-left-color:var(--warn)}
.verdict.v-FAIL{border-left-color:var(--bad)}
table{width:100%;border-collapse:collapse;margin:10px 0 6px;font-size:13px}
th,td{border:1px solid var(--bd);padding:7px 9px;text-align:left;vertical-align:top}
th{background:var(--bg);font-weight:700;white-space:nowrap}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tr:nth-child(even) td{background:#fcfcfd}
code,.mono{font-family:Consolas,"D2Coding",monospace;font-size:12px}
.pill{display:inline-block;padding:1px 8px;border-radius:4px;font-size:11.5px;font-weight:700}
.p-exact{background:#fdecea;color:var(--bad)}
.p-near{background:#fff4e0;color:var(--warn)}
.note{background:#f2f7ff;border:1px solid #cfe0ff;padding:9px 12px;border-radius:5px;margin:8px 0;font-size:13px}
.err{background:#fff5f5;border:1px solid #f3c9c6;padding:9px 12px;border-radius:5px;margin:8px 0;font-size:13px}
.kv{font-size:13px}
.kv td:first-child{width:230px;background:var(--bg);font-weight:600}
.zero{color:var(--mut)}
td.rf{color:#b3261e;font-weight:600}
.footer{margin-top:40px;padding-top:12px;border-top:1px solid var(--bd);color:var(--mut);font-size:12px}
.prev{color:#333;max-width:520px;word-break:break-all}
@media print{body{padding:0}h2{page-break-after:avoid}}
"""


def _e(s):
    return html.escape("" if s is None else str(s))


def _fmt(n):
    return "{:,}".format(n)


def build_html(result):
    v = result.verdict
    vt, vd = VERDICT_TEXT[v]
    parts = []
    A = parts.append
    A("<!DOCTYPE html><html lang='ko'><head><meta charset='utf-8'>")
    A("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    A("<title>%s 결과 리포트</title><style>%s</style></head><body><div class='wrap'>" % (_e(APP_NAME), CSS))
    A("<h1>학습/시험 데이터 중복성 검사 리포트</h1>")
    A("<div class='sub'>%s v%s · 생성 %s</div>" % (_e(APP_NAME), APP_VERSION,
                                                _e(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))))

    A("<div class='verdict v-%s'><span class='badge b-%s'>%s</span> &nbsp;%s</div>" % (v, v, _e(vt), _e(vd)))
    if result.cancelled:
        A("<div class='err'>사용자가 검사를 중지했습니다. 아래 결과는 부분 검사 결과입니다.</div>")
    for n in result.global_notes:
        A("<div class='note'>%s</div>" % _e(n))

    A("<h2>1. 검사 개요</h2><table class='kv'>")
    rows = [
        ("학습데이터 폴더", result.train_dir),
        ("시험데이터 폴더", result.test_dir),
        ("검사 시작", result.started_at),
        ("검사 종료", result.finished_at),
        ("소요 시간", "%.1f초" % result.elapsed_sec),
    ]
    for k, val in rows:
        A("<tr><td>%s</td><td class='mono'>%s</td></tr>" % (_e(k), _e(val)))
    A("</table>")

    A("<h2>2. 요약</h2>")
    A("<table><tr><th>검사 항목</th><th class='num'>학습 단위</th><th class='num'>시험 단위</th>"
      "<th class='num'>완전 일치</th><th class='num'>근사 중복</th><th class='num'>중복률</th>"
      "<th class='num'>읽기 실패</th><th>판정</th></tr>")
    for c in result.categories:
        if not c.ran:
            continue
        mark = "정상" if c.dup_units == 0 else ("중복" if c.exact_units else "유사")
        cls = "zero" if c.dup_units == 0 else ""
        A("<tr><td>%s</td><td class='num'>%s%s</td><td class='num'>%s%s</td>"
          "<td class='num'>%s</td><td class='num'>%s</td><td class='num'>%.2f%%</td>"
          "<td class='num %s'>%s</td><td class='%s'>%s</td></tr>"
          % (_e(c.label), _fmt(c.train_units), _e(c.unit_name), _fmt(c.test_units), _e(c.unit_name),
             _fmt(c.exact_units), _fmt(c.near_units), c.leak_rate,
             "rf" if c.read_fail else "zero", _fmt(c.read_fail), cls, mark))
    A("<tr><th>합계</th><th class='num'>-</th><th class='num'>-</th><th class='num'>%s</th>"
      "<th class='num'>%s</th><th class='num'>-</th><th class='num'>%s</th><th>%s</th></tr>"
      % (_fmt(sum(c.exact_units for c in result.categories)),
         _fmt(sum(c.near_units for c in result.categories)),
         _fmt(sum(c.read_fail for c in result.categories)), _e(vt)))
    A("</table>")
    A("<div class='note'>‘단위’는 검사 항목에 따라 행·문서·이미지 장수·샘플 수를 의미합니다. "
      "중복률 = (완전 일치 + 근사 중복) ÷ 시험 단위 수.</div>")
    if sum(c.read_fail for c in result.categories):
        A("<div class='err'>‘읽기 실패’는 파일을 열지 못해 해당 검사에서 빠진 파일 수입니다. "
          "중복이 없다는 뜻이 아니므로 아래 3장에서 목록을 확인하세요.</div>")

    A("<h2>3. 상세 결과</h2>")
    idx = 0
    for c in result.categories:
        if not c.ran:
            continue
        idx += 1
        A("<h3>3.%d %s</h3>" % (idx, _e(c.label)))
        A("<div class='sub'>학습 파일 %s개 / 시험 파일 %s개 · 완전 일치 %s건 · 근사 중복 %s건</div>"
          % (_fmt(c.train_files), _fmt(c.test_files), _fmt(c.exact_units), _fmt(c.near_units)))
        for n in c.notes:
            A("<div class='note'>%s</div>" % _e(n))
        for er in c.errors[:30]:
            A("<div class='err'>%s</div>" % _e(er))
        if len(c.errors) > 30:
            A("<div class='err'>… 외 %d건의 읽기 오류</div>" % (len(c.errors) - 30))
        if not c.items:
            A("<div class='note'>중복으로 판정된 항목이 없습니다.</div>")
            continue
        if c.truncated:
            A("<div class='note'>리포트에는 최대 %d건까지만 표시합니다(전체 중복 %s건)."
              "</div>" % (len(c.items), _fmt(c.dup_units)))
        A("<table><tr><th>#</th><th>구분</th><th>학습셋 위치</th><th>시험셋 위치</th>"
          "<th class='num'>유사도</th><th>내용 미리보기 (학습 / 시험)</th></tr>")
        for i, it in enumerate(c.items, 1):
            pill = "p-exact" if it.kind == "exact" else "p-near"
            kname = "완전 일치" if it.kind == "exact" else "근사 중복"
            prev = ""
            if it.train_preview or it.test_preview:
                prev = "<div class='prev mono'>%s</div><div class='prev mono' style='color:#666'>%s</div>" % (
                    _e(it.train_preview), _e(it.test_preview))
            if it.note:
                prev += "<div style='color:#5f6b7a;font-size:11.5px'>%s</div>" % _e(it.note)
            A("<tr><td class='num'>%d</td><td><span class='pill %s'>%s</span></td>"
              "<td class='mono'>%s</td><td class='mono'>%s</td><td class='num'>%.2f</td><td>%s</td></tr>"
              % (i, pill, kname, _e(it.train_ref), _e(it.test_ref), it.similarity, prev))
        A("</table>")

    A("<h2>4. 검사 설정</h2><table class='kv'>")
    cfg = result.config
    label_map = [
        ("exact", "완전 일치 검사"), ("near", "근사 중복 검사"),
        ("check_file", "파일 단위 동일성"), ("check_tabular", "정형 테이블"),
        ("check_image", "이미지"), ("check_text", "텍스트/JSON"), ("check_array", "NumPy/PKL 배열"),
        ("exclude_columns", "제외 컬럼"), ("key_columns", "기준 컬럼(지정 시 이 컬럼만 비교)"),
        ("ignore_column_order", "컬럼 순서 무시"), ("float_decimals", "수치 허용오차(소수점 자리)"),
        ("text_cell_normalize", "셀 공백·대소문자 무시"), ("text_similarity", "텍스트 유사도 임계값"),
        ("text_min_chars", "텍스트 최소 길이"), ("image_hamming", "이미지 해밍거리 임계값"),
        ("max_rows_per_file", "파일당 최대 행(0=무제한)"), ("csv_sep", "CSV 구분자(공백=자동)"),
        ("max_samples_in_report", "리포트 표시 상한"),
    ]
    for k, lbl in label_map:
        if k not in cfg:
            continue
        val = cfg[k]
        if isinstance(val, bool):
            val = "예" if val else "아니오"
        elif isinstance(val, list):
            val = ", ".join(str(x) for x in val) if val else "(없음)"
        elif val == "":
            val = "(자동)"
        A("<tr><td>%s</td><td>%s</td></tr>" % (_e(lbl), _e(val)))
    A("</table>")

    A("<h2>5. 판정 기준 및 유의사항</h2>")
    A("<div class='note'><b>완전 일치</b>: 비교 단위의 내용이 동일한 경우입니다. "
      "수치는 유효자리 12자리로, 문자열은 앞뒤 공백을 제거한 뒤 비교합니다.<br>"
      "<b>근사 중복</b>: 수치는 지정한 소수점 자리로 반올림, 문자열은 공백·대소문자·유니코드 형태를 정규화한 뒤 "
      "비교하며, 텍스트 문서는 MinHash 기반 Jaccard 유사도, 이미지는 dHash 해밍거리로 판정합니다.<br>"
      "<b>유의</b>: 근사 중복은 통계적 추정에 기반하므로 소수의 오탐/미탐이 있을 수 있습니다. "
      "최종 판단은 표시된 위치의 원본 데이터를 확인하여 수행하시기 바랍니다.</div>")

    A("<div class='footer'>%s v%s · 생성 시각 %s · 이 리포트는 단일 HTML 파일로, "
      "브라우저에서 인쇄하여 PDF로 저장할 수 있습니다.</div>" %
      (_e(APP_NAME), APP_VERSION, _e(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))))
    A("</div></body></html>")
    return "".join(parts)


def write_report(result, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    name = "중복성검사_리포트_%s.html" % datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_html(result))
    result.report_path = path
    return path
