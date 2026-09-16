"""Shared upload-content validation — used by both routes/jobs.py (terrain)
and routes/silt_jobs.py (river-silt). Extracted here rather than one
importing the other's private helpers, since both job kinds validate
uploads identically (PRD §9.5 / §17).
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from app.core.errors import ApiException, ErrorCode


def sniff_media_type(content: bytes) -> str:
    """Content-based type detection — never trust the declared Content-Type,
    especially for TIFF (client MIME for TIFF is unreliable)."""
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if content[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if content[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    raise ApiException(ErrorCode.UNSUPPORTED_FILE, "File is not a PNG, JPEG, or TIFF/GeoTIFF.")


def validate_image_content(content: bytes, media_type: str) -> None:
    """PNG/JPEG are fully verified via Pillow. TIFF deliberately stops at the
    magic-byte check above: many valid GeoTIFFs (multi-band, 16-bit, unusual
    compression) aren't Pillow-decodable, but rasterio (worker-side) can read
    them. Rejecting here on Pillow's narrower support would silently disable
    the GeoTIFF path."""
    if media_type == "image/tiff":
        return
    try:
        with Image.open(BytesIO(content)) as img:
            img.verify()
    except Exception as exc:
        raise ApiException(ErrorCode.INVALID_IMAGE, "File could not be decoded as a valid image.") from exc
