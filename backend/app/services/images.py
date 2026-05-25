import io

from PIL import Image as PILImage

_JPEG_QUALITY = 85
_ALLOWED_PIL_FORMATS = {"JPEG", "PNG", "WEBP", "HEIF"}


def validate_image_format(data: bytes) -> None:
    """Verify image bytes decode to an allowed format via PIL magic bytes.

    Raises ValueError for non-image bytes or formats outside the allowlist.
    Content-Type headers are intentionally ignored — they are client-controlled.
    """
    try:
        img = PILImage.open(io.BytesIO(data))
    except Exception as exc:
        raise ValueError("Could not decode image") from exc
    if img.format not in _ALLOWED_PIL_FORMATS:
        raise ValueError(f"Unsupported image format: {img.format}. Allowed: JPEG, PNG, WebP, HEIF")


def resize_to_jpeg(data: bytes, max_px: int = 1600) -> bytes:
    """Resize to at most max_px on the longest side and encode as JPEG."""
    img = PILImage.open(io.BytesIO(data))
    img = img.convert("RGB")  # type: ignore[assignment]
    img.thumbnail((max_px, max_px), PILImage.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
    return out.getvalue()
