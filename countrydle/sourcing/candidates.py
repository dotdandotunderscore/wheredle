import random
import re

from ..game import countries
from .commons import fetch_candidates
from .geocode import country_for

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

# Landscape/nature/cityscape categories — vetted to hold geotagged outdoor photos.
DEFAULT_CATEGORIES = (
    "Featured pictures of landscapes",
    "Quality images of landscapes",
    "Quality images of cityscapes",
)


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


def gather(limit_per_category=50, categories=DEFAULT_CATEGORIES):
    """Fetch and qualify candidates across categories; return list of (candidate, iso2)."""
    qualified = []
    for category in categories:
        for candidate in fetch_candidates(category, limit=limit_per_category):
            iso2 = qualify(candidate)
            if iso2:
                qualified.append((candidate, iso2))
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
    """Insert a qualified candidate as a queued puzzle; skip if its image was already used."""
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
           VALUES (?, 'commons', ?, ?, ?, ?, ?, ?, ?, 'queued')""",
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
