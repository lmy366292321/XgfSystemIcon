#!/usr/bin/env python3
"""Compose 120px diagnostic sheets without rewriting any input asset."""
import argparse
from datetime import datetime, timezone
import io
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, __version__ as PILLOW_VERSION
from batch_common import (binding, changed_inputs, context, digest, load_manifest,
                          prepare_output, resolve, snapshot, write_json)
import check_icon

BACKGROUNDS = {"light": "#F4EDE1", "dark": "#293139"}
SIZE, COLS, STEP, MARGIN = 120, 5, 140, 20
WIDTH, HEIGHT = 720, 700


def load_tile(base, desc, snap, reference):
    bound = binding(base, desc, snap)
    if bound["status"] != "pass":
        raise ValueError(f"Cannot compose changed/unreadable input: {bound['file']}")
    data = resolve(base, desc["path"]).read_bytes()
    if digest(data) != bound["actual_sha256"]:
        raise ValueError("Input changed while loading tile")
    header, _ = check_icon.read_png_chunks(data)
    expected = 1024 if reference else 120
    if (header["width"], header["height"], header["bit_depth"], header["color_type"]) != (expected, expected, 8, 6):
        raise ValueError(f"Tile must be {expected}px, 8-bit RGBA: {desc['path']}")
    with Image.open(io.BytesIO(data)) as source:
        tile = source.convert("RGBA")
    if reference:
        tile = tile.resize((SIZE, SIZE), Image.Resampling.LANCZOS,
                           box=(0, 0, 1024, 1024), reducing_gap=None)
    return tile


def build_sheets(manifest_path, output):
    path, m = load_manifest(manifest_path)
    before = snapshot(path, m)
    base = path.parent
    if len(m["references"]) != 10:
        raise ValueError("Exactly 10 official references required for these sheets")
    if len({r["id"] for r in m["references"]}) != 10:
        raise ValueError("Reference IDs must be distinct")
    hashes = [binding(base, r["file"], before) for r in m["references"]]
    if any(h["status"] != "pass" for h in hashes) or len({h["actual_sha256"] for h in hashes}) != 10:
        raise ValueError("References must be 10 distinct, unchanged files")
    for d in [m["skill"]] + [r["file"] for r in m["rules"]]:
        if binding(base, d, before)["status"] != "pass":
            raise ValueError("Skill/rule source changed")
    if (len(m["items"]) != len(m["expected_ids"])
            or {i["id"] for i in m["items"]} != set(m["expected_ids"])):
        raise ValueError("Items must match expected IDs exactly once")
    by_id = {i["id"]: i for i in m["items"]}
    references, candidates = [], []
    for ref in m["references"]:
        references.append((ref["id"], "reference", ref["file"],
                           load_tile(base, ref["file"], before, True), ref["id"]))
    for asset_id in m["expected_ids"]:
        item = by_id[asset_id]
        for k in ("master", "control_card"):
            if binding(base, item[k], before)["status"] != "pass":
                raise ValueError(f"{asset_id}: {k} changed")
        if item.get("previous_preview"):
            candidates.append((asset_id, "previous", item["previous_preview"],
                               load_tile(base, item["previous_preview"], before, False),
                               f"{asset_id} / previous"))
        candidates.append((asset_id, "candidate", item["preview"],
                           load_tile(base, item["preview"], before, False),
                           f"{asset_id} / {item['version']}"))
    out = prepare_output(path, m, output)
    font = ImageFont.load_default(size=14)
    pages = []
    page_count = math.ceil(len(candidates) / 10)
    for page in range(page_count):
        for theme, bg in BACKGROUNDS.items():
            canvas = Image.new("RGBA", (WIDTH, HEIGHT), bg)
            draw = ImageDraw.Draw(canvas)
            ink = "#25333A" if theme == "light" else "#F4EDE1"
            draw.text((20, 8), f"References / full canvas 120 px / page {page + 1}", fill=ink, font=font)
            draw.text((20, 340), "Candidates / delivered 120 px / no crop or rescale", fill=ink, font=font)
            tiles = []
            for section, entries, y0 in (
                    ("reference", references, 36),
                    ("candidate", candidates[page * 10:(page + 1) * 10], 370)):
                for n, (asset_id, role, desc, tile, label) in enumerate(entries):
                    x, y = MARGIN + STEP * (n % COLS), y0 + 154 * (n // COLS)
                    canvas.alpha_composite(tile, (x, y))
                    draw.text((x, y + SIZE + 4), label, fill=ink, font=font)
                    tiles.append({"id": asset_id, "role": role, "section": section,
                                  "box_xywh": [x, y, SIZE, SIZE], "source": desc,
                                  "recipe": f"Pillow {PILLOW_VERSION} full-canvas LANCZOS" if role == "reference"
                                  else "Delivered 120px pixels; no resize"})
            filename = f"qa-{theme}-{page + 1:02}.png"
            buffer = io.BytesIO()
            canvas.save(buffer, "PNG")
            data = buffer.getvalue()
            (out / filename).write_bytes(data)
            pages.append({"path": filename, "sha256": digest(data), "background": bg,
                          "size": [WIDTH, HEIGHT], "tiles": tiles})
    changed = changed_inputs(before, snapshot(path, m))
    index = {"schema_version": 1, "batch_id": m["batch_id"],
             "created_at": datetime.now(timezone.utc).isoformat(),
             "manifest_sha256": before[str(path)]["sha256"], "context": context(path, m, before),
             "pillow_version": PILLOW_VERSION, "reference_count_per_page": 10,
             "candidate_count": len(m["items"]), "tile_size": [120, 120],
             "status": "error" if changed else "pass", "changed_inputs": changed,
             "inputs_unchanged": not changed, "input_snapshot": before, "pages": pages,
             "visual_acceptance": "unverified",
             "scope": "Layout/pixel composition only. Viewing size, color provenance and art acceptance not certified."}
    write_json(out / "sheet-index.json", index)
    return index


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        index = build_sheets(args.manifest, args.output_dir)
        print(json.dumps({"status": index["status"], "pages": len(index["pages"]),
                          "inputs_unchanged": index["inputs_unchanged"]}, ensure_ascii=False))
        return 0 if index["status"] == "pass" else 2
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
