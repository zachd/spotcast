"""Every track an account played, each with what it was played from.

The recents log keeps one entry per album, artist or playlist, and
Spotify's play history stops at the last 50 tracks. The play log keeps
one entry per play, so a client can draw Spotify's Recents screen: the
contexts of each day, how many songs played from each, and which ones.
The coordinator records what is playing on every refresh; Spotify's
play history fills in what played while Home Assistant was not running.

Classes:
    - PlayLog
"""

from datetime import datetime, timedelta
from logging import getLogger

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from custom_components.spotcast.spotify.utils import select_image_url

LOGGER = getLogger(__name__)

LIKED_SONGS = "Liked Songs"


def _timestamp(value: str | None) -> float:
    """Returns an ISO time in epoch seconds (0 when unknown)."""
    parsed = dt_util.parse_datetime(value or "")
    return parsed.timestamp() if parsed is not None else 0.0


def _play(track: dict, context: dict | None, context_name: str | None,
          started: datetime) -> dict:
    """Builds a log entry for one play of a track.

    Args:
        - track(dict): the track, as Spotify returns it
        - context(dict | None): what it was played from (`type`, `uri`)
        - context_name(str | None): the playlist's name, when known
        - started(datetime): when the play started
    """
    context = context or {}
    album = track.get("album") or {}
    artists = track.get("artists") or []
    context_type = context.get("type") if context.get("uri") else None
    context_uri = context.get("uri") if context_type else None
    name = context_name if context_type == "playlist" else None

    if context_type == "album" and album.get("uri") == context_uri:
        name = album.get("name")
    elif context_type == "artist":
        name = next(
            (a.get("name") for a in artists if a.get("uri") == context_uri),
            None,
        )
    elif context_type == "collection":
        name = LIKED_SONGS

    return {
        "track_uri": track.get("uri"),
        "name": track.get("name"),
        "artists": [a.get("name") for a in artists],
        "album": album.get("name"),
        "album_uri": album.get("uri"),
        "icon": select_image_url(album.get("images") or []),
        "duration_ms": track.get("duration_ms"),
        "context_type": context_type,
        "context_uri": context_uri,
        "context_name": name,
        "played_at": started.isoformat(),
    }


