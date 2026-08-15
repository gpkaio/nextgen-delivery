"""Tests for the service-layer pieces (geocoding.py, memory_store.py).

Separate from test_engine.py on purpose: these touch the network (geocoding)
and a real embedding model (Chroma), so they're not free or hermetic --
they don't belong in the 16/16 suite that must stay offline and instant.
Requires the venv: .venv\\Scripts\\python.exe -m pip install -r requirements.txt

Run:  .venv\\Scripts\\python.exe test_service.py
"""
import shutil
import sys
import tempfile

from geocoding import geocode_barbados
from memory_store import PersistentLandmarkMemory

results = []


def record(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"\n         -> {detail}" if not ok and detail else ""))


def test_geocoding():
    known = geocode_barbados("Bridgetown, Barbados")
    record("geocoding: resolves a real named place", known is not None, f"got {known}")
    nonsense = geocode_barbados("third house past the blue rum shop green gate")
    record("geocoding: informal landmark falls back to None (not an error)", nonsense is None, f"got {nonsense}")
    empty = geocode_barbados("")
    record("geocoding: empty query returns None without erroring", empty is None)


def test_persistence():
    tmpdir = tempfile.mkdtemp(prefix="nextgen_chroma_test_")
    try:
        mem1 = PersistentLandmarkMemory(path=tmpdir)
        base_size = mem1.size()
        fixed = (13.0555, -59.6222)
        mem1.learn("the tamarind tree by miss enid shop", fixed)
        record("persistence: resolves immediately after learn (Jaccard path)",
               mem1.resolve("tamarind tree miss enid shop") == fixed)

        # simulate a service restart: fresh instance, same on-disk path
        mem2 = PersistentLandmarkMemory(path=tmpdir)
        record("persistence: learned landmark survives a fresh instance at the same path",
               mem2.resolve("the tamarind tree by miss enid shop") == fixed,
               f"got {mem2.resolve('the tamarind tree by miss enid shop')}")
        record("persistence: hydration didn't duplicate the built-in seed landmarks",
               mem2.size() == base_size + 1, f"size={mem2.size()}, expected {base_size + 1}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_semantic_fallback():
    tmpdir = tempfile.mkdtemp(prefix="nextgen_chroma_test_")
    try:
        mem = PersistentLandmarkMemory(path=tmpdir)
        fixed = (13.111, -59.622)
        mem.learn("blue rum shop corner", fixed)
        # zero shared tokens with the learned phrase -- Jaccard alone can't catch this
        paraphrase = "the little shop painted blue that sells rum, on the corner"
        got = mem.resolve(paraphrase)
        record("semantic fallback: true paraphrase (no shared tokens) still resolves",
               got == fixed, f"got {got}")

        unrelated = mem.resolve("the cricket oval by the roundabout")
        record("semantic fallback: an unrelated landmark does not collide",
               unrelated != fixed, f"got {unrelated}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def main():
    for test in (test_geocoding, test_persistence, test_semantic_fallback):
        try:
            test()
        except Exception as ex:
            record(f"{test.__name__} (harness)", False, f"EXCEPTION {type(ex).__name__}: {ex}")
    passed = sum(ok for _, ok, _ in results)
    total = len(results)
    print(f"\n  {passed}/{total} checks passed.")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
