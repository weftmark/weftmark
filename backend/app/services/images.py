import io

from PIL import Image as PILImage

_JPEG_QUALITY = 85


def resize_to_jpeg(data: bytes, max_px: int = 1600) -> bytes:
    """Resize to at most max_px on the longest side and encode as JPEG."""
    img = PILImage.open(io.BytesIO(data))
    img = img.convert("RGB")
    img.thumbnail((max_px, max_px), PILImage.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
    return out.getvalue()
