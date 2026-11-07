"""Module to test the PlayLog class"""

from datetime import datetime, timedelta, timezone
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import MagicMock, AsyncMock, patch

from custom_components.spotcast.spotify.play_log import (
    PlayLog,
    HomeAssistant,
)

from test.spotify.play_log import TEST_MODULE

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)


def track(uri: str = "spotify:track:a", duration_ms: int = 200_000) -> dict:
    """A track as Spotify returns it"""
    return {
        "type": "track",
        "uri": uri,
        "name": uri.rsplit(":", 1)[-1].upper(),
        "duration_ms": duration_ms,
        "album": {
            "uri": "spotify:album:x",
            "name": "X",
            "images": [{"url": "https://i/x", "width": 300, "height": 300}],
        },
        "artists": [{"uri": "spotify:artist:y", "name": "Y"}],
    }


def playback(uri: str = "spotify:track:a", progress_ms: int = 0,
             context: dict | None = None, playing: bool = True) -> dict:
    """A playback state as Spotify returns it"""
    return {
        "is_playing": playing,
        "progress_ms": progress_ms,
        "context": context,
        "item": track(uri),
    }


PLAYLIST = {"type": "playlist", "uri": "spotify:playlist:p"}


class LogTestCase(TestCase):

    def setUp(self):
        patcher = patch(f"{TEST_MODULE}.Store")
        self.store = patcher.start().return_value
        self.addCleanup(patcher.stop)
        clock = patch(f"{TEST_MODULE}.dt_util.utcnow", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)
        self.log = PlayLog(MagicMock(spec=HomeAssistant), "entry")

    def record(self, minutes: float, **kwargs):
        self.log.record_playback(
            playback(**{k: v for k, v in kwargs.items() if k != "name"}),
            kwargs.get("name"),
            now=NOW + timedelta(minutes=minutes),
        )


class TestRecordPlayback(LogTestCase):

    def test_a_play_is_logged_once_while_its_progress_grows(self):
        self.record(0, progress_ms=10_000, context=PLAYLIST, name="Mix")
        self.record(0.5, progress_ms=40_000, context=PLAYLIST, name="Mix")
        self.record(1, progress_ms=70_000, context=PLAYLIST, name="Mix")

        plays = self.log.plays(10)
        self.assertEqual(len(plays), 1)
        self.assertEqual(plays[0]["context_name"], "Mix")
        self.assertEqual(plays[0]["context_type"], "playlist")
        self.assertEqual(plays[0]["icon"], "https://i/x")
        self.assertEqual(
            plays[0]["played_at"], (NOW - timedelta(seconds=10)).isoformat()
        )

    def test_a_new_track_or_a_restart_is_a_new_play(self):
        self.record(0, uri="spotify:track:a", progress_ms=150_000)
        self.record(1, uri="spotify:track:b", progress_ms=20_000)
        self.record(5, uri="spotify:track:b", progress_ms=5_000)

        self.assertEqual(
            [p["track_uri"] for p in self.log.plays(10)],
            ["spotify:track:b", "spotify:track:b", "spotify:track:a"],
        )

    def test_after_a_restart_the_play_in_progress_is_not_counted_again(self):
        self.record(0, progress_ms=10_000)
        self.log._current = None
        self.record(2, progress_ms=130_000)

        self.assertEqual(len(self.log.plays(10)), 1)

    def test_paused_or_not_a_track_is_not_logged(self):
        self.log.record_playback(playback(playing=False), None, now=NOW)
        state = playback()
        state["item"]["type"] = "episode"
        self.log.record_playback(state, None, now=NOW)

        self.assertEqual(self.log.plays(10), [])

    def test_a_late_playlist_name_fills_the_play(self):
        self.record(0, progress_ms=10_000, context=PLAYLIST, name=None)
        self.record(0.5, progress_ms=40_000, context=PLAYLIST, name="Mix")

        self.assertEqual(self.log.plays(10)[0]["context_name"], "Mix")

    def test_album_artist_and_liked_songs_are_named_from_the_track(self):
        self.record(0, uri="spotify:track:a", progress_ms=1_000,
                    context={"type": "album", "uri": "spotify:album:x"})
        self.record(4, uri="spotify:track:b", progress_ms=1_000,
                    context={"type": "artist", "uri": "spotify:artist:y"})
        self.record(8, uri="spotify:track:c", progress_ms=1_000,
                    context={"type": "collection", "uri": "spotify:user:u:collection"})

        self.assertEqual(
            [p["context_name"] for p in self.log.plays(10)],
            ["Liked Songs", "Y", "X"],
        )


class TestMergeHistory(LogTestCase):

    def test_plays_the_log_missed_are_added_in_order(self):
        self.record(0, uri="spotify:track:b", progress_ms=0)
        history = [
            # The same play as logged: ends 200 s after it started.
            {"track": track("spotify:track:b"), "context": None,
             "played_at": (NOW + timedelta(seconds=200)).isoformat()},
            {"track": track("spotify:track:a"), "context": PLAYLIST,
             "played_at": (NOW - timedelta(minutes=1)).isoformat()},
        ]
        self.log.merge_history(history)

        plays = self.log.plays(10)
        self.assertEqual(
            [p["track_uri"] for p in plays],
            ["spotify:track:b", "spotify:track:a"],
        )
        self.assertEqual(plays[1]["context_uri"], "spotify:playlist:p")

    def test_name_context_names_unnamed_plays(self):
        self.log.merge_history([
            {"track": track(), "context": PLAYLIST,
             "played_at": NOW.isoformat()},
        ])
        self.log.name_context("spotify:playlist:p", "Mix")

        self.assertEqual(self.log.plays(10)[0]["context_name"], "Mix")


class TestRetention(LogTestCase):

    def fill(self, count: int, days_ago: float):
        start = NOW - timedelta(days=days_ago)
        self.log._plays += [
            {"track_uri": f"spotify:track:{days_ago}-{i}",
             "played_at": (start + timedelta(minutes=i)).isoformat(),
             "context_type": None, "context_uri": None, "context_name": None}
            for i in range(count)
        ]

    def test_keeps_14_days_when_that_is_more_than_300_plays(self):
        self.fill(100, 20)
        self.fill(400, 3)
        self.log._prune()

        self.assertEqual(len(self.log.plays(1000)), 400)

    def test_keeps_the_newest_300_when_14_days_hold_fewer(self):
        self.fill(250, 20)
        self.fill(100, 3)
        self.log._prune()

        plays = self.log.plays(1000)
        self.assertEqual(len(plays), 300)
        self.assertTrue(plays[0]["track_uri"].startswith("spotify:track:3-"))

    def test_never_more_than_max_plays(self):
        self.fill(PlayLog.MAX_PLAYS + 50, 1)
        self.log._prune()

        self.assertEqual(len(self.log.plays(10_000)), PlayLog.MAX_PLAYS)


class TestAsyncLoad(IsolatedAsyncioTestCase):

    async def test_loads_stored_plays_oldest_first(self):
        with patch(f"{TEST_MODULE}.Store") as store:
            store.return_value.async_load = AsyncMock(return_value={"plays": [
                {"track_uri": "spotify:track:b", "played_at": NOW.isoformat()},
                {"track_uri": "spotify:track:a",
                 "played_at": (NOW - timedelta(hours=1)).isoformat()},
                {"track_uri": None, "played_at": NOW.isoformat()},
            ]})
            log = PlayLog(MagicMock(spec=HomeAssistant), "entry")
            await log.async_load()

        self.assertEqual(
            [p["track_uri"] for p in log.plays(10)],
            ["spotify:track:b", "spotify:track:a"],
        )
