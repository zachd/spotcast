"""Module to test the async_queue function"""

from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import MagicMock, AsyncMock, patch

from custom_components.spotcast.spotify.account import SpotifyAccount
from custom_components.spotcast.websocket.queue_handler import (
    async_queue,
    queue_item,
    SCHEMA,
    vol,
    HomeAssistant,
    ActiveConnection,
)

from test.websocket.queue_handler import TEST_MODULE

ALBUM_IMAGES = [
    {"url": "https://i.scdn.co/image/640", "height": 640, "width": 640},
    {"url": "https://i.scdn.co/image/300", "height": 300, "width": 300},
    {"url": "https://i.scdn.co/image/64", "height": 64, "width": 64},
]


def track(name: str, images: list[dict] = None) -> dict:
    """Builds a track object as the queue endpoint returns it"""
    return {
        "type": "track",
        "uri": f"spotify:track:{name}",
        "id": name,
        "name": name.title(),
        "duration_ms": 215000,
        "artists": [
            {"uri": "spotify:artist:foo", "name": "Foo"},
            {"uri": "spotify:artist:bar", "name": "Bar"},
        ],
        "album": {
            "uri": "spotify:album:foo",
            "name": "Foo Album",
            "images": ALBUM_IMAGES if images is None else images,
        },
    }


EPISODE = {
    "type": "episode",
    "uri": "spotify:episode:pod",
    "id": "pod",
    "name": "Episode 12",
    "duration_ms": 3600000,
    "images": [
        {"url": "https://i.scdn.co/image/ep640", "height": 640, "width": 640},
        {"url": "https://i.scdn.co/image/ep64", "height": 64, "width": 64},
    ],
    "show": {
        "uri": "spotify:show:show",
        "name": "The Show",
        "publisher": "Show Studio",
        "images": [
            {"url": "https://i.scdn.co/image/show", "height": 64, "width": 64},
        ],
    },
}


class TestTrackItem(TestCase):

    def test_track_mapped(self):
        self.assertEqual(
            queue_item(track("one")),
            {
                "uri": "spotify:track:one",
                "id": "one",
                "type": "track",
                "name": "One",
                "artists": ["Foo", "Bar"],
                "album": "Foo Album",
                "image": "https://i.scdn.co/image/64",
                "duration_ms": 215000,
            },
        )

    def test_track_without_images(self):
        self.assertIsNone(queue_item(track("one", images=[]))["image"])

    def test_local_track(self):
        item = queue_item(
            {
                "type": "track",
                "uri": "spotify:local:Foo:Foo+Album:Local:200",
                "id": None,
                "name": "Local",
                "duration_ms": 200000,
                "is_local": True,
                "artists": [{"uri": None, "name": "Foo"}],
                "album": {"uri": None, "name": "Foo Album", "images": []},
            }
        )
        self.assertIsNone(item["id"])
        self.assertIsNone(item["image"])
        self.assertEqual(item["artists"], ["Foo"])

    def test_no_item(self):
        self.assertIsNone(queue_item(None))


class TestEpisodeItem(TestCase):

    def test_episode_mapped(self):
        self.assertEqual(
            queue_item(EPISODE),
            {
                "uri": "spotify:episode:pod",
                "id": "pod",
                "type": "episode",
                "name": "Episode 12",
                "artists": ["Show Studio"],
                "album": "The Show",
                "image": "https://i.scdn.co/image/ep64",
                "duration_ms": 3600000,
            },
        )

    def test_show_image_when_episode_has_none(self):
        episode = {**EPISODE, "images": []}
        self.assertEqual(
            queue_item(episode)["image"],
            "https://i.scdn.co/image/show",
        )

    def test_no_image_at_all(self):
        episode = {
            **EPISODE,
            "images": [],
            "show": {**EPISODE["show"], "images": []},
        }
        self.assertIsNone(queue_item(episode)["image"])

    def test_show_without_publisher(self):
        episode = {**EPISODE, "show": {"name": "The Show", "images": []}}
        self.assertEqual(queue_item(episode)["artists"], [])


class TestSchema(TestCase):

    def test_limit_optional(self):
        SCHEMA({"id": 1, "type": "spotcast/queue"})

    def test_limit_bounds_accepted(self):
        for limit in (1, 20):
            SCHEMA({"id": 1, "type": "spotcast/queue", "limit": limit})

    def test_limit_out_of_bounds_refused(self):
        for limit in (0, 21):
            with self.assertRaises(vol.Invalid):
                SCHEMA({"id": 1, "type": "spotcast/queue", "limit": limit})


