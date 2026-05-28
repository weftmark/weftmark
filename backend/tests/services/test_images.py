"""Tests for app.services.images."""

import io

import pytest
from PIL import Image as PILImage

from app.services.images import resize_to_jpeg, validate_image_format


def _make_png_bytes(width: int = 4, height: int = 4) -> bytes:
    img = PILImage.new("RGB", (width, height), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_gif_bytes(width: int = 4, height: int = 4) -> bytes:
    img = PILImage.new("P", (width, height))
    buf = io.BytesIO()
    img.save(buf, format="GIF")
    return buf.getvalue()


class TestValidateImageFormat:
    def test_valid_png_passes(self):
        validate_image_format(_make_png_bytes())  # no exception

    def test_non_image_bytes_raise(self):
        with pytest.raises(ValueError, match="Could not decode image"):
            validate_image_format(b"this is not an image")

    def test_unsupported_format_raises(self):
        with pytest.raises(ValueError, match="Unsupported image format"):
            validate_image_format(_make_gif_bytes())

    def test_empty_bytes_raise(self):
        with pytest.raises(ValueError, match="Could not decode image"):
            validate_image_format(b"")


class TestResizeToJpeg:
    def test_returns_bytes(self):
        result = resize_to_jpeg(_make_png_bytes())
        assert isinstance(result, bytes)

    def test_output_is_jpeg(self):
        result = resize_to_jpeg(_make_png_bytes())
        img = PILImage.open(io.BytesIO(result))
        assert img.format == "JPEG"

    def test_large_image_resized(self):
        large = _make_png_bytes(width=3000, height=3000)
        result = resize_to_jpeg(large, max_px=100)
        img = PILImage.open(io.BytesIO(result))
        assert max(img.size) <= 100

    def test_small_image_not_upscaled(self):
        small = _make_png_bytes(width=10, height=10)
        result = resize_to_jpeg(small, max_px=1600)
        img = PILImage.open(io.BytesIO(result))
        assert max(img.size) <= 10
