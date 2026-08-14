# NextGen Delivery — Agentic Dispatch & Routing Engine

**Owner:** Kai (Martino Bayley)
**Context:** Future Caribbean Buildathon submission
**Setting:** Barbados — landmark-based addressing (most delivery locations have no
street address; people navigate by "third house past the blue rum shop, green gate")

---

## WHAT EXISTS RIGHT NOW (verified working)

Two files, pure stdlib Python, zero dependencies:

- `nextgen_engine.py` — the engine. Multi-agent pipeline:
  Intake → Address Resolution → Merchant → Dispatch → Exception/Recovery → Comms
- `test_engine.py` — stress harness, 7 suites, **16/16 passing**

Verified on this machine: Python 3.11.1 (`C:\Python311\python.exe`), git 2.54.0.

```bash
python nextgen_engine.py   # live demo with dramatic pauses
python test_engine.py      # full suite; exit 0 = all green
```

---

## THE MOAT — read this before changing anything

`AddressResolutionAgent` + `LandmarkMemory` are the differentiator, not the routing.

A landmark description resolves to a precise drop point. First time: the engine
estimates, a human confirms, and the engine **learns it**. Every subsequent order to
that landmark — *including re-phrasings* — resolves instantly from memory.

Matching is token-set Jaccard (threshold 0.5) with a stopword list. Deliberately
chosen so that:
- word order doesn't matter ("tamarind tree by miss enid shop" == "miss enid shop by the tamarind tree")
- landmarks sharing one common word ("shop") do **not** over-merge

The demo's whole payoff is the second order resolving instantly. Suites C
(propagation) and D (distinctness) exist to protect exactly this behaviour.
**If you touch matching, those two suites are the regression gate.**

---

## BUILD DIRECTION (Kai's stated plan — not yet implemented)

- Wire a real LLM behind the `llm()` stub in `nextgen_engine.py`
  (in-code TODO names Llama/Qwen via vLLM/Ollama on a Highrise H200; Kai has since
  mentioned MiniMax — **confirm which before building**)
- FastAPI service wrapping `Orchestrator.handle()`
- Web UI on top of that service

Everything above is direction, not decided architecture. Ask before assuming.

---

## HOUSE RULES

1. **`python test_engine.py` must exit 0 before any change is called done.** No exceptions.
2. **Keep the engine dependency-free**, or isolate new deps behind the service layer.
   Its "runs anywhere, no install" property is a demo asset — a judge can run it cold.
3. **Filename is lowercase `nextgen_engine.py`.** It was `Nextgen_engine.py` and the
   test import broke (Python enforces module-name case even on Windows). Don't
   reintroduce the capital.
4. **Never weaken a test to make it pass.** If a suite fails, the engine is wrong.
5. `random.seed(7)` at module top and per-suite seeds keep runs reproducible — don't
   remove them casually or the demo stops being repeatable.
6. Deadline-driven project. Prefer the working, demoable path over the elegant one.

---

## KNOWN ROUGH EDGES (fair game, not urgent)

- `LandmarkMemory` is an in-process dict — nothing persists across runs.
  In-code TODO suggests Chroma/Qdrant + embeddings.
- `MerchantAgent` / `ExceptionRecoveryAgent` outcomes are `random.random()` coin flips,
  not real logic. Fine for the demo; needs replacing for anything real.
- No persistence, no API, no UI yet.
