"""Profile pictures (2026-10-20): stored as a BLOB directly on `users`, never on disk --
same reasoning as qmail_attachments (migration 023) and profile_change_attachments
(identity_core.py): the database already carries the volume-persistence guarantee a disk path
on Railway would need a separately-configured mount to earn. One picture per user (not a
history), so a direct column is simpler than a whole new table.

Self-service, no council approval needed -- a picture isn't a FOUNDATIONAL identity fact
(name/DOB/location) that needs verification, it's cosmetic, same category as relationship_status
or hide_identity (app.py's RELATIONSHIP_STATUSES/WORK_PROFILES docstring already draws this
distinction for similar fields).

Every stored picture is re-encoded server-side, unconditionally -- never the raw upload:
  - EXIF is stripped. A phone photo's EXIF routinely carries GPS coordinates -- a real location
    leak, not a hypothetical one, for an app whose entire design is already careful about never
    exposing more location precision than a feature needs.
  - EXIF orientation is applied BEFORE stripping (ImageOps.exif_transpose) -- many phones store
    rotation in EXIF rather than rotating the pixels; stripping first would leave the stored
    image sideways.
  - Center-cropped to a square, resized to a fixed 256x256, saved as JPEG (quality 85). Every
    consumer (tree card, search result, profile hero) gets the same small, predictable size
    regardless of what the user uploaded -- "we should not serve a 5MB image in a 40px avatar."
"""
from __future__ import annotations

import datetime as dt
import io
import os

from PIL import Image, ImageOps

MAX_UPLOAD_BYTES = 3 * 1024 * 1024  # matches app.py's existing app-wide MAX_CONTENT_LENGTH ceiling
THUMBNAIL_SIZE = 256
JPEG_QUALITY = 85

# Extension -> the content types a browser may declare for it, narrower than qmail_core's general
# attachment allowlist (which also permits pdf/docx/etc -- not valid for a profile picture at all).
ALLOWED_IMAGE_TYPES = {
    "png": ("image/png",),
    "jpg": ("image/jpeg", "image/pjpeg"),
    "jpeg": ("image/jpeg", "image/pjpeg"),
    "webp": ("image/webp",),
}


class ImageTypeError(ValueError):
    """A file type outside ALLOWED_IMAGE_TYPES, or an extension and declared content type that
    disagree -- same pattern as qmail_core.AttachmentTypeError, a ValueError subclass so a plain
    `except ValueError` still catches it, with its own distinct type for a caller that wants to
    tell "wrong type" (400) apart from "too big" (413)."""


def _validate_image_type(filename: str, content_type: str) -> None:
    ext = os.path.splitext(filename or "")[1].lower().lstrip(".")
    allowed = ALLOWED_IMAGE_TYPES.get(ext)
    if not allowed:
        raise ImageTypeError("Only PNG, JPG and WEBP images are accepted")
    declared = (content_type or "").split(";")[0].strip().lower()
    if declared not in allowed:
        raise ImageTypeError("The file's type doesn't match its extension")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def process_image(data: bytes) -> bytes:
    """Raw upload bytes -> a 256x256 JPEG, EXIF stripped (orientation applied first), center-cropped
    to square. Raises ValueError (via Pillow) if the bytes aren't a readable image at all -- a
    file that passed the extension/content-type check but isn't really an image of that type."""
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)  # bake in rotation before EXIF is discarded below
    img = img.convert("RGB")  # JPEG has no alpha channel; flattens PNG transparency onto white

    w, h = img.size
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    img = img.crop((left, top, left + side, top + side)).resize(
        (THUMBNAIL_SIZE, THUMBNAIL_SIZE), Image.LANCZOS
    )

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY)  # no exif= kwarg -- nothing carried over
    return out.getvalue()


def save_profile_picture(conn, user_id: int, filename: str, content_type: str, data: bytes) -> None:
    """Validates, processes and stores one user's profile picture. Raises ImageTypeError (400) for
    a disallowed/mismatched type, ValueError for an oversized upload or unreadable image data."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"Image exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")
    _validate_image_type(filename, content_type)
    thumbnail = process_image(data)
    conn.execute(
        "UPDATE users SET profile_picture = ?, profile_picture_updated_at = ? WHERE id = ?",
        (thumbnail, _now(), user_id),
    )
    conn.commit()


def get_profile_picture(conn, user_id: int, viewer_user_id) -> bytes | None:
    """The stored JPEG bytes, or None if there isn't one -- or if there is, but the owner has
    hide_identity set and the viewer isn't an established family member (see
    social_core.is_family_member()): a hidden identity's face is exactly as sensitive as their
    name, masked the same way, not an oversight to leave exposed just because this is a different
    code path from the name-masking one."""
    row = conn.execute(
        "SELECT profile_picture, hide_identity FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if not row or not row["profile_picture"]:
        return None
    if row["hide_identity"] and viewer_user_id != user_id:
        import social_core
        if not social_core.is_family_member(conn, user_id, viewer_user_id):
            return None
    return row["profile_picture"]