class PlayLog:
    """A persistent log of the tracks an account played, one entry per
    play, newest last. It keeps the plays of the last `MAX_AGE`, or the
    newest `MIN_PLAYS` when that is more, and never more than
    `MAX_PLAYS`.

    Attributes:
        - MAX_AGE(timedelta): how long a play is kept
        - MIN_PLAYS(int): the plays kept however old they are
        - MAX_PLAYS(int): the most plays kept
        - SAME_PLAY(timedelta): how close two start times of a track
            must be to count as one play

    Methods:
        - async_load
        - record_playback
        - merge_history
        - name_context
        - plays
    """

    MAX_AGE = timedelta(days=14)
    MIN_PLAYS = 300
    MAX_PLAYS = 3000
    SAME_PLAY = timedelta(minutes=3)
    SAVE_DELAY = 60

    def __init__(self, hass: HomeAssistant, entry_id: str):
        """A persistent log of the tracks an account played.

        Args:
            - hass(HomeAssistant): The Home Assistant instance
            - entry_id(str): the config entry of the account
        """
        self._store = Store(hass, 1, f"spotcast_{entry_id}_plays")
        self._plays: list[dict] = []
        # The play in progress and how far into it the last refresh was:
        # progress that keeps growing is the same play, a reset is a new one.
        self._current: tuple[str, int] | None = None

    async def async_load(self):
        """Reads the stored plays."""
        data = await self._store.async_load() or {}
        self._plays = sorted(
            (
                play for play in data.get("plays", [])
                if play.get("track_uri") and play.get("played_at")
            ),
            key=lambda play: _timestamp(play["played_at"]),
        )

    def record_playback(
        self,
        playback_state: dict,
        context_name: str | None,
        now: datetime | None = None,
    ):
        """Records what is playing, as returned by the playback state
        endpoint: a new play when the track changes or starts over.

        Args:
            - playback_state(dict): the account's playback state
            - context_name(str | None): the name of the playlist playing,
                resolved by the coordinator
            - now(datetime, optional): the time of the refresh. Defaults
                to the current time.
        """
        if not playback_state or not playback_state.get("is_playing"):
            return

        track = playback_state.get("item") or {}
        uri = track.get("uri")

        if track.get("type") != "track" or uri is None:
            return

        now = now or dt_util.utcnow()
        progress = playback_state.get("progress_ms") or 0
        started = now - timedelta(milliseconds=progress)
        last = self._plays[-1] if self._plays else None
        current, self._current = self._current, (uri, progress)

        if last is not None and last["track_uri"] == uri:
            # Still the same play: its progress grew since the last
            # refresh, or (after a restart) it started when the log says.
            if current is not None and current[0] == uri:
                if progress >= current[1] - 5000:
                    self._fill_name(last, context_name)
                    return
            elif abs(started.timestamp() - _timestamp(last["played_at"])) \
                    < self.SAME_PLAY.total_seconds():
                return

        self._plays.append(
            _play(track, playback_state.get("context"), context_name, started)
        )
        self._changed()

    def merge_history(self, history: list[dict]):
        """Adds the plays of Spotify's play history the log does not
        have, such as those while Home Assistant was not running.

        Args:
            - history(list[dict]): play history items (`track`,
                `played_at` when it ended, `context`), newest first
        """
        added = False

        for item in history:
            track = item.get("track") or {}
            ended = dt_util.parse_datetime(item.get("played_at") or "")

            if track.get("uri") is None or ended is None:
                continue

            started = ended - timedelta(
                milliseconds=track.get("duration_ms") or 0
            )

            if any(
                play["track_uri"] == track["uri"]
                and abs(_timestamp(play["played_at"]) - started.timestamp())
                < self.SAME_PLAY.total_seconds()
                for play in self._plays
            ):
                continue

            self._plays.append(_play(track, item.get("context"), None, started))
            added = True

        if added:
            self._plays.sort(key=lambda play: _timestamp(play["played_at"]))
            self._changed()

    def name_context(self, uri: str, name: str):
        """Names every play of a playlist that has no name yet.

        Args:
            - uri(str): the playlist's URI
            - name(str): its name
        """
        changed = False

        for play in self._plays:
            if play["context_uri"] == uri and play["context_name"] is None:
                play["context_name"] = name
                changed = True

        if changed:
            self._changed()

    def plays(self, limit: int) -> list[dict]:
        """Returns the logged plays, newest first.

        Args:
            - limit(int): the maximum number of plays to return
        """
        return [dict(play) for play in reversed(self._plays[-limit:])]

    def _fill_name(self, play: dict, context_name: str | None):
        """Gives a playlist play the name the coordinator found later."""
        if (
            context_name
            and play["context_type"] == "playlist"
            and play["context_name"] is None
        ):
            play["context_name"] = context_name
            self._changed()

    def _changed(self):
        """Prunes the log and schedules a save."""
        self._prune()
        self._store.async_delay_save(self._data, self.SAVE_DELAY)

    def _prune(self):
        """Keeps the plays newer than `MAX_AGE`, or the newest
        `MIN_PLAYS` when that is more, at most `MAX_PLAYS`."""
        cutoff = (dt_util.utcnow() - self.MAX_AGE).timestamp()
        recent = sum(
            1 for play in self._plays
            if _timestamp(play["played_at"]) >= cutoff
        )
        keep = min(max(recent, self.MIN_PLAYS), self.MAX_PLAYS)
        self._plays = self._plays[-keep:]

    def _data(self) -> dict:
        """Returns the data to store."""
        return {"plays": self._plays}
