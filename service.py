"""FastAPI service wrapping the NextGen Delivery engine's Orchestrator.

Service-layer only, per CLAUDE.md house rule 2 -- nextgen_engine.py itself
stays pure stdlib and untouched. This file wires in the real pieces built
in steps 1-2 (MiniMax-backed llm(), Nominatim geocoding, Chroma-backed
persistent landmark memory) via the Orchestrator's injectable memory/
estimator hooks, so test_engine.py's 16/16 stays green and unaffected.

Run (from the venv):
    .venv\\Scripts\\python.exe -m uvicorn service:app --reload
Then open http://127.0.0.1:8000
"""
from __future__ import annotations

import json
import queue
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

import nextgen_engine as ng
from geocoding import geocode_barbados
from memory_store import PersistentLandmarkMemory

STATIC_DIR = Path(__file__).parent / "static"

# --- capture the engine's per-step log lines and route them to whichever ---
# order's SSE queue is active on the current thread. Each order runs on its
# own dedicated thread (see _run_order), so thread-local storage stays
# correctly scoped for the lifetime of that one order's processing.
_thread_local = threading.local()
_original_log = ng.log


def _capturing_log(agent: str, msg: str) -> None:
    _original_log(agent, msg)  # keep server-console output too (paced by STEP_DELAY)
    q = getattr(_thread_local, "queue", None)
    if q is not None:
        q.put({"type": "step", "agent": agent, "message": msg})


ng.log = _capturing_log

# One shared engine instance for the process: landmark memory accumulates
# across orders (and, via Chroma, across restarts) -- that persistence IS
# the moat's payoff in a live demo.
memory = PersistentLandmarkMemory(path="./chroma_data")
engine = ng.Orchestrator(memory=memory, estimator=geocode_barbados)
engine_lock = threading.Lock()  # serialize orders -- engine/memory state is shared


class Job:
    def __init__(self) -> None:
        self.queue: queue.Queue = queue.Queue()
        self.confirm_event = threading.Event()
        self.confirm_result: tuple | None = None
        self.awaiting_confirm = False


JOBS: dict[str, Job] = {}

app = FastAPI(title="NextGen Delivery")


class OrderRequest(BaseModel):
    raw_text: str
    landmark: str


class ConfirmRequest(BaseModel):
    lat: float
    lon: float


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/orders")
def create_order(req: OrderRequest):
    order_id = uuid.uuid4().hex[:8]
    job = Job()
    JOBS[order_id] = job
    threading.Thread(
        target=_run_order, args=(job, req.raw_text, req.landmark), daemon=True
    ).start()
    return {"order_id": order_id}


@app.get("/orders/{order_id}/events")
def order_events(order_id: str):
    job = JOBS.get(order_id)
    if job is None:
        raise HTTPException(404, "unknown order_id")

    def stream():
        while True:
            item = job.queue.get()
            if item is None:  # sentinel -- pipeline finished, close the stream
                break
            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/orders/{order_id}/confirm")
def confirm_order(order_id: str, req: ConfirmRequest):
    job = JOBS.get(order_id)
    if job is None:
        raise HTTPException(404, "unknown order_id")
    if not job.awaiting_confirm:
        raise HTTPException(409, "this order isn't waiting on a confirmation")
    job.confirm_result = (round(req.lat, 4), round(req.lon, 4))
    job.confirm_event.set()
    return {"ok": True}


def _run_order(job: Job, raw_text: str, landmark: str) -> None:
    _thread_local.queue = job.queue

    def confirm_fn(lm: str, estimate: tuple) -> tuple:
        job.awaiting_confirm = True
        job.queue.put({"type": "confirm_needed", "landmark": lm, "estimate": estimate})
        got_response = job.confirm_event.wait(timeout=120)  # don't hang forever on a closed tab
        job.confirm_event.clear()
        job.awaiting_confirm = False
        if not got_response:
            job.queue.put({"type": "confirm_timeout", "used_estimate": estimate})
            return estimate
        result, job.confirm_result = job.confirm_result, None
        return result

    try:
        with engine_lock:
            order = engine.handle(raw_text, landmark, confirm_fn)
        job.queue.put({
            "type": "done",
            "driver": order.driver,
            "eta_min": order.eta_min,
            "drop_point": order.drop_point,
            "items": order.items,
            "category": order.category,
            "events": order.events,
        })
    except Exception as ex:
        job.queue.put({"type": "error", "message": f"{type(ex).__name__}: {ex}"})
    finally:
        job.queue.put(None)
        _thread_local.queue = None
