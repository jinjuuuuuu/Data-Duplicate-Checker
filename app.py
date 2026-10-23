# -*- coding: utf-8 -*-
"""AI 학습/시험 데이터 중복성 검사기 — GUI 진입점.

더블클릭 실행용. 표준 라이브러리 tkinter 만 사용한다.
"""
import json
import os
import queue
import sys
import threading
import traceback
import webbrowser

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from dupcheck.config import (APP_NAME, APP_VERSION, CATEGORY_LABELS, Config)

# 폴더 끌어다 놓기. tkinter 자체는 지원하지 않아 tkinterdnd2 를 쓴다.
# 없으면 끌어다 놓기만 빠지고 나머지는 그대로 동작한다(경로 붙여넣기·찾아보기).
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _BASE_TK = TkinterDnD.Tk
    DND_OK = True
except Exception:                                            # noqa: BLE001
    _BASE_TK = tk.Tk
    DND_FILES = None
    DND_OK = False

PAD = 8
# 화면 색·글꼴. 웹 화면과 같은 계열로 맞춘다.
FAM = "Malgun Gothic"
C_BG = "#ffffff"        # 배경 (칸 안팎 모두 흰색으로 두고 테두리로만 구분)
C_INK = "#1a1f26"       # 본문
C_MUTED = "#5f6b7a"     # 보조 설명
C_LINE = "#d8e0e9"      # 테두리
C_FIELD = "#fdfefe"     # 입력칸
C_HEAD = "#eef2f7"      # 표 머리글
C_PRI = "#1a56db"       # 강조 (칸 제목, 주 버튼)
C_PRI_ON = "#154bc4"    # 주 버튼 눌림
C_OK = "#127c4a"
C_WARN = "#8a5a00"
C_BAD = "#b3261e"
# 칸(LabelFrame) 사이 간격. PAD 는 칸 안쪽 여백이라 따로 둔다.
GAP = 18

def missing_deps():
    """무거운 의존 패키지는 실행 시점에 확인한다(EXE 가 아닌 소스 실행 대비)."""
    missing = []
    for mod, pipname in (("pandas", "pandas"), ("numpy", "numpy")):
        try:
            __import__(mod)
        except Exception:
            missing.append(pipname)
    return missing


def resource_path(name):
    """함께 배포한 파일의 실제 경로.

    EXE 로 묶으면 실행 시 임시 폴더(sys._MEIPASS)에 풀리므로 그쪽을 먼저 본다.
    소스로 실행할 때는 프로젝트 안의 위치도 찾아본다.
    """
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(base, name),
                 os.path.join(base, "web", "static", name)):
        if os.path.exists(cand):
            return cand
    return os.path.join(base, name)


def logo_photo(master, height=46):
    """제목 오른쪽에 넣을 로고 그림. 없으면 None.

    원본은 흰 배경 정사각형에 마크가 가운데만 차지한다. 그대로 줄이면
    마크가 작아 보이므로 흰 여백을 잘라낸 뒤 높이를 맞춘다.
    JPEG 는 tkinter 가 직접 읽지 못해 PNG 로 바꿔 넘긴다.
    """
    try:
        import base64
        from io import BytesIO
        from PIL import Image, ImageChops

        path = resource_path("logo.jpg")
        if not os.path.exists(path):
            return None
        im = Image.open(path).convert("RGB")
        # 흰 배경과 다른 부분만 남겨 실제 마크 영역을 찾는다
        diff = ImageChops.difference(im, Image.new("RGB", im.size, (255, 255, 255)))
        box = diff.convert("L").point(lambda v: 255 if v > 12 else 0).getbbox()
        if box:
            m = 2
            im = im.crop((max(0, box[0] - m), max(0, box[1] - m),
                          min(im.width, box[2] + m), min(im.height, box[3] + m)))
        w = max(1, int(round(im.width * height / float(im.height))))
        im = im.resize((w, int(height)), Image.LANCZOS)
        buf = BytesIO()
        im.save(buf, "PNG")
        return tk.PhotoImage(master=master,
                             data=base64.b64encode(buf.getvalue()).decode("ascii"))
    except Exception:                                        # noqa: BLE001
        return None


def downloads_dir():
    """Windows 다운로드 폴더 경로.

    사용자가 위치를 옮겼을 수 있으므로 레지스트리의 실제 값을 먼저 본다.
    (이 PC 처럼 바탕화면·문서가 OneDrive 로 리디렉션된 환경에서도 맞다)
    찾지 못하면 홈 폴더 아래 Downloads, 그것도 없으면 홈 폴더를 쓴다.
    """
    home = os.path.expanduser("~")
    guess = os.path.join(home, "Downloads")
    try:
        import winreg
        key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            path, _ = winreg.QueryValueEx(k, "{374DE290-123F-4565-9164-39C4925E467B}")
        path = os.path.expandvars(path or "")
        if path and os.path.isdir(path):
            return os.path.normpath(path)
    except Exception:                                        # noqa: BLE001
        pass
    return guess if os.path.isdir(guess) else home


