import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pycountry
from rapidfuzz import fuzz, process

from .scoring import haversine_km

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "countries.csv"


@dataclass(frozen=True)
class Country:
    """A country's ISO 3166-1 alpha-2 code, display name, and centroid coordinates."""

    iso2: str
    name: str
    lat: float
    lon: float


@lru_cache(maxsize=1)
def _registry(path=str(DATA_PATH)):
    """Load countries.csv into an iso2 -> Country mapping (cached after first call)."""
    registry = {}
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            iso2 = row["iso2"].strip().upper()
            registry[iso2] = Country(iso2, row["name"].strip(), float(row["lat"]), float(row["lon"]))
    return registry


def all_countries():
    """Return every known country sorted by display name (handy for autocomplete)."""
    return sorted(_registry().values(), key=lambda c: c.name)


def get(iso2):
    """Return the Country for an ISO2 code, or None if it is unknown."""
    return _registry().get(iso2.upper())


def distance_between(iso_a, iso_b):
    """Great-circle distance in km between two countries' centroids."""
    a, b = get(iso_a), get(iso_b)
    if a is None or b is None:
        raise KeyError(f"unknown country code: {iso_a if a is None else iso_b}")
    return haversine_km(a.lat, a.lon, b.lat, b.lon)


def flag_emoji(iso2):
    """Return the Unicode regional-indicator flag for an ISO2 code, or '' if invalid."""
    code = iso2.upper()
    if len(code) != 2 or not code.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in code)


def resolve(query):
    """Resolve free-text input to an ISO2 code via pycountry, falling back to fuzzy matching."""
    text = query.strip()
    if not text:
        return None
    registry = _registry()
    try:
        match = pycountry.countries.lookup(text)
        if match.alpha_2 in registry:
            return match.alpha_2
    except LookupError:
        pass
    names = {country.name: iso2 for iso2, country in registry.items()}
    best = process.extractOne(text, names.keys(), scorer=fuzz.WRatio, score_cutoff=80)
    return names[best[0]] if best else None
