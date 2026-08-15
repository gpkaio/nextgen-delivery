# NextGen Delivery — Service Layer (Steps 1–3)

Status as of 2026-08-14. Core engine (`nextgen_engine.py`, `test_engine.py`) stays
pure stdlib and passes 16/16 throughout everything below — nothing here touches
that guarantee.

## What's in the service layer

| File | Purpose |
|---|---|
| `nextgen_engine.py` | Core engine. Unchanged behavior by default; two new *optional* hooks added so the service can plug in real pieces without altering the tested path. |
| `geocoding.py` | Nominatim (OpenStreetMap) geocoder. Stdlib-only (`urllib`), no pip dependency. Barbados-biased (`countrycodes=bb`). Returns `None` on any failure or non-match — never raises. |
| `memory_store.py` | `PersistentLandmarkMemory` — subclasses the tested `LandmarkMemory`, adds Chroma-backed persistence (survives restarts) and a semantic fallback for true paraphrases (different words, same meaning) that Jaccard alone can't catch. |
| `service.py` | FastAPI app. Wraps `Orchestrator.handle()`, streams agent steps live over SSE, supports human-in-the-loop landmark confirmation over HTTP. |
| `static/index.html` | Single self-contained page (no build step, no CDN calls). Place an order, watch the agent log stream in, confirm new landmarks inline, see the dispatch result. |
| `requirements.txt` | Service-only dependencies (`chromadb`, `fastapi`, `uvicorn`). Installed into `.venv/`, not system Python — the core engine's "zero install, runs anywhere" property is untouched. |
| `test_service.py` | 8 checks for the new pieces (geocoding, persistence, semantic fallback). Separate from `test_engine.py` on purpose — these legitimately touch the network/an embedding model, so they don't belong in the hermetic 16/16 suite. |

## Engine changes (both backward-compatible, zero effect on tests/CLI demo)

- `AddressResolutionAgent(memory, estimator=None)` — `estimator` defaults to the
  original random-estimate function. The service passes `geocode_barbados`.
- `Orchestrator(memory=None, estimator=None)` — defaults to `LandmarkMemory()` and
  the random estimator, same as before. The service passes `PersistentLandmarkMemory`
  and `geocode_barbados`.
- `llm(prompt, system="", max_tokens=150)` (added in step 1) — calls MiniMax's
  OpenAI-compatible API if `MINIMAX_API_KEY` is set, else returns the stub.
  `test_engine.py` force-stubs this regardless of environment, so tests never hit
  the network even if the key is exported in your shell.

## Running it

**One-time setup:**
```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**Start the service:**
```
.venv\Scripts\python.exe -m uvicorn service:app --reload
```
Open **http://127.0.0.1:8000**. Enter an order + landmark, click "Place order."

**Optional environment variables** (set before starting, to enable MiniMax-generated
customer messages — the engine works fully without this, falling back to a fixed
template):
```
set MINIMAX_API_KEY=sk-...
set MINIMAX_MODEL=MiniMax-M2.7-highspeed   (optional, this is already the default)
```

**Run the two test suites:**
```
python test_engine.py                        # core: 16/16, no venv needed, offline
.venv\Scripts\python.exe test_service.py      # service: 8/8, needs venv + network
```

## API

- `POST /orders` — `{"raw_text": "...", "landmark": "..."}` → `{"order_id": "..."}`.
  Kicks off the pipeline in a background thread.
- `GET /orders/{order_id}/events` — Server-Sent Events stream. Event `type`s:
  `step` (agent name + message), `confirm_needed` (landmark + estimated point,
  waiting on human input), `confirm_timeout` (no response in 120s, estimate used
  automatically), `done` (final order summary), `error`.
- `POST /orders/{order_id}/confirm` — `{"lat": ..., "lon": ...}`. Only valid while
  that order is in `confirm_needed` state (409 otherwise).

## Design decisions worth knowing

- **The moat is untouched.** `LandmarkMemory`'s Jaccard matching (the thing suites
  C/D in `test_engine.py` protect) is still the *first* check on every resolve —
  `PersistentLandmarkMemory.resolve()` calls `super().resolve()` before ever
  touching Chroma. Persistence and semantic paraphrase-matching are additive, not
  a replacement.
- **Geocoding is a best-effort starting estimate, not a source of truth.** Nominatim
  indexes real map entities — it resolves "Bridgetown" or "Black Rock" but not
  "third house past the blue rum shop." When it can't find anything it returns
  `None` and the engine falls back to the same random-estimate-within-Barbados
  behavior as before; a human still confirms and the engine still learns the
  result either way.
- **One shared `Orchestrator` instance per process**, guarded by a lock so orders
  process one at a time. This is what makes the "second order resolves instantly"
  demo moment work live over HTTP — memory persists across requests within a run,
  and via Chroma, across restarts too.
- **Concurrency model**: each order runs on its own `threading.Thread`; SSE events
  route to the right browser tab via `threading.local` (set once per thread, for
  the life of that one order). A `queue.Queue` per order buffers events between
  the worker thread and the streaming HTTP response.
- **First `chromadb` import downloads a ~79MB local embedding model** (`all-MiniLM-L6-v2`,
  cached under `~/.cache/chroma`, no ongoing API cost — runs locally after that).
  This happened during setup verification; it won't repeat on the same machine.

## Verified end-to-end (2026-08-14)

Ran the live service via HTTP: placed an order to a new landmark → streamed all
6 agent steps over SSE → received `confirm_needed` → posted a confirmation →
pipeline completed with dispatch + exception-recovery + comms events, all
correct. Placed a second, differently-worded order to the same landmark →
resolved instantly from memory (`landmark KNOWN -> drop point ... (instant)`),
confirming the moat's core demo payoff now works through the web service, not
just the CLI script. `test_engine.py` re-confirmed 16/16 after every change in
this step.

## Known limitations (fair game, not urgent)

- `JOBS` (in-memory order registry in `service.py`) never gets cleaned up —
  fine for a demo session, would need a TTL/eviction for anything longer-running.
- No auth on any endpoint — fine for a local demo, not for a public deployment.
- Orders process strictly one at a time (the `engine_lock`) — a deliberate
  simplicity/correctness tradeoff, not a scaling design.
- `PersistentLandmarkMemory`'s semantic-fallback distance threshold (0.35) is a
  reasonable starting guess, not tuned against real Barbados landmark data.

## Not yet done

Web UI exists but hasn't been polished beyond functional; no deployment step;
`app-preview.html` mentioned in earlier project context still doesn't exist in
the repo (only `index.html` does) — worth checking with Kai whether that's
expected or still to be added.
