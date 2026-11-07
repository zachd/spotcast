"""Websocket endpoint for every track an account played, each with the
album, artist or playlist it was played from."""

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
from custom_components.spotcast.websocket.utils import (
    websocket_wrapper,
    async_get_account,
)

ENDPOINT = "spotcast/play_history"
SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.positive_int,
        vol.Required("type"): ENDPOINT,
        vol.Optional("limit"): cv.positive_int,
        vol.Optional("account"): cv.string,
    }
)

LOGGER = getLogger(__name__)


async def async_name_playlist(account, log, uri: str):
    """Looks up a playlist's name and gives it to the log's plays of it.
    A failed lookup leaves them unnamed.

    Args:
        - account(SpotifyAccount): the account to query with
        - log(PlayLog): the account's play log
        - uri(str): the playlist's URI
    """
    try:
        name = await async_get_playlist_name(account, uri)
    except SpotifyException as exc:
        LOGGER.debug("Could not name `%s`: %s", uri, exc)
        return

    if name:
        log.name_context(uri, name)


@websocket_wrapper
async def async_play_history(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict
):
    """Gets the tracks an account played, newest first, one entry per
    play: Spotcast's own log, completed with Spotify's last 50 plays.

    Args:
        - hass (HomeAssistant): The Home Assistant instance.
        - connection (ActiveConnection): The active WebSocket connection.
        - msg (dict): The message received through the WebSocket API.
    """
    account_id = msg.get("account")
    limit = msg.get("limit", 500)

    account = await async_get_account(hass, account_id)
    history = await account.async_recently_played()
    log = hass.data.get(DOMAIN, {}).get(account.entry_id, {}).get("plays")

    if log is None:
        connection.send_result(
            msg["id"], {"total": 0, "account": account.id, "items": []},
        )
        return

    log.merge_history(history)
    unnamed = {
        play["context_uri"]
        for play in log.plays(limit)
        if play["context_type"] == "playlist" and play["context_name"] is None
    }
    await gather(*(async_name_playlist(account, log, uri) for uri in unnamed))
    items = log.plays(limit)

    connection.send_result(
        msg["id"],
        {
            "total": len(items),
            "account": account.id,
            "items": items,
        },
    )
