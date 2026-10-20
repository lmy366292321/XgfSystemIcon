#!/usr/bin/env python3
"""Supplementary ID-only 120px relation panels; never changes input artwork."""
import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, __version__ as PILLOW_VERSION
from batch_common import (binding, changed_inputs, context, digest, load_manifest,
                          prepare_output, snapshot, write_json)
from build_qa_sheet import BACKGROUNDS, SIZE, WIDTH, STEP, MARGIN, load_tile


def build_relations(manifest_path, output):
    path, m = load_manifest(manifest_path)
    if not m.get("comparison_groups"):
        raise ValueError("No comparison_groups in manifest")
    before = snapshot(path, m)
    base = path.parent
    refs = {r["id"]: r for r in m["references"]}
    candidates = {i["id"]: i for i in m["items"]}
    if len(refs) != 10 or len(m["references"]) != 10:
        raise ValueError("Keep the same 10 official references for relation review")
    if (len(m["items"]) != len(m["expected_ids"])
            or set(candidates) != set(m["expected_ids"])):
        raise ValueError("Items must match expected IDs exactly once")
    reference_bindings = [binding(base, r["file"], before) for r in m["references"]]
    if (any(b["status"] != "pass" for b in reference_bindings)
            or len({b["actual_sha256"] for b in reference_bindings}) != 10):
        raise ValueError("References must be 10 distinct unchanged files")
    required = [m["skill"]] + [r["file"] for r in m["rules"]]
    required += [i[k] for i in m["items"] for k in ("master", "preview", "control_card")]
    if any(binding(base, d, before)["status"] != "pass" for d in required):
        raise ValueError("Asset/control/skill/rule changed")
    # Validate and load before creating any output directory.
    tiles = {}
    for group in m["comparison_groups"]:
        for member in group["members"]:
            role, aid = member["role"], member["id"]
            entry = refs[aid] if role == "reference" else candidates[aid]
            desc = entry["file"] if role == "reference" else entry["preview"]
            tiles[(role, aid)] = (entry, desc, load_tile(base, desc, before, role == "reference"))
    out = prepare_output(path, m, output)
    font = ImageFont.load_default(size=14)
    pages = []
    for group in m["comparison_groups"]:
        for theme, bg in BACKGROUNDS.items():
            canvas = Image.new("RGBA", (WIDTH, 200), bg)
            draw = ImageDraw.Draw(canvas)
            ink = "#25333A" if theme == "light" else "#F4EDE1"
            draw.text((20, 8), f"{group['id']} / full canvas 120 px / ID only", fill=ink, font=font)
            records = []
            for n, member in enumerate(group["members"]):
                role, aid = member["role"], member["id"]
                entry, desc, tile = tiles[(role, aid)]
                x, y = MARGIN + STEP * n, 36
                canvas.alpha_composite(tile, (x, y))
                label = aid if role == "reference" else f"{aid} / {entry['version']}"
                draw.text((x, y + SIZE + 4), label, fill=ink, font=font)
                records.append({"id": aid, "role": role, "source": desc,
                                "box_xywh": [x, y, SIZE, SIZE],
                                "recipe": f"Pillow {PILLOW_VERSION} full-canvas LANCZOS"
                                if role == "reference" else "Delivered 120px pixels; no resize"})
            name = f"relation-{group['id']}-{theme}.png"
            buffer = io.BytesIO()
            canvas.save(buffer, "PNG")
            data = buffer.getvalue()
            (out / name).write_bytes(data)
            pages.append({"path": name, "sha256": digest(data), "group_id": group["id"],
                          "background": bg, "size": [WIDTH, 200], "tiles": records})
    changed = changed_inputs(before, snapshot(path, m))
    index = {"schema_version": 1, "batch_id": m["batch_id"],
             "created_at": datetime.now(timezone.utc).isoformat(),
             "manifest_sha256": before[str(path)]["sha256"],
             "context": context(path, m, before), "pillow_version": PILLOW_VERSION,
             "groups": m["comparison_groups"],
             "name_mapping": {i["id"]: i["name"] for i in m["items"]},
             "status": "error" if changed else "pass", "inputs_unchanged": not changed,
             "changed_inputs": changed, "input_snapshot": before,
             "tile_size": [120, 120], "pages": pages, "visual_acceptance": "unverified",
             "scope": "Supplementary layout only; keep the 10-reference overview. No visual judgment."}
    write_json(out / "relation-index.json", index)
    return index


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = build_relations(args.manifest, args.output_dir)
        print(json.dumps({"status": result["status"], "pages": len(result["pages"]),
                          "inputs_unchanged": result["inputs_unchanged"]}, ensure_ascii=False))
        return 0 if result["status"] == "pass" else 2
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
