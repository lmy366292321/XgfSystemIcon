"""Shared manifest, evidence and output guards. Python stdlib only."""
import hashlib
import json
import re
from pathlib import Path

STATES = ("pass", "fail", "unverified", "error")
VISUAL_FIELDS = ("semantics", "weight", "structure", "materials",
                 "lighting_outline", "edges", "keep", "palette")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(value):
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8"))


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def resolve(base, path):
    return (base / path).resolve()


def load_manifest(path):
    path = Path(path).resolve()
    m = read_json(path)
    if not isinstance(m, dict) or m.get("schema_version") != 1:
        raise ValueError("Expected manifest object with schema_version=1")

    def string(value, label):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label}: expected nonempty string")

    def strings(value, label):
        if not isinstance(value, list) or not value:
            raise ValueError(f"{label}: expected nonempty string array")
        for v in value:
            string(v, label)

    def descriptor(value, label):
        if not isinstance(value, dict):
            raise ValueError(f"{label}: expected file descriptor")
        string(value.get("path"), label + ".path")
        if not re.fullmatch(r"[a-fA-F0-9]{64}", str(value.get("sha256", ""))):
            raise ValueError(f"{label}: SHA-256 must contain 64 hex digits")

    string(m.get("batch_id"), "batch_id")
    strings(m.get("expected_ids"), "expected_ids")
    if len(set(m["expected_ids"])) != len(m["expected_ids"]):
        raise ValueError("expected_ids must be unique")
    descriptor(m.get("skill"), "skill")
    for field in ("rules", "references", "items"):
        if not isinstance(m.get(field), list) or not m[field]:
            raise ValueError(f"{field}: expected nonempty array")
    for r in m["rules"]:
        string(r.get("id"), "rule.id")
        descriptor(r.get("file"), "rule.file")
    for r in m["references"]:
        for field in ("id", "purpose", "limits"):
            string(r.get(field), "reference." + field)
        descriptor(r.get("file"), "reference.file")
    for item in m["items"]:
        for field in ("id", "name", "version"):
            string(item.get(field), "item." + field)
        req = item.get("requirements")
        if not isinstance(req, dict):
            raise ValueError("item.requirements must be an object")
        for field in ("action", "subject", "name_dependency"):
            string(req.get(field), "requirements." + field)
        strings(req.get("keep"), "requirements.keep")
        for field in ("master", "preview", "control_card"):
            descriptor(item.get(field), "item." + field)
        if item.get("previous_preview"):
            descriptor(item["previous_preview"], "previous_preview")
        export = item.get("export")
        if not isinstance(export, dict):
            raise ValueError("item.export must be an object")
        for field in ("library", "version", "resample", "alpha_handling",
                      "color_conversion"):
            string(export.get(field), "export." + field)
        if type(export.get("complete_canvas")) is not bool:
            raise ValueError("export.complete_canvas must be boolean")
        for field in ("visual_review", "color_provenance"):
            if not isinstance(item.get(field, {}), dict):
                raise ValueError(f"{field} must be an object")
    # Validate every optional evidence descriptor as well.
    for d in descriptors(m):
        descriptor(d, "file/evidence")
    for field in ("protected_roots", "inventory_dirs"):
        if field in m:
            strings(m[field], field)
    if "comparison_groups" in m:
        groups = m["comparison_groups"]
        if not isinstance(groups, list) or not groups:
            raise ValueError("comparison_groups must be a nonempty array")
        seen = set()
        known = {"reference": {r["id"] for r in m["references"]},
                 "candidate": set(m["expected_ids"])}
        for group in groups:
            if not isinstance(group, dict):
                raise ValueError("comparison group must be an object")
            gid = group.get("id", "")
            if not isinstance(gid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", gid) or gid in seen:
                raise ValueError("Comparison group IDs must be unique safe filename tokens")
            seen.add(gid)
            string(group.get("purpose"), "comparison_group.purpose")
            members = group.get("members")
            if not isinstance(members, list) or not 2 <= len(members) <= 5:
                raise ValueError("Comparison group must contain 2-5 members")
            pairs = []
            for member in members:
                if not isinstance(member, dict):
                    raise ValueError("Comparison member must be an object")
                role, aid = member.get("role"), member.get("id")
                if not isinstance(role, str) or not isinstance(aid, str) or role not in known or aid not in known[role]:
                    raise ValueError("Comparison member must refer to an existing reference/candidate ID")
                pairs.append((role, aid))
            if len(set(pairs)) != len(pairs) or not any(role == "candidate" for role, _ in pairs):
                raise ValueError("Comparison group needs distinct members and at least one candidate")
    return path, m


def descriptors(value):
    if isinstance(value, dict):
        if "path" in value and "sha256" in value:
            yield value
        for child in value.values():
            yield from descriptors(child)
    elif isinstance(value, list):
        for child in value:
            yield from descriptors(child)


def review_sheet_files(review):
    """Accept direct descriptors and the background/file form used by batch review."""
    sheets = review.get("sheets", [])
    if not isinstance(sheets, list):
        raise ValueError("visual_review.sheets must be an array")
    files = []
    for n, sheet in enumerate(sheets):
        if not isinstance(sheet, dict):
            raise ValueError(f"visual_review.sheets[{n}] must be a file descriptor")
        file = sheet.get("file", sheet)
        if not isinstance(file, dict) or not file.get("path") or not file.get("sha256"):
            raise ValueError(f"visual_review.sheets[{n}] needs path/sha256 or background/file")
        files.append(file)
    return files


def snapshot(path, m):
    paths = {path}
    paths.update(resolve(path.parent, d["path"]) for d in descriptors(m))
    # Color receipts include source/profile/decision files outside the manifest.
    # Track them through the complete batch run, not only during color replay.
    for item in m.get("items", []):
        if item.get("color_record"):
            try:
                receipt = read_json(resolve(path.parent, item["color_record"]["path"]))
                paths.update(resolve(path.parent, d["path"]) for d in descriptors(receipt))
            except (OSError, ValueError, TypeError, KeyError):
                pass  # The color validator reports this explicitly; no acceptance here.
    result = {}
    for p in sorted(paths):
        try:
            result[str(p)] = {"sha256": digest(p.read_bytes()), "error": None}
        except OSError as exc:
            result[str(p)] = {"sha256": None, "error": str(exc)}
    return result


def changed_inputs(before, after):
    return [p for p in before if before[p] != after.get(p)]


def binding(base, desc, snap):
    p = str(resolve(base, desc["path"]))
    entry = snap[p]
    if entry["error"]:
        return state("error", entry["error"], file=p, actual_sha256=None)
    ok = entry["sha256"] == desc["sha256"].lower()
    return state("pass" if ok else "fail",
                 "Hash matches" if ok else "File differs from manifest",
                 file=p, actual_sha256=entry["sha256"])


def state(status, reason, **extra):
    return {"status": status, "reason": reason, **extra}


def worst(statuses):
    values = list(statuses)
    for s in ("error", "fail", "unverified"):
        if s in values:
            return s
    return "pass" if values else "unverified"


def context(path, m, snap):
    base = path.parent
    rules = [{"id": r["id"], "sha256": snap[str(resolve(base, r["file"]["path"]))]["sha256"]}
             for r in m["rules"]]
    refs = [{"id": r["id"], "sha256": snap[str(resolve(base, r["file"]["path"]))]["sha256"],
             "purpose": r["purpose"], "limits": r["limits"]} for r in m["references"]]
    result = {"rules_fingerprint": fingerprint(rules),
              "references_fingerprint": fingerprint(refs),
              "skill_sha256": snap[str(resolve(base, m["skill"]["path"]))]["sha256"]}
    if "comparison_groups" in m:
        result["comparison_groups_fingerprint"] = fingerprint(m["comparison_groups"])
    if "design_plan" in m:
        result["design_plan_sha256"] = snap[str(resolve(base, m["design_plan"]["path"]))]["sha256"]
    return result


def item_binding(base, item, ctx, snap):
    result = {**ctx,
            "master_sha256": snap[str(resolve(base, item["master"]["path"]))]["sha256"],
            "preview_sha256": snap[str(resolve(base, item["preview"]["path"]))]["sha256"],
            "control_card_sha256": snap[str(resolve(base, item["control_card"]["path"]))]["sha256"],
            "requirements_fingerprint": fingerprint(item["requirements"])}
    if item.get("color_record"):
        result["color_record_sha256"] = snap[str(resolve(base, item["color_record"]["path"]))]["sha256"]
    return result


def prepare_output(path, m, output):
    """Require a new directory; resolve symlinks before enforcing input boundaries."""
    output = Path(output).resolve()
    base = path.parent
    roots = [resolve(base, r) for r in m.get("protected_roots", [])]
    roots += [resolve(base, r) for r in m.get("inventory_dirs", [])]
    roots += [resolve(base, r["file"]["path"]).parent for r in m["references"]]
    for item in m["items"]:
        roots += [resolve(base, item[k]["path"]).parent
                  for k in ("master", "preview", "previous_preview") if item.get(k)]
    for root in roots:
        if output == root or root in output.parents:
            raise ValueError(f"Output is inside protected input directory: {root}")
    if output.exists():
        raise ValueError("Output directory already exists; choose a new run directory")
    # An ancestor of any input cannot be new, but check explicitly for file collisions.
    for p in [path] + [resolve(base, d["path"]) for d in descriptors(m)]:
        if output == p or output in p.parents:
            raise ValueError("Output overlaps an input")
    output.mkdir(parents=True, exist_ok=False)
    return output


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
