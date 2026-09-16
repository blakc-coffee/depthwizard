"""Shared upload-content validation — used by both routes/jobs.py (terrain)
and routes/silt_jobs.py (river-silt). Extracted here rather than one
importing the other's private helpers, since both job kinds validate
uploads identically (PRD §9.5 / §17).
"""

from __future__ import annotations

import struct
from io import BytesIO
from pathlib import Path

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


def _tiff_dimensions(content: bytes) -> tuple[int, int] | None:
    """Reads ImageWidth/ImageLength (tags 256/257) straight from the first
    IFD — Pillow can't open many valid GeoTIFFs, so it can't be used here."""
    endian = "<" if content[:2] == b"II" else ">"
    try:
        (ifd_offset,) = struct.unpack_from(endian + "I", content, 4)
        (entry_count,) = struct.unpack_from(endian + "H", content, ifd_offset)
        dims: dict[int, int] = {}
        for i in range(entry_count):
            entry = ifd_offset + 2 + i * 12
            tag, field_type = struct.unpack_from(endian + "HH", content, entry)
            if tag in (256, 257):
                # SHORT (type 3) or LONG (type 4), stored in the 4-byte value field.
                (dims[tag],) = struct.unpack_from(endian + ("H" if field_type == 3 else "I"), content, entry + 8)
        return dims[256], dims[257]
    except (struct.error, KeyError):
        return None


def validate_image_content(content: bytes, media_type: str, max_pixels: int) -> None:
    """PNG/JPEG are fully verified via Pillow. TIFF deliberately stops at the
    magic-byte check above: many valid GeoTIFFs (multi-band, 16-bit, unusual
    compression) aren't Pillow-decodable, but rasterio (worker-side) can read
    them. Rejecting here on Pillow's narrower support would silently disable
    the GeoTIFF path.

    Every format gets a width x height check, since the worker decodes the
    full-resolution image."""
    if media_type == "image/tiff":
        size = _tiff_dimensions(content)
    else:
        try:
            with Image.open(BytesIO(content)) as img:
                size = img.size
                img.verify()
        except Exception as exc:
            raise ApiException(ErrorCode.INVALID_IMAGE, "File could not be decoded as a valid image.") from exc

    if size is None:
        raise ApiException(ErrorCode.INVALID_IMAGE, "File could not be decoded as a valid image.")
    width, height = size
    if width * height > max_pixels:
        raise ApiException(
            ErrorCode.INVALID_IMAGE,
            f"Image is {width}x{height} pixels; the limit is {max_pixels / 1_000_000:g} megapixels.",
        )


def sanitize_filename(filename: str | None) -> str:
    """The client-supplied filename is embedded directly in the storage path
    (inputs/{user_id}/{job_id}/{filename}, PRD §7) — never trust it. `.name`
    strips any directory components (e.g. "../../etc/passwd" -> "passwd"),
    but doesn't normalize a bare "." or ".." on its own, so those are caught
    explicitly."""
    name = Path(filename or "upload").name
    if name in ("", ".", ".."):
        return "upload"
    return name