class TestBasicRequest(IsolatedAsyncioTestCase):

    @patch(f"{TEST_MODULE}.async_get_account")
    async def asyncSetUp(self, mock_account: AsyncMock):

        mock_account.return_value = MagicMock(spec=SpotifyAccount)

        self.mocks = {
            "hass": MagicMock(spec=HomeAssistant),
            "connection": MagicMock(spec=ActiveConnection),
            "account": mock_account.return_value,
            "get_account": mock_account,
        }

        self.mocks["account"].id = "12345"
        self.mocks["account"].async_queue = AsyncMock(
            return_value={
                "currently_playing": track("now"),
                "queue": [
                    track(name) for name in ("one", "two", "three")
                ] + [EPISODE],
            }
        )

        await async_queue(
            self.mocks["hass"],
            self.mocks["connection"],
            {"id": 1, "type": "spotcast/queue", "account": "foo"},
        )

        self.result = self.mocks["connection"].send_result.call_args.args

    def test_account_requested(self):
        self.mocks["get_account"].assert_called_once_with(
            self.mocks["hass"],
            "foo",
        )

    def test_result_properly_sent(self):
        self.assertEqual(self.result[0], 1)
        self.assertEqual(self.result[1]["account"], "12345")
        self.assertEqual(self.result[1]["current"]["uri"], "spotify:track:now")
        self.assertEqual(
            [item["uri"] for item in self.result[1]["queue"]],
            [
                "spotify:track:one",
                "spotify:track:two",
                "spotify:track:three",
                "spotify:episode:pod",
            ],
        )
        self.assertEqual(self.result[1]["queue"][3]["type"], "episode")


class TestLimit(IsolatedAsyncioTestCase):

    @patch(f"{TEST_MODULE}.async_get_account")
    async def test_limit_applied(self, mock_account: AsyncMock):

        account = MagicMock(spec=SpotifyAccount)
        account.id = "12345"
        account.async_queue = AsyncMock(
            return_value={
                "currently_playing": track("now"),
                "queue": [track(str(i)) for i in range(20)],
            }
        )
        mock_account.return_value = account
        connection = MagicMock(spec=ActiveConnection)

        await async_queue(
            MagicMock(spec=HomeAssistant),
            connection,
            {"id": 1, "type": "spotcast/queue", "limit": 3},
        )

        queue = connection.send_result.call_args.args[1]["queue"]
        self.assertEqual(
            [item["id"] for item in queue],
            ["0", "1", "2"],
        )

    @patch(f"{TEST_MODULE}.async_get_account")
    async def test_default_limit_is_10(self, mock_account: AsyncMock):

        account = MagicMock(spec=SpotifyAccount)
        account.id = "12345"
        account.async_queue = AsyncMock(
            return_value={
                "currently_playing": track("now"),
                "queue": [track(str(i)) for i in range(20)],
            }
        )
        mock_account.return_value = account
        connection = MagicMock(spec=ActiveConnection)

        await async_queue(
            MagicMock(spec=HomeAssistant),
            connection,
            {"id": 1, "type": "spotcast/queue"},
        )

        queue = connection.send_result.call_args.args[1]["queue"]
        self.assertEqual(len(queue), 10)


class TestNothingPlaying(IsolatedAsyncioTestCase):

    @patch(f"{TEST_MODULE}.async_get_account")
    async def test_empty_result_sent(self, mock_account: AsyncMock):

        account = MagicMock(spec=SpotifyAccount)
        account.id = "12345"
        account.async_queue = AsyncMock(return_value={})
        mock_account.return_value = account
        connection = MagicMock(spec=ActiveConnection)

        await async_queue(
            MagicMock(spec=HomeAssistant),
            connection,
            {"id": 1, "type": "spotcast/queue"},
        )

        connection.send_result.assert_called_once_with(
            1,
            {"account": "12345", "current": None, "queue": []},
        )

    @patch(f"{TEST_MODULE}.async_get_account")
    async def test_null_fields_give_empty_result(
        self,
        mock_account: AsyncMock,
    ):

        account = MagicMock(spec=SpotifyAccount)
        account.id = "12345"
        account.async_queue = AsyncMock(
            return_value={"currently_playing": None, "queue": None},
        )
        mock_account.return_value = account
        connection = MagicMock(spec=ActiveConnection)

        await async_queue(
            MagicMock(spec=HomeAssistant),
            connection,
            {"id": 1, "type": "spotcast/queue"},
        )

        connection.send_result.assert_called_once_with(
            1,
            {"account": "12345", "current": None, "queue": []},
        )

    @patch(f"{TEST_MODULE}.async_get_account")
    async def test_empty_queue_items_dropped(self, mock_account: AsyncMock):

        account = MagicMock(spec=SpotifyAccount)
        account.id = "12345"
        account.async_queue = AsyncMock(
            return_value={
                "currently_playing": track("now"),
                "queue": [None, track("one")],
            },
        )
        mock_account.return_value = account
        connection = MagicMock(spec=ActiveConnection)

        await async_queue(
            MagicMock(spec=HomeAssistant),
            connection,
            {"id": 1, "type": "spotcast/queue"},
        )

        queue = connection.send_result.call_args.args[1]["queue"]
        self.assertEqual([item["id"] for item in queue], ["one"])
