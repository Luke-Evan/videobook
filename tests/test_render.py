import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('renderer', Path(__file__).resolve().parents[1] / 'src' / 'post_process.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class RenderTests(unittest.TestCase):
    def test_screenshot_and_anchor_materialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / 'shot_00_01_02.png'
            image.touch()
            rendered = r.replace_screenshots_with_embeds('![diagram](SCREENSHOT:00:01:02)',
                'https://www.bilibili.com/video/BVtest/', tmp)
            self.assertNotIn('SCREENSHOT:', rendered)
            self.assertIn('images/shot_00_01_02.png', rendered)
            self.assertIn('t=62', rendered)

    def test_aids_are_separate_and_links_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'book.md').write_text('# Course\n\n## Main\n\nTeacher voice.', encoding='utf-8')
            (root / 'review.md').write_text('# Review\n\nAID_ONLY', encoding='utf-8')
            r.process_markdown('https://www.bilibili.com/video/BVtest/', str(root / 'book.md'))
            rendered = (root / 'book.html').read_text(encoding='utf-8')
            self.assertIn('href="review.html"', rendered)
            self.assertNotIn('AID_ONLY', rendered)
            self.assertIn('aria-label="课程目录"', rendered)
            self.assertIn('linear-gradient', rendered)
            self.assertIn('fonts.googleapis.com', rendered)


if __name__ == '__main__': unittest.main()
