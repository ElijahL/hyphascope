#!/usr/bin/env python3
"""Read-only REST API for the fungal recording rig.

Serves whatever the sampler has written to SQLite and does NO signal processing
itself — spike detection and analysis live on the powerful host that consumes
this API and runs the MCP server. Endpoints:

  GET /health            is sampling still alive? counts and last-sample age
  GET /readings/latest   the most recent sample
  GET /readings?since=   everything strictly after a timestamp (for backfill)

Run with:  uvicorn api:app --host 0.0.0.0 --port 8000
"""
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, HTTPException

import db

STALE_AFTER_S = 10.0  # newest sample older than this => sampling looks dead


@asynccontextmanager
async def lifespan(app):
    db.init_db()
    yield


app = FastAPI(title="Fungal rig", version="1.0", lifespan=lifespan)


@app.get("/health")
def health():
    info = db.count_and_span()
    latest = db.latest_reading()
    now = time.time()
    last_age = (now - latest["ts"]) if latest else None
    sampling_ok = last_age is not None and last_age < STALE_AFTER_S
    return {
        "status": "ok" if sampling_ok else "stale",
        "sampling_alive": sampling_ok,
        "now": now,
        "last_sample_age_s": last_age,
        "total_readings": info["n"],
        "first_ts": info["first_ts"],
        "last_ts": info["last_ts"],
    }


@app.get("/readings/latest")
def latest():
    row = db.latest_reading()
    if row is None:
        raise HTTPException(status_code=404, detail="no readings yet")
    return row


@app.get("/readings")
def readings(
    since: float = Query(0.0, description="unix epoch seconds; returns samples strictly after this"),
    limit: int = Query(10000, ge=1, le=100000),
):
    rows = db.readings_since(since, limit=limit)
    return {
        "since": since,
        "count": len(rows),
        "readings": rows,
        # cursor for the host's next backfill request — pass this back as `since`
        "next_since": rows[-1]["ts"] if rows else since,
    }
