"""Photo storage, and the EXIF stripping that has to happen before anything is written.

Photographs of someone's home are the most sensitive thing this product handles. Two rules, enforced
here rather than trusted to callers:

* Metadata is stripped on the way in. A phone photo carries GPS coordinates, a device serial, and a
  timestamp; we keep the location only as our own field, with consent, and the rest never lands.
* Bytes are never publicly addressable. Files are stored under an unguessable path and served only
  through an authenticated endpoint, so a leaked URL is not a leaked house.

The interface is deliberately small so a Supabase Storage backend can replace the local one without
touching a handler.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from PIL import Image, UnidentifiedImageError

# Formats we accept from the client. Anything else is refused rather than stored and puzzled over
# later by the inference worker.
ACCEPTED_FORMATS = {"JPEG", "PNG", "HEIF", "HEIC", "WEBP"}
MAX_DIMENSION_PX = 4096


class UnsupportedImage(ValueError):
    """The upload was not an image we can process."""


@dataclass(frozen=True)
class StoredPhoto:
    path: str
    width_px: int
    height_px: int
    byte_size: int


def sanitize(raw: bytes) -> tuple[bytes, int, int]:
    """Decode, strip every scrap of metadata, and re-encode.

    Re-encoding through a fresh image object is what actually removes EXIF, ICC, and XMP data: it
    copies the pixels and nothing else. Oversized images are also scaled down here, since a 12-
    megapixel photo costs upload time and inference time without helping the model.
    """
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ACCEPTED_FORMATS:
                raise UnsupportedImage(f"unsupported image format: {image.format}")

            # EXIF orientation must be applied before we discard EXIF, or a portrait photo would be
            # stored sideways and every bounding box would be wrong.
            from PIL import ImageOps

            upright = ImageOps.exif_transpose(image)
            upright = upright.convert("RGB")

            if max(upright.size) > MAX_DIMENSION_PX:
                upright.thumbnail((MAX_DIMENSION_PX, MAX_DIMENSION_PX), Image.LANCZOS)

            # Rebuild from raw pixel bytes. This is what actually removes EXIF, ICC, and XMP: the
            # new image has no `info` dict to carry them, so only pixels can survive.
            clean = Image.frombytes(upright.mode, upright.size, upright.tobytes())

            buffer = io.BytesIO()
            clean.save(buffer, format="JPEG", quality=88, optimize=True)
            return buffer.getvalue(), clean.width, clean.height
    except UnidentifiedImageError as exc:
        raise UnsupportedImage("could not decode that file as an image") from exc


class PhotoStorage(Protocol):
    def put(self, scan_id: UUID, data: bytes) -> str: ...

    def get(self, path: str) -> bytes: ...

    def delete(self, path: str) -> None: ...


class LocalPhotoStorage:
    """Filesystem storage for development and for the demo-day laptop fallback."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, path: str) -> Path:
        # Paths come from our own database, but treating them as untrusted costs nothing and stops
        # a traversal from ever being one bug away.
        candidate = (self.root / path).resolve()
        if not candidate.is_relative_to(self.root.resolve()):
            raise ValueError("refusing to access a path outside the storage root")
        return candidate

    def put(self, scan_id: UUID, data: bytes) -> str:
        # A random name, not a sequential or guessable one: the path is the only thing between an
        # attacker and a photograph of somebody's house.
        path = f"{scan_id}/{uuid4().hex}.jpg"
        destination = self._resolve(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return path

    def get(self, path: str) -> bytes:
        return self._resolve(path).read_bytes()

    def delete(self, path: str) -> None:
        self._resolve(path).unlink(missing_ok=True)


_storage: PhotoStorage | None = None


def init_storage(root: Path) -> PhotoStorage:
    global _storage
    _storage = LocalPhotoStorage(root)
    return _storage


def get_storage() -> PhotoStorage:
    if _storage is None:
        raise RuntimeError("photo storage is not initialised; call init_storage() during startup")
    return _storage
