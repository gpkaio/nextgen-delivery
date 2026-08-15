"""Chroma-backed landmark memory for the live service.

Isolated from the core engine per CLAUDE.md house rule 2 -- nextgen_engine.py
and test_engine.py never import this module, so the dependency-free "runs
anywhere" demo path is untouched.

Adds two things on top of the tested in-memory LandmarkMemory:
  1. Persistence -- learned landmarks survive process restarts.
  2. Semantic fallback -- Chroma's embeddings catch true paraphrases
     (different words, same meaning, e.g. "the drinks shop painted blue"
     vs "blue rum shop") that word-overlap Jaccard matching can't.

The Jaccard matcher stays the FIRST check on every resolve(), via super().
That's the tested, demoed moat behavior (see suites C/D in test_engine.py)
-- this class only adds a second-chance lookup, never replaces the first.
"""
from __future__ import annotations

import chromadb

from nextgen_engine import LandmarkMemory

# Cosine distance cutoff for the semantic fallback. Chroma's default
# embedding function (all-MiniLM-L6-v2, runs locally, no API calls) puts
# near-duplicate sentences well under this; unrelated landmarks land above
# it. Tune against real Barbados landmark data once you have some.
SEMANTIC_DISTANCE_THRESHOLD = 0.35


class PersistentLandmarkMemory(LandmarkMemory):
    def __init__(self, path: str = "./chroma_data"):
        super().__init__()  # seeds the same 2 built-in landmarks + Jaccard store
        client = chromadb.PersistentClient(path=path)
        self.collection = client.get_or_create_collection("landmarks")
        self._hydrate_jaccard_store_from_chroma()

    def _hydrate_jaccard_store_from_chroma(self) -> None:
        """On startup, replay everything Chroma has persisted into the fast
        in-memory Jaccard store, so a restarted service resolves previously
        learned landmarks instantly again, not just via the slower semantic path."""
        existing = self.collection.get(include=["documents", "metadatas"])
        for doc, meta in zip(existing.get("documents") or [], existing.get("metadatas") or []):
            self._store[self._key(doc)] = (meta["lat"], meta["lon"])

    def resolve(self, landmark: str) -> tuple | None:
        exact = super().resolve(landmark)  # Jaccard first -- the tested moat behavior
        if exact:
            return exact
        results = self.collection.query(query_texts=[landmark], n_results=1)
        ids = results.get("ids") or [[]]
        if not ids[0]:
            return None
        distance = results["distances"][0][0]
        if distance > SEMANTIC_DISTANCE_THRESHOLD:
            return None
        meta = results["metadatas"][0][0]
        return (meta["lat"], meta["lon"])

    def learn(self, landmark: str, drop_point: tuple) -> None:
        super().learn(landmark, drop_point)  # keeps the Jaccard store in sync
        key = self._key(landmark)
        if not key:
            return
        lat, lon = drop_point
        self.collection.upsert(
            ids=[key],
            documents=[landmark],
            metadatas=[{"lat": lat, "lon": lon}],
        )
