import pytest

from countrydle.sourcing import candidates
from countrydle.sourcing.commons import _clean, _pick_coord


def _candidate(**overrides):
    base = {
        "title": "File:Beautiful fjord.jpg",
        "pageid": 123,
        "mime": "image/jpeg",
        "width": 4000,
        "height": 3000,
        "lat": 60.0,
        "lon": 5.0,
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def fake_geocode(monkeypatch):
    # Avoid the offline reverse-geocoder dataset in unit tests; pretend everything is Norway.
    monkeypatch.setattr(candidates, "country_for", lambda lat, lon: "NO")


def test_qualify_accepts_good_candidate():
    assert candidates.qualify(_candidate()) == "NO"


def test_qualify_rejects_small_image():
    assert candidates.qualify(_candidate(width=800, height=600)) is None


def test_qualify_rejects_wrong_mime():
    assert candidates.qualify(_candidate(mime="image/svg+xml")) is None


def test_qualify_rejects_blocked_title():
    assert candidates.qualify(_candidate(title="File:Map of Norway.jpg")) is None


def test_clean_strips_html():
    assert _clean('<a href="x">Jane Doe</a>') == "Jane Doe"
    assert _clean(None) is None


def test_pick_coord_prefers_object_location():
    coords = [
        {"lat": 1.0, "lon": 1.0, "primary": "", "globe": "earth"},  # camera (primary)
        {"lat": 2.0, "lon": 2.0, "globe": "earth"},                  # object (secondary)
    ]
    assert _pick_coord(coords) == {"lat": 2.0, "lon": 2.0}
