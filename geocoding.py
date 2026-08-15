"""Nominatim (OpenStreetMap) geocoding for new landmarks.

Isolated from nextgen_engine.py per CLAUDE.md house rule 2 -- the core engine
stays dependency-free and offline-safe. This module is used only by the live
service (see PersistentLandmarkMemory / AddressResolutionAgent's estimator hook).

Reality check: Nominatim indexes real map entities (named places, roads,
POIs) -- it will resolve "Esso gas station, Black Rock" but not "third house
past the blue rum shop, green gate". That's expected: for informal landmark
descriptions with no map entity, geocode_barbados() returns None and the
caller falls back to AddressResolutionAgent's random estimate, same as today
-- a human still confirms and the engine still learns it. Geocoding just
gives a better starting estimate for the subset of landmarks that ARE real
named places.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy requires an identifying User-Agent -- unauthenticated
# generic-looking requests get silently rate-limited or blocked.
USER_AGENT = "nextgen-delivery-buildathon/0.1 (contact: martino.bayley@gmail.com)"


def geocode_barbados(query: str, timeout: float = 5.0) -> tuple | None:
    """Best-effort geocode of `query`, biased to Barbados. Returns (lat, lon)
    rounded to 4dp, or None if nothing matched or the request failed for any
    reason (network down, timeout, rate limited, malformed response) --
    callers must treat None as "fall back", never as an error."""
    query = (query or "").strip()
    if not query:
        return None
    params = {
        "q": query,
        "format": "json",
        "limit": 1,
        "countrycodes": "bb",  # ISO 3166-1 alpha-2 for Barbados
    }
    url = f"{NOMINATIM_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            results = json.loads(resp.read().decode("utf-8"))
        if not results:
            return None
        return (round(float(results[0]["lat"]), 4), round(float(results[0]["lon"]), 4))
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError, json.JSONDecodeError):
        return None
