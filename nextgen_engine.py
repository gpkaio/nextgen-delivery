"""
NextGen Delivery — Agentic Dispatch & Routing Engine (prototype)
================================================================
A runnable skeleton of the multi-agent engine for the Future Caribbean Buildathon.

It demonstrates, in pure Python (no dependencies, runs anywhere):
  - a multi-agent pipeline (Intake -> Address Resolution -> Merchant -> Dispatch -> Comms)
  - the MOAT: an Address Resolution Agent that turns a landmark description into a
    precise, reusable drop point -- and LEARNS it, so the 2nd order is instant
  - human-in-the-loop confirmation for first-time locations
  - an Exception & Recovery Agent that re-plans when a driver falls through

Run the demo:  python nextgen_engine.py
Run the tests: python test_engine.py
"""

from __future__ import annotations
import json
import os
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

random.seed(7)

# --- output / timing controls (tests flip these) --------------------------- #
VERBOSE = True        # False = no printing (fast, quiet — used in bulk tests)
STEP_DELAY = 0.35     # seconds between agent steps in the live demo; 0 in tests

# --- llm() config ------------------------------------------------------------ #
# MiniMax, OpenAI-compatible /chat/completions endpoint (confirmed with Kai,
# 2026-08-14 — supersedes the old in-code TODO naming Llama/Qwen via vLLM/Ollama).
LLM_STUB = "(stubbed llm response)"
MINIMAX_API_URL = "https://api.minimax.io/v1/chat/completions"
MINIMAX_MODEL = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.7-highspeed")


def llm(prompt: str, system: str = "", max_tokens: int = 150) -> str:
    """Calls the MiniMax API if MINIMAX_API_KEY is set in the environment.
    Falls back to a stub on a missing key, any network error, or a bad response --
    the engine (and test_engine.py, which force-stubs this) must never depend on
    network access to run."""
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        return LLM_STUB
    messages = ([{"role": "system", "content": system}] if system else [])
    messages.append({"role": "user", "content": prompt})
    body = {
        "model": MINIMAX_MODEL,
        "messages": messages,
        "max_completion_tokens": max_tokens,
        "temperature": 0.7,
    }
    req = urllib.request.Request(
        MINIMAX_API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError):
        return LLM_STUB


def log(agent: str, msg: str) -> None:
    if not VERBOSE:
        return
    print(f"   [{agent:<22}] {msg}")
    if STEP_DELAY:
        time.sleep(STEP_DELAY)


@dataclass
class Order:
    raw_text: str
    landmark: str
    items: list = field(default_factory=list)
    category: str = ""
    drop_point: tuple | None = None
    driver: str | None = None
    eta_min: int | None = None
    status: str = "new"
    events: list = field(default_factory=list)

    def event(self, text: str) -> None:
        self.events.append(text)


class LandmarkMemory:
    """Landmark description -> precise drop point, with learning.
    Token-set (Jaccard) matching: order-insensitive, and won't over-merge
    landmarks that merely share a common word like 'shop'.
    TODO(build): swap for a real vector DB (Chroma/Qdrant) + embeddings."""

    MATCH_THRESHOLD = 0.5
    STOPWORDS = {"the", "a", "an", "past", "house", "with", "gate", "third",
                 "next", "to", "near", "by", "in", "on", "at", "of", "and"}

    def __init__(self):
        self._store: dict[str, tuple] = {}
        for desc, pt in [("st. mary's church", (13.0975, -59.6188)),
                         ("esso gas station black rock", (13.1122, -59.6350))]:
            self._store[self._key(desc)] = pt

    def resolve(self, landmark: str) -> tuple | None:
        q = self._tokens(landmark)
        if not q:
            return None
        best_pt, best_sim = None, 0.0
        for key, pt in self._store.items():
            sim = self._jaccard(q, set(key.split()))
            if sim > best_sim:
                best_sim, best_pt = sim, pt
        return best_pt if best_sim >= self.MATCH_THRESHOLD else None

    def learn(self, landmark: str, drop_point: tuple) -> None:
        key = self._key(landmark)
        if not key:
            return
        self._store[key] = drop_point

    def size(self) -> int:
        return len(self._store)

    @classmethod
    def _tokens(cls, text: str) -> set:
        raw = [w.strip(".,;:!?'\"()").lower() for w in (text or "").split()]
        raw = [w for w in raw if w]
        toks = [w for w in raw if w not in cls.STOPWORDS]
        return set(toks) if toks else set(raw)

    @classmethod
    def _key(cls, text: str) -> str:
        return " ".join(sorted(cls._tokens(text)))

    @staticmethod
    def _jaccard(a: set, b: set) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)


