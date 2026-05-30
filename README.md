# Fungal recording rig — Pi Zero side

Lightweight data capture stack for fungal electrophysiology. Runs on a Raspberry Pi: one process reads an ADS1115 ADC over I²C and logs raw voltage samples to SQLite; a second serves those samples over a read-only REST API. All spike detection and analysis happen on the host machine that consumes the API — the Pi just captures clean data reliably.

---

Two small processes that share one SQLite file:

- **`sampler.py`** — reads the ADS1115 once per second, writes to `fungal.db`. The only thing that touches the hardware. Stays running across API restarts.
- **`api.py`** — a read-only FastAPI app that serves the data to your MCP host.

The Pi does *no* analysis. Spike detection and everything clever happen on the more powerful machine that consumes this API and runs the MCP server. The Pi just captures clean data and never loses it.

## 1. Enable I²C on the Pi

```bash
sudo raspi-config        # Interface Options -> I2C -> Enable, then reboot
sudo apt install -y i2c-tools python3-pip
i2cdetect -y 1           # you should see your ADC at 0x48
```

If `0x48` doesn't appear, recheck SDA/SCL/3.3V/GND wiring and that ADDR is tied to GND.

## 2. Install

```bash
cd fungal-rig
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Run

Two terminals (or use the systemd units below):

```bash
# terminal 1 — start sampling
python sampler.py

# terminal 2 — serve the API on the LAN
uvicorn api:app --host 0.0.0.0 --port 8000
```

Check it:

```bash
curl http://<pi-ip>:8000/health
curl http://<pi-ip>:8000/readings/latest
```

## Develop on a laptop first (no hardware)

You don't need the Pi or the Adafruit packages to build against this. With
`SIMULATE=1` the sampler generates a slow-drifting, occasionally-spiking signal
that looks roughly like real fungal data:

```bash
pip install fastapi "uvicorn[standard]"   # adafruit packages NOT needed
SIMULATE=1 python sampler.py              # synthetic data into fungal.db
uvicorn api:app --port 8000               # same API, served locally
```

## Run as services (recommended for multi-day recordings)

So sampling auto-starts on boot and restarts if it ever crashes. Create
`/etc/systemd/system/fungal-sampler.service`:

```ini
[Unit]
Description=Fungal signal sampler
After=multi-user.target

[Service]
WorkingDirectory=/home/pi/fungal-rig
ExecStart=/home/pi/fungal-rig/.venv/bin/python sampler.py
Restart=always
RestartSec=3
User=pi

[Install]
WantedBy=multi-user.target
```

And `/etc/systemd/system/fungal-api.service`:

```ini
[Unit]
Description=Fungal rig API
After=fungal-sampler.service

[Service]
WorkingDirectory=/home/pi/fungal-rig
ExecStart=/home/pi/fungal-rig/.venv/bin/uvicorn api:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3
User=pi

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now fungal-sampler fungal-api
journalctl -u fungal-sampler -f      # watch the sampler live
```

## How the host backfills without losing data

The `/readings` endpoint is cursor-based. The host keeps the last timestamp it
saw and asks for everything after it:

```python
import requests
since = 0.0
while True:
    r = requests.get("http://<pi-ip>:8000/readings",
                     params={"since": since, "limit": 10000}).json()
    for row in r["readings"]:
        ...                      # hand to spike detection / store on the host
    since = r["next_since"]      # advance the cursor
    # sleep, then poll again — gaps are impossible because `since` only moves
    # forward over rows that actually exist in the Pi's database
```

Because the Pi logs every sample locally regardless of whether anyone is
polling, a network drop or a host reboot just means the host backfills the gap
on reconnect. Nothing is lost.

## Notes

- `/health` reports `sampling_alive: false` if the newest sample is older than
  10 s — a cheap way for the host (or you) to know the rig is still recording
  without walking over to look at it.
- Default sample rate is 1 Hz (`SAMPLE_HZ` to change). The interesting fungal
  dynamics are slow, so going faster mostly buys you bigger files.
- The ADC reads single-ended on A0 because the AD8232 already did the
  differential, noise-rejecting job at the electrodes.
