import csv
import random
import re
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

from ..game import countries
from .commons import fetch_candidates
from .geocode import country_for

CATEGORIES_PATH = Path(__file__).resolve().parents[2] / "data" / "commons_categories.csv"

MIN_WIDTH = 1920
MIN_HEIGHT = 1080
MAX_ASPECT_RATIO = 2.0  # rejects 360° panoramas (2:1+); allows wide cityscape skylines
ALLOWED_MIME = {"image/jpeg", "image/png"}

# Titles matching these are not "guess the place from a striking photo" puzzles.
BLOCK_RE = re.compile(
    r"\b(map|diagram|chart|logo|coat of arms|svg|graph|schematic|sculpture|statue|"
    r"organ|museum|specimen|interior|coin|stamp|sign|portrait|monument)\b",
    re.I,
)


@lru_cache(maxsize=1)
def _load_categories(path=str(CATEGORIES_PATH)):
    """Load the per-country sampling catalogue as a list of (iso2, category)."""
    with open(path, newline="", encoding="utf-8") as handle:
        return [
            (row["iso2"].strip().upper(), row["category"].strip())
            for row in csv.DictReader(handle)
        ]


def qualify(candidate):
    """Return the answer ISO2 if a candidate passes all quality filters, else None."""
    if candidate.get("mime") not in ALLOWED_MIME:
        return None
    width = candidate.get("width") or 0
    height = candidate.get("height") or 0
    if width < MIN_WIDTH or height < MIN_HEIGHT:
        return None
    if height > 0 and (width / height) > MAX_ASPECT_RATIO:
        return None
    if BLOCK_RE.search(candidate.get("title") or ""):
        return None
    return country_for(candidate["lat"], candidate["lon"])


def _fetch_for_category(args):
    category, per_country, fetch_limit = args
    passing = []
    for candidate in fetch_candidates(category, limit=fetch_limit):
        answer = qualify(candidate)
        if answer:
            passing.append((candidate, answer))
    random.shuffle(passing)
    return passing[:per_country]


def gather(per_country=1, countries_per_run=10, fetch_limit=60, catalogue=None):
    """Sample qualified candidates from a balanced random subset of countries.

    Drawing from per-country categories and capping each country's contribution keeps
    any one region (historically Europe) from dominating the queue. The category only
    decides where we look; each photo's own coordinate still decides the answer.
    """
    catalogue = catalogue if catalogue is not None else _load_categories()
    selection = random.sample(catalogue, min(countries_per_run, len(catalogue)))

    with ThreadPoolExecutor(max_workers=3) as pool:
        batches = pool.map(_fetch_for_category, [(cat, per_country, fetch_limit) for _, cat in selection])
    qualified = [item for batch in batches for item in batch]

    random.shuffle(qualified)
    seen_authors: set[str] = set()
    deduped = []
    for candidate, iso2 in qualified:
        author = candidate.get("author")
        if author is None or author not in seen_authors:
            deduped.append((candidate, iso2))
            if author is not None:
                seen_authors.add(author)
    return deduped


def queue_candidate(conn, candidate, iso2):
    """Insert a qualified candidate as a pending puzzle (awaiting admin review); skip if already used."""
    used = conn.execute(
        "SELECT 1 FROM puzzles WHERE source='commons' AND source_id=?",
        (str(candidate["pageid"]),),
    ).fetchone()
    if used:
        return False
    country = countries.get(iso2)
    conn.execute(
        """INSERT INTO puzzles
               (image_path, source, source_id, author, license, attribution_url,
                answer_iso, answer_lat, answer_lon, status)
           VALUES (?, 'commons', ?, ?, ?, ?, ?, ?, ?, 'pending')""",
        (
            candidate["image_url"],
            str(candidate["pageid"]),
            candidate["author"],
            candidate["license"],
            candidate["attribution_url"],
            iso2,
            country.lat,
            country.lon,
        ),
    )
    return True
