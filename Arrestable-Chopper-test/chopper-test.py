from __future__ import annotations

import csv
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from cffi import FFI
import matplotlib.pyplot as plt

# ----------------------------
# CONFIG
# ----------------------------
BENTHAM_VID = 1240

PID_417 = 5892
ADDR_487_ADC = 72

PID_418 = 4097   # updated chopper PID
ADDR_418_CHOPPER = 200

ADC_START_WAIT_S = 0.100
ADC_AFTER_R_WAIT_S = 0.010

WAIT_CHOPPER_ON_S = 17.500
WAIT_CHOPPER_OFF_S = 6.000

N_SAMPLES = 10
CYCLE_PAUSE_S = 0.5

ROLLING_WINDOW_SECONDS = 300
CSV_PATH = Path("adc_chopper_log.csv")

HERE = Path(__file__).resolve().parent
DLL_PATH = HERE / "dll" / "usbcomms64.dll"


# ----------------------------
# USB COMMS
# ----------------------------
class USBCommsCFFI:
    _CDEF = """
        int BI_usb_initialise(int pid, int vid);
        int BI_usb_send(int sendpid, int _addr, char* _msg);
        int BI_usb_enter(int enterpid, int _addr, char* _msg);
    """

    def __init__(self, dll_path: str):
        self._ffi = FFI()
        self._ffi.cdef(self._CDEF)

        dll_path = Path(dll_path).resolve()
        os.add_dll_directory(str(dll_path.parent))
        self._lib = self._ffi.dlopen(str(dll_path))

    def initialise(self, pid: int, vid: int) -> None:
        rc = int(self._lib.BI_usb_initialise(int(pid), int(vid)))
        if rc != 0:
            raise RuntimeError(f"Initialise failed pid={pid} rc={rc}")

    def send(self, pid: int, addr: int, msg: str) -> int:
        b = msg.encode("ascii")
        buf = self._ffi.new("char[]", len(b) + 1)
        self._ffi.memmove(buf, b, len(b))
        buf[len(b)] = b"\x00"
        return int(self._lib.BI_usb_send(int(pid), int(addr), buf))

    def enter_into(self, pid: int, addr: int, buf) -> int:
        return int(self._lib.BI_usb_enter(int(pid), int(addr), buf))


# ----------------------------
# ADC READ
# ----------------------------
def read_487_adc_once(usb: USBCommsCFFI) -> int:
    usb.send(PID_417, ADDR_487_ADC, "s")
    time.sleep(ADC_START_WAIT_S)

    usb.send(PID_417, ADDR_487_ADC, "r")
    time.sleep(ADC_AFTER_R_WAIT_S)

    buf = usb._ffi.new("char[]", 11)
    for i in range(11):
        buf[i] = b"\x00"

    usb.enter_into(PID_417, ADDR_487_ADC, buf)

    raw = usb._ffi.buffer(buf, 11)[:].decode("ascii", errors="replace")
    text = raw.replace("\x00", "").strip()

    digits = ""
    for ch in text:
        if ch.isdigit():
            digits += ch
        else:
            break

    return int(digits)


def read_487_adc_average(usb: USBCommsCFFI, n: int) -> float:
    vals = [read_487_adc_once(usb) for _ in range(n)]
    return sum(vals) / len(vals)


# ----------------------------
# CHOPPER
# ----------------------------
def chopper_on(usb):
    usb.send(PID_418, ADDR_418_CHOPPER, "N")


def chopper_off(usb):
    usb.send(PID_418, ADDR_418_CHOPPER, "O")


# ----------------------------
# CSV
# ----------------------------
def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def append_csv_row(path: Path, timestamp: str, state: str, avg: float) -> None:
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["timestamp_utc", "state", "adc_average"])
        w.writerow([timestamp, state, f"{avg:.0f}"])


# ----------------------------
# MAIN
# ----------------------------
def main() -> int:

    usb = USBCommsCFFI(str(DLL_PATH))
    usb.initialise(PID_417, BENTHAM_VID)
    usb.initialise(PID_418, BENTHAM_VID)

    # ---- Live Plot Setup ----
    plt.ion()
    fig, ax = plt.subplots()
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("487 ADC Reading")
    ax.set_ylim(0, 8000)
    ax.set_xlim(0, ROLLING_WINDOW_SECONDS)

    line, = ax.plot([], [], marker="o")

    fig.show()
    fig.canvas.draw()
    fig.canvas.flush_events()

    start_time = time.time()
    times = []
    values = []

    def update_plot():
        if not times:
            return

        current = times[-1]

        # rolling window trim
        while times and (current - times[0] > ROLLING_WINDOW_SECONDS):
            times.pop(0)
            values.pop(0)

        if current < ROLLING_WINDOW_SECONDS:
            ax.set_xlim(0, ROLLING_WINDOW_SECONDS)
        else:
            ax.set_xlim(current - ROLLING_WINDOW_SECONDS, current)

        line.set_xdata(times)
        line.set_ydata(values)

        ax.relim()
        ax.autoscale_view(scalex=False, scaley=False)

        fig.canvas.draw_idle()
        fig.canvas.flush_events()

    print("Running forever. Ctrl+C to stop.")

    try:
        while True:
            # CHOPPER ON
            chopper_on(usb)
            time.sleep(WAIT_CHOPPER_ON_S)

            avg_on = read_487_adc_average(usb, N_SAMPLES)
            print(f"chopper on  - {avg_on:.0f}")
            append_csv_row(CSV_PATH, utc_now_iso(), "chopper on", avg_on)

            now = time.time() - start_time
            times.append(now)
            values.append(avg_on)
            update_plot()

            # CHOPPER OFF
            chopper_off(usb)
            time.sleep(WAIT_CHOPPER_OFF_S)

            avg_off = read_487_adc_average(usb, N_SAMPLES)
            print(f"chopper off - {avg_off:.0f}")
            append_csv_row(CSV_PATH, utc_now_iso(), "chopper off", avg_off)

            now = time.time() - start_time
            times.append(now)
            values.append(avg_off)
            update_plot()

            time.sleep(CYCLE_PAUSE_S)

    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())