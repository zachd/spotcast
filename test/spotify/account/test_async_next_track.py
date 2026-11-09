"""Module to test the async_next_track function"""

from unittest import IsolatedAsyncioTestCase
from unittest.mock import MagicMock, AsyncMock, patch
from time import time

from custom_components.spotcast.spotify.account import (
    SpotifyAccount,
    HomeAssistant,
    DesktopSession,
    PublicSession,
    PlaybackError,
    SpotifyException,
    Store,
)
from custom_components.spotcast.spotify.exceptions import RateLimitedError

from test.spotify.account import TEST_MODULE


def build_account(hass: MagicMock) -> SpotifyAccount:
    """Builds an account on a mocked Home Assistant instance"""
    account = SpotifyAccount(
        entry_id="12345",
        hass=hass,
        private_session=MagicMock(spec=DesktopSession),
        public_session=MagicMock(spec=PublicSession),
    )
    account._datasets["profile"].expires_at = time() + 9999
    account._datasets["profile"]._data = {"display_name": "Foo"}
    return account


class TestNextTrack(IsolatedAsyncioTestCase):

    @patch(f"{TEST_MODULE}.Store", spec=Store, new_callable=MagicMock)
    @patch.object(SpotifyAccount, "async_ensure_tokens_valid")
    async def test_active_device_targeted(
        self,
        mock_valid: AsyncMock,
        mock_store: MagicMock,
    ):
        hass = MagicMock(spec=HomeAssistant)
        hass.async_add_executor_job = AsyncMock(return_value=None)
        account = build_account(hass)

        await account.async_next_track()

        hass.async_add_executor_job.assert_called_once_with(
            account.apis["public"].next_track,
            None,
        )

    @patch(f"{TEST_MODULE}.Store", spec=Store, new_callable=MagicMock)
    @patch.object(SpotifyAccount, "async_ensure_tokens_valid")
    async def test_device_targeted(
        self,
        mock_valid: AsyncMock,
        mock_store: MagicMock,
    ):
        hass = MagicMock(spec=HomeAssistant)
        hass.async_add_executor_job = AsyncMock(return_value=None)
        account = build_account(hass)

        await account.async_next_track("device")

        hass.async_add_executor_job.assert_called_once_with(
            account.apis["public"].next_track,
            "device",
        )


class TestNextTrackFails(IsolatedAsyncioTestCase):

    @patch(f"{TEST_MODULE}.Store", spec=Store, new_callable=MagicMock)
    @patch.object(SpotifyAccount, "async_ensure_tokens_valid")
    async def test_playback_error_raised(
        self,
        mock_valid: AsyncMock,
        mock_store: MagicMock,
    ):
        hass = MagicMock(spec=HomeAssistant)
        hass.async_add_executor_job = AsyncMock(
            side_effect=SpotifyException(404, -1, "No active device"),
        )

        with self.assertRaises(PlaybackError):
            await build_account(hass).async_next_track()

    @patch(f"{TEST_MODULE}.Store", spec=Store, new_callable=MagicMock)
    @patch.object(SpotifyAccount, "async_ensure_tokens_valid")
    async def test_rate_limit_raised_untouched(
        self,
        mock_valid: AsyncMock,
        mock_store: MagicMock,
    ):
        hass = MagicMock(spec=HomeAssistant)
        hass.async_add_executor_job = AsyncMock(
            side_effect=RateLimitedError(time() + 30),
        )

        with self.assertRaises(RateLimitedError):
            await build_account(hass).async_next_track()
