import os
import tempfile
import time
import unittest
from pathlib import Path

import screenshots as shots

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    Image = None


def scene(path, offset=0, size=(160, 90)):
    image = Image.new('RGB', size, (40, 60, 80))
    draw = ImageDraw.Draw(image)
    for i in range(0, size[0], 20):
        draw.rectangle((i + offset, 10, i + offset + 8, 80), fill=(200, 180 - i, 90 + i // 2))
    draw.ellipse((20 + offset * 3, 20, 70 + offset * 3, 70), fill=(250, 250, 250))
    image.save(path)
    return path


@unittest.skipIf(Image is None, 'Pillow is required')
class ScreenshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_engine_names_are_unique_and_validated(self):
        name = shots.engine_name(3)
        self.assertRegex(name, r'^ares_[a-f0-9]{32}_3$')
        self.assertNotEqual(name, shots.engine_name(3))
        with self.assertRaises(ValueError):
            shots.collect_engine_screenshot([self.root], '../mp_glitch0000', self.root / 'x.png', 0)

    def test_collects_only_fresh_owned_file_and_removes_it(self):
        folder = self.root / 'screenshots'
        folder.mkdir()
        name = shots.engine_name(0)
        other = Image.new('RGB', (8, 8), (1, 2, 3))
        other.save(folder / 'mp_glitch0000.tga')
        before = time.time_ns()
        self.assertFalse(shots.collect_engine_screenshot([folder], name, self.root / 'v.png', before))
        Image.new('RGB', (16, 9), (10, 200, 30)).save(folder / (name + '.tga'))
        os.utime(folder / (name + '.tga'), ns=(before + 1, before + 1))
        self.assertTrue(shots.collect_engine_screenshot([folder], name, self.root / 'out' / 'v.png', before))
        self.assertFalse((folder / (name + '.tga')).exists())
        self.assertTrue((folder / 'mp_glitch0000.tga').exists())
        with Image.open(self.root / 'out' / 'v.png') as image:
            self.assertEqual((image.format, image.size), ('PNG', (16, 9)))

    def test_stale_screenshot_is_ignored(self):
        folder = self.root / 'screenshots'
        folder.mkdir()
        name = shots.engine_name(0)
        Image.new('RGB', (8, 8)).save(folder / (name + '.jpg'))
        self.assertFalse(shots.collect_engine_screenshot([folder], name, self.root / 'v.png', time.time_ns() + 10**12))
        self.assertTrue((folder / (name + '.jpg')).exists())

    def test_review_flags_black_blank_and_duplicate_views(self):
        good = scene(self.root / 'view0.png')
        moved = scene(self.root / 'view1.png', offset=9)
        same = scene(self.root / 'view2.png')
        black = self.root / 'view3.png'
        Image.new('RGB', (64, 36), (0, 0, 0)).save(black)
        grey = self.root / 'view4.png'
        Image.new('RGB', (64, 36), (128, 128, 128)).save(grey)
        review = shots.review_frames([good, moved, same, black, grey])
        self.assertEqual(review['errors'], ['VIEW 3: black frame', 'VIEW 4: blank frame (one colour)'])
        self.assertEqual(review['warnings'], ['VIEW 2: nearly identical to VIEW 0; check the camera moved'])
        self.assertEqual([f['path'] for f in review['frames']], [p.name for p in (good, moved, same, black, grey)])
        self.assertEqual(review['frames'][0]['problems'], [])

    def test_unreadable_frame_is_an_error(self):
        broken = self.root / 'view_0.png'
        broken.write_bytes(b'not an image')
        self.assertTrue(shots.review_frames([broken])['errors'][0].startswith('VIEW 0: unreadable screenshot'))

    def test_no_frames_no_review(self):
        self.assertEqual(shots.review_frames([]), {'frames': [], 'errors': [], 'warnings': []})


if __name__ == '__main__':
    unittest.main()
