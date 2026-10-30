"""Module to test the RecentsLog class"""

from datetime import datetime, timedelta, timezone
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import MagicMock, AsyncMock, patch

from custom_components.spotcast.spotify.recents import (
    RecentsLog,
    HomeAssistant,
)

from test.spotify.recents import TEST_MODULE

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


def at(minutes_ago: float) -> str:
    """An ISO time some minutes before NOW"""
    return (NOW - timedelta(minutes=minutes_ago)).isoformat()


def entry(uri: str, minutes_ago: float, **fields) -> dict:
    """An entry as group_plays builds it"""
    return {
        "type": uri.split(":")[1],
        "uri": uri,
        "name": None,
        "artists": [],
        "icon": None,
        "played_at": at(minutes_ago),
        "track_uri": "spotify:track:x",
    } | fields


def playback(context: dict | None, playing: bool = True, kind="track"):
    """A playback state as Spotify returns it"""
    return {
        "is_playing": playing,
        "context": context,
        "item": {
            "type": kind,
            "uri": "spotify:track:now",
            "name": "Now",
            "album": {"uri": "spotify:album:a", "name": "A", "images": []},
            "artists": [{"uri": "spotify:artist:b", "name": "B"}],
        },
    }


class LogTestCase(TestCase):

    def setUp(self):
        patcher = patch(f"{TEST_MODULE}.Store")
        self.store = patcher.start().return_value
        self.addCleanup(patcher.stop)
        clock = patch(f"{TEST_MODULE}.dt_util.utcnow", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)
        self.log = RecentsLog(MagicMock(spec=HomeAssistant), "entry")


class TestRecordPlayback(LogTestCase):

    def test_playlist_recorded_with_its_name(self):
        self.log.record_playback(
            playback({"type": "playlist", "uri": "spotify:playlist:p"}),
            "Glass Beams Radio",
            NOW,
        )
        [recorded] = self.log.entries(10)
        self.assertEqual(recorded["uri"], "spotify:playlist:p")
        self.assertEqual(recorded["name"], "Glass Beams Radio")
        self.assertEqual(recorded["played_at"], NOW.isoformat())
        self.store.async_delay_save.assert_called_once()

    def test_album_recorded(self):
        self.log.record_playback(
            playback({"type": "album", "uri": "spotify:album:a"}),
            None,
        )
        self.assertEqual(self.log.entries(10)[0]["name"], "A")

    def test_paused_playback_ignored(self):
        self.log.record_playback(playback(None, playing=False), None)
        self.assertEqual(self.log.entries(10), [])

    def test_episode_ignored(self):
        self.log.record_playback(playback(None, kind="episode"), None)
        self.assertEqual(self.log.entries(10), [])

    def test_no_playback_ignored(self):
        self.log.record_playback({}, None)
        self.assertEqual(self.log.entries(10), [])


class TestMerge(LogTestCase):

    def test_newest_play_wins_and_details_are_kept(self):
        self.log.merge([entry("spotify:album:a", 60, name="A", icon="i")])
        self.log.merge([entry("spotify:album:a", 5)])
        [merged] = self.log.entries(10)
        self.assertEqual(merged["played_at"], at(5))
        self.assertEqual(merged["name"], "A")
        self.assertEqual(merged["icon"], "i")

    def test_older_play_does_not_move_an_entry_back(self):
        self.log.merge([entry("spotify:album:a", 5)])
        self.log.merge([entry("spotify:album:a", 60, name="A")])
        [merged] = self.log.entries(10)
        self.assertEqual(merged["played_at"], at(5))
        self.assertEqual(merged["name"], "A")

    def test_unchanged_entry_not_saved_again(self):
        self.log.merge([entry("spotify:album:a", 5)])
        self.log.merge([entry("spotify:album:a", 5)])
        self.store.async_delay_save.assert_called_once()

    def test_entry_without_uri_skipped(self):
        self.log.merge([{"name": "x"}])
        self.assertEqual(self.log.entries(10), [])

    def test_newest_first_and_limited(self):
        self.log.merge([
            entry("spotify:album:old", 300),
            entry("spotify:playlist:new", 1),
            entry("spotify:artist:mid", 60),
        ])
        self.assertEqual(
            [e["uri"] for e in self.log.entries(2)],
            ["spotify:playlist:new", "spotify:artist:mid"],
        )

    def test_old_entries_pruned(self):
        self.log.merge([
            entry("spotify:album:recent", 60),
            entry("spotify:album:stale", 60 * 24 * 31),
        ])
        self.assertEqual(
            [e["uri"] for e in self.log.entries(10)],
            ["spotify:album:recent"],
        )

    def test_size_capped(self):
        self.log.MAX_ENTRIES = 2
        self.log.merge([entry(f"spotify:album:{i}", i) for i in range(4)])
        self.assertEqual(
            [e["uri"] for e in self.log.entries(10)],
            ["spotify:album:0", "spotify:album:1"],
        )

    def test_entry_without_time_dropped(self):
        self.log.merge([
            entry("spotify:album:a", 5),
            entry("spotify:album:b", 0) | {"played_at": None},
        ])
        self.assertEqual(
            [e["uri"] for e in self.log.entries(10)],
            ["spotify:album:a"],
        )

    def test_saved_data(self):
        self.log.merge([entry("spotify:album:a", 5)])
        save = self.store.async_delay_save.call_args.args[0]
        self.assertEqual(save()["entries"][0]["uri"], "spotify:album:a")


class TestLoad(IsolatedAsyncioTestCase):

    @patch(f"{TEST_MODULE}.Store")
    async def test_stored_entries_read(self, mock_store: MagicMock):
        mock_store.return_value.async_load = AsyncMock(
            return_value={"entries": [entry("spotify:album:a", 5), {}]},
        )
        log = RecentsLog(MagicMock(spec=HomeAssistant), "entry")
        await log.async_load()
        self.assertEqual(
            [e["uri"] for e in log.entries(10)],
            ["spotify:album:a"],
        )

    @patch(f"{TEST_MODULE}.Store")
    async def test_empty_store(self, mock_store: MagicMock):
        mock_store.return_value.async_load = AsyncMock(return_value=None)
        log = RecentsLog(MagicMock(spec=HomeAssistant), "entry")
        await log.async_load()
        self.assertEqual(log.entries(10), [])
