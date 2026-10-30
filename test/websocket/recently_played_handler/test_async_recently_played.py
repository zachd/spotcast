"""Module to test the async_recently_played function"""

from unittest import IsolatedAsyncioTestCase
from unittest.mock import MagicMock, AsyncMock, patch

from custom_components.spotcast.spotify.account import SpotifyAccount
from custom_components.spotcast.websocket.recently_played_handler import (
    async_complete_entry,
    async_recently_played,
    group_plays,
    SpotifyException,
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

    def test_relinked_album_left_for_lookup(self):
        entry = group_plays(
            [play("x", {"type": "album", "uri": "spotify:album:other"}, "t")],
            20,
        )[0]
        self.assertIsNone(entry["name"])
        self.assertIsNone(entry["icon"])
        self.assertEqual(entry["artists"], [])

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


def entry(item_type: str, uri: str, name: str | None = None) -> dict:
    """Builds an entry as group_plays returns it"""
    return {
        "type": item_type,
        "uri": uri,
        "name": name,
        "artists": [],
        "icon": None,
        "played_at": "t",
        "track_uri": "spotify:track:x",
    }


class TestCompleteEntry(IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.account = MagicMock(spec=SpotifyAccount)
        self.account.async_get_album = AsyncMock(return_value=ALBUM)
        self.account.async_get_artist = AsyncMock(
            return_value={"name": "Baz"},
        )

    async def test_album_looked_up(self):
        album = entry("album", "spotify:album:foo")
        await async_complete_entry(self.account, album)
        self.assertEqual(album["name"], "Foo Album")
        self.assertEqual(album["artists"], ["Foo"])
        self.assertEqual(album["icon"], "https://i.scdn.co/foo")

    async def test_artist_looked_up(self):
        artist = entry("artist", "spotify:artist:baz")
        await async_complete_entry(self.account, artist)
        self.assertEqual(artist["name"], "Baz")

    async def test_named_entry_left_alone(self):
        album = entry("album", "spotify:album:foo", "Known")
        await async_complete_entry(self.account, album)
        self.assertEqual(album["name"], "Known")
        self.account.async_get_album.assert_not_called()

    async def test_unknown_type_left_alone(self):
        show = entry("show", "spotify:show:foo")
        await async_complete_entry(self.account, show)
        self.assertIsNone(show["name"])

    async def test_failed_lookup_leaves_entry(self):
        self.account.async_get_album.side_effect = SpotifyException(
            404, -1, "not found",
        )
        album = entry("album", "spotify:album:gone")
        await async_complete_entry(self.account, album)
        self.assertIsNone(album["name"])
