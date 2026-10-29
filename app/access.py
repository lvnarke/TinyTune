"""Permission checks always read committed PostgreSQL state, never the content cache."""

from uuid import UUID

from fastapi import HTTPException, Request


def require_tools(request: Request):
    # Nginx overwrites this header for every public listener. API ports are internal.
    if request.headers.get("X-TinyTune-Surface") != "tools":
        raise HTTPException(404, "Not found")


async def playlist_role(connection, playlist_id: UUID, user_id: UUID, *, edit=False, owner=False, lock=False):
    row = await connection.fetchrow(
        "SELECT owner_id FROM playlists WHERE id=$1" + (" FOR UPDATE" if lock else ""), playlist_id)
    if not row or not row["owner_id"]:
        raise HTTPException(404, "Playlist not found or not shared with you")
    role = "owner" if row["owner_id"] == user_id else await connection.fetchval(
        "SELECT role FROM playlist_members WHERE playlist_id=$1 AND user_id=$2", playlist_id, user_id)
    if not role:
        raise HTTPException(404, "Playlist not found or not shared with you")
    if owner and role != "owner":
        raise HTTPException(403, "Only the owner can manage sharing")
    if edit and role not in {"owner", "editor"}:
        raise HTTPException(403, "You have view access. Ask the owner for edit access.")
    return role
