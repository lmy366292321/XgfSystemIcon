#!/usr/bin/env python3
"""Read-only batch checks. Outputs reports only; never repairs or exports assets."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import json

from PIL import __version__ as PILLOW_VERSION
import check_icon
import color_record
from batch_common import (VISUAL_FIELDS, binding, changed_inputs, context, item_binding,
                          load_manifest, prepare_output, read_json, resolve, snapshot,
                          state, worst, write_json, review_sheet_files)


def inspect_file(path, size, margin):
    raw, image = check_icon.load_and_inspect(path, size, margin)
    status = "error" if image is None else ("pass" if raw["hard_spec_pass"] else "fail")
    return state(status, "; ".join(raw["errors"]) or "Hard specifications passed",
                 raw=raw), image


def color_state(raw_files):
    colors = [x["raw"]["color_metadata"]["status"] for x in raw_files]
    if any(x["status"] == "error" for x in raw_files):
        status = "error"
    elif any(c in ("conflicting", "invalid_metadata") for c in colors):
        status = "fail"
    elif all(c == "declared_srgb" for c in colors):
        status = "pass"
    else:
        status = "unverified"
    return state(status, "PNG declarations only; not source colorimetry",
                 master=colors[0], preview=colors[1])


def derivation(base, item, pair, images, snap):
    export = item["export"]
    if not export["complete_canvas"]:
        return state("fail", "Preview must derive from complete master canvas", replayed=False)
    if any(p["status"] != "pass" for p in pair):
        return state("unverified", "Hard-spec failure prevents derivation check", replayed=False)
    if export["library"].casefold() == "pillow":
        if export["version"] != PILLOW_VERSION:
            return state("unverified", "Recorded Pillow version is unavailable",
                         recorded_version=export["version"], runtime_version=PILLOW_VERSION,
                         replayed=False)
        if (export["resample"] not in check_icon.RESAMPLERS
                or export["alpha_handling"] != "Pillow RGBA resize"
                or export["color_conversion"] != "none"):
            return state("unverified", "Unsupported Pillow export recipe", replayed=False)
        raw = check_icon.compare_preview(images[0], images[1], pair[0]["raw"],
                                         pair[1]["raw"], export["resample"])
        return state("pass" if raw["derivation_pass"] else "fail",
                     "Pillow exact replay executed", replayed=True, raw=raw)
    result = state("unverified", "No replay adapter; external record is not a fresh replay",
                   replayed=False)
    evidence = export.get("evidence")
    if not evidence:
        return result
    bound = binding(base, evidence, snap)
    if bound["status"] != "pass":
        return state(bound["status"], "External evidence changed/unreadable",
                     replayed=False, external_record=bound)
    if export["library"].casefold() != "sharp":
        return result
    try:
        records = read_json(resolve(base, evidence["path"]))
        rows = [r for r in records if r.get("name") == export.get("record_name")]
        if len(rows) != 1:
            raise ValueError("External record_name must identify exactly one row")
        row = rows[0]
        recorded = row["preview_export"]
        expected_hashes = [p["raw"]["sha256"] for p in pair]
        matches = (row.get("sha256_1024") == expected_hashes[0]
                   and row.get("sha256_120") == expected_hashes[1]
                   and recorded.get("library") == "sharp"
                   and recorded.get("version") == export["version"]
                   and recorded.get("kernel") == export["resample"]
                   and recorded.get("complete_canvas") is True)
        external_status = "pass" if matches and recorded.get("exact_replay_pixels_equal") is True else "fail"
        result["external_record"] = state(
            external_status, "Historical Sharp record; only version/hash association checked now",
            binding="current" if matches else "stale", evidence=bound,
            historical_replay_equal=recorded.get("exact_replay_pixels_equal"))
        if external_status == "fail":
            result["status"] = "fail"
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        result = state("error", str(exc), replayed=False)
    return result


def imported_review(base, review, bound, snap, visual=False):
    """Validate linkage of a supplied review; do not manufacture a visual judgment."""
    result = state("unverified", "No fully bound review", freshness="stale",
                   reported_status=review.get("status"), basis="imported_review_not_machine_judgment")
    if review.get("legacy_evidence"):
        result["legacy_evidence"] = binding(base, review["legacy_evidence"], snap)
    if review.get("bound") != bound:
        return result
    evidence = review.get("evidence")
    if not evidence or not str(review.get("reviewer", "")).strip() or not str(review.get("reviewed_at", "")).strip():
        return result
    check = binding(base, evidence, snap)
    if check["status"] != "pass":
        result["reason"] = "Review evidence changed/unreadable"
        return result
    if visual:
        try:
            sheets = review_sheet_files(review)
        except ValueError as exc:
            result["reason"] = str(exc)
            return result
        sheet_paths = {str(resolve(base, d["path"])) for d in sheets}
        if (len(sheets) < 2 or len(sheet_paths) != len(sheets)
                or any(binding(base, d, snap)["status"] != "pass" for d in sheets)):
            result["reason"] = "Two unchanged background sheets required"
            return result
        entries = review.get("items", {})
        if any(k not in entries or not isinstance(entries[k], dict)
               or entries[k].get("status") not in ("pass", "fail", "unverified")
               or not isinstance(entries[k].get("observation"), str) or not entries[k]["observation"].strip()
               or not isinstance(entries[k].get("location"), str) or not entries[k]["location"].strip()
               for k in VISUAL_FIELDS):
            return result
        status = worst(entries[k]["status"] for k in VISUAL_FIELDS)
    else:
        if review.get("status") not in ("pass", "fail", "unverified") or not review.get("statement"):
            return result
        status = review["status"]
    return state(status, "Bound review imported; no new visual/color judgment performed",
                 freshness="current", basis="imported_review_not_machine_judgment",
                 evidence=check, review=review)


def check_batch(path, *, delivery=True):
    path, m = load_manifest(path)
    base = path.parent
    before = snapshot(path, m)
    ctx = context(path, m, before)
    errors, issues = [], []
    ctx_checks = [binding(base, m["skill"], before)]
    ctx_checks += [binding(base, r["file"], before) for r in m["rules"] + m["references"]]
    if len(m["references"]) != 10:
        issues.append("Expected 10 distinct official references; missing references are not fabricated")
    for group in ("references", "rules"):
        if len({r["id"] for r in m[group]}) != len(m[group]):
            errors.append(f"Duplicate {group} IDs")
    reference_paths = [str(resolve(base, r["file"]["path"])) for r in m["references"]]
    if len(set(reference_paths)) != len(reference_paths):
        errors.append("References reuse a file path")
    reference_hashes = [before[p]["sha256"] for p in reference_paths]
    if len({h for h in reference_hashes if h}) != len(reference_hashes):
        issues.append("Reference images are missing or duplicated by content")
    # Old references retain their historical color acceptance; only usable image geometry is gated here.
    reference_checks = []
    for ref in m["references"]:
        check, _ = inspect_file(resolve(base, ref["file"]["path"]), 1024, 102)
        reference_checks.append({"id": ref["id"], "check": check})
    context_status = worst([c["status"] for c in ctx_checks]
                           + [r["check"]["status"] for r in reference_checks]
                           + (["error"] if errors else [])
                           + (["unverified"] if issues else []))
    by_id = defaultdict(list)
    for item in m["items"]:
        by_id[item["id"]].append(item)
    unexpected = sorted(set(by_id) - set(m["expected_ids"]))
    if unexpected:
        errors.append("Unexpected manifest item IDs: " + ", ".join(unexpected))
    rows = []
    for asset_id in m["expected_ids"]:
        entries = by_id[asset_id]
        if len(entries) != 1:
            errors.append(f"{asset_id}: expected one manifest row, found {len(entries)}")
            rows.append({"id": asset_id, "name": "", "machine_status": "error",
                         "error": "Missing or duplicate manifest item",
                         **{k: state("error", "Missing or duplicate manifest item")
                            for k in ("integrity", "hard_specs", "color_metadata", "color_provenance", "derivation")},
                         "visual": state("unverified", "No unambiguous asset")})
            continue
        item = entries[0]
        try:
            bindings = {k: binding(base, item[k], before) for k in ("master", "preview", "control_card")}
            integrity = state(worst(v["status"] for v in bindings.values()),
                              "Manifest hashes compared to current bytes", files=bindings)
            master, master_im = inspect_file(resolve(base, item["master"]["path"]), 1024, 102)
            preview, preview_im = inspect_file(resolve(base, item["preview"]["path"]), 120, 0)
            hard = state(worst((master["status"], preview["status"])),
                         "Both delivered files checked", master=master, preview=preview)
            bound = item_binding(base, item, ctx, before)
            color = color_state([master, preview])
            derived = derivation(base, item, [master, preview], [master_im, preview_im], before)
            provenance = color_record.check_item(base, item)
            visual = imported_review(base, item.get("visual_review", {}), bound, before, visual=True)
            if integrity["status"] != "pass" or context_status != "pass":
                visual = state("unverified", "Asset/control/reference/rule integrity prevents current acceptance",
                               freshness="stale", prior_review=visual)
                provenance = state("unverified", "Integrity prevents accepting linked provenance",
                                   freshness="stale", prior_review=provenance)
            rows.append({"id": asset_id, "name": item["name"], "version": item["version"],
                         "requirements": item["requirements"], "binding_for_review": bound,
                         "integrity": integrity, "hard_specs": hard, "color_metadata": color,
                         "color_provenance": provenance, "derivation": derived, "visual": visual,
                         "other_recorded_states": item.get("other_states", {}),
                         "machine_status": worst([context_status, integrity["status"], hard["status"],
                                                  color["status"], provenance["status"], derived["status"]])})
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            errors.append(f"{asset_id}: {exc}")
            rows.append({"id": asset_id, "name": item["name"], "machine_status": "error",
                         "error": str(exc),
                         **{k: state("error", str(exc)) for k in
                            ("integrity", "hard_specs", "color_metadata", "color_provenance", "derivation")},
                         "visual": state("unverified", "Execution error")})
    listed = {str(resolve(base, i[k]["path"])) for i in m["items"]
              for k in ("master", "preview", "previous_preview") if i.get(k)}
    extra_files = []
    for folder in m.get("inventory_dirs", []):
        try:
            extra_files += [str(p.resolve()) for p in resolve(base, folder).iterdir()
                            if p.is_file() and p.suffix.lower() == ".png" and str(p.resolve()) not in listed]
        except OSError as exc:
            errors.append(f"Inventory error: {exc}")
    same_master = defaultdict(list)
    for item in m["items"]:
        sha = before[str(resolve(base, item["master"]["path"]))]["sha256"]
        if sha:
            same_master[sha].append(item["id"])
    reused = [ids for ids in same_master.values() if len(ids) > 1]
    after = snapshot(path, m)
    changed = changed_inputs(before, after)
    if changed:
        errors.append("Input changed during checks; discard current acceptance")
        for row in rows:
            row["machine_status"] = "error"
            row["visual"] = state("unverified", "Batch inputs changed during run", freshness="stale")
    status = worst([r["machine_status"] for r in rows] + [context_status]
                   + (["error"] if errors else []))
    report = {
        "schema_version": 1, "batch_id": m["batch_id"], "manifest": str(path),
        "manifest_sha256": before[str(path)]["sha256"],
        "checked_at": datetime.now(timezone.utc).isoformat(), "pillow_version": PILLOW_VERSION,
        "context": ctx, "context_checks": ctx_checks, "reference_checks": reference_checks,
        "context_status": context_status, "errors": errors, "issues": issues,
        "expected_count": len(m["expected_ids"]),
        "covered_count": sum(len(by_id[i]) == 1 for i in m["expected_ids"]),
        "readable_file_pair_count": sum(
            len(by_id[i]) == 1 and all(before[str(resolve(base, by_id[i][0][k]["path"]))]["error"] is None
                                      for k in ("master", "preview"))
            for i in m["expected_ids"]),
        "unexpected_item_ids": unexpected, "extra_files_not_counted": sorted(extra_files),
        "reused_master_semantics_need_review": reused, "items": rows,
        "summary": {key: dict(Counter(r[key]["status"] for r in rows))
                    for key in ("integrity", "hard_specs", "color_metadata",
                                "color_provenance", "derivation", "visual")},
        "machine_status": status, "exit_code": 2 if status == "error" else (0 if status == "pass" else 1),
        "inputs_unchanged": not changed, "changed_inputs": changed,
        "input_snapshot": before,
        "scope": "Machine file/evidence checks only. No new visual, user, UI or engine acceptance."
    }
    report["machine_exit_code"] = report["exit_code"]
    if delivery:
        from review_workflow import delivery_gate
        gate = delivery_gate(path, m, report)
        report["delivery"] = gate
        report["exit_code"] = 2 if gate["status"] == "error" else (0 if gate["status"] == "pass" else 1)
        report["scope"] = "Resource delivery gate: technical checks and current recorded visual/recheck evidence. Not user, UI or engine acceptance."
    return report


def markdown(report):
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    lines = [f"# {report['batch_id']} 批量检查", "",
             f"覆盖 {report['covered_count']}/{report['expected_count']}；机器状态 "
             f"`{report['machine_status']}`；退出码 {report['exit_code']}。",
             f"高清与120均可读取的文件对：{report['readable_file_pair_count']}/{report['expected_count']}。",
             "", "机器不代替实际看图；不授予用户、UI或工程通过。", "",
             "| ID | 入口 | 版本关联 | 硬规格 | 色彩声明 | 色彩空间/导出记录 | 派生复验 | 视觉记录 |",
             "|---|---|---|---|---|---|---|---|"]
    for row in report["items"]:
        values = [row["id"], row["name"]] + [row[k]["status"] for k in (
            "integrity", "hard_specs", "color_metadata", "color_provenance", "derivation", "visual")]
        lines.append("| " + " | ".join(map(cell, values)) + " |")
    lines += ["", "## 需处理或保留未验证的项目", ""]
    for row in report["items"]:
        for key in ("integrity", "hard_specs", "color_metadata", "color_provenance", "derivation", "visual"):
            if row[key]["status"] != "pass":
                lines.append(f"- {row['id']} {key}: {cell(row[key]['reason'])}")
        ext = row["derivation"].get("external_record")
        if ext:
            lines.append(f"- {row['id']} Sharp历史记录关联：{ext['status']}；本次未重跑该导出。")
    lines += ["", "## 已有用户与接入记录", "",
              "以下仅转述清单绑定的已有记录，不由机器检查授予接受或上线结论。", ""]
    for row in report["items"]:
        recorded = row.get("other_recorded_states", {})
        if recorded:
            lines.append(f"- {row['id']}: {cell(json.dumps(recorded, ensure_ascii=False))}")
    lines += [""] + [f"- {cell(s)}" for s in report["errors"] + report["issues"]]
    lines += ["", f"输入检查前后未改变：{report['inputs_unchanged']}。",
              f"额外PNG（不计入交付）：{len(report['extra_files_not_counted'])}。",
              "", "逐文件数值、原始单图结果、版本绑定及其他状态见 batch-report.json。", ""]
    if "delivery" in report:
        gate = report["delivery"]
        lines += [f"## 资源交付判定：{gate['status']}", "", gate["reason"], ""]
        lines += [f"- {cell(x)}" for x in gate.get("issues", [])]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        path, manifest = load_manifest(args.manifest)
        out = prepare_output(path, manifest, args.output_dir)
        report = check_batch(path)
        write_json(out / "batch-report.json", report)
        (out / "batch-report.md").write_text(markdown(report), encoding="utf-8")
        print(json.dumps({"report": str(out / "batch-report.json"), "summary": report["summary"],
                          "exit_code": report["exit_code"]}, ensure_ascii=False))
        return report["exit_code"]
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
