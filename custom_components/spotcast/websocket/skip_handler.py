"""Websocket endpoint for skipping ahead in the queue of an account"""

from logging import getLogger

import voluptuous as vol
from homeassistant.helpers import config_validation as cv
from homeassistant.core import HomeAssistant
from homeassistant.components.websocket_api import ActiveConnection

from custom_components.spotcast.spotify.exceptions import (
    PlaybackError,
    RateLimitedError,
)
from custom_components.spotcast.websocket.utils import (
    websocket_wrapper,
    async_get_account,
)

ENDPOINT = "spotcast/skip"
SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.positive_int,
        vol.Required("type"): ENDPOINT,
        vol.Required("count"): vol.All(
            vol.Coerce(int),
            vol.Range(min=1, max=20),
        ),
        vol.Optional("account"): cv.string,
    }
)

LOGGER = getLogger(__name__)


@websocket_wrapper
async def async_skip(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict
):
    """Skips forward `count` items in an account's queue, one skip
    after the other, so the Nth queued item plays next.

    A failed first skip is reported as an error. A failure after that
    stops the skipping and reports how many skips went through.

    Args:
        - hass (HomeAssistant): The Home Assistant instance.
        - connection (ActiveConnection): The active WebSocket connection.
        - msg (dict): The message received through the WebSocket API.
    """
    account_id = msg.get("account")
    count = msg["count"]

    account = await async_get_account(hass, account_id)
    skipped = 0

    for _ in range(count):
        try:
            await account.async_next_track()
        except (PlaybackError, RateLimitedError) as exc:
            if skipped == 0:
                raise

            LOGGER.warning(
                "Stopped skipping after %d of %d tracks: %s",
                skipped,
                count,
                exc,
            )
            break

        skipped += 1

    connection.send_result(
        msg["id"],
        {
            "account": account.id,
            "skipped": skipped,
        },
    )
