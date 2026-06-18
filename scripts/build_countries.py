import csv
import io
import sys
import urllib.request
from pathlib import Path

# Canonical country centroids published by Google (public domain), columns: country,latitude,longitude,name
SOURCE_URL = "https://raw.githubusercontent.com/google/dspl/master/samples/google/canonical/countries.csv"
OUT_PATH = Path(__file__).resolve().parents[1] / "data" / "countries.csv"


def main():
    """Download canonical country centroids and write data/countries.csv as iso2,name,lat,lon."""
    with urllib.request.urlopen(SOURCE_URL, timeout=30) as response:
        text = response.read().decode("utf-8")

    rows = []
    for record in csv.DictReader(io.StringIO(text)):
        iso2 = (record.get("country") or "").strip().upper()
        name = (record.get("name") or "").strip()
        lat = (record.get("latitude") or "").strip()
        lon = (record.get("longitude") or "").strip()
        if not (iso2 and name and lat and lon):
            continue
        rows.append((iso2, name, lat, lon))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["iso2", "name", "lat", "lon"])
        writer.writerows(sorted(rows))

    print(f"wrote {len(rows)} countries to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
