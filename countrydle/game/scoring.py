import math

EARTH_RADIUS_KM = 6371.0

# Distance at which a guess decays to 100/e (~37) points. Larger = more forgiving.
DECAY_KM = 2000.0


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in kilometres between two lat/lon points (degrees)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def score_for_distance(distance_km, exact=False):
    """Map a guess distance to 0-100 points; an exact-country match always scores 100."""
    if exact:
        return 100
    return round(100 * math.exp(-distance_km / DECAY_KM))
