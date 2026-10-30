"""Module to test the async_recently_played function"""

from unittest import IsolatedAsyncioTestCase
from unittest.mock import MagicMock, AsyncMock, patch

from custom_components.spotcast.spotify.account import SpotifyAccount
from custom_components.spotcast.websocket.recently_played_handler import (
    async_recently_played,
    group_plays,
    HomeAssistant,
    ActiveConnection,
)

from test.websocket.recently_played_handler import TEST_MODULE

ALBUM = {
    "uri": "spotify:album:foo",
    "name": "Foo Album",
    "artists": [{"uri": "spotify:artist:foo", "name": "Foo"}],
    "images": [{"url": "https://i.scdn.co/foo", "height": 640, "width": 640}],
}


def play(track: str, context: dict | None, played_at: str) -> dict:
    """Builds a play history item"""
    return {
        "track": {
            "uri": f"spotify:track:{track}",
            "name": track.title(),
            "album": ALBUM,
            "artists": [
                {"uri": "spotify:artist:foo", "name": "Foo"},
                {"uri": "spotify:artist:bar", "name": "Bar"},
            ],
        },
        "context": context,
        "played_at": played_at,
    }


PLAYS = [
    play("one", {"type": "playlist", "uri": "spotify:playlist:mix"}, "t9"),
    play("two", {"type": "playlist", "uri": "spotify:playlist:mix"}, "t8"),
    play("three", {"type": "album", "uri": "spotify:album:foo"}, "t7"),
    play("four", {"type": "artist", "uri": "spotify:artist:bar"}, "t6"),
    play("five", None, "t5"),
    play(
        "six",
        {"type": "collection", "uri": "spotify:user:me:collection"},
        "t4",
    ),
    play("seven", {"type": "album", "uri": "spotify:album:foo"}, "t3"),
    play("eight", {"type": "artist", "uri": "spotify:artist:baz"}, "t2"),
]


class TestGroupPlays(IsolatedAsyncioTestCase):

    def setUp(self):
        self.result = group_plays(PLAYS, 20)

    def test_one_entry_per_context_newest_first(self):
        self.assertEqual(
            [e["uri"] for e in self.result],
            [
                "spotify:playlist:mix",
                "spotify:album:foo",
                "spotify:artist:bar",
                "spotify:track:five",
                "spotify:user:me:collection",
                "spotify:artist:baz",
            ],
        )

    def test_entry_keeps_newest_play(self):
        self.assertEqual(self.result[0]["played_at"], "t9")
        self.assertEqual(self.result[0]["track_uri"], "spotify:track:one")

    def test_playlist_name_left_for_lookup(self):
        self.assertIsNone(self.result[0]["name"])
        self.assertIsNone(self.result[0]["icon"])

    def test_album_entry(self):
        self.assertEqual(
            self.result[1],
            {
                "type": "album",
                "uri": "spotify:album:foo",
                "name": "Foo Album",
                "artists": ["Foo"],
                "icon": "https://i.scdn.co/foo",
                "played_at": "t7",
                "track_uri": "spotify:track:three",
            },
        )

    def test_artist_named_from_track(self):
        self.assertEqual(self.result[2]["name"], "Bar")
        self.assertEqual(self.result[2]["artists"], [])

    def test_unknown_artist_has_no_name(self):
        self.assertIsNone(self.result[5]["name"])

    def test_track_without_context(self):
        self.assertEqual(self.result[3]["type"], "track")
        self.assertEqual(self.result[3]["name"], "Five")
        self.assertEqual(self.result[3]["artists"], ["Foo", "Bar"])

    def test_liked_songs_named(self):
        self.assertEqual(self.result[4]["name"], "Liked Songs")

    def test_limit_applied(self):
        self.assertEqual(len(group_plays(PLAYS, 2)), 2)

    def test_play_without_track_skipped(self):
        self.assertEqual(group_plays([{"track": None}], 20), [])


class TestBasicRequest(IsolatedAsyncioTestCase):

    @patch(f"{TEST_MODULE}.async_get_playlist_name", new_callable=AsyncMock)
    @patch(f"{TEST_MODULE}.async_get_account")
    async def asyncSetUp(self, mock_account: AsyncMock, mock_name: AsyncMock):

        mock_account.return_value = MagicMock(spec=SpotifyAccount)
        mock_name.return_value = "Daily Mix"

        self.mocks = {
            "hass": MagicMock(spec=HomeAssistant),
            "connection": MagicMock(spec=ActiveConnection),
            "account": mock_account.return_value,
            "name": mock_name,
        }

        self.mocks["account"].id = "12345"
        self.mocks["account"].async_recently_played = AsyncMock(
            return_value=PLAYS,
        )

        await async_recently_played(
            self.mocks["hass"],
            self.mocks["connection"],
            {"id": 1, "limit": 3},
        )

    def test_playlist_name_resolved(self):
        self.mocks["name"].assert_called_once_with(
            self.mocks["account"],
            "spotify:playlist:mix",
        )

    def test_result_properly_sent(self):
        args = self.mocks["connection"].send_result.call_args.args
        self.assertEqual(args[0], 1)
        self.assertEqual(args[1]["total"], 3)
        self.assertEqual(args[1]["account"], "12345")
        self.assertEqual(args[1]["items"][0]["name"], "Daily Mix")
        self.assertEqual(
            [e["type"] for e in args[1]["items"]],
            ["playlist", "album", "artist"],
        )
