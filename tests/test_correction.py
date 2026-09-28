import os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import make_corrected as mc

SEGS = [{"start": "00:00:01", "text": "hello world"},
        {"start": "00:00:05", "text": "呃"},
        {"start": "00:00:09", "text": "deep pick is great"}]


def baseline(segs=SEGS):
    base = {}
    for i, seg in enumerate(segs):
        raw = seg["text"].strip()
        if raw in mc.FILLER_ONLY:
            continue
        txt = mc.correct(raw)
        if txt:
            base[i] = txt
    return base


def prop(edits, segs=SEGS):
    return {"source_sha256": mc.source_hash(segs), "edits": edits}


def test_map_pass_still_applies():
    assert baseline()[2] == "DeepSeek is great"


def test_filler_segment_dropped_from_baseline():
    assert 1 not in baseline()


def test_source_hash_pins_version():
    with pytest.raises(ValueError):
        mc.apply_ai_edits(SEGS, baseline(), {"source_sha256": "wrong", "edits": []})


def test_happy_path_edit():
    b = baseline()
    applied, report = mc.apply_ai_edits(SEGS, b, prop([
        {"segment_index": 0, "original": b[0], "replacement": "Hello world",
         "category": "punctuation", "reason": "首字母大写"}]))
    assert applied == {0: "Hello world"} and len(report) == 1


def test_original_must_match_baseline():
    with pytest.raises(ValueError):
        mc.apply_ai_edits(SEGS, baseline(), prop([
            {"segment_index": 0, "original": "nope", "replacement": "x",
             "category": "punctuation", "reason": "r"}]))


def test_dropped_segment_rejected():
    with pytest.raises(ValueError):
        mc.apply_ai_edits(SEGS, baseline(), prop([
            {"segment_index": 1, "original": "呃", "replacement": "嗯",
             "category": "punctuation", "reason": "r"}]))


def test_multiline_and_empty_rejected():
    b = baseline()
    for rep in ("a\nb", "", "   "):
        with pytest.raises(ValueError):
            mc.apply_ai_edits(SEGS, b, prop([
                {"segment_index": 0, "original": b[0], "replacement": rep,
                 "category": "punctuation", "reason": "r"}]))


def test_category_and_reason_required():
    b = baseline()
    with pytest.raises(ValueError):
        mc.apply_ai_edits(SEGS, b, prop([
            {"segment_index": 0, "original": b[0], "replacement": "Hi",
             "category": "vibes", "reason": "r"}]))
    with pytest.raises(ValueError):
        mc.apply_ai_edits(SEGS, b, prop([
            {"segment_index": 0, "original": b[0], "replacement": "Hi",
             "category": "punctuation", "reason": "  "}]))


def test_large_edit_guard():
    segs = [{"start": "00:00:01", "text": "甲" * 80}]
    b = {0: "甲" * 80}
    edit = {"segment_index": 0, "original": "甲" * 80, "replacement": "乙" * 80,
            "category": "transcription", "reason": "整体错认"}
    with pytest.raises(ValueError):
        mc.apply_ai_edits(segs, b, prop([edit], segs))
    applied, report = mc.apply_ai_edits(segs, b, prop([edit], segs), allow_large=True)
    assert applied == {0: "乙" * 80}


def test_duplicate_segment_index_rejected():
    b = baseline()
    e = {"segment_index": 0, "original": b[0], "replacement": "Hi",
         "category": "punctuation", "reason": "r"}
    with pytest.raises(ValueError):
        mc.apply_ai_edits(SEGS, b, prop([e, dict(e)]))
