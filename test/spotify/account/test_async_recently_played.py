"""Module to test the async_recently_played function"""

from unittest import IsolatedAsyncioTestCase
from unittest.mock import MagicMock, AsyncMock, patch
from time import time

from custom_components.spotcast.spotify.account import (
    SpotifyAccount,
    HomeAssistant,
    DesktopSession,
    PublicSession,
    Store,
)

from test.spotify.account import TEST_MODULE


class TestRecentlyPlayedRetrieval(IsolatedAsyncioTestCase):

    @patch(f"{TEST_MODULE}.Store", spec=Store, new_callable=MagicMock)
    @patch.object(SpotifyAccount, "async_ensure_tokens_valid")
    async def asyncSetUp(self, mock_valid: AsyncMock, mock_store: MagicMock):

        self.mocks = {
            "hass": MagicMock(spec=HomeAssistant),
            "internal": MagicMock(spec=DesktopSession),
            "external": MagicMock(spec=PublicSession),
        }

        self.mocks["hass"].async_add_executor_job = AsyncMock(
            return_value={
                "items": [
                    {"track": {"uri": "spotify:track:foo"}},
                    None,
                    {"track": {"uri": "spotify:track:bar"}},
                ]
            }
        )

        self.account = SpotifyAccount(
            entry_id="12345",
            hass=self.mocks["hass"],
            private_session=self.mocks["internal"],
            public_session=self.mocks["external"],
        )
        self.account._datasets["profile"].expires_at = time() + 9999
        self.account._datasets["profile"]._data = {"display_name": "Foo"}

        self.result = await self.account.async_recently_played(20)

    def test_empty_items_dropped(self):
        self.assertEqual(
            self.result,
            [
                {"track": {"uri": "spotify:track:foo"}},
                {"track": {"uri": "spotify:track:bar"}},
            ],
        )

    def test_executor_job_properly_called(self):
        try:
            self.mocks["hass"].async_add_executor_job.assert_called_with(
                self.account.apis["public"].current_user_recently_played,
                20,
            )
        except AssertionError:
            self.fail()


class TestNoItems(IsolatedAsyncioTestCase):

    @patch(f"{TEST_MODULE}.Store", spec=Store, new_callable=MagicMock)
    @patch.object(SpotifyAccount, "async_ensure_tokens_valid")
    async def asyncSetUp(self, mock_valid: AsyncMock, mock_store: MagicMock):

        hass = MagicMock(spec=HomeAssistant)
        hass.async_add_executor_job = AsyncMock(return_value={"items": None})

        account = SpotifyAccount(
            entry_id="12345",
            hass=hass,
            private_session=MagicMock(spec=DesktopSession),
            public_session=MagicMock(spec=PublicSession),
        )
        account._datasets["profile"].expires_at = time() + 9999
        account._datasets["profile"]._data = {"display_name": "Foo"}

        self.result = await account.async_recently_played()

    def test_empty_list_returned(self):
        self.assertEqual(self.result, [])


class TestArtistRetrieval(IsolatedAsyncioTestCase):

    @patch(f"{TEST_MODULE}.Store", spec=Store, new_callable=MagicMock)
    @patch.object(SpotifyAccount, "async_ensure_tokens_valid")
    async def asyncSetUp(self, mock_valid: AsyncMock, mock_store: MagicMock):

        self.hass = MagicMock(spec=HomeAssistant)
        self.hass.async_add_executor_job = AsyncMock(
            return_value={"name": "Foo"},
        )

        self.account = SpotifyAccount(
            entry_id="12345",
            hass=self.hass,
            private_session=MagicMock(spec=DesktopSession),
            public_session=MagicMock(spec=PublicSession),
        )

        self.result = await self.account.async_get_artist(
            "spotify:artist:foo",
        )

    def test_artist_returned(self):
        self.assertEqual(self.result, {"name": "Foo"})

    def test_executor_job_properly_called(self):
        try:
            self.hass.async_add_executor_job.assert_called_with(
                self.account.apis["public"].artist,
                "spotify:artist:foo",
            )
        except AssertionError:
            self.fail()
