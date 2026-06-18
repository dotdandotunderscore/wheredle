from countrydle.game import countries


def test_registry_loads_many_countries():
    assert len(countries.all_countries()) > 150


def test_lookup_by_iso():
    france = countries.get("FR")
    assert france is not None
    assert "France" in france.name


def test_resolve_common_names():
    assert countries.resolve("United States") == "US"
    assert countries.resolve("USA") == "US"
    assert countries.resolve("germany") == "DE"


def test_resolve_handles_typos():
    assert countries.resolve("Frnace") == "FR"


def test_resolve_unknown_returns_none():
    assert countries.resolve("not a real place zzz") is None


def test_distance_between_neighbours_is_small():
    # France and Germany centroids are close; France and Australia are far.
    assert countries.distance_between("FR", "DE") < 1500
    assert countries.distance_between("FR", "AU") > 10000
