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
from custom_components.spotcast.const import DOMAIN
from custom_components.spotcast.spotify.recents import group_plays
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

LOGGER = getLogger(__name__)


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
    recently, newest first, as Spotify's Recents shows them: Spotcast's
    own log, refreshed with Spotify's last 50 plays.

    Args:
        - hass (HomeAssistant): The Home Assistant instance.
        - connection (ActiveConnection): The active WebSocket connection.
        - msg (dict): The message received through the WebSocket API.
    """
    account_id = msg.get("account")
    limit = msg.get("limit", 20)

    account = await async_get_account(hass, account_id)

    plays = await account.async_recently_played()
    played = group_plays(plays, len(plays))
    recents = (
        hass.data.get(DOMAIN, {}).get(account.entry_id, {}).get("recents")
    )

    if recents is None:
        entries = played[:limit]
    else:
        recents.merge(played)
        entries = recents.entries(limit)

    await gather(*(async_complete_entry(account, e) for e in entries))

    if recents is not None:
        # Keeps the looked up names and covers for the next request
        recents.merge(entries)

    connection.send_result(
        msg["id"],
        {
            "total": len(entries),
            "account": account.id,
            "items": entries,
        },
    )
