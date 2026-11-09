"""Module to test the select thumbnail url function"""

from unittest import TestCase

from custom_components.spotcast.spotify.utils import select_thumbnail_url

ALBUM_IMAGES = [
    {"height": 640, "url": "http://image.com/640", "width": 640},
    {"height": 300, "url": "http://image.com/300", "width": 300},
    {"height": 64, "url": "http://image.com/64", "width": 64},
]


class TestSmallestWideEnough(TestCase):

    def test_64_px_image_selected(self):
        self.assertEqual(
            select_thumbnail_url(ALBUM_IMAGES),
            "http://image.com/64",
        )

    def test_order_does_not_matter(self):
        self.assertEqual(
            select_thumbnail_url(list(reversed(ALBUM_IMAGES))),
            "http://image.com/64",
        )

    def test_narrower_images_skipped(self):
        images = [
            {"height": 32, "url": "http://image.com/32", "width": 32},
            {"height": 300, "url": "http://image.com/300", "width": 300},
            {"height": 640, "url": "http://image.com/640", "width": 640},
        ]
        self.assertEqual(
            select_thumbnail_url(images),
            "http://image.com/300",
        )

    def test_min_width_applied(self):
        self.assertEqual(
            select_thumbnail_url(ALBUM_IMAGES, min_width=200),
            "http://image.com/300",
        )


class TestNoneWideEnough(TestCase):

    def test_largest_image_selected(self):
        images = [
            {"height": 32, "url": "http://image.com/32", "width": 32},
            {"height": 48, "url": "http://image.com/48", "width": 48},
        ]
        self.assertEqual(
            select_thumbnail_url(images),
            "http://image.com/48",
        )


class TestImagesWithoutSize(TestCase):

    def test_first_image_selected(self):
        images = [
            {"height": None, "url": "http://image.com/1", "width": None},
            {"url": "http://image.com/2"},
        ]
        self.assertEqual(select_thumbnail_url(images), "http://image.com/1")

    def test_sized_image_preferred(self):
        images = [
            {"url": "http://image.com/1"},
            {"height": 300, "url": "http://image.com/300", "width": 300},
        ]
        self.assertEqual(
            select_thumbnail_url(images),
            "http://image.com/300",
        )


class TestNoImage(TestCase):

    def test_empty_list(self):
        self.assertIsNone(select_thumbnail_url([]))

    def test_none(self):
        self.assertIsNone(select_thumbnail_url(None))
