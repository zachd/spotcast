"""Module to test the async_refresh_playback_state function"""

from unittest import IsolatedAsyncioTestCase
from unittest.mock import MagicMock, AsyncMock, patch

from custom_components.spotcast.services.refresh_playback_state import (
    async_refresh_playback_state,
    SpotifyAccount,
    ServiceCall,
    HomeAssistant,
)

from test.services.refresh_playback_state import TEST_MODULE


class TestRefreshPlaybackState(IsolatedAsyncioTestCase):

    @patch.object(SpotifyAccount, "async_from_config_entry")
    @patch(f"{TEST_MODULE}.get_account_entry", new_callable=MagicMock)
    async def asyncSetUp(self, mock_entry: MagicMock, mock_account: AsyncMock):

        mock_account.return_value = MagicMock(spec=SpotifyAccount)

        self.mocks = {
            "hass": MagicMock(spec=HomeAssistant),
            "call": MagicMock(spec=ServiceCall),
            "account": mock_account.return_value,
            "entry": mock_entry,
        }

        self.mocks["account"].async_playback_state = AsyncMock()
        self.mocks["call"].data = {"account": "12345"}

        await async_refresh_playback_state(
            self.mocks["hass"],
            self.mocks["call"],
        )

    def test_account_entry_requested(self):
        self.mocks["entry"].assert_called_with(self.mocks["hass"], "12345")

    def test_playback_state_forced(self):
        self.mocks["account"].async_playback_state.assert_called_once_with(
            force=True
        )
