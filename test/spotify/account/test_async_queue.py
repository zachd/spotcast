"""Module to test the async_queue function"""

from unittest import IsolatedAsyncioTestCase
from unittest.mock import MagicMock, AsyncMock, patch
from time import time

from custom_components.spotcast.spotify.account import (
    SpotifyAccount,
    HomeAssistant,
    DesktopSession,
    PublicSession,
    SpotifyException,
    Store,
)
from custom_components.spotcast.spotify.exceptions import RateLimitedError

from test.spotify.account import TEST_MODULE

QUEUE = {
    "currently_playing": {"uri": "spotify:track:foo"},
    "queue": [{"uri": "spotify:track:bar"}],
}


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


class TestQueueRetrieval(IsolatedAsyncioTestCase):

    @patch(f"{TEST_MODULE}.Store", spec=Store, new_callable=MagicMock)
    @patch.object(SpotifyAccount, "async_ensure_tokens_valid")
    async def asyncSetUp(self, mock_valid: AsyncMock, mock_store: MagicMock):

        self.hass = MagicMock(spec=HomeAssistant)
        self.hass.async_add_executor_job = AsyncMock(return_value=QUEUE)

        self.account = build_account(self.hass)
        self.result = await self.account.async_queue()

    def test_queue_returned(self):
        self.assertEqual(self.result, QUEUE)

    def test_executor_job_properly_called(self):
        try:
            self.hass.async_add_executor_job.assert_called_with(
                self.account.apis["public"].queue,
            )
        except AssertionError:
            self.fail()


class TestNothingPlaying(IsolatedAsyncioTestCase):

    @patch(f"{TEST_MODULE}.Store", spec=Store, new_callable=MagicMock)
    @patch.object(SpotifyAccount, "async_ensure_tokens_valid")
    async def test_no_content_gives_empty_dict(
        self,
        mock_valid: AsyncMock,
        mock_store: MagicMock,
    ):
        hass = MagicMock(spec=HomeAssistant)
        hass.async_add_executor_job = AsyncMock(return_value=None)

        result = await build_account(hass).async_queue()

        self.assertEqual(result, {})

    @patch(f"{TEST_MODULE}.Store", spec=Store, new_callable=MagicMock)
    @patch.object(SpotifyAccount, "async_ensure_tokens_valid")
    async def test_no_active_device_gives_empty_dict(
        self,
        mock_valid: AsyncMock,
        mock_store: MagicMock,
    ):
        hass = MagicMock(spec=HomeAssistant)
        hass.async_add_executor_job = AsyncMock(
            side_effect=SpotifyException(404, -1, "No active device"),
        )

        result = await build_account(hass).async_queue()

        self.assertEqual(result, {})


class TestQueueErrors(IsolatedAsyncioTestCase):

    @patch(f"{TEST_MODULE}.Store", spec=Store, new_callable=MagicMock)
    @patch.object(SpotifyAccount, "async_ensure_tokens_valid")
    async def test_other_errors_raised(
        self,
        mock_valid: AsyncMock,
        mock_store: MagicMock,
    ):
        hass = MagicMock(spec=HomeAssistant)
        hass.async_add_executor_job = AsyncMock(
            side_effect=SpotifyException(403, -1, "Forbidden"),
        )

        with self.assertRaises(SpotifyException):
            await build_account(hass).async_queue()

    @patch(f"{TEST_MODULE}.Store", spec=Store, new_callable=MagicMock)
    @patch.object(SpotifyAccount, "async_ensure_tokens_valid")
    async def test_rate_limit_raised(
        self,
        mock_valid: AsyncMock,
        mock_store: MagicMock,
    ):
        hass = MagicMock(spec=HomeAssistant)
        hass.async_add_executor_job = AsyncMock(
            side_effect=RateLimitedError(time() + 30),
        )

        with self.assertRaises(RateLimitedError):
            await build_account(hass).async_queue()
