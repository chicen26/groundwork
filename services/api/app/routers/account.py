"""Account deletion.

The privacy screen promises that deleting an account deletes the photographs. That promise is only
real if the bytes go too — a database cascade leaves the files sitting in storage, orphaned but very
much still there.

So this collects the storage paths first, deletes the user (which cascades through properties,
scans, photos, findings, and plans), and then removes each file. Doing it in that order means a
crash halfway leaves orphaned files rather than orphaned rows, and orphaned files are recoverable by
a sweep while a half-deleted account is not.

Deliberately irreversible, and it says so.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.auth import CurrentUser
from app.db import pool
from app.storage import get_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/account", tags=["account"])


class DeletionConfirmation(BaseModel):
    """Typed confirmation, so a stray request cannot destroy somebody's data."""

    confirm: str


class DeletionReceipt(BaseModel):
    properties_deleted: int
    photos_deleted: int
    files_removed: int
    # Files the database knew about but storage could not remove. Reported rather than swallowed:
    # an unreported failure here is a broken privacy promise.
    files_failed: int


@router.delete("", response_model=DeletionReceipt)
async def delete_account(user_id: CurrentUser, payload: DeletionConfirmation) -> DeletionReceipt:
    if payload.confirm != "DELETE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='send {"confirm": "DELETE"} to permanently delete this account and its photos',
        )

    async with pool.acquire_as_user(user_id) as conn:
        paths = [
            row["storage_path"]
            for row in await conn.fetch(
                """
                SELECT ph.storage_path
                FROM photos ph
                JOIN scans s ON s.id = ph.scan_id
                JOIN properties p ON p.id = s.property_id
                WHERE p.user_id = $1
                """,
                user_id,
            )
        ]
        properties = await conn.fetchval(
            "SELECT count(*) FROM properties WHERE user_id = $1", user_id
        )

    # The delete runs as the service role: removing the user row is what cascades everything else,
    # and the row-level policy on `users` is scoped to the caller's own row.
    async with pool.acquire_service() as conn:
        await conn.execute("DELETE FROM users WHERE id = $1", user_id)

    storage = get_storage()
    removed = failed = 0
    for path in paths:
        try:
            storage.delete(path)
            removed += 1
        except OSError:
            # Keep going: one unreadable file must not leave the rest of someone's photos behind.
            logger.exception("could not delete photo file during account deletion")
            failed += 1

    return DeletionReceipt(
        properties_deleted=properties,
        photos_deleted=len(paths),
        files_removed=removed,
        files_failed=failed,
    )
