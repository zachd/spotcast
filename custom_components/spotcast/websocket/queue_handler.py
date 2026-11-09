"""Websocket endpoint for the "Up next" queue of an account"""

import voluptuous as vol
from homeassistant.helpers import config_validation as cv
from homeassistant.core import HomeAssistant
from homeassistant.components.websocket_api import ActiveConnection

from custom_components.spotcast.spotify.utils import select_thumbnail_url
from custom_components.spotcast.websocket.utils import (
    websocket_wrapper,
    async_get_account,
)

ENDPOINT = "spotcast/queue"
SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.positive_int,
        vol.Required("type"): ENDPOINT,
        vol.Optional("limit"): vol.All(
            vol.Coerce(int),
            vol.Range(min=1, max=20),
        ),
        vol.Optional("account"): cv.string,
    }
)


def queue_item(item: dict | None) -> dict | None:
    """Builds the entry of a track or podcast episode of the queue.

    Args:
        - item(dict | None): a track or episode object from Spotify

    Returns:
        - dict | None: the entry, or None when there is no item
    """
    if item is None:
        return None

    if item.get("type") == "episode":
        show = item.get("show") or {}
        publisher = show.get("publisher")
        artists = [publisher] if publisher else []
        album = show.get("name")
        images = item.get("images") or show.get("images")
        item_type = "episode"
    else:
        album_data = item.get("album") or {}
        artists = [a.get("name") for a in item.get("artists") or []]
        album = album_data.get("name")
        images = album_data.get("images")
        item_type = "track"

    return {
        "uri": item.get("uri"),
        "id": item.get("id"),
        "type": item_type,
        "name": item.get("name"),
        "artists": artists,
        "album": album,
        "image": select_thumbnail_url(images),
        "duration_ms": item.get("duration_ms"),
    }


@websocket_wrapper
async def async_queue(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict
):
    """Gets the item playing on an account and the items queued after
    it, as the Spotify app's "Up next" shows them.

    Args:
        - hass (HomeAssistant): The Home Assistant instance.
        - connection (ActiveConnection): The active WebSocket connection.
        - msg (dict): The message received through the WebSocket API.
    """
    account_id = msg.get("account")
    limit = msg.get("limit", 10)

    account = await async_get_account(hass, account_id)
    data = await account.async_queue()

    queue = [
        queue_item(item)
        for item in data.get("queue") or []
        if item is not None
    ]

    connection.send_result(
        msg["id"],
        {
            "account": account.id,
            "current": queue_item(data.get("currently_playing")),
            "queue": queue[:limit],
        },
    )
