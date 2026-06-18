import reverse_geocoder as rg

from ..game import countries


def country_for(lat, lon):
    """Reverse-geocode a coordinate to an ISO2 code known to the registry, or None.

    Uses an offline dataset (no network, no rate limits). Returns None for points that
    resolve to an unknown/unsupported country (e.g. ocean, disputed regions).
    """
    result = rg.search([(float(lat), float(lon))], mode=1)
    if not result:
        return None
    cc = (result[0].get("cc") or "").upper()
    return cc if countries.get(cc) else None
