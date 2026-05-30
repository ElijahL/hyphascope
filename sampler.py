#!/usr/bin/env python3
"""Fungal signal sampler — reads the ADS1115 and logs to SQLite, forever.

This is the ONLY process that touches the hardware, so it stays dumb and
crash-resistant: a bad ADC read is logged and skipped, never fatal. Spike
detection and analysis deliberately live elsewhere (on the host that runs the
MCP server) — the Pi's job is just to capture clean raw data and not lose it.

Environment variables:
  SAMPLE_HZ    samples per second        (default 1.0 — matches the research)
  ADC_ADDRESS  I2C address of the ADS1115 (default 0x48, set by ADDR->GND)
  SIMULATE     "1" to generate synthetic data with no hardware attached
"""
import os
import sys
import time
import math
import random
import signal

from dotenv import load_dotenv

import db

load_dotenv()

SAMPLE_HZ = float(os.environ.get("SAMPLE_HZ", "1.0"))
ADC_ADDRESS = int(os.environ.get("ADC_ADDRESS", "0x48"), 16)
SIMULATE = os.environ.get("SIMULATE", "0") == "1"

_running = True


def _stop(signum, frame):
    global _running
    _running = False


signal.signal(signal.SIGINT, _stop)
signal.signal(signal.SIGTERM, _stop)


def make_reader():
    """Return a read() -> (voltage, raw) function for the chosen backend."""
    if SIMULATE:
        print("[sampler] SIMULATE=1 — generating synthetic fungal-like signal")
        start = time.time()
        spike_left = 0

        def read():
            nonlocal spike_left
            t = time.time() - start
            drift = 0.05 * math.sin(t / 90.0)          # slow baseline wander
            if spike_left == 0 and random.random() < 0.01:
                spike_left = random.randint(3, 12)      # begin a slow spike
            spike = 0.0
            if spike_left > 0:
                spike = random.uniform(0.15, 0.35)
                spike_left -= 1
            noise = random.gauss(0, 0.004)
            v = 0.5 + drift + spike + noise             # volts, arbitrary baseline
            return v, int(max(0.0, v) / 4.096 * 32767)
        return read

    # Real hardware path (Raspberry Pi + ADS1115 over I2C)
    import board
    import busio
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn

    i2c = busio.I2C(board.SCL, board.SDA)
    ads = ADS.ADS1115(i2c, address=ADC_ADDRESS)
    ads.gain = 1                       # +/-4.096 V — comfortable for a 3.3V amp output
    chan = AnalogIn(ads, ADS.P0)       # single-ended on A0 (the AD8232 OUTPUT)
    print(f"[sampler] ADS1115 ready at {hex(ADC_ADDRESS)}, gain=1, channel A0")

    def read():
        return chan.voltage, chan.value
    return read


def main():
    db.init_db()
    read = make_reader()
    period = 1.0 / SAMPLE_HZ
    print(f"[sampler] logging to {db.DB_PATH} at {SAMPLE_HZ} Hz. Ctrl-C to stop.")
    next_t = time.time()
    while _running:
        ts = time.time()
        try:
            voltage, raw = read()
            db.insert_reading(ts, voltage, raw)
        except Exception as exc:        # one bad read must never kill the daemon
            print(f"[sampler] read/write error at {ts:.1f}: {exc}", file=sys.stderr)
        next_t += period                # keep a steady cadence without drift
        sleep = next_t - time.time()
        if sleep > 0:
            time.sleep(sleep)
        else:
            next_t = time.time()        # we fell behind — resync rather than spiral
    print("[sampler] stopped cleanly")


if __name__ == "__main__":
    main()
