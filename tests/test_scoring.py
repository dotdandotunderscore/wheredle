from countrydle.game.scoring import haversine_km, score_for_distance


def test_haversine_known_distance():
    # London to Paris is roughly 343 km.
    distance = haversine_km(51.5074, -0.1278, 48.8566, 2.3522)
    assert 330 < distance < 360


def test_haversine_zero():
    assert haversine_km(10.0, 20.0, 10.0, 20.0) == 0


def test_exact_match_scores_full():
    assert score_for_distance(0, exact=True) == 100
    assert score_for_distance(5000, exact=True) == 100


def test_score_decays_with_distance():
    near = score_for_distance(100)
    far = score_for_distance(5000)
    assert near > far
    assert score_for_distance(0) == 100
    assert 0 <= far <= 100


def test_score_is_bounded():
    assert score_for_distance(40000) >= 0
