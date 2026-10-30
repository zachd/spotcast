"""The albums, artists, playlists and tracks an account played recently.

Spotify's play history endpoint only returns the last 50 tracks, so a
long session from one playlist hides everything played before it.
Spotcast keeps its own log instead: the coordinator records the context
of what is playing on every refresh, and the play history fills in what
was played while Home Assistant was not running.

Classes:
    - RecentsLog

Functions:
    - group_plays
"""

from datetime import datetime, timedelta
from logging import getLogger

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from custom_components.spotcast.spotify.utils import select_image_url

LOGGER = getLogger(__name__)

LIKED_SONGS = "Liked Songs"


def group_plays(plays: list[dict], limit: int) -> list[dict]:
    """Groups plays by the context they were played from, newest first,
    keeping each context once. A play without a context stands for its
    track.

    Args:
        - plays(list[dict]): play history items, newest first
        - limit(int): the maximum number of entries to return

    Returns:
        - list[dict]: one entry per context or track, without playlist
            names, which need a separate lookup
    """
    entries = []
    seen = set()

    for play in plays:
        track = play.get("track") or {}
        context = play.get("context") or {}
        uri = context.get("uri") or track.get("uri")

        if uri is None or uri in seen:
            continue

        seen.add(uri)
        item_type = context.get("type") if context.get("uri") else "track"
        album = track.get("album") or {}
        artists = track.get("artists") or []
        name = None

        if item_type == "track":
            name = track.get("name")
        elif item_type == "album":
            # A relinked track can belong to another release than the
            # album it was played from: then the album is looked up.
            if album.get("uri") != uri:
                album = {}
            name = album.get("name")
            artists = album.get("artists") or []
        elif item_type == "artist":
            name = next(
                (a.get("name") for a in artists if a.get("uri") == uri),
                None,
            )
        elif item_type == "collection":
            name = LIKED_SONGS

        entries.append({
            "type": item_type,
            "uri": uri,
            "name": name,
            "artists": (
                [a.get("name") for a in artists]
                if item_type in ("album", "track")
                else []
            ),
            "icon": (
                select_image_url(album.get("images") or [])
                if item_type in ("album", "track")
                else None
            ),
            "played_at": play.get("played_at"),
            "track_uri": track.get("uri"),
        })

        if len(entries) >= limit:
            break

    return entries


def _timestamp(entry: dict) -> float:
    """Returns when an entry was last played, in epoch seconds (0 when
    unknown)."""
    played_at = dt_util.parse_datetime(entry.get("played_at") or "")
    return played_at.timestamp() if played_at is not None else 0.0


class RecentsLog:
    """A persistent log of the contexts an account played, one entry
    each, kept for `MAX_AGE` and at most `MAX_ENTRIES`.

    Attributes:
        - MAX_AGE(timedelta): how long an entry is kept after its last
            play
        - MAX_ENTRIES(int): the most entries kept

    Methods:
        - async_load
        - record_playback
        - merge
        - entries
    """

    MAX_AGE = timedelta(days=30)
    MAX_ENTRIES = 100
    SAVE_DELAY = 60

    def __init__(self, hass: HomeAssistant, entry_id: str):
        """A persistent log of the contexts an account played.

        Args:
            - hass(HomeAssistant): The Home Assistant instance
            - entry_id(str): the config entry of the account
        """
        self._store = Store(hass, 1, f"spotcast_{entry_id}_recents")
        self._entries: dict[str, dict] = {}

    async def async_load(self):
        """Reads the stored entries."""
        data = await self._store.async_load() or {}
        self._entries = {
            entry["uri"]: entry
            for entry in data.get("entries", [])
            if entry.get("uri")
        }

    def record_playback(
        self,
        playback_state: dict,
        context_name: str | None,
        now: datetime | None = None,
    ):
        """Records what is playing, as returned by the playback state
        endpoint.

        Args:
            - playback_state(dict): the account's playback state
            - context_name(str | None): the name of the playlist playing,
                resolved by the coordinator
            - now(datetime, optional): the time of the play. Defaults to
                the current time.
        """
        if not playback_state or not playback_state.get("is_playing"):
            return

        item = playback_state.get("item") or {}

        if item.get("type") != "track":
            return

        now = now or dt_util.utcnow()
        play = {
            "track": item,
            "context": playback_state.get("context"),
            "played_at": now.isoformat(),
        }

        for entry in group_plays([play], 1):
            if entry["type"] == "playlist":
                entry["name"] = context_name
            self.merge([entry])

    def merge(self, entries: list[dict]):
        """Adds entries or refreshes the ones already logged: the newest
        play wins, and details an entry lacks are taken from the other.

        Args:
            - entries(list[dict]): entries as built by `group_plays`
        """
        changed = False

        for entry in entries:
            uri = entry.get("uri")

            if uri is None:
                continue

            known = self._entries.get(uri)

            if known is None:
                self._entries[uri] = dict(entry)
                changed = True
                continue

            newer, older = (
                (entry, known)
                if _timestamp(entry) > _timestamp(known)
                else (known, entry)
            )
            merged = {
                key: (
                    newer.get(key)
                    if newer.get(key) not in (None, [])
                    else older.get(key)
                )
                for key in set(newer) | set(older)
            }

            if merged != known:
                self._entries[uri] = merged
                changed = True

        if changed:
            self._prune()
            self._store.async_delay_save(self._data, self.SAVE_DELAY)

    def entries(self, limit: int) -> list[dict]:
        """Returns the logged entries, newest first.

        Args:
            - limit(int): the maximum number of entries to return
        """
        ordered = sorted(
            self._entries.values(),
            key=_timestamp,
            reverse=True,
        )
        return [dict(entry) for entry in ordered[:limit]]

    def _prune(self):
        """Drops entries older than `MAX_AGE` and the oldest past
        `MAX_ENTRIES`."""
        cutoff = (dt_util.utcnow() - self.MAX_AGE).timestamp()
        kept = [
            entry for entry in self.entries(self.MAX_ENTRIES)
            if _timestamp(entry) >= cutoff
        ]
        self._entries = {entry["uri"]: entry for entry in kept}

    def _data(self) -> dict:
        """Returns the data to store."""
        return {"entries": list(self._entries.values())}
