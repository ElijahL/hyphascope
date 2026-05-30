# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies and create .venv
uv sync

# Run sampler (simulate mode — no hardware required)
SIMULATE=1 uv run python sampler.py

# Run API server
uv run uvicorn api:app --host 0.0.0.0 --port 8000

# Run both locally for development
SIMULATE=1 uv run python sampler.py &
uv run uvicorn api:app --port 8000
```

There are no tests or linter configs in this project.

## Architecture

This is a two-process, one-database system designed to run on a Raspberry Pi:

```
[ADS1115 ADC] --I2C--> sampler.py --writes--> fungal.db <--reads-- api.py --> MCP host
```

**`sampler.py`** is the sole hardware process. It runs forever, reads the ADS1115 ADC at `SAMPLE_HZ` Hz, and inserts raw samples into SQLite. It handles `SIGINT`/`SIGTERM` for clean shutdown. All signal processing is deliberately absent — the Pi's only job is reliable capture.

**`api.py`** is a read-only FastAPI app. It never writes to the DB. The `/readings` endpoint is cursor-based (`since` parameter = unix timestamp); callers advance the cursor using `next_since` from the response to backfill without loss across network gaps.

**`db.py`** is the shared SQLite layer. WAL mode is critical — it lets the sampler write at the same time the API reads. Every connection enables WAL and `synchronous=NORMAL`. The DB file (`fungal.db`) lives next to the source files.

## Environment variables (loaded from `.env` via python-dotenv)

| Variable | Default | Purpose |
|---|---|---|
| `SIMULATE` | `0` | Set to `1` to generate synthetic data with no hardware |
| `SAMPLE_HZ` | `1.0` | Samples per second |
| `ADC_ADDRESS` | `0x48` | I2C address of the ADS1115 (hex string) |

Copy `.env.example` to `.env` and edit as needed. Shell exports override `.env` values.

## Hardware notes

- ADC is ADS1115, single-ended on channel A0 (AD8232 amplifier output)
- `adafruit-blinka` and `adafruit-circuitpython-ads1x15` are only exercised on real Pi hardware; they import inside the hardware branch of `make_reader()`, so `SIMULATE=1` never imports them
- For multi-day recordings, run both processes as systemd services (see README.md for unit files)
