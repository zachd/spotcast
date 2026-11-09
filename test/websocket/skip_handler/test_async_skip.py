"""Module to test the async_skip function"""

from asyncio import sleep
from time import time
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import MagicMock, AsyncMock, patch

from custom_components.spotcast.spotify.account import SpotifyAccount
from custom_components.spotcast.spotify.exceptions import (
    PlaybackError,
    RateLimitedError,
)
from custom_components.spotcast.websocket.skip_handler import (
    async_skip,
    SCHEMA,
    vol,
    HomeAssistant,
    ActiveConnection,
)

from test.websocket.skip_handler import TEST_MODULE


class TestSchema(TestCase):

    def test_count_required(self):
        with self.assertRaises(vol.Invalid):
            SCHEMA({"id": 1, "type": "spotcast/skip"})

    def test_count_bounds_accepted(self):
        for count in (1, 20):
            SCHEMA({"id": 1, "type": "spotcast/skip", "count": count})

    def test_count_out_of_bounds_refused(self):
        for count in (0, 21, -1):
            with self.assertRaises(vol.Invalid):
                SCHEMA({"id": 1, "type": "spotcast/skip", "count": count})


class TestSequentialSkips(IsolatedAsyncioTestCase):

    @patch(f"{TEST_MODULE}.async_get_account")
    async def asyncSetUp(self, mock_account: AsyncMock):

        mock_account.return_value = MagicMock(spec=SpotifyAccount)

        self.mocks = {
            "hass": MagicMock(spec=HomeAssistant),
            "connection": MagicMock(spec=ActiveConnection),
            "account": mock_account.return_value,
            "get_account": mock_account,
        }

        self.events = []
        self.running = 0
        self.max_running = 0

        async def next_track():
            self.running += 1
            self.max_running = max(self.max_running, self.running)
            self.events.append("start")
            await sleep(0)
            self.events.append("end")
            self.running -= 1

        self.mocks["account"].id = "12345"
        self.mocks["account"].async_next_track = AsyncMock(
            side_effect=next_track,
        )

        await async_skip(
            self.mocks["hass"],
            self.mocks["connection"],
            {"id": 1, "type": "spotcast/skip", "count": 3, "account": "foo"},
        )

    def test_account_requested(self):
        self.mocks["get_account"].assert_called_once_with(
            self.mocks["hass"],
            "foo",
        )

    def test_one_call_per_skip(self):
        self.assertEqual(self.mocks["account"].async_next_track.call_count, 3)

    def test_calls_not_overlapping(self):
        self.assertEqual(self.max_running, 1)
        self.assertEqual(self.events, ["start", "end"] * 3)

    def test_result_properly_sent(self):
        self.mocks["connection"].send_result.assert_called_once_with(
            1,
            {"account": "12345", "skipped": 3},
        )


class TestFailureAfterSomeSkips(IsolatedAsyncioTestCase):

    @patch(f"{TEST_MODULE}.async_get_account")
    async def test_partial_count_sent(self, mock_account: AsyncMock):

        account = MagicMock(spec=SpotifyAccount)
        account.id = "12345"
        account.async_next_track = AsyncMock(
            side_effect=[None, None, PlaybackError("refused"), None],
        )
        mock_account.return_value = account
        connection = MagicMock(spec=ActiveConnection)

        await async_skip(
            MagicMock(spec=HomeAssistant),
            connection,
            {"id": 1, "type": "spotcast/skip", "count": 4},
        )

        self.assertEqual(account.async_next_track.call_count, 3)
        connection.send_result.assert_called_once_with(
            1,
            {"account": "12345", "skipped": 2},
        )

    @patch(f"{TEST_MODULE}.async_get_account")
    async def test_rate_limit_stops_skipping(self, mock_account: AsyncMock):

        account = MagicMock(spec=SpotifyAccount)
        account.id = "12345"
        account.async_next_track = AsyncMock(
            side_effect=[None, RateLimitedError(time() + 30), None],
        )
        mock_account.return_value = account
        connection = MagicMock(spec=ActiveConnection)

        await async_skip(
            MagicMock(spec=HomeAssistant),
            connection,
            {"id": 1, "type": "spotcast/skip", "count": 3},
        )

        self.assertEqual(account.async_next_track.call_count, 2)
        connection.send_result.assert_called_once_with(
            1,
            {"account": "12345", "skipped": 1},
        )


class TestFirstSkipFails(IsolatedAsyncioTestCase):

    @patch(f"{TEST_MODULE}.async_get_account")
    async def test_error_sent(self, mock_account: AsyncMock):

        account = MagicMock(spec=SpotifyAccount)
        account.id = "12345"
        account.async_next_track = AsyncMock(
            side_effect=PlaybackError("No active device"),
        )
        mock_account.return_value = account
        connection = MagicMock(spec=ActiveConnection)

        await async_skip(
            MagicMock(spec=HomeAssistant),
            connection,
            {"id": 1, "type": "spotcast/skip", "count": 3},
        )

        self.assertEqual(account.async_next_track.call_count, 1)
        connection.send_result.assert_not_called()
        connection.send_error.assert_called_once_with(
            1,
            "PlaybackError",
            "No active device",
        )