class IntakeAgent:
    """Parse a messy natural-language order into items + category."""
    CATALOG = {
        "pharmacy": ["prescription", "panadol", "plasters", "vitamins"],
        "grocery": ["water", "bread", "rice", "milk", "eggs"],
        "food": ["rotis", "roti", "cutter", "fish", "macaroni pie"],
    }

    def run(self, order: Order) -> None:
        text = (order.raw_text or "").lower()
        items, category = [], ""
        for cat, goods in self.CATALOG.items():
            for g in goods:
                if g in text and g not in items:
                    items.append(g)
                    category = category or cat
        # de-dupe substrings (e.g. drop 'roti' when 'rotis' already matched)
        items = [i for i in items if not any(i != j and i in j for j in items)]
        if "usual" in text or "pharmacy" in text:
            if not any("prescription" in i for i in items):
                items.insert(0, "prescription (your usual)")
            category = "pharmacy"
        order.items = items or ["(unrecognized item)"]
        order.category = category or "general"
        log("Intake Agent", f"understood: {order.items} ({order.category})")
        order.event("order parsed")


class AddressResolutionAgent:
    """THE MOAT: landmark description -> precise drop point, with learning."""

    def __init__(self, memory: LandmarkMemory, estimator=None):
        self.memory = memory
        # estimator(landmark: str) -> tuple | None. Default matches the original
        # random-within-Barbados behavior exactly, so the engine/tests are
        # unaffected. The live service injects a real geocoder here instead
        # (see geocoding.py) -- kept pluggable so this file stays dependency-free.
        self.estimator = estimator or self._random_estimate

    @staticmethod
    def _random_estimate(landmark: str) -> tuple:
        return (round(13.10 + random.uniform(-0.02, 0.02), 4),
                round(-59.62 + random.uniform(-0.02, 0.02), 4))

    def run(self, order: Order, confirm_fn) -> None:
        known = self.memory.resolve(order.landmark)
        if known:
            order.drop_point = known
            log("Address Resolution", f"landmark KNOWN -> drop point {known} (instant)")
            order.event("landmark resolved from memory")
            return
        estimate = self.estimator(order.landmark) or self._random_estimate(order.landmark)
        log("Address Resolution", f"new landmark -> estimated drop point {estimate}")
        confirmed = confirm_fn(order.landmark, estimate)
        if not (isinstance(confirmed, tuple) and len(confirmed) == 2):
            confirmed = estimate
        order.drop_point = confirmed
        self.memory.learn(order.landmark, confirmed)
        log("Address Resolution", "customer confirmed -> LEARNED for next time")
        order.event("landmark resolved + learned")


class MerchantAgent:
    def run(self, order: Order) -> None:
        if random.random() > 0.15:
            log("Merchant Agent", "all items in stock -> order placed")
            order.event("merchant confirmed")
        else:
            log("Merchant Agent", "1 item out of stock -> substitution proposed & approved")
            order.event("substitution approved")


class DispatchAgent:
    DRIVERS = ["Andre D.", "Shanice B.", "Kemar J."]

    def run(self, order: Order) -> None:
        order.driver = random.choice(self.DRIVERS)
        order.eta_min = random.randint(9, 22)
        order.status = "dispatched"
        log("Dispatch & Routing", f"assigned {order.driver}, route optimized, ETA {order.eta_min} min")
        order.event("driver dispatched")


