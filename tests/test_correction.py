import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'src' / 'make_corrected.py'
spec = importlib.util.spec_from_file_location('correction', MODULE)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class CorrectionTests(unittest.TestCase):
    def setUp(self):
        self.segments = [
            {'start': '00:00:00', 'end': '00:00:03', 'text': '外部 WIFI 工作工作工作工作，对吧'},
            {'start': '00:00:03', 'end': '00:00:06', 'text': '编辑器 NEO VM'}]

    def proposal(self, **changes):
        edit = dict(segment_index=1, original='编辑器 NEO VM', replacement='编辑器 Neovim',
                    category='technical_term', reason='PPT labels the editor Neovim')
        edit.update(changes)
        return {'source_sha256': c.source_hash(self.segments), 'edits': [edit]}

    def test_unmodified_copy_preserves_emphasis_and_ordinary_words(self):
        output, report = c.apply_edits(self.segments, {'source_sha256': c.source_hash(self.segments), 'edits': []})
        self.assertEqual(output, self.segments)
        self.assertEqual(report, [])

    def test_term_edit_keeps_timestamps_count_and_source(self):
        output, report = c.apply_edits(self.segments, self.proposal())
        self.assertEqual(output[1]['text'], '编辑器 Neovim')
        self.assertEqual(output[1]['start'], self.segments[1]['start'])
        self.assertEqual(len(output), 2)
        self.assertEqual(self.segments[1]['text'], '编辑器 NEO VM')
        self.assertEqual(len(report), 1)

    def test_invalid_proposals_rejected(self):
        for changes in ({'replacement': ''}, {'replacement': 'a\nb'}, {'original': 'wrong'},
                        {'category': 'rewrite'}, {'reason': ''}, {'segment_index': -1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                c.apply_edits(self.segments, self.proposal(**changes))
        p = self.proposal(); p['source_sha256'] = 'stale'
        with self.assertRaises(ValueError): c.apply_edits(self.segments, p)
        p = self.proposal(); p['edits'] *= 2
        with self.assertRaises(ValueError): c.apply_edits(self.segments, p)

    def test_raw_immutable_and_corrected_overwrite_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = json.dumps({'segments': self.segments}, ensure_ascii=False)
            (root / 'transcript.json').write_text(source, encoding='utf-8')
            c.process(root)
            raw = (root / 'transcript.raw.txt').read_bytes()
            with self.assertRaises(ValueError): c.process(root)
            edits = root / 'edits.json'
            edits.write_text(json.dumps(self.proposal()), encoding='utf-8')
            c.process(root, edits, force=True)
            self.assertEqual((root / 'transcript.raw.txt').read_bytes(), raw)
            self.assertEqual((root / 'transcript.json').read_text(encoding='utf-8'), source)


if __name__ == '__main__': unittest.main()
