#!/usr/bin/env python3
"""Record immutable review stages and fail closed on incomplete resource delivery.

This validates evidence/sequence, not whether a human or model actually looked.
start precedes production; review mode explicitly makes no historical-process claim.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import json
import design_language

from batch_common import (binding, descriptors, digest, fingerprint, load_manifest,
                          read_json, resolve, snapshot, state, worst, write_json)
from batch_common import review_sheet_files


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def timestamp(value):
    require(nonempty(value), "Missing timestamp")
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(t.tzinfo is not None, "Timestamps must include timezone")
    require(t <= datetime.now(timezone.utc), "Future timestamp")
    return t


def descriptor(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": digest(path.read_bytes())}


def validate_files(value):
    # Workflow and plan descriptors are absolute so records can be moved safely.
    for d in descriptors(value):
        require(Path(d["path"]).is_absolute(), "Plan/workflow evidence paths must be absolute")
        require(descriptor(d["path"])["sha256"] == d["sha256"].lower(),
                f"Evidence changed: {d['path']}")


def same_file(a, b, base):
    return (resolve(base, a["path"]) == resolve(base, b["path"])
            and a["sha256"].lower() == b["sha256"].lower())


def validate_plan(plan):
    require(plan.get("schema_version") == 2, "Expected plan schema_version=2; prepare design_language without rewriting historical plans")
    require(plan.get("mode") in ("create", "revise", "review"), "Unknown workflow mode")
    require(nonempty(plan.get("batch_id")), "Missing batch_id")
    require(nonempty(plan.get("batch_palette_reason")), "Explain batch color distribution/repetition")
    refs = plan.get("references", [])
    require(len(refs) == 10 and len({r["id"] for r in refs}) == 10,
            "Plan needs 10 distinct official references")
    ref_ids = {r["id"] for r in refs}
    items = plan.get("items", [])
    require(items and len({i["id"] for i in items}) == len(items), "Plan items missing/duplicated")
    for item in items:
        design_language.validate(item.get("design_language"), ref_ids)
        palette = item.get("palette", {})
        for key in ("dominant", "reason", "color_source", "hierarchy"):
            require(nonempty(palette.get(key)), f"{item['id']}: missing palette.{key}")
        for key in ("secondary", "accent"):
            require(isinstance(palette.get(key), list) and all(nonempty(x) for x in palette[key]),
                    f"{item['id']}: palette.{key} must be an array (may be empty)")
        require(type(palette.get("preserve_existing")) is bool, "Set preserve_existing explicitly")
        for key in ("style_reference_ids", "color_reference_ids"):
            ids = item.get(key)
            require(isinstance(ids, list) and len(set(ids)) == len(ids) and set(ids) <= ref_ids,
                    f"Invalid {key}")
        require(item["style_reference_ids"], "Select a style reference separately from color")
        require(isinstance(item.get("control_card"), dict), "Missing control card descriptor")
        inputs = item.get("generation_inputs", [])
        if plan["mode"] == "review":
            require(not inputs, "Review mode must not fabricate generation inputs")
        else:
            require(isinstance(inputs, list) and inputs, "Production needs actual planned image inputs")
            for x in inputs:
                require(x.get("role") in ("style", "color", "content", "edit_target"), "Invalid input role")
                require(nonempty(x.get("purpose")) and nonempty(x.get("limits")), "Specify input scope")
                require(isinstance(x.get("file"), dict), "Missing image input descriptor")
                if x["role"] in ("style", "color"):
                    eligible = [r for r in refs if r["id"] in item[x["role"] + "_reference_ids"]]
                    require(any(same_file(x["file"], r["file"], Path.cwd()) for r in eligible),
                            "Style/color inputs must be declared official references; candidates are not substitutes")
            require(1 <= sum(x["role"] in ("style", "color") for x in inputs) <= 3,
                    "Select 1-3 official generation references")
            if plan["mode"] == "revise":
                require(any(x["role"] == "edit_target" for x in inputs), "Revision needs its edit target")
    validate_files(plan)


def stages(mode):
    return ["plan"] + ([] if mode == "review" else ["generated"]) + ["files", "visual", "recheck"]


def validate_record(record):
    require(record.get("schema_version") == 1, "Unknown workflow record version")
    validate_files(record)
    plan = read_json(record["plan"]["path"])
    validate_plan(plan)
    expected = stages(plan["mode"])
    events = record.get("events", [])
    require(events and [e["stage"] for e in events] == expected[:len(events)], "Stages missing/out of order")
    previous_time = None
    for n, event in enumerate(events):
        t = timestamp(event["at"])
        require(previous_time is None or t >= previous_time, "Events out of chronological order")
        require(nonempty(event.get("actor")), "Missing event actor")
        require(event["prior_fingerprint"] == fingerprint(events[:n]), "Stage history changed")
        previous_time = t
    require(events[0]["plan_sha256"] == record["plan"]["sha256"], "Plan changed after start")
    return plan


def current_binding(path, manifest, report, plan):
    require(all("binding_for_review" in r for r in report["items"]),
            "Cannot bind workflow while item checks have execution errors: " + "; ".join(report["errors"]))
    require(manifest["batch_id"] == plan["batch_id"], "Batch differs from sealed plan")
    require(manifest["expected_ids"] == [i["id"] for i in plan["items"]], "Plan coverage/order differs")
    actual = {r["id"]: r for r in manifest["references"]}
    require(set(actual) == {r["id"] for r in plan["references"]}, "Reference set changed")
    for ref in plan["references"]:
        require(same_file(ref["file"], actual[ref["id"]]["file"], path.parent)
                and all(ref[k] == actual[ref["id"]][k] for k in ("purpose", "limits")),
                "Reference version/purpose changed")
    require(len(manifest["items"]) == len(plan["items"]), "Item coverage differs")
    for item, intended in zip(manifest["items"], plan["items"]):
        require(item["id"] == intended["id"] and same_file(item["control_card"], intended["control_card"], path.parent),
                "Control card changed after planning")
    return fingerprint({"plan": fingerprint(plan), "bindings": [r["binding_for_review"] for r in report["items"]]})


def verified_pages(path, manifest, report):
    """Check complete indexed sheets, their current pixels, and relation coverage."""
    from collections import Counter
    from PIL import Image
    candidate = {i["id"]: i["preview"] for i in manifest["items"]}
    reference = {r["id"]: r["file"] for r in manifest["references"]}
    pages_by_background = {"#F4EDE1": [], "#293139": []}
    groups = manifest.get("comparison_groups", [])
    if len(candidate) > 1:
        require(groups and {x["id"] for g in groups for x in g["members"] if x["role"] == "candidate"} == set(candidate),
                "Multi-icon review needs relation groups covering every candidate")
    for key in ["qa_index"] + (["relation_index"] if groups else []):
        require(isinstance(manifest.get(key), dict), f"Missing {key}")
        desc = manifest[key]
        index_path = resolve(path.parent, desc["path"])
        require(descriptor(index_path)["sha256"] == desc["sha256"].lower(), f"Changed {key}")
        index = read_json(index_path)
        require(index.get("status") == "pass" and index.get("context") == report["context"], f"Stale {key}")
        counts = {bg: Counter() for bg in pages_by_background}
        seen_groups = {bg: [] for bg in pages_by_background}
        for page in index["pages"]:
            bg = page["background"]
            require(bg in pages_by_background, "Unexpected sheet background")
            page_path = index_path.parent / page["path"]
            require(descriptor(page_path)["sha256"] == page["sha256"], "Changed sheet pixels")
            if key == "qa_index":
                pages_by_background[bg].append({**descriptor(page_path),
                    "candidate_ids": [t["id"] for t in page["tiles"] if t["role"] == "candidate"]})
                require({t["id"] for t in page["tiles"] if t["role"] == "reference"} == set(reference), "Page lacks ten references")
            else:
                group = next((g for g in groups if g["id"] == page["group_id"]), None)
                require(group and [(t["role"], t["id"]) for t in page["tiles"]] == [(t["role"], t["id"]) for t in group["members"]],
                        "Relation members differ")
                seen_groups[bg].append(group["id"])
            with Image.open(page_path) as sheet:
                for tile in page["tiles"]:
                    role, aid = tile["role"], tile["id"]
                    expected = reference.get(aid) if role == "reference" else candidate.get(aid)
                    if role == "previous":
                        expected = next(i.get("previous_preview") for i in manifest["items"] if i["id"] == aid)
                    require(expected and same_file(tile["source"], expected, path.parent), "Tile source/version mismatch")
                    x, y, w, h = tile["box_xywh"]
                    require((w, h) == (120, 120), "Tile is not 120px")
                    with Image.open(resolve(path.parent, expected["path"])) as source:
                        im = source.convert("RGBA")
                        if role == "reference":
                            im = im.resize((120, 120), Image.Resampling.LANCZOS)
                        composed = Image.new("RGBA", (120, 120), bg)
                        composed.alpha_composite(im)
                    require(sheet.convert("RGBA").crop((x, y, x+w, y+h)).tobytes() == composed.tobytes(), "Sheet tile does not match current pixels")
                    if role == "candidate":
                        counts[bg][aid] += 1
        for bg in counts:
            if key == "qa_index":
                require(counts[bg] == Counter({i: 1 for i in candidate}), "Incomplete/duplicate candidate coverage")
            else:
                require(Counter(seen_groups[bg]) == Counter({g["id"]: 1 for g in groups}), "Missing relation background/group")
    return pages_by_background


def generation_status(plan, log, plan_time, manifest):
    calls = log.get("calls", [])
    require(calls, "Generation log missing calls")
    intended = {i["id"]: i for i in plan["items"]}
    covered = set()
    last_outputs = {}
    for call in calls:
        require(call.get("item_id") in intended, "Unknown generation item")
        require(timestamp(call["at"]) >= plan_time, "Generation predates sealed plan")
        require(call.get("outcome") in ("success", "failed"), "Unknown generation outcome")
        require(call.get("inputs") == intended[call["item_id"]]["generation_inputs"],
                "Actual inputs differ from planned inputs; revise plan before next call")
        require(nonempty(call.get("tool")), "Missing tool name")
        require(isinstance(call.get("receipt"), dict), "Bind the actual tool receipt")
        if call["outcome"] == "success":
            require(isinstance(call.get("output"), dict), "Successful call needs source image evidence")
            covered.add(call["item_id"])
            last_outputs[call["item_id"]] = call["output"]
    require(covered == set(intended), "No successful source recorded for every item")
    validate_files(log)
    for item in manifest["items"]:
        require(isinstance(item.get("source"), dict), "Production items must bind their generated source")
        require(same_file(item["source"], last_outputs[item["id"]], Path(manifest.get("_base", "."))),
                "Candidate source differs from last successful call; record a new candidate version")
    return "pass"


def group_review(path, manifest, record, bound, earliest):
    require(record.get("bound") == bound, "Batch palette review is stale/missing")
    require(nonempty(record.get("reviewer")), "Palette review has no reviewer")
    require(timestamp(record.get("reviewed_at")) >= earliest, "Palette review predates this workflow stage")
    require(record.get("status") in ("pass", "fail", "unverified"), "Palette review status missing")
    for key in ("observation", "location", "repetition_reason", "hierarchy"):
        require(nonempty(record.get(key)), f"Palette review missing {key}")
    require(record.get("item_ids") == manifest["expected_ids"], "Palette review must cover every item")
    require(isinstance(record.get("evidence"), dict), "Palette review missing evidence")
    sheets = record.get("sheets", [])
    require({x.get("background") for x in sheets} == {"#F4EDE1", "#293139"}, "Need both palette backgrounds")
    require(len({str(resolve(path.parent, x["file"]["path"])) for x in sheets}) == len(sheets),
            "Palette backgrounds reuse a file")
    snap = snapshot(path, manifest)
    for d in descriptors(record):
        require(binding(path.parent, d, snap)["status"] == "pass", "Palette review evidence changed")
    return record["status"]


def review_status(path, manifest, report, bound, stage, earliest):
    from check_batch import imported_review
    second = stage == "recheck"
    key = "visual_recheck" if second else "visual_review"
    snap = snapshot(path, manifest)
    pages = verified_pages(path, manifest, report)
    statuses = []
    for item, row in zip(manifest["items"], report["items"]):
        review = item.get(key, {})
        value = imported_review(path.parent, review, row["binding_for_review"], snap, visual=True)
        require(value.get("freshness") == "current", f"{item['id']}: incomplete/stale {key}")
        require(timestamp(review.get("reviewed_at")) >= earliest, f"{item['id']}: review predates stage")
        supplied = {str(resolve(path.parent, d["path"])) for d in review_sheet_files(review)}
        require(all(any(item["id"] in d["candidate_ids"] and str(resolve(path.parent, d["path"])) in supplied
                        for d in ds) for ds in pages.values()),
                "Visual review must include indexed light and dark sheets")
        if second:
            method = review.get("method")
            require(method in ("independent", "same_reviewer_second_pass"), "Declare recheck method")
            first = item["visual_review"]
            if method == "independent":
                require(first["reviewer"] != review["reviewer"], "Same reviewer cannot claim independence")
            require(not same_file(first["evidence"], review["evidence"], path.parent), "Recheck needs separate observations")
            require(first["evidence"]["sha256"].lower() != review["evidence"]["sha256"].lower(),
                    "Recheck cannot reuse identical observation bytes under a new filename")
        statuses.append(value["status"])
        statuses.extend(design_language.review_status(review))
    group_key = "palette_recheck" if second else "palette_review"
    group = manifest.get(group_key, {})
    statuses.append(group_review(path, manifest, group, bound, earliest))
    require({str(resolve(path.parent, s["file"]["path"])) for s in group["sheets"]}
            == {d["path"] for ds in pages.values() for d in ds}, "Palette review must cover every indexed page")
    relations = group.get("relations", {})
    require(set(relations) == {g["id"] for g in manifest.get("comparison_groups", [])}, "Missing relation observations")
    for value in relations.values():
        require(value.get("status") in ("pass", "fail", "unverified") and nonempty(value.get("observation"))
                and nonempty(value.get("location")), "Incomplete relation observation")
        statuses.append(value["status"])
    payload = {"items": [i.get(key, {}) for i in manifest["items"]], "group": manifest.get(group_key, {})}
    return worst(statuses), fingerprint(payload)


def new_event(record, stage, actor, **extra):
    require(nonempty(actor), "Missing event actor")
    return {"stage": stage, "at": datetime.now(timezone.utc).isoformat(), "actor": actor,
            "prior_fingerprint": fingerprint(record["events"]), **extra}


def save_new(path, value):
    path = Path(path).resolve()
    require(not path.exists(), "Output exists; choose a new record file")
    for d in descriptors(value):
        src = Path(d["path"]).resolve()
        require(path != src and src.parent not in path.parents,
                f"Output inside source/evidence directory: {src.parent}")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also protects against another writer racing the check.
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def start(plan_path, output, actor):
    plan = read_json(plan_path)
    validate_plan(plan)
    record = {"schema_version": 1, "plan": descriptor(plan_path), "events": []}
    record["events"].append(new_event(record, "plan", actor, plan_sha256=record["plan"]["sha256"]))
    save_new(output, record)
    return record


def advance(record_path, manifest_path, stage, output, actor, evidence=None):
    from check_batch import check_batch
    record = read_json(record_path)
    plan = validate_record(record)
    expected = stages(plan["mode"])
    require(stage in expected[1:], "Stage not applicable to this mode")
    index = expected.index(stage)
    require(len(record["events"]) >= index, "Cannot skip a workflow stage")
    # Re-running an earlier stage creates a new record and invalidates later stages.
    record["events"] = record["events"][:index]
    path, manifest = load_manifest(manifest_path)
    require(same_file(manifest["design_plan"], record["plan"], path.parent), "Manifest must bind sealed design_plan")
    report = check_batch(path, delivery=False)
    bound = current_binding(path, manifest, report, plan)
    for event in record["events"][1:]:
        require(event["bound"] == bound, "Assets/rules changed; repeat from generated/files stage")
    extra = {"bound": bound}
    if stage == "generated":
        require(evidence is not None, "generated requires --evidence calls.json")
        log = read_json(evidence)
        extra.update(status=generation_status(plan, log, timestamp(record["events"][0]["at"]), {**manifest, "_base": str(path.parent)}),
                     evidence=descriptor(evidence), calls=log)
    elif stage == "files":
        extra.update(status=report["machine_status"], machine_summary=report["summary"])
    else:
        status, review_hash = review_status(path, manifest, report, bound, stage,
                                           timestamp(record["events"][-1]["at"]))
        extra.update(status=status, review_fingerprint=review_hash)
    record["events"].append(new_event(record, stage, actor, **extra))
    save_new(output, record)
    return record


def delivery_gate(path, manifest, report):
    base_statuses = [report["machine_status"]] + [r["visual"]["status"] for r in report["items"]]
    issues = []
    checks = {"technical": report["machine_status"], "workflow": "unverified"}
    try:
        require(isinstance(manifest.get("workflow"), dict), "Missing workflow; legacy reports cannot claim current delivery pass")
        require(isinstance(manifest.get("design_plan"), dict), "Missing design_plan")
        desc = manifest["workflow"]
        record_path = resolve(path.parent, desc["path"])
        require(descriptor(record_path)["sha256"] == desc["sha256"].lower(), "Workflow file changed")
        record = read_json(record_path)
        plan = validate_record(record)
        require(same_file(manifest["design_plan"], record["plan"], path.parent), "Plan descriptor mismatch")
        bound = current_binding(path, manifest, report, plan)
        events = record["events"]
        require([e["stage"] for e in events] == stages(plan["mode"]), "Workflow not complete through recheck")
        for index, event in enumerate(events[1:], 1):
            require(event["bound"] == bound, f"{event['stage']}: stale asset/rule/plan binding")
            if event["stage"] == "generated":
                base_statuses.append(generation_status(plan, event["calls"], timestamp(events[0]["at"]), {**manifest, "_base": str(path.parent)}))
                require(read_json(event["evidence"]["path"]) == event["calls"], "Generation log differs from recorded calls")
            elif event["stage"] in ("visual", "recheck"):
                status, review_hash = review_status(path, manifest, report, bound, event["stage"], timestamp(events[index-1]["at"]))
                require(review_hash == event["review_fingerprint"], "Review changed after stage recorded")
                require(event["status"] == status, "Recorded review status differs")
                base_statuses.append(status)
                checks[event["stage"]] = status
                if status != "pass":
                    item_key = "visual_recheck" if event["stage"] == "recheck" else "visual_review"
                    group_key = "palette_recheck" if event["stage"] == "recheck" else "palette_review"
                    for item in manifest["items"]:
                        for key, value in item[item_key]["items"].items():
                            if value["status"] != "pass":
                                issues.append(f"{event['stage']} {item['id']}/{key}: {value['status']}: {value['observation']}")
                    group = manifest[group_key]
                    if group["status"] != "pass":
                        issues.append(f"{group_key}: {group['status']}: {group['observation']}")
                    for key, value in group.get("relations", {}).items():
                        if value["status"] != "pass":
                            issues.append(f"{group_key}/{key}: {value['status']}: {value['observation']}")
        # Re-read all nested evidence after evaluation; do not accept mid-run changes.
        validate_files(record)
        require(descriptor(record_path)["sha256"] == desc["sha256"].lower(), "Workflow changed during check")
        require(snapshot(path, manifest) == report["input_snapshot"], "Manifest inputs changed during delivery gate")
        checks["workflow"] = "pass"
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
        issues.append(str(exc))
        base_statuses.append("unverified")
    status = worst(base_statuses)
    if report["machine_status"] != "pass":
        issues.append("Technical checks incomplete/failed; see per-item machine results")
    if any(r["visual"]["status"] != "pass" for r in report["items"]):
        issues.append("Primary visual review incomplete/failed; see per-item results")
    return state(status, "Only pass permits resource delivery acceptance; user/engine remain separate.",
                 issues=issues, checks=checks, automated_visual_judgment=False,
                 design_method_effectiveness="unverified")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("start")
    p.add_argument("plan", type=Path)
    p = sub.add_parser("record")
    p.add_argument("previous", type=Path)
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--stage", required=True, choices=("generated", "files", "visual", "recheck"))
    p.add_argument("--evidence", type=Path)
    for p in sub.choices.values():
        p.add_argument("--output", required=True, type=Path)
        p.add_argument("--actor", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            record = start(args.plan, args.output, args.actor)
        else:
            record = advance(args.previous, args.manifest, args.stage, args.output, args.actor, args.evidence)
        print(json.dumps({"record": str(args.output), "last_stage": record["events"][-1]["stage"],
                          "resource_acceptance": "run check_batch on final manifest"}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