class ExceptionRecoveryAgent:
    def maybe_disrupt(self, order: Order, dispatch: DispatchAgent) -> None:
        if random.random() < 0.5:
            old = order.driver
            remaining = [d for d in dispatch.DRIVERS if d != old]
            if not remaining:
                log("Exception & Recovery", f"! {old} cancelled — no backup driver available")
                order.event("disruption: no backup driver")
                return
            log("Exception & Recovery", f"! {old} cancelled — re-planning automatically")
            order.driver = random.choice(remaining)
            order.eta_min += random.randint(2, 6)
            log("Exception & Recovery", f"re-assigned {order.driver}, new ETA {order.eta_min} min")
            order.event("auto-recovered from driver cancellation")


class CommsAgent:
    FALLBACK_TEMPLATE = "On the way! {driver} arriving in ~{eta} min."

    def run(self, order: Order) -> None:
        msg = llm(
            f"Write ONE short, warm WhatsApp message (max 20 words, no greeting, "
            f"no sign-off) telling a customer in Barbados their order is on the way. "
            f"Driver: {order.driver}. ETA: {order.eta_min} minutes.",
            system="You are a friendly Barbadian delivery dispatcher writing customer texts.",
        )
        if msg == LLM_STUB:
            msg = self.FALLBACK_TEMPLATE.format(driver=order.driver, eta=order.eta_min)
        log("Comms Agent", f"WhatsApp -> \"{msg}\"")
        order.event("customer notified")


class Orchestrator:
    def __init__(self, memory: LandmarkMemory | None = None, estimator=None):
        # memory/estimator default to the original in-memory dict + random
        # estimate -- zero behavior change for the CLI demo and test_engine.py.
        # The live service injects PersistentLandmarkMemory + geocode_barbados.
        self.memory = memory or LandmarkMemory()
        self.intake = IntakeAgent()
        self.address = AddressResolutionAgent(self.memory, estimator=estimator)
        self.merchant = MerchantAgent()
        self.dispatch = DispatchAgent()
        self.exceptions = ExceptionRecoveryAgent()
        self.comms = CommsAgent()

    def handle(self, raw_text: str, landmark: str, confirm_fn) -> Order:
        order = Order(raw_text=raw_text, landmark=landmark)
        if VERBOSE:
            print(f"\n>>> NEW ORDER: \"{raw_text}\"\n    location: \"{landmark}\"")
        self.intake.run(order)
        self.address.run(order, confirm_fn)
        self.merchant.run(order)
        self.dispatch.run(order)
        self.exceptions.maybe_disrupt(order, self.dispatch)
        self.comms.run(order)
        order.status = "en route"
        if VERBOSE:
            print(f"    --> DONE: {order.driver} en route to {order.drop_point}, ETA {order.eta_min} min")
        return order


def auto_confirm(landmark: str, estimate: tuple) -> tuple:
    log("Human-in-the-loop", f"customer confirms drop point for '{landmark}'")
    return estimate


def main():
    print("=" * 68)
    print("  NextGen Delivery — Agentic Dispatch Engine (prototype demo)")
    print("=" * 68)
    engine = Orchestrator()
    engine.handle(
        "I need my usual from the pharmacy and a case of water",
        "third house past the blue rum shop, Bank Hall, green gate",
        auto_confirm,
    )
    engine.handle(
        "2 rotis and a fish cutter please",
        "past the blue rum shop in Bank Hall, the green gate",
        auto_confirm,
    )
    print("\n" + "=" * 68)
    print("  Notice: the 2nd order to the same landmark resolved INSTANTLY.")
    print("  Every delivery makes the engine smarter -- that's the moat.")
    print("=" * 68)


if __name__ == "__main__":
    main()