def base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


SETTINGS_PATH = os.path.join(base_dir(), "settings.json")


def enable_dpi():
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            from ctypes import windll
            windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class App(_BASE_TK):
    def __init__(self):
        super().__init__()
        self.title("%s v%s" % (APP_NAME, APP_VERSION))
        # 기본 창 크기. 내용이 한 화면에 최대한 들어오게 키우되
        # 작은 모니터에서 화면 밖으로 나가지 않도록 제한한다.
        _sw, _sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry("%dx%d" % (min(1080, _sw - 80), min(940, _sh - 120)))
        # 스크롤이 있으므로 작은 화면에서도 쓸 수 있다
        self.minsize(820, 520)
        self.q = queue.Queue()
        self.worker = None
        self.cancel_event = threading.Event()
        self.result = None

        self.v_train = tk.StringVar()
        self.v_test = tk.StringVar()
        self.v_out = tk.StringVar(value=downloads_dir())
        self.v_file = tk.BooleanVar(value=True)
        # 형식별 검사는 화면에서 고르지 않는다. 들어온 형식은 모두 검사한다.
        # 설정 파일에 옛 값이 남아 있어도 되살아나지 않도록 저장·복원에서 제외한다.
        self.v_tab = tk.BooleanVar(value=True)
        self.v_img = tk.BooleanVar(value=True)
        self.v_txt = tk.BooleanVar(value=True)
        self.v_arr = tk.BooleanVar(value=True)
        self.v_exact = tk.BooleanVar(value=True)
        self.v_near = tk.BooleanVar(value=True)
        self.v_excl = tk.StringVar()
        self.v_keys = tk.StringVar()
        self.v_order = tk.BooleanVar(value=True)
        self.v_dec = tk.IntVar(value=4)
        self.v_cellnorm = tk.BooleanVar(value=True)
        self.v_sim = tk.DoubleVar(value=0.80)
        self.v_ham = tk.IntVar(value=5)
        self.v_maxrows = tk.IntVar(value=0)
        self.v_cap = tk.IntVar(value=300)
        self.v_open = tk.BooleanVar(value=True)
        self.v_status = tk.StringVar(value="폴더를 지정하고 [검사 시작]을 누르세요.")

        self._build()
        self._load_settings()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(120, self._pump)

    # ---------------- 화면 스타일 ----------------
    def _style(self):
        """색을 다룰 수 있는 clam 테마 위에 팔레트를 얹는다."""
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except Exception:                                    # noqa: BLE001
            pass
        self.configure(background=C_BG)

        base = (FAM, 10)
        st.configure(".", background=C_BG, foreground=C_INK, font=base,
                     focuscolor=C_PRI)
        st.configure("TFrame", background=C_BG)
        st.configure("TLabel", background=C_BG, foreground=C_INK)
        # clam 기본 체크 표시는 취소 표시처럼 보여서 직접 칠한다.
        st.configure("TCheckbutton", background=C_BG, foreground=C_INK,
                     indicatorbackground=C_FIELD, indicatorforeground="#ffffff",
                     indicatorsize=13, indicatormargin=(0, 0, 8, 0),
                     upperbordercolor=C_LINE, lowerbordercolor=C_LINE,
                     padding=(0, 3))
        st.map("TCheckbutton",
               background=[("active", C_BG)],
               indicatorbackground=[("selected", C_PRI), ("active", "#eef3fc"),
                                    ("disabled", "#f1f4f8")],
               indicatorforeground=[("selected", "#ffffff")],
               upperbordercolor=[("selected", C_PRI), ("disabled", C_LINE)],
               lowerbordercolor=[("selected", C_PRI), ("disabled", C_LINE)])
        st.configure("TSeparator", background=C_LINE)

        # 칸: 테두리 + 굵은 파랑 제목
        st.configure("TLabelframe", background=C_BG, bordercolor=C_LINE,
                     relief="solid", borderwidth=1, padding=PAD)
        st.configure("TLabelframe.Label", background=C_BG, foreground=C_PRI,
                     font=(FAM, 10, "bold"))

        # 제목·보조 문구
        st.configure("H1.TLabel", font=(FAM, 15, "bold"), foreground=C_INK)
        st.configure("Sub.TLabel", font=base, foreground=C_MUTED)
        st.configure("Muted.TLabel", font=(FAM, 9), foreground=C_MUTED)
        st.configure("Item.TLabel", font=(FAM, 10, "bold"), foreground=C_INK)

        # 입력칸
        for name in ("TEntry", "TSpinbox"):
            st.configure(name, fieldbackground=C_FIELD, background=C_BG,
                         foreground=C_INK, bordercolor=C_LINE,
                         lightcolor=C_LINE, darkcolor=C_LINE,
                         insertcolor=C_INK, padding=4)
            st.map(name, bordercolor=[("focus", C_PRI)])

        # 버튼: 기본은 담백하게, 주 버튼만 색을 준다
        st.configure("TButton", background="#f3f5f8", foreground=C_INK,
                     bordercolor=C_LINE, lightcolor="#f3f5f8",
                     darkcolor="#f3f5f8", relief="solid", borderwidth=1,
                     padding=(12, 6), font=base)
        st.map("TButton",
               background=[("pressed", "#e4e9f0"), ("active", "#eaeff5"),
                           ("disabled", "#f7f9fb")],
               foreground=[("disabled", "#a9b3bf")])

        st.configure("Go.TButton", background=C_PRI, foreground="#ffffff",
                     bordercolor=C_PRI, lightcolor=C_PRI, darkcolor=C_PRI,
                     font=(FAM, 11, "bold"), padding=(22, 9))
        st.map("Go.TButton",
               background=[("pressed", C_PRI_ON), ("active", "#2a62df"),
                           ("disabled", "#b8c6e6")],
               bordercolor=[("disabled", "#b8c6e6")],
               foreground=[("disabled", "#eef2fb")])

        # 접이식 토글은 링크처럼
        st.configure("Link.TButton", background=C_BG, foreground=C_PRI,
                     bordercolor=C_BG, lightcolor=C_BG, darkcolor=C_BG,
                     relief="flat", padding=(0, 4), font=(FAM, 10, "bold"))
        st.map("Link.TButton", background=[("active", C_BG), ("pressed", C_BG)])

        # 진행률
        st.configure("TProgressbar", troughcolor="#eef2f7", background=C_PRI,
                     bordercolor=C_LINE, lightcolor=C_PRI, darkcolor=C_PRI,
                     thickness=10)

        # 결과 표
        st.configure("Treeview", background=C_BG, fieldbackground=C_BG,
                     foreground=C_INK, bordercolor=C_LINE, rowheight=27,
                     font=base)
        st.configure("Treeview.Heading", background=C_HEAD, foreground=C_INK,
                     font=(FAM, 9, "bold"), relief="flat", padding=(6, 6))
        st.map("Treeview.Heading", background=[("active", C_HEAD)])
        st.map("Treeview", background=[("selected", "#dbe6fb")],
               foreground=[("selected", C_INK)])

        # 탭
        st.configure("TNotebook", background=C_BG, bordercolor=C_LINE)
        st.configure("TNotebook.Tab", background="#f1f4f8", foreground=C_MUTED,
                     bordercolor=C_LINE, padding=(18, 8), font=base)
        st.map("TNotebook.Tab",
               background=[("selected", C_BG)],
               foreground=[("selected", C_PRI)],
               font=[("selected", (FAM, 10, "bold"))])

        # 스크롤바
        st.configure("TScrollbar", background="#f1f4f8", troughcolor=C_BG,
                     bordercolor=C_LINE, arrowcolor=C_MUTED)

    # ---------------- UI ----------------
    def _build(self):
        self._style()

        # 내용이 창보다 길어질 수 있으므로 전체를 스크롤 영역에 담는다.
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True)
        self._canvas = tk.Canvas(outer, highlightthickness=0, borderwidth=0,
                                 background=C_BG)
        vbar = ttk.Scrollbar(outer, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vbar.set)
        vbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        root = ttk.Frame(self._canvas, padding=PAD)
        self._canvas_win = self._canvas.create_window((0, 0), window=root, anchor="nw")
        # 안쪽 프레임 폭을 캔버스 폭에 맞춘다(가로로 채우는 위젯이 제대로 늘어나게)
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfigure(self._canvas_win, width=e.width))
        # 내용 크기가 바뀌면 스크롤 범위를 다시 계산한다
        root.bind(
            "<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self.bind_all("<MouseWheel>", self._on_wheel)

        head = ttk.Frame(root)
        head.pack(fill="x")
        titles = ttk.Frame(head)
        titles.pack(side="left", fill="x", expand=True)
        ttk.Label(titles, text="AI 학습/시험 데이터 중복성 검사",
                  style="H1.TLabel").pack(anchor="w")
        ttk.Label(titles, text="학습데이터와 시험데이터 폴더를 지정하면 중복(데이터 누출) 여부를 "
                              "자동으로 검사하고 HTML 리포트를 만듭니다.",
                  style="Sub.TLabel").pack(anchor="w", pady=(2, PAD))
        # 로고는 참조를 붙들고 있지 않으면 사라지므로 self 에 보관한다
        self._logo = logo_photo(self, height=46)
        if self._logo is not None:
            ttk.Label(head, image=self._logo).pack(side="right", anchor="ne",
                                                   padx=(PAD, 2))

        # 경로
        f1 = ttk.LabelFrame(root, text=" 폴더 지정 ", padding=PAD)
        if DND_OK:
            ttk.Label(f1, text="폴더를 이 칸에 끌어다 놓거나, 경로를 붙여넣거나, "
                              "[찾아보기]로 고르세요.",
                      style="Muted.TLabel").grid(row=99, column=0, columnspan=3,
                                                 sticky="w", pady=(8, 0))
        f1.pack(fill="x")
        self._path_row(f1, 0, "학습데이터 폴더", self.v_train)
        self._path_row(f1, 1, "시험데이터 폴더", self.v_test)
        self._path_row(f1, 2, "리포트 저장 폴더 (기본: 다운로드 폴더)", self.v_out)
        f1.columnconfigure(1, weight=1)


        # 검사 가능 항목 — 고르는 것이 아니라 무엇이 검사되는지 알려주는 자리
        f2 = ttk.LabelFrame(root, text=" 검사 가능 항목 ", padding=PAD)
        f2.pack(fill="x", pady=(GAP, 0))
        ttk.Label(f2, text="아래 형식을 자동으로 알아보고 모두 검사합니다. "
                          "한 폴더에 섞여 있어도 됩니다.",
                  style="Muted.TLabel", wraplength=880,
                  justify="left").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        caps = [
            ("정형 테이블", "CSV · TSV · Excel(xlsx/xlsm/xls) · Parquet · PKL — 행 단위"),
            ("이미지", "JPG · PNG · BMP · GIF · TIF · WebP · PPM — 장 단위"),
            ("텍스트 · JSON", "TXT · MD · JSON · JSONL · NDJSON — 문서 단위"),
            ("NumPy 배열", "NPY · NPZ · PKL 안의 배열 — 샘플 단위"),
            ("영상 · 음성 · 압축파일 등", "아래 [파일 단위 동일성]으로 바이트까지 똑같은 파일만"),
        ]
        for i, (name, desc) in enumerate(caps, start=1):
            ttk.Label(f2, text=name, style="Item.TLabel").grid(
                row=i, column=0, sticky="nw", pady=3)
            ttk.Label(f2, text=desc, style="Muted.TLabel", wraplength=680,
                      justify="left").grid(row=i, column=1, sticky="w", padx=(14, 0), pady=3)
        f2.columnconfigure(1, weight=1)

        # 판정 기준
        f3 = ttk.LabelFrame(root, text=" 판정 기준 ", padding=PAD)
        f3.pack(fill="x", pady=(GAP, 0))
        self._check(f3, text="파일 단위 동일성 (같은 파일이 양쪽에 존재)",
                        variable=self.v_file).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(f3, text="양쪽 폴더에 README.txt 같은 부수 파일이 똑같이 들어 있어 "
                          "중복으로 잡힐 때 끕니다.",
                  style="Muted.TLabel", wraplength=880,
                  justify="left").grid(row=1, column=0, columnspan=2,
                                       sticky="w", padx=(22, 0), pady=(0, 6))
        ttk.Separator(f3, orient="horizontal").grid(row=2, column=0, columnspan=2,
                                                    sticky="ew", pady=(2, 6))
        self._check(f3, text="완전 일치 (내용이 동일)", variable=self.v_exact).grid(row=3, column=0, columnspan=2, sticky="w")
        self._check(f3, text="근사 중복 (허용오차·정규화·유사도)", variable=self.v_near).grid(row=4, column=0, columnspan=2, sticky="w")
        self._spin_row(f3, 5, "수치 허용오차 (소수점 자리)", self.v_dec, 0, 12, 1)
        self._spin_row(f3, 6, "텍스트 유사도 임계값 (0~1)", self.v_sim, 0.3, 1.0, 0.01)
        self._spin_row(f3, 7, "이미지 해밍거리 임계값 (0~16)", self.v_ham, 0, 16, 1)
        f3.columnconfigure(1, weight=1)

        # 근사 중복 값 설정 예시 — 접어 두고 눌렀을 때만 펼친다
        self._build_tips(root)

        # 상세 옵션
        f4 = ttk.LabelFrame(root, text=" 정형 테이블 상세 옵션 ", padding=PAD)
        f4.pack(fill="x", pady=(GAP, 0))
        ttk.Label(f4, text="제외 컬럼").grid(row=0, column=0, sticky="w")
        ttk.Entry(f4, textvariable=self.v_excl).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ttk.Label(f4, text="기준 컬럼 (지정 시 이 컬럼만 비교)").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(f4, textvariable=self.v_keys).grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=(4, 0))
        opts = ttk.Frame(f4)
        opts.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        # 컬럼 순서 무시 · 셀 공백/대소문자 무시는 끄면 오탐만 늘어
        # 화면에서 감추고 항상 켠 상태로 둔다(웹 화면과 동일).
        ttk.Label(opts, text="파일당 최대 행(0=무제한)").pack(side="left", padx=(0, 4))
        ttk.Spinbox(opts, from_=0, to=100000000, increment=10000, textvariable=self.v_maxrows, width=12).pack(side="left")
        ttk.Label(opts, text="리포트 표시 상한").pack(side="left", padx=(16, 4))
        ttk.Spinbox(opts, from_=10, to=5000, increment=50, textvariable=self.v_cap, width=8).pack(side="left")
        f4.columnconfigure(1, weight=1)

        # 실행
        f5 = ttk.Frame(root)
        f5.pack(fill="x", pady=(GAP, 0))
        self.btn_run = ttk.Button(f5, text="검사 시작", command=self.on_run,
                                  style="Go.TButton")
        self.btn_run.pack(side="left")
        self.btn_stop = ttk.Button(f5, text="중지", command=self.on_stop, state="disabled")
        self.btn_stop.pack(side="left", padx=(8, 0))
        self.btn_report = ttk.Button(f5, text="리포트 열기", command=self.on_open_report, state="disabled")
        self.btn_report.pack(side="left", padx=(8, 0))
        self._check(f5, text="검사 후 리포트 자동 열기", variable=self.v_open).pack(side="left", padx=(14, 0))
        self.lbl_verdict = ttk.Label(f5, text="", font=(FAM, 12, "bold"))
        self.lbl_verdict.pack(side="right")

        self.pb = ttk.Progressbar(root, mode="determinate", maximum=100)
        self.pb.pack(fill="x", pady=(6, 2))
        ttk.Label(root, textvariable=self.v_status,
                  foreground=C_MUTED).pack(anchor="w", pady=(2, 0))

        # 결과
        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, pady=(GAP, 0))
        tab1 = ttk.Frame(nb, padding=4)
        tab2 = ttk.Frame(nb, padding=4)
        nb.add(tab1, text="  요약  ")
        nb.add(tab2, text="  진행 로그  ")

        cols = ("cat", "tr", "te", "ex", "nr", "rate", "rf", "vd")
        self.tree = ttk.Treeview(tab1, columns=cols, show="headings", height=7)
        heads = [("cat", "검사 항목", 210), ("tr", "학습 단위", 95), ("te", "시험 단위", 95),
                 ("ex", "완전 일치", 85), ("nr", "근사 중복", 85), ("rate", "중복률", 75),
                 ("rf", "읽기 실패", 85), ("vd", "판정", 70)]
        for key, txt, w in heads:
            self.tree.heading(key, text=txt)
            self.tree.column(key, width=w, anchor="center" if key != "cat" else "w")
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(tab1, orient="vertical", command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.tag_configure("bad", foreground=C_BAD)
        self.tree.tag_configure("warn", foreground=C_WARN)
        self.tree.tag_configure("ok", foreground=C_OK)

        self.log = tk.Text(tab2, height=12, wrap="none", font=("Consolas", 10),
                           background="#fbfcfd", foreground=C_INK,
                           relief="flat", borderwidth=0, padx=8, pady=6,
                           insertbackground=C_INK)
        self.log.pack(side="left", fill="both", expand=True)
        sb2 = ttk.Scrollbar(tab2, orient="vertical", command=self.log.yview)
        sb2.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=sb2.set, state="disabled")

    def _path_row(self, parent, row, label, var):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w",
                                           pady=4, padx=(0, 12))
        ent = ttk.Entry(parent, textvariable=var)
        ent.grid(row=row, column=1, sticky="ew", padx=6)
        ttk.Button(parent, text="찾아보기…", width=11,
                   command=lambda v=var: self._pick(v)).grid(row=row, column=2, sticky="e")
        self._make_drop_target(ent, var)

    def _on_wheel(self, event):
        """마우스 휠로 전체 화면을 스크롤한다.

        자체 스크롤이 있는 위젯(결과 표·진행 로그·스핀박스) 위에서는
        그쪽이 처리하도록 두고 여기서는 아무것도 하지 않는다.
        """
        try:
            cls = event.widget.winfo_class()
        except Exception:                                    # noqa: BLE001
            return
        if cls in ("Text", "Treeview", "Listbox", "Spinbox", "TSpinbox", "TCombobox"):
            return
        try:
            first, last = self._canvas.yview()
        except Exception:                                    # noqa: BLE001
            return
        if first <= 0.0 and last >= 1.0:
            return                                           # 스크롤할 것이 없다
        self._canvas.yview_scroll(int(-event.delta / 120), "units")

    # ---------------- 끌어다 놓기 ----------------
    def _make_drop_target(self, widget, var):
        """입력칸에 폴더를 끌어다 놓을 수 있게 한다."""
        if not DND_OK:
            return
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", lambda e, v=var: self._on_drop(e, v))
        # 끌고 들어왔을 때 어디에 놓이는지 보이게 한다
        widget.dnd_bind("<<DropEnter>>", lambda e, w=widget: (w.state(["focus"]), None)[1])
        widget.dnd_bind("<<DropLeave>>", lambda e, w=widget: (w.state(["!focus"]), None)[1])

    @staticmethod
    def parse_drop(data):
        """드롭 데이터에서 경로 목록을 뽑는다.

        Windows 는 공백이 든 경로를 {C:\my folder} 처럼 중괄호로 감싸 보낸다.
        여러 개를 한 번에 놓으면 공백으로 이어 붙여 온다.
        """
        out, buf, brace = [], "", False
        for ch in data or "":
            if ch == "{" and not brace and not buf:
                brace = True
            elif ch == "}" and brace:
                brace = False
                if buf:
                    out.append(buf)
                buf = ""
            elif ch == " " and not brace:
                if buf:
                    out.append(buf)
                buf = ""
            else:
                buf += ch
        if buf:
            out.append(buf)
        return out

    def _on_drop(self, event, var):
        try:
            event.widget.state(["!focus"])
        except Exception:                                    # noqa: BLE001
            pass
        raw = getattr(event, "data", "") or ""
        # 공백이 든 경로는 보통 {…} 로 감싸져 오지만, 그대로 오는 경우도 있다.
        # 통째로 본 것을 먼저 시도하고, 아니면 쪼개서 첫 번째를 쓴다.
        whole = raw.strip().strip("{}")
        candidates = ([whole] if whole else []) + self.parse_drop(raw)
        target = ""
        for c in candidates:
            if os.path.exists(c):
                target = c
                break
        if not target:
            target = candidates[0] if candidates else ""
        if not target:
            return
        target = os.path.normpath(target)
        if os.path.isdir(target):
            var.set(target)
            self.v_status.set("폴더를 지정했습니다: %s" % target)
            return
        if os.path.isfile(target):
            # 엔진은 폴더 단위로 검사한다. 파일을 놓으면 그 파일이 든 폴더를 쓴다.
            folder = os.path.dirname(target)
            var.set(folder)
            self.v_status.set("파일이 아니라 그 파일이 있는 폴더를 지정했습니다: %s" % folder)
            return
        self.v_status.set("경로를 읽을 수 없습니다: %s" % target)

    def _build_tips(self, root):
        """근사 중복 임계값을 어떻게 정하는지 예시. 기본은 접힌 상태."""
        wrap = ttk.Frame(root)
        wrap.pack(fill="x", pady=(GAP, 0))
        self._tips_open = False
        self._tips_btn = ttk.Button(wrap, text="▸  근사 중복 값 설정 예시",
                                    style="Link.TButton", command=self._toggle_tips)
        self._tips_btn.pack(anchor="w")

        self._tips_box = ttk.LabelFrame(wrap, text=" 예시 ", padding=PAD)
        ttk.Label(self._tips_box,
                  text="기본값 그대로 두어도 대부분 맞습니다. 엄격하게 하면 놓치는 중복이 늘고, "
                       "느슨하게 하면 중복이 아닌 것까지 잡힙니다.",
                  foreground="#5f6b7a", wraplength=880,
                  justify="left").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        tips = [
            ("수치 허용오차 — 소수점 자리", None),
            ("4  기본", "일반적인 실수 특징값. 소수 5째 자리 이하 차이는 같은 값으로 봅니다"),
            ("6~8  엄격", "좌표·센서 측정값처럼 미세한 차이가 의미 있을 때"),
            ("2  느슨", "금액·비율처럼 이미 반올림된 값"),
            ("0", "정수로 취급. 소수점 아래를 아예 무시"),
            ("텍스트 유사도 임계값", None),
            ("0.80  기본", "단어 몇 개를 바꿔 쓴 정도의 재작성까지 잡습니다"),
            ("0.90  엄격", "거의 그대로 베낀 문서만. 오탐을 줄이고 싶을 때"),
            ("0.60~0.70  느슨", "문장 순서를 바꾸거나 요약한 변형까지. 서식이 같은 정형 문서에서는 오탐이 늘어납니다"),
            ("이미지 해밍거리 임계값", None),
            ("5  기본", "크기 변경·재압축·약한 보정을 거친 같은 사진"),
            ("0~2  엄격", "사실상 같은 이미지만"),
            ("8 이상  느슨", "잘라내기·색보정까지. 다만 7을 넘으면 후보를 좁히는 방식의 한계로 일부 유사쌍을 놓칠 수 있습니다"),
        ]
        r = 1
        for key, desc in tips:
            if desc is None:
                ttk.Label(self._tips_box, text=key,
                          font=("Malgun Gothic", 9, "bold")).grid(
                    row=r, column=0, columnspan=2, sticky="w", pady=(8, 2))
            else:
                ttk.Label(self._tips_box, text=key, foreground="#5f6b7a").grid(
                    row=r, column=0, sticky="nw", padx=(12, 0))
                ttk.Label(self._tips_box, text=desc, wraplength=740,
                          justify="left").grid(row=r, column=1, sticky="w", padx=(12, 0))
            r += 1
        ttk.Label(self._tips_box,
                  text="완전히 같은 것만 찾고 싶으면 위의 [근사 중복] 체크를 끄면 됩니다. "
                       "그러면 이 세 값은 쓰이지 않습니다.",
                  foreground="#5f6b7a", wraplength=880,
                  justify="left").grid(row=r, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self._tips_box.columnconfigure(1, weight=1)

    def _toggle_tips(self):
        self._tips_open = not self._tips_open
        if self._tips_open:
            self._tips_box.pack(fill="x", pady=(6, 0))
            self._tips_btn.config(text="▾  근사 중복 값 설정 예시")
        else:
            self._tips_box.pack_forget()
            self._tips_btn.config(text="▸  근사 중복 값 설정 예시")

    def _check(self, parent, text="", variable=None, **kw):
        """체크박스. clam 의 ✕ 표시 대신 Windows 기본 체크(✓)를 쓰기 위해
        ttk 가 아닌 고전 위젯을 색만 맞춰서 쓴다."""
        return tk.Checkbutton(parent, text=text, variable=variable,
                              background=C_BG, activebackground=C_BG,
                              foreground=C_INK, activeforeground=C_INK,
                              selectcolor="#ffffff", font=(FAM, 10),
                              anchor="w", padx=0, pady=2,
                              borderwidth=0, highlightthickness=0,
                              cursor="hand2", **kw)

    def _spin_row(self, parent, row, label, var, lo, hi, inc):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Spinbox(parent, from_=lo, to=hi, increment=inc, textvariable=var, width=8).grid(
            row=row, column=1, sticky="w", padx=(6, 0))

    def _pick(self, var):
        init = var.get() or os.path.expanduser("~")
        d = filedialog.askdirectory(title="폴더 선택", initialdir=init if os.path.isdir(init) else None)
        if d:
            var.set(os.path.normpath(d))

    # ---------------- 설정 저장/복원 ----------------
    def _settings_dict(self):
        return {
            "train": self.v_train.get(), "test": self.v_test.get(), "out": self.v_out.get(),
            "file": self.v_file.get(),
            "exact": self.v_exact.get(), "near": self.v_near.get(),
            "excl": self.v_excl.get(), "keys": self.v_keys.get(),
            "dec": self.v_dec.get(),
            "sim": self.v_sim.get(), "ham": self.v_ham.get(),
            "maxrows": self.v_maxrows.get(), "cap": self.v_cap.get(), "open": self.v_open.get(),
        }

    def _load_settings(self):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            return
        pairs = [("train", self.v_train), ("test", self.v_test), ("out", self.v_out),
                 ("file", self.v_file), ("exact", self.v_exact),
                 ("near", self.v_near), ("excl", self.v_excl), ("keys", self.v_keys),
                 ("dec", self.v_dec),
                 ("sim", self.v_sim), ("ham", self.v_ham), ("maxrows", self.v_maxrows),
                 ("cap", self.v_cap), ("open", self.v_open)]
        for k, var in pairs:
            if k not in d:
                continue
            # 예전 설정에 빈 값이 남아 있으면 기본값(다운로드 폴더)을 덮어쓰지 않는다
            if k == "out" and not str(d[k] or "").strip():
                continue
            try:
                var.set(d[k])
            except Exception:
                pass

    def _save_settings(self):
        try:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(self._settings_dict(), f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------------- 실행 ----------------
    def _collect_config(self):
        def split(s):
            return [x.strip() for x in s.replace(";", ",").split(",") if x.strip()]

        def num(var, default):
            try:
                return var.get()
            except Exception:
                return default

        return Config(
            train_dir=self.v_train.get().strip().strip('"'),
            test_dir=self.v_test.get().strip().strip('"'),
            out_dir=self.v_out.get().strip().strip('"'),
            check_file=self.v_file.get(), check_tabular=self.v_tab.get(),
            check_image=self.v_img.get(), check_text=self.v_txt.get(),
            check_array=self.v_arr.get(),
            exact=self.v_exact.get(), near=self.v_near.get(),
            exclude_columns=split(self.v_excl.get()), key_columns=split(self.v_keys.get()),
            ignore_column_order=self.v_order.get(),
            float_decimals=int(num(self.v_dec, 4)),
            text_cell_normalize=self.v_cellnorm.get(),
            text_similarity=float(num(self.v_sim, 0.80)),
            image_hamming=int(num(self.v_ham, 5)),
            max_rows_per_file=int(num(self.v_maxrows, 0)),
            max_samples_in_report=int(num(self.v_cap, 300)),
            open_report=self.v_open.get(),
        )

    def on_run(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            cfg = self._collect_config()
        except Exception as e:
            messagebox.showerror("설정 오류", str(e))
            return
        if not os.path.isdir(cfg.train_dir):
            messagebox.showwarning("경로 확인", "학습데이터 폴더 경로가 올바르지 않습니다.")
            return
        if not os.path.isdir(cfg.test_dir):
            messagebox.showwarning("경로 확인", "시험데이터 폴더 경로가 올바르지 않습니다.")
            return
        if not (cfg.exact or cfg.near):
            messagebox.showwarning("판정 기준", "완전 일치 또는 근사 중복 중 하나 이상을 선택하세요.")
            return
        if not cfg.enabled_categories():
            messagebox.showwarning("검사 항목", "검사할 항목을 하나 이상 선택하세요.")
            return
        if os.path.abspath(cfg.train_dir) == os.path.abspath(cfg.test_dir):
            if not messagebox.askyesno("경로 동일", "학습/시험 폴더가 동일합니다. 그래도 진행할까요?"):
                return

        self._save_settings()
        self.tree.delete(*self.tree.get_children())
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.lbl_verdict.configure(text="")
        self.result = None
        self.btn_run.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_report.configure(state="disabled")
        self.pb.configure(value=0)
        self.cancel_event.clear()
        self.v_status.set("검사 중…")

        self.worker = threading.Thread(target=self._work, args=(cfg,), daemon=True)
        self.worker.start()

    def _work(self, cfg):
        put = self.q.put
        try:
            from dupcheck.engine import run_check
            from dupcheck.report import write_report
            res = run_check(
                cfg,
                log=lambda m: put(("log", m)),
                progress=lambda d, t, m="": put(("prog", d, t)),
                cancel_check=self.cancel_event.is_set,
            )
            out_dir = cfg.out_dir
            if not out_dir:
                parent = os.path.dirname(os.path.abspath(cfg.test_dir))
                out_dir = os.path.join(parent, "중복성검사_결과")
            try:
                path = write_report(res, out_dir)
                put(("log", "리포트 저장: %s" % path))
            except Exception as e:
                put(("log", "리포트 저장 실패(%s). 홈 폴더에 저장합니다." % e))
                path = write_report(res, os.path.join(os.path.expanduser("~"), "중복성검사_결과"))
                put(("log", "리포트 저장: %s" % path))
            put(("done", res))
        except Exception:
            put(("err", traceback.format_exc()))

    def on_stop(self):
        self.cancel_event.set()
        self.v_status.set("중지 요청… 현재 파일 처리 후 종료합니다.")

    def on_open_report(self):
        if not (self.result and self.result.report_path):
            return
        p = self.result.report_path
        try:
            if os.name == "nt":
                os.startfile(p)  # noqa
            else:
                webbrowser.open("file://" + p)
        except Exception as e:
            messagebox.showerror("열기 실패", "%s\n\n경로: %s" % (e, p))

    # ---------------- 메시지 펌프 ----------------
    def _pump(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self._append_log(msg[1])
                elif kind == "prog":
                    d, t = msg[1], msg[2]
                    self.pb.configure(maximum=max(1, t), value=min(d, t))
                    self.v_status.set("검사 중… %d / %d 파일" % (d, t))
                elif kind == "done":
                    self._finish(msg[1])
                elif kind == "err":
                    self._append_log(msg[1])
                    self._reset_buttons()
                    self.v_status.set("오류로 중단되었습니다. 진행 로그를 확인하세요.")
                    messagebox.showerror("검사 오류", msg[1].strip().splitlines()[-1])
        except queue.Empty:
            pass
        self.after(120, self._pump)

    def _append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _reset_buttons(self):
        self.btn_run.configure(state="normal")
        self.btn_stop.configure(state="disabled")

    def _finish(self, res):
        self.result = res
        self._reset_buttons()
        self.pb.configure(maximum=100, value=100)
        for c in res.categories:
            if not c.ran:
                continue
            if c.exact_units:
                tag, vd = "bad", "중복"
            elif c.near_units:
                tag, vd = "warn", "유사"
            else:
                tag, vd = "ok", "정상"
            self.tree.insert("", "end", values=(
                CATEGORY_LABELS.get(c.key, c.label),
                "{:,}{}".format(c.train_units, c.unit_name),
                "{:,}{}".format(c.test_units, c.unit_name),
                "{:,}".format(c.exact_units),
                "{:,}".format(c.near_units),
                "%.2f%%" % c.leak_rate,
                "{:,}".format(c.read_fail),
                vd), tags=(tag,))
        v = res.verdict
        color = {"PASS": "#127c4a", "WARN": "#8a5a00", "FAIL": "#b3261e"}[v]
        text = {"PASS": "판정: 중복 없음", "WARN": "판정: 근사 중복 발견", "FAIL": "판정: 중복 발견"}[v]
        if res.cancelled:
            text += " (부분 검사)"
        self.lbl_verdict.configure(text=text, foreground=color)
        self.v_status.set("완료 · %.1f초 · 중복 %s건 · 리포트: %s"
                          % (res.elapsed_sec, "{:,}".format(res.total_dup), res.report_path or "-"))
        if res.report_path:
            self.btn_report.configure(state="normal")
            if self.v_open.get():
                self.on_open_report()

    def _on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("종료", "검사가 진행 중입니다. 종료할까요?"):
                return
            self.cancel_event.set()
        self._save_settings()
        self.destroy()


def main():
    enable_dpi()
    try:
        app = App()
    except tk.TclError as e:
        print("GUI를 초기화할 수 없습니다: %s" % e)
        return 1
    miss = missing_deps()
    if miss:
        messagebox.showwarning(
            "필수 패키지 없음",
            "다음 패키지가 설치되어 있지 않아 검사를 실행할 수 없습니다.\n\n  %s\n\n"
            "명령 프롬프트에서 아래를 실행한 뒤 다시 시도하세요.\n"
            "  python -m pip install pandas numpy pillow openpyxl" % ", ".join(miss))
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
