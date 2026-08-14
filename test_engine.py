"""
NextGen Delivery — engine stress & propagation test harness
===========================================================
Feeds hundreds of bot-generated orders plus deliberately nasty edge cases through
the agentic engine and checks invariants on every single one. Pure stdlib.

Run:  python test_engine.py     (exit code 0 = all green, 1 = something failed)
"""

import random
import sys
import nextgen_engine as ng

# quiet + fast: no printing, no dramatic pauses
ng.VERBOSE = False
ng.STEP_DELAY = 0

results = []  # (name, ok, detail)


def record(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def confirm_est(landmark, est):
    """Human-in-the-loop stub that accepts the engine's estimate."""
    return est


def confirm_fixed(point):
    """Return a confirm_fn that always confirms a fixed point (for determinism)."""
    return lambda landmark, est: point


def invariants(order):
    """Every completed order must satisfy all of these. Returns list of problems."""
    p = []
    if order.status != "en route":
        p.append(f"status={order.status!r}")
    if not (isinstance(order.items, list) and order.items):
        p.append("items empty")
    if not (isinstance(order.category, str) and order.category):
        p.append("category empty")
    dp = order.drop_point
    if not (isinstance(dp, tuple) and len(dp) == 2
            and all(isinstance(x, (int, float)) for x in dp)):
        p.append(f"drop_point={dp!r}")
    if order.driver not in ng.DispatchAgent.DRIVERS:
        p.append(f"driver={order.driver!r}")
    if not (isinstance(order.eta_min, int) and order.eta_min > 0):
        p.append(f"eta={order.eta_min!r}")
    if "driver dispatched" not in order.events:
        p.append("missing dispatch event")
    if "customer notified" not in order.events:
        p.append("missing comms event")
    return p


# --------------------------------------------------------------------------- #
# Suite A — smoke: the demo learning arc
# --------------------------------------------------------------------------- #
def suite_smoke():
    ng.random.seed(1)
    eng = ng.Orchestrator()
    o1 = eng.handle("my usual from the pharmacy and a case of water",
                    "third house past the blue rum shop, Bank Hall, green gate", confirm_est)
    o2 = eng.handle("2 rotis and a fish cutter",
                    "past the blue rum shop in Bank Hall, the green gate", confirm_est)
    record("smoke: order 1 invariants", not invariants(o1), str(invariants(o1)))
    record("smoke: order 2 invariants", not invariants(o2), str(invariants(o2)))
    record("smoke: order 1 learned a new landmark",
           "landmark resolved + learned" in o1.events)
    record("smoke: order 2 resolved from memory",
           "landmark resolved from memory" in o2.events)
    record("smoke: both orders share the learned drop point",
           o1.drop_point == o2.drop_point, f"{o1.drop_point} vs {o2.drop_point}")


# --------------------------------------------------------------------------- #
# Suite B — bulk stress: 300 randomized orders, invariants on each
# --------------------------------------------------------------------------- #
def suite_bulk():
    random.seed(42)
    eng = ng.Orchestrator()
    items_pool = ["water", "bread", "rice and milk", "eggs", "rotis", "a fish cutter",
                  "panadol and vitamins", "my usual from the pharmacy", "macaroni pie",
                  "some plasters", "bread water eggs", "just a roti please"]
    place_pool = ["past the blue rum shop bank hall", "by st. mary's church",
                  "near the esso gas station black rock", "the tamarind tree miss enid shop",
                  "third house with the green gate christ church", "opposite the cricket oval",
                  "next to the pink house speightstown", "by the standpipe in bush hall",
                  "the yellow shop near the roundabout", "behind the mahogany tree oistins"]
    n, fails = 300, []
    for i in range(n):
        o = eng.handle(random.choice(items_pool), random.choice(place_pool), confirm_est)
        prob = invariants(o)
        if prob:
            fails.append((i, prob))
    record(f"bulk: {n} randomized orders all satisfy invariants",
           not fails, f"{len(fails)} failed; first: {fails[:3]}")
    record("bulk: engine learned new landmarks (memory grew)",
           eng.memory.size() > 2, f"memory size={eng.memory.size()}")


# --------------------------------------------------------------------------- #
# Suite C — memory propagation: variations of one landmark -> same drop point
# --------------------------------------------------------------------------- #
def suite_propagation():
    eng = ng.Orchestrator()
    fixed = (13.1234, -59.6111)
    base = "the tamarind tree by miss enid shop"
    eng.handle("bread", base, confirm_fixed(fixed))
    variations = [
        "tamarind tree by miss enid shop",
        "by the tamarind tree, miss enid shop",
        "the tamarind tree near miss enid shop green fence",
        "miss enid shop by the tamarind tree",
    ]
    bad = []
    for v in variations:
        o = eng.handle("water", v, confirm_est)
        if o.drop_point != fixed:
            bad.append((v, o.drop_point))
    record("propagation: re-phrasings of a learned landmark resolve to the same point",
           not bad, str(bad))


# --------------------------------------------------------------------------- #
# Suite D — distinctness: 20 clearly-different landmarks must not collide
# --------------------------------------------------------------------------- #
def suite_distinctness():
    eng = ng.Orchestrator()
    words = ["zephyr", "quokka", "juniper", "marlin", "obsidian", "cinnamon", "lagoon",
             "almond", "harbour", "cassava", "flamboyant", "pelican", "mahogany", "conch",
             "cricket", "banyan", "coral", "breadfruit", "hummingbird", "calypso"]
    pts = {}
    for i, w in enumerate(words):
        pt = (round(13.00 + i * 0.013, 4), round(-59.00 - i * 0.017, 4))
        eng.handle("water", f"the {w} spot", confirm_fixed(pt))
        pts[w] = pt
    bad = []
    for w in words:
        o = eng.handle("bread", f"the {w} spot", confirm_est)
        if o.drop_point != pts[w]:
            bad.append((w, o.drop_point, pts[w]))
    record("distinctness: 20 distinct landmarks each recall their own point",
           not bad, f"{len(bad)} collided/lost; first: {bad[:3]}")


# --------------------------------------------------------------------------- #
# Suite E — edge cases: engine must never crash and must stay valid
# --------------------------------------------------------------------------- #
def suite_edges():
    eng = ng.Orchestrator()
    edge = [
        ("", ""),                                   # totally empty
        ("   ", "   "),                             # whitespace only
        ("asldkfjqwpoeiru", "zxcvbnm qwerty"),      # gibberish, no known items/places
        ("water " * 500, "the " * 200 + "blue shop"),  # very long strings
        ("café ☕ piña \U0001F964", "por la tienda azul \U0001F3E0 esquina"),  # unicode/emoji
        ("12345 67890", "999 corner"),             # numbers
        ("!!!???...", ",,,;;;"),                    # punctuation only
        ("WATER AND BREAD", "THE BLUE RUM SHOP"),   # all caps
    ]
    problems = []
    for txt, lm in edge:
        try:
            o = eng.handle(txt, lm, confirm_est)
            prob = invariants(o)
            if prob:
                problems.append((txt[:12], lm[:12], prob))
        except Exception as ex:  # noqa: BLE001 — we WANT to catch anything here
            problems.append((txt[:12], lm[:12], f"EXCEPTION {type(ex).__name__}: {ex}"))
    record("edge cases: no crashes, invariants hold on 8 nasty inputs",
           not problems, str(problems[:5]))


# --------------------------------------------------------------------------- #
# Suite F — exception & recovery correctness
# --------------------------------------------------------------------------- #
def suite_recovery():
    orig_random = ng.random.random
    ng.random.random = lambda: 0.0  # force: always disrupt (and always substitute)
    try:
        eng = ng.Orchestrator()
        recs = [eng.handle("water", f"place number {i} corner", confirm_est) for i in range(25)]
        recovered = all("auto-recovered from driver cancellation" in o.events for o in recs)
        drivers_ok = all(o.driver in ng.DispatchAgent.DRIVERS for o in recs)
        valid = all(not invariants(o) for o in recs)
        record("recovery: forced disruption always auto re-plans", recovered)
        record("recovery: reassigned driver is always valid", drivers_ok)
        record("recovery: orders still satisfy invariants after recovery", valid)

        # single-driver pool must not crash (guard path)
        orig_drivers = ng.DispatchAgent.DRIVERS
        ng.DispatchAgent.DRIVERS = ["Solo Driver"]
        try:
            eng2 = ng.Orchestrator()
            o = eng2.handle("water", "the lonely corner", confirm_est)
            ok = (o.driver == "Solo Driver"
                  and "disruption: no backup driver" in o.events)
            record("recovery: single-driver pool handled without crashing", ok,
                   f"driver={o.driver}, events={o.events}")
        finally:
            ng.DispatchAgent.DRIVERS = orig_drivers
    finally:
        ng.random.random = orig_random


# --------------------------------------------------------------------------- #
# Suite G — isolation: orders don't leak state into each other
# --------------------------------------------------------------------------- #
def suite_isolation():
    eng = ng.Orchestrator()
    a = eng.handle("water", "the coral spot", confirm_fixed((1.0, 2.0)))
    b = eng.handle("bread", "the banyan spot", confirm_fixed((3.0, 4.0)))
    record("isolation: two orders keep separate drop points",
           a.drop_point == (1.0, 2.0) and b.drop_point == (3.0, 4.0),
           f"a={a.drop_point} b={b.drop_point}")
    record("isolation: two orders keep separate event logs",
           a.events is not b.events and len(a.events) > 0 and len(b.events) > 0)


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def main():
    for suite in (suite_smoke, suite_bulk, suite_propagation, suite_distinctness,
                  suite_edges, suite_recovery, suite_isolation):
        try:
            suite()
        except Exception as ex:  # a suite itself blew up
            record(f"{suite.__name__} (harness)", False, f"EXCEPTION {type(ex).__name__}: {ex}")

    print("=" * 72)
    print("  NextGen Engine — Stress & Propagation Test Report")
    print("=" * 72)
    passed = 0
    for name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        line = f"  [{mark}] {name}"
        if not ok and detail:
            line += f"\n         -> {detail}"
        print(line)
        passed += ok
    total = len(results)
    print("-" * 72)
    print(f"  {passed}/{total} checks passed.")
    print("=" * 72)
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
