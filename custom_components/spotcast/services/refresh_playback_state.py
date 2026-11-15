"""Module for the refresh playback state service

Functions:
    - async_refresh_playback_state
"""

from logging import getLogger

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from custom_components.spotcast.spotify import SpotifyAccount
from custom_components.spotcast.utils import get_account_entry

LOGGER = getLogger(__name__)

REFRESH_PLAYBACK_STATE_SCHEMA = vol.Schema({
    vol.Optional("account"): cv.string,
})


async def async_refresh_playback_state(
    hass: HomeAssistant,
    call: ServiceCall,
):
    """Service to read the account's current playback from Spotify now,
    bypassing the cache. An active playback is also saved as the last
    known playback state, which `transfer_playback` rebuilds from once
    the playback has stopped (e.g. a Cast announcement took over the
    speaker). Call it just before interrupting a speaker so the resume
    starts at the song and position that were playing then, not at the
    last periodic refresh (up to 30 s old)."""
    account_id = call.data.get("account")

    entry = get_account_entry(hass, account_id)
    account = await SpotifyAccount.async_from_config_entry(hass, entry)

    LOGGER.debug("Forcing a playback state refresh for `%s`", account.name)
    await account.async_playback_state(force=True)
