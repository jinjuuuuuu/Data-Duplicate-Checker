# -*- coding: utf-8 -*-
"""GUI 스모크 테스트: 가상 디스플레이에서 실제로 창을 띄우고 검사까지 수행한다.

실행: xvfb-run -s "-screen 0 1200x900x24" python3.12 tests/gui_smoke.py <sample_root>
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SAMPLE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/dlc_sample"
TRAIN = sys.argv[2] if len(sys.argv) > 2 else os.path.join(SAMPLE, "train")
TEST = sys.argv[3] if len(sys.argv) > 3 else os.path.join(SAMPLE, "test")
OUT = "/tmp/dlc_gui_out"


def shot(path):
    try:
        subprocess.run(["import", "-window", "root", path], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("스크린샷:", path)
    except Exception as e:
        print("스크린샷 실패:", e)


def main():
    import app as appmod
    a = appmod.App()
    a.geometry("1180x880+0+0")
    if not (os.path.isdir(TRAIN) and os.path.isdir(TEST)):
        print("경로 없음:", TRAIN, TEST)
        return 1
    a.v_train.set(TRAIN)
    a.v_test.set(TEST)
    a.v_out.set(OUT)
    a.v_open.set(False)
    a.v_sim.set(0.70)
    a.update()
    time.sleep(0.4)
    a.update()
    shot("/tmp/gui_before.png")

    a.on_run()
    deadline = time.time() + 180
    while time.time() < deadline:
        a.update()
        if a.result is not None and not (a.worker and a.worker.is_alive()):
            break
        time.sleep(0.05)
    for _ in range(20):
        a.update()
        time.sleep(0.05)
    shot("/tmp/gui_after.png")

    res = a.result
    print("판정:", None if res is None else res.verdict)
    if res:
        for c in res.categories:
            print("  %-26s exact=%d near=%d" % (c.label, c.exact_units, c.near_units))
        print("리포트:", res.report_path)
    rows = a.tree.get_children()
    print("요약표 행 수:", len(rows))
    log_len = len(a.log.get("1.0", "end"))
    print("로그 길이:", log_len)
    a.destroy()
    ok = res is not None and len(rows) == 5 and log_len > 100
    print("GUI 스모크:", "OK" if ok else "실패")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
