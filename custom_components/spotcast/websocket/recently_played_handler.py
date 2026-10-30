"""Websocket endpoint for the recently played albums, artists, playlists
and tracks of an account."""

from asyncio import gather
from logging import getLogger

import voluptuous as vol
from spotipy import SpotifyException
from homeassistant.helpers import config_validation as cv
from homeassistant.core import HomeAssistant
from homeassistant.components.websocket_api import ActiveConnection

from custom_components.spotcast.spotify.internal_api import (
    async_get_playlist_name,
)
from custom_components.spotcast.spotify.utils import select_image_url
from custom_components.spotcast.websocket.utils import (
    websocket_wrapper,
    async_get_account,
)

ENDPOINT = "spotcast/recently_played"
SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.positive_int,
        vol.Required("type"): ENDPOINT,
        vol.Optional("limit"): cv.positive_int,
        vol.Optional("account"): cv.string,
    }
)

LIKED_SONGS = "Liked Songs"

LOGGER = getLogger(__name__)


def group_plays(plays: list[dict], limit: int) -> list[dict]:
    """Groups plays by the context they were played from, newest first,
    keeping each context once. A play without a context stands for its
    track.

    Args:
        - plays(list[dict]): play history items, newest first
        - limit(int): the maximum number of entries to return

    Returns:
        - list[dict]: one entry per context or track, without playlist
            names, which need a separate lookup
    """
    entries = []
    seen = set()

    for play in plays:
        track = play.get("track") or {}
        context = play.get("context") or {}
        uri = context.get("uri") or track.get("uri")

        if uri is None or uri in seen:
            continue

        seen.add(uri)
        item_type = context.get("type") if context.get("uri") else "track"
        album = track.get("album") or {}
        artists = track.get("artists") or []
        name = None

        if item_type == "track":
            name = track.get("name")
        elif item_type == "album":
            # A relinked track can belong to another release than the
            # album it was played from: then the album is looked up.
            if album.get("uri") != uri:
                album = {}
            name = album.get("name")
            artists = album.get("artists") or []
        elif item_type == "artist":
            name = next(
                (a.get("name") for a in artists if a.get("uri") == uri),
                None,
            )
        elif item_type == "collection":
            name = LIKED_SONGS

        entries.append({
            "type": item_type,
            "uri": uri,
            "name": name,
            "artists": (
                [a.get("name") for a in artists]
                if item_type in ("album", "track")
                else []
            ),
            "icon": (
                select_image_url(album.get("images") or [])
                if item_type in ("album", "track")
                else None
            ),
            "played_at": play.get("played_at"),
            "track_uri": track.get("uri"),
        })

        if len(entries) >= limit:
            break

    return entries


async def async_complete_entry(account, entry: dict):
    """Fills in what a play does not carry: playlist names, and the
    name, artists and cover of an album or artist that differs from the
    track's own. A failed lookup leaves the entry as it is.

    Args:
        - account(SpotifyAccount): the account to query with
        - entry(dict): an entry built by `group_plays`, updated in place
    """
    if entry["name"] is not None and entry["type"] != "playlist":
        return

    try:
        if entry["type"] == "playlist":
            entry["name"] = await async_get_playlist_name(
                account,
                entry["uri"],
            )
        elif entry["type"] == "album":
            album = await account.async_get_album(entry["uri"])
            entry["name"] = album.get("name")
            entry["artists"] = [
                a.get("name") for a in album.get("artists") or []
            ]
            entry["icon"] = select_image_url(album.get("images") or [])
        elif entry["type"] == "artist":
            artist = await account.async_get_artist(entry["uri"])
            entry["name"] = artist.get("name")
    except SpotifyException as exc:
        LOGGER.debug("Could not complete `%s`: %s", entry["uri"], exc)


@websocket_wrapper
async def async_recently_played(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict
):
    """Gets the albums, artists, playlists and tracks an account played
    recently, newest first, as Spotify's Recents shows them.

    Args:
        - hass (HomeAssistant): The Home Assistant instance.
        - connection (ActiveConnection): The active WebSocket connection.
        - msg (dict): The message received through the WebSocket API.
    """
    account_id = msg.get("account")
    limit = msg.get("limit", 20)

    account = await async_get_account(hass, account_id)

    plays = await account.async_recently_played()
    entries = group_plays(plays, limit)

    await gather(*(async_complete_entry(account, e) for e in entries))

    connection.send_result(
        msg["id"],
        {
            "total": len(entries),
            "account": account.id,
            "items": entries,
        },
    )
