import io

import requests
from PIL import Image

from .commons import USER_AGENT


def fetch_clean_image(url, max_px=2000):
    """Download an image, strip metadata, downscale, and return a JPEG BytesIO.

    Re-encoding drops all EXIF (including GPS), and re-uploading under a generic filename
    hides the Commons title — both prevent players from looking up the answer.
    """
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    image = Image.open(io.BytesIO(response.content)).convert("RGB")
    image.thumbnail((max_px, max_px))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=88)
    buffer.seek(0)
    return buffer
