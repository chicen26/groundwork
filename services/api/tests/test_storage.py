"""Photo sanitising and storage tests.

The EXIF test is the one that matters. A phone photograph of someone's house carries their GPS
coordinates, and the promise on the privacy screen is that we do not keep them. This proves it for
real: build an image with GPS and a device make in its EXIF, run it through, and assert the metadata
is gone from the bytes we would store.
"""

from __future__ import annotations

import io
from pathlib import Path
from uuid import uuid4

import piexif
import pytest
from PIL import Image

from app.storage import LocalPhotoStorage, UnsupportedImage, sanitize


def image_with_exif(*, width: int = 800, height: int = 600) -> bytes:
    """A JPEG carrying GPS coordinates and a camera make, like a real phone photo."""
    image = Image.new("RGB", (width, height), (90, 120, 70))
    exif = {
        "0th": {piexif.ImageIFD.Make: b"TestPhone", piexif.ImageIFD.Model: b"TestPhone 15"},
        "Exif": {piexif.ExifIFD.DateTimeOriginal: b"2026:08:04 09:30:00"},
        "GPS": {
            piexif.GPSIFD.GPSLatitudeRef: b"N",
            piexif.GPSIFD.GPSLatitude: ((37, 1), (49, 1), (1800, 100)),
            piexif.GPSIFD.GPSLongitudeRef: b"W",
            piexif.GPSIFD.GPSLongitude: ((121, 1), (59, 1), (5900, 100)),
        },
        "1st": {},
        "thumbnail": None,
    }
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=piexif.dump(exif))
    return buffer.getvalue()


def test_the_fixture_really_does_carry_gps() -> None:
    """Guard the guard: if the fixture stopped embedding GPS, the next test would prove nothing."""
    exif = piexif.load(image_with_exif())

    assert exif["GPS"], "fixture must carry GPS for the stripping test to mean anything"
    assert exif["0th"][piexif.ImageIFD.Make] == b"TestPhone"


def test_sanitising_removes_gps_and_device_metadata() -> None:
    clean, width, height = sanitize(image_with_exif())

    exif = piexif.load(clean)
    assert not exif["GPS"], "GPS coordinates survived sanitising"
    assert not exif["0th"], "camera make and model survived sanitising"
    assert not exif["Exif"], "capture timestamp survived sanitising"
    assert (width, height) == (800, 600)


def test_sanitising_keeps_the_picture() -> None:
    """Stripping metadata must not disturb the pixels the model will look at."""
    clean, _, _ = sanitize(image_with_exif(width=200, height=100))

    with Image.open(io.BytesIO(clean)) as image:
        assert image.size == (200, 100)
        assert image.getpixel((10, 10))[1] > image.getpixel((10, 10))[2]  # still green-dominant


def test_oversized_photos_are_scaled_down() -> None:
    clean, width, height = sanitize(image_with_exif(width=6000, height=4000))

    assert max(width, height) == 4096
    assert width / height == pytest.approx(1.5, abs=0.01)
    assert len(clean) > 0


def test_a_rotated_photo_is_stored_upright() -> None:
    """Orientation lives in EXIF. Applying it before stripping keeps bounding boxes meaningful."""
    image = Image.new("RGB", (400, 200), (10, 20, 30))
    exif = piexif.dump({"0th": {piexif.ImageIFD.Orientation: 6}, "Exif": {}, "GPS": {}, "1st": {}})
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)

    _, width, height = sanitize(buffer.getvalue())

    # Orientation 6 means "rotate 90°": the stored image should be portrait.
    assert (width, height) == (200, 400)


def test_a_non_image_upload_is_refused() -> None:
    with pytest.raises(UnsupportedImage):
        sanitize(b"this is not an image, it is a sentence")


def test_stored_paths_are_unguessable(tmp_path: Path) -> None:
    """The path is the only thing between an attacker and a photograph of somebody's house."""
    storage = LocalPhotoStorage(tmp_path)
    scan_id = uuid4()

    first = storage.put(scan_id, b"one")
    second = storage.put(scan_id, b"two")

    assert first != second
    assert not first.endswith("1.jpg")
    assert storage.get(first) == b"one"


def test_storage_refuses_to_escape_its_root(tmp_path: Path) -> None:
    storage = LocalPhotoStorage(tmp_path / "photos")

    with pytest.raises(ValueError, match="outside the storage root"):
        storage.get("../../../etc/passwd")


def test_deleting_a_photo_removes_the_bytes(tmp_path: Path) -> None:
    """Delete-account has to mean the photograph is gone, not merely unreferenced."""
    storage = LocalPhotoStorage(tmp_path)
    path = storage.put(uuid4(), b"pixels")

    storage.delete(path)

    with pytest.raises(FileNotFoundError):
        storage.get(path)
