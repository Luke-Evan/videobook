"""Export raw/corrected subtitles; apply explicit, auditable AI edits only.

No global term map, filler removal, segment merging, or stutter folding.
AI proposes corrections.json; this module validates and applies the proposal.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CATEGORIES = {"proper_noun", "technical_term", "transcription", "punctuation", "segmentation"}


def render(segments):
    lines = []
    for seg in segments:
        h, m, s = str(seg["start"]).split(":")
        lines.append(f"[{int(h) * 60 + int(m):02d}:{s}] {seg['text']}")
    return "\n".join(lines) + "\n"


def source_hash(segments):
    canonical = json.dumps(segments, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def apply_edits(segments, proposal, allow_large=False):
    if proposal.get("source_sha256") != source_hash(segments):
        raise ValueError("Source hash mismatch: regenerate the proposal from this raw transcript")
    corrected = [dict(seg) for seg in segments]
    seen, report = set(), []
    for edit in proposal.get("edits", []):
        index = edit["segment_index"]
        if type(index) is not int or not 0 <= index < len(segments) or index in seen:
            raise ValueError(f"Invalid or duplicated segment_index: {index}")
        seen.add(index)
        raw = segments[index]["text"]
        if edit.get("original") != raw:
            raise ValueError(f"Original text mismatch at segment {index}")
        replacement = edit.get("replacement")
        if not isinstance(replacement, str) or not replacement.strip() or "\n" in replacement or "\r" in replacement:
            raise ValueError(f"Segment {index}: deletion, multiline text, and merging are not allowed")
        if edit.get("category") not in CATEGORIES or not str(edit.get("reason", "")).strip():
            raise ValueError(f"Segment {index}: allowed category and reason are required")
        change_ratio = 1 - difflib.SequenceMatcher(None, raw, replacement).ratio()
        if len(raw) >= 40 and change_ratio > 0.4 and not allow_large:
            raise ValueError(f"Segment {index}: large edit ({change_ratio:.0%}); inspect it before --allow-large-edits")
        corrected[index]["text"] = replacement
        if replacement != raw:
            report.append({**edit, "start": segments[index]["start"], "change_ratio": round(change_ratio, 4)})
    return corrected, report


def process(video_dir, edits=None, force=False, allow_large=False):
    src = video_dir / "transcript.json"
    data = json.loads(src.read_text(encoding="utf-8"))
    segments = data["segments"]
    raw = render(segments)
    raw_path = video_dir / "transcript.raw.txt"
    if raw_path.exists() and raw_path.read_text(encoding="utf-8") != raw:
        raise ValueError("Existing raw transcript differs; preserve it and use a new output folder")
    corrected_path = video_dir / "transcript.corrected.txt"
    if corrected_path.exists() and not force:
        raise ValueError("Corrected transcript already exists; inspect it before using --force")
    proposal = json.loads(Path(edits).read_text(encoding="utf-8")) if edits else {
        "source_sha256": source_hash(segments), "edits": []}
    corrected, report = apply_edits(segments, proposal, allow_large)
    # Validate before writing any artifact. Never mutate transcript.json/transcript.txt.
    if not raw_path.exists():
        raw_path.write_text(raw, encoding="utf-8")
    corrected_path.write_text(render(corrected), encoding="utf-8")
    (video_dir / "transcript.corrections.json").write_text(json.dumps({
        "source_sha256": source_hash(segments), "segment_count": len(segments),
        "status": "applied_ai_edits" if edits else "raw_copy_not_ai_reviewed",
        "edits": report}, ensure_ascii=False, indent=2), encoding="utf-8")
    if not edits:
        (video_dir / "corrections.template.json").write_text(json.dumps({
            "source_sha256": source_hash(segments), "edits": []}, indent=2), encoding="utf-8")
    print(f"{video_dir.name}: {len(segments)} segments preserved; {len(report)} explicit edits; "
          f"{'AI proposal applied' if edits else 'raw copy only, awaiting AI review'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video_id", nargs="*")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--edits", help="AI-authored corrections.json (one video only)")
    parser.add_argument("--force", action="store_true", help="Explicitly replace corrected output, never raw")
    parser.add_argument("--allow-large-edits", action="store_true", help="Allow individually inspected large edits")
    args = parser.parse_args()
    if not args.video_id and not args.all:
        parser.error("Specify video_id or --all")
    ids = args.video_id or [p.parent.name for p in (BASE / "output").glob("*/transcript.json")]
    if args.edits and len(ids) != 1:
        parser.error("--edits requires exactly one video")
    for vid in ids:
        if Path(vid).name != vid or vid in {".", ".."}:
            parser.error("video_id must be a folder name, not a path")
        process(BASE / "output" / vid, args.edits, args.force, args.allow_large_edits)


if __name__ == "__main__":
    main()
