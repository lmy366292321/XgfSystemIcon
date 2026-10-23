#!/usr/bin/env python3
"""Collect color declarations and verify reproducible PNG exports. Never overwrite inputs."""
import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path

from PIL import Image, ImageCms, ImageFilter, PngImagePlugin, features, __version__ as PILLOW_VERSION
import check_icon
from batch_common import digest, descriptors, read_json, state, worst


def require(condition, message):
    if not condition:
        raise ValueError(message)


class SourceUnknown(ValueError):
    """Expected policy stop, not a command/runtime failure."""


def timestamp(value, field):
    require(isinstance(value, str) and value.strip(), f"Missing {field}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid {field}: ISO timestamp required") from exc
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None, f"{field} requires timezone")
    require(parsed <= datetime.now(timezone.utc), f"{field} cannot be in the future")
    return parsed


def now():
    return datetime.now(timezone.utc).isoformat()


def descriptor(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": digest(path.read_bytes())}


def checked(desc):
    path = Path(desc["path"])
    require(path.is_absolute(), "Color records require absolute paths")
    data = path.read_bytes()
    require(digest(data) == desc["sha256"], f"Evidence changed: {path}")
    return data


def save_new(path, value):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def observe(data):
    header, chunks = check_icon.read_png_chunks(data)
    require(header["bit_depth"] == 8 and header["color_type"] in (2, 6),
            "Supported input: 8-bit RGB/RGBA PNG; other formats need a separate recorded adapter")
    color = check_icon.inspect_color(chunks)
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        icc_bytes = image.info.get("icc_profile")
        rgba = image.convert("RGBA")
    result = {"size": list(rgba.size), "png_header": header, "color_metadata": color,
              "rgba_sha256": digest(rgba.tobytes()), "space": "unknown"}
    if color["status"] in ("conflicting", "invalid_metadata"):
        result["space"] = "invalid"
    elif color["status"] == "declared_srgb":
        result["space"] = "declared_srgb"
    elif "cICP" in color["metadata"]["chunks_present"]:
        # cICP has precedence over ICC/sRGB. This adapter cannot validate it.
        result["space"] = "unknown"
    elif color["status"] == "icc_unverified":
        try:
            require(bool(icc_bytes), "Missing ICC payload")
            profile = ImageCms.ImageCmsProfile(io.BytesIO(icc_bytes))
            require(profile.profile.xcolor_space.strip() == "RGB", "ICC is not an RGB profile")
            # Opening a profile is insufficient: it must also build an actual RGB transform.
            ImageCms.buildTransform(profile, ImageCms.createProfile("sRGB"), "RGB", "RGB")
            result.update(space="embedded_rgb_icc", icc={"sha256": digest(icc_bytes),
                "description": profile.profile.profile_description,
                "color_space": profile.profile.xcolor_space.strip()})
        except (OSError, ValueError, TypeError, ImageCms.PyCMSError) as exc:
            result.update(space="invalid", icc_error=str(exc))
    return result, rgba, chunks, icc_bytes


def collect(source, output, *, role, note, knowledge="file", context=()):
    require(role in ("original", "working-master"), "Source role required")
    require(knowledge in ("file", "unknown") and str(note).strip(), "Source note/knowledge required")
    source = descriptor(source)
    observation = observe(checked(source))[0]
    record = {"schema_version": 1, "kind": "color_capture", "collected_at": now(),
              "source": source, "role": role, "note": note, "knowledge": knowledge,
              "context_evidence": [descriptor(p) for p in context], "observation": observation,
              "scope": "File declarations collected now; no historical generation time or physical color accuracy inferred"}
    save_new(output, record)
    return record


def read_capture(path):
    desc = descriptor(path)
    capture = json.loads(checked(desc))
    require(capture.get("schema_version") == 1 and capture.get("kind") == "color_capture", "Invalid capture")
    timestamp(capture.get("collected_at"), "collected_at")
    require(capture.get("role") in ("original", "working-master") and capture.get("knowledge") in ("file", "unknown"),
            "Invalid source role/knowledge")
    require(isinstance(capture.get("note"), str) and capture["note"].strip(), "Missing source note")
    for d in descriptors(capture):
        checked(d)
    observation, image, chunks, icc = observe(checked(capture["source"]))
    require(observation == capture["observation"], "Captured metadata does not match current source")
    return desc, capture, observation, image, chunks, icc


def source_state(capture, observation):
    if observation["space"] == "invalid":
        return state("fail", "Invalid/conflicting source declarations")
    if capture["knowledge"] == "unknown":
        return state("unverified", "Source knowledge explicitly unknown; any existing tag is not promoted to proof")
    if capture["role"] != "original":
        return state("unverified", "Working master only; original source declaration is not established")
    if observation["space"] not in ("declared_srgb", "embedded_rgb_icc"):
        return state("unverified", "No supported original source color-space declaration")
    return state("pass", "Original file declaration verified; not independent colorimetry or model-internal proof")


def recipe(mode, resample="lanczos", target_profile=None, assumption=None):
    return {"mode": mode, "library": "Pillow", "version": PILLOW_VERSION,
            "lcms_version": features.version("littlecms2"), "resample": resample,
            "geometry": "full-square-canvas-to-1024", "preview_size": [120, 120],
            "rendering_intent": 0, "flags": 0, "target_profile": target_profile,
            "assumption": assumption}


def clean_detached_alpha(image):
    """Remove only alpha=1 samples >8px from alpha>=2, never edge AA.

    Opt-in export normalization, not a general background remover. RGB, canvas,
    stronger samples and alpha=1 within the protected neighborhood stay exact.
    """
    alpha = image.getchannel("A")
    guard = alpha.point(lambda v: 255 if v >= 2 else 0).filter(ImageFilter.MaxFilter(17))
    mask = bytes(255 if a == 1 and not g else 0 for a, g in zip(alpha.tobytes(), guard.tobytes()))
    count = mask.count(255)
    require(count <= image.width * image.height // 1000,
            "Detached alpha exceeds 0.1% cap; inspect rather than bulk-clear")
    result = image.copy()
    alpha.paste(0, (0, 0), Image.frombytes("L", image.size, mask))
    result.putalpha(alpha)
    return result, count


def replay(image, icc, operation):
    require(operation["library"] == "Pillow" and operation["version"] == PILLOW_VERSION,
            "Recorded Pillow version unavailable for exact replay")
    require(operation["lcms_version"] == features.version("littlecms2"), "Recorded LittleCMS version unavailable")
    require(operation["geometry"] == "full-square-canvas-to-1024" and image.width == image.height,
            "Only full square canvas supported; no crop, cleanup, segmentation or stretching implied")
    require(operation["preview_size"] == [120, 120], "Unsupported preview size")
    require(operation["rendering_intent"] == 0 and operation["flags"] == 0, "Unsupported ICC parameters")
    mode = operation["mode"]
    require(mode in ("preserve-srgb", "icc-to-srgb", "preserve-unknown", "assume-srgb", "audit-existing"), "Unknown color operation")
    if mode == "icc-to-srgb":
        target = ImageCms.ImageCmsProfile(io.BytesIO(checked(operation["target_profile"])))
        # Profile name is not proof: compare the actual colorimetric ICC tags against
        # the runtime's generated sRGB profile, ignoring its creation-time header.
        require(target.tobytes()[128:] == ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()[128:],
                "Target profile is not the supported generated sRGB profile")
        rgb = ImageCms.profileToProfile(image.convert("RGB"), ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                                       target, renderingIntent=0, outputMode="RGB", flags=0)
        rgb.putalpha(image.getchannel("A"))
        image = rgb
    resample = check_icon.RESAMPLERS[operation["resample"]]
    placement = None
    side = 1024
    if operation.get("placement") is not None:
        require(mode != "audit-existing", "Audit must not invent placement history")
        placement = json.loads(checked(operation["placement"]))
        require(placement.get("schema_version") == 1, "Unsupported placement schema")
        require(bool(checked(placement["basis"]).strip()), "Placement needs task basis")
        side = placement.get("resize_side")
        require(type(side) is int and 1 <= side <= 4096, "Invalid uniform resize side")
        offset = placement.get("offset")
        require(isinstance(offset, list) and len(offset) == 2 and
                all(type(x) is int and abs(x) <= 4096 for x in offset), "Invalid placement offset")
    master = image.copy() if image.size == (side, side) else image.resize((side, side), resample)
    cleanup = operation.get("alpha_cleanup")
    if cleanup is not None:
        require(operation["mode"] != "audit-existing", "Audit must not invent cleanup history")
        require(cleanup.get("method") == "detached-alpha1-guard8-cap0.001-v1", "Unsupported alpha cleanup")
        require(bool(checked(cleanup["basis"]).strip()), "Missing cleanup decision/evidence")
        master, count = clean_detached_alpha(master)
        require(type(cleanup.get("removed_count")) is int and cleanup["removed_count"] == count,
                "Alpha cleanup count differs")
    if placement is not None:
        dx, dy = placement["offset"]
        alpha = master.getchannel("A")
        retained = (max(0, -dx), max(0, -dy), min(side, 1024-dx), min(side, 1024-dy))
        require(retained[0] < retained[2] and retained[1] < retained[3], "Placement outside canvas")
        lost = alpha.copy(); lost.paste(0, retained)
        require(lost.getbbox() is None, "Placement would clip nontransparent pixels; resolve explicitly")
        out = Image.new("RGBA", (1024, 1024)); out.paste(master, (dx, dy)); master = out
    return master, master.resize((120, 120), resample)


def new_record(capture_path, capture, master, preview, operation, activity):
    return {"schema_version": 1, "kind": "color_export", "recorded_at": now(),
            "activity": activity, "capture": descriptor(capture_path), "source": capture["source"],
            "context_evidence": capture["context_evidence"], "master": descriptor(master),
            "preview": descriptor(preview), "operation": operation,
            "scope": "Current color declaration/export replay; no visual, user, UI or historical acceptance"}


def export(capture_path, output_dir, *, unknown="stop", basis=None, resample="lanczos", alpha_cleanup_basis=None, placement=None):
    _, capture, observation, image, chunks, icc = read_capture(capture_path)
    src_status = source_state(capture, observation)["status"]
    require(src_status != "fail", "Invalid source metadata must be resolved, not relabelled")
    require(unknown in ("stop", "preserve", "assume-srgb"), "Unknown-source policy required")
    require(image.width == image.height, "Only square source supported")
    assumption = None
    if src_status == "pass":
        mode = "icc-to-srgb" if observation["space"] == "embedded_rgb_icc" else "preserve-srgb"
    else:
        if unknown == "stop":
            raise SourceUnknown("Source unknown: stop; explicitly choose preserve or a documented sRGB assumption")
        if unknown == "assume-srgb":
            require(observation["space"] == "unknown" or capture["knowledge"] == "unknown", "Do not replace a known profile with an assumption")
            require(not set(observation["color_metadata"]["metadata"]["chunks_present"]) & {"iCCP", "cICP"},
                    "Do not replace ICC/cICP declarations with an sRGB assumption")
            require(bool(basis), "assume-srgb requires a real written project decision/assumption file")
            assumption = descriptor(basis)
            require(bool(checked(assumption).strip()), "Assumption file is empty")
        mode = "assume-srgb" if unknown == "assume-srgb" else "preserve-unknown"
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    target = None
    if mode == "icc-to-srgb":
        profile_path = output_dir / "target-srgb.icc"
        profile_path.write_bytes(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
        target = descriptor(profile_path)
    operation = recipe(mode, resample, target, assumption)
    if placement is not None:
        operation["placement"] = descriptor(placement)
    if alpha_cleanup_basis is not None:
        decision = descriptor(alpha_cleanup_basis)
        require(bool(checked(decision).strip()), "Missing cleanup decision/evidence")
        # Diagnose on the same resized canvas that replay cleans, before placement.
        side = json.loads(checked(operation["placement"]))["resize_side"] if placement is not None else 1024
        require(type(side) is int and 1 <= side <= 4096, "Invalid uniform resize side")
        resized = image.resize((side, side), check_icon.RESAMPLERS[resample])
        _, count = clean_detached_alpha(resized)
        operation["alpha_cleanup"] = {"method": "detached-alpha1-guard8-cap0.001-v1",
                                      "basis": decision, "removed_count": count}
    master, preview = replay(image, icc, operation)
    info = PngImagePlugin.PngInfo()
    if mode == "preserve-unknown":
        for kind, payload in chunks:
            if kind in check_icon.COLOR_CHUNKS:
                info.add(kind, payload)
    else:
        info.add(b"sRGB", b"\0")
    for filename, im in (("master-1024.png", master), ("preview-120.png", preview)):
        im.info.clear()
        with (output_dir / filename).open("xb") as stream:
            im.save(stream, format="PNG", pnginfo=info)
    record = new_record(capture_path, capture, output_dir / "master-1024.png",
                        output_dir / "preview-120.png", operation, "exported-now")
    save_new(output_dir / "color-export.json", record)
    result = verify(output_dir / "color-export.json")
    save_new(output_dir / "color-verification.json", result)
    return result


def audit(capture_path, master, preview, output, *, resample="lanczos"):
    _, capture, _, _, _, _ = read_capture(capture_path)
    record = new_record(capture_path, capture, master, preview, recipe("audit-existing", resample), "audited-now")
    save_new(output, record)
    return verify(output)


def verify(path, geometry=None):
    """Recompute evidence; saved status/reviewer prose never grants color acceptance."""
    try:
        desc = descriptor(path)
        record = json.loads(checked(desc))
        require(record.get("schema_version") == 1 and record.get("kind") == "color_export", "Invalid color export record")
        require(record.get("activity") in ("exported-now", "audited-now"), "Missing export/audit activity")
        recorded_at = timestamp(record.get("recorded_at"), "recorded_at")
        inputs = list(descriptors(record)) + [desc]
        for d in inputs:
            checked(d)
        capture_desc, capture, observation, image, chunks, icc = read_capture(record["capture"]["path"])
        require(timestamp(capture["collected_at"], "collected_at") <= recorded_at,
                "recorded_at cannot precede collected_at")
        require(capture_desc == record["capture"] and capture["source"] == record["source"], "Source/capture binding mismatch")
        require(capture["context_evidence"] == record["context_evidence"], "Context evidence omitted or changed")
        operation = record["operation"]
        src = source_state(capture, observation)
        mode = operation["mode"]
        if mode in ("preserve-srgb", "icc-to-srgb"):
            require(src["status"] == "pass", "Unknown source cannot claim a known-space export")
            require(observation["space"] == ("embedded_rgb_icc" if mode == "icc-to-srgb" else "declared_srgb"), "Operation/source mismatch")
        if mode == "assume-srgb":
            require(operation.get("assumption") and checked(operation["assumption"]).strip(), "Missing assumption basis")
            require(not set(observation["color_metadata"]["metadata"]["chunks_present"]) & {"iCCP", "cICP"},
                    "Assumption cannot override ICC/cICP")
        require((mode == "audit-existing") == (record["activity"] == "audited-now"), "Audit cannot impersonate a historical export")
        master_data, preview_data = checked(record["master"]), checked(record["preview"])
        mo, master, master_chunks, _ = observe(master_data)
        po, preview, preview_chunks, _ = observe(preview_data)
        require(master.size == (1024, 1024) and preview.size == (120, 120), "Wrong output dimensions")
        expected_master, expected_preview = replay(image, icc, operation)
        match_master = expected_master.tobytes() == master.tobytes()
        # The preview is also checked independently against the actual delivered master.
        match_preview = master.resize((120, 120), check_icon.RESAMPLERS[operation["resample"]]).tobytes() == preview.tobytes()
        chain = state("pass" if match_master else ("unverified" if mode == "audit-existing" else "fail"),
                      "Exact supported source-to-master replay" if match_master else "Source-to-master differs; missing/unsupported processing recipe")
        if mode == "audit-existing" and observation["space"] == "embedded_rgb_icc":
            chain = state("unverified", "ICC source needs a recorded conversion; unchanged RGB values cannot prove an sRGB conversion")
        derived = state("pass" if match_preview else "fail", "Exact full-canvas master-to-preview replay")
        if mode == "preserve-unknown":
            source_chunks = [(k, v) for k, v in chunks if k in check_icon.COLOR_CHUNKS]
            require(all([(k, v) for k, v in cs if k in check_icon.COLOR_CHUNKS] == source_chunks
                        for cs in (master_chunks, preview_chunks)), "Preserve mode changed color declarations")
        color_states = [o["color_metadata"]["status"] for o in (mo, po)]
        metadata = state("pass" if color_states == ["declared_srgb"] * 2 else
                         "fail" if any(s in ("invalid_metadata", "conflicting") for s in color_states) else "unverified",
                         "Output PNG declarations only", master=color_states[0], preview=color_states[1])
        for d in inputs:
            checked(d)
        states = [src["status"], chain["status"], derived["status"], metadata["status"]]
        if mode == "assume-srgb":
            states.append("unverified")
        result = state(worst(states), "Color-space/export checks recomputed; unknown/assumed origin never becomes verified",
                     record_integrity="pass", source=src, source_space=observation["space"],
                     policy=mode, source_to_master=chain, master_to_preview=derived, output_metadata=metadata,
                     record=desc, source_file=record["source"], master=record["master"], preview=record["preview"],
                     scope=record["scope"])
        if geometry is not None:
            result = verify_positioned(result, geometry)
        return result
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError, ImageCms.PyCMSError) as exc:
        return state("fail", str(exc), record_integrity="fail")


def verify_positioned(prior, geometry_path):
    """Extend a genuine pre-placement color receipt without relabelling its source."""
    import geometry_contract
    geometry_path = Path(geometry_path).resolve()
    data = geometry_path.read_bytes()
    contract = json.loads(data)
    base = geometry_path.parent
    for role in ("master", "preview"):
        origin = contract["chains"][role]["source"]
        expected = prior[role]
        if role == "preview" and contract["mode"] == "master-to-preview":
            expected = contract["outputs"]["master"]
            expected_path = (base / expected["path"]).resolve()
        else:
            expected_path = Path(expected["path"]).resolve()
        require((base / origin["path"]).resolve() == expected_path and origin["sha256"] == expected["sha256"],
                f"Geometry {role} source is not linked to this color receipt")
    final = {k: (base / contract["outputs"][k]["path"]).resolve() for k in ("master", "preview")}
    geometry = geometry_contract.verify(geometry_path, final["master"], final["preview"])
    require(geometry_path.read_bytes() == data, "Geometry changed during color verification")
    return {**prior, "status": worst([prior["status"], geometry["status"]]),
            "reason": "Original color receipt plus bound placement replay; original uncertainty retained",
            "pre_geometry": prior, "geometry": geometry,
            "master": descriptor(final["master"]), "preview": descriptor(final["preview"]),
            "master_to_preview": state(geometry["status"], "Placement relationship; see mode, not necessarily direct resize",
                                       mode=contract["mode"])}


def check_item(base, item):
    desc = item.get("color_record")
    if not desc:
        return state("unverified", "Missing color-space/export record; legacy prose is retained but cannot grant pass",
                     legacy_reported_status=item.get("color_provenance", {}).get("status"))
    try:
        record_path = (base / desc["path"]).resolve()
        require(descriptor(record_path)["sha256"] == desc["sha256"].lower(), "Color record changed")
        geometry_path = None
        if item.get("geometry"):
            geometry_path = (base / item["geometry"]["path"]).resolve()
            require(descriptor(geometry_path)["sha256"] == item["geometry"]["sha256"].lower(), "Geometry record changed")
        result = verify(record_path, geometry=geometry_path)
        if result.get("record_integrity") == "pass":
            for key in ("master", "preview"):
                current = descriptor((base / item[key]["path"]).resolve())
                require(current == result[key], f"Color record belongs to another {key}")
            if "source" in item:
                current = descriptor((base / item["source"]["path"]).resolve())
                require(current["sha256"] == item["source"]["sha256"].lower(), "Manifest source changed")
                require(current == result["source_file"], "Color record belongs to another source")
        return result
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return state("fail", str(exc), record_integrity="fail")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("collect")
    p.add_argument("source", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--role", choices=("original", "working-master"), required=True)
    p.add_argument("--note", required=True)
    p.add_argument("--knowledge", choices=("file", "unknown"), default="file")
    p.add_argument("--context", action="append", default=[], type=Path)
    p = sub.add_parser("export")
    p.add_argument("capture", type=Path)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--unknown", choices=("stop", "preserve", "assume-srgb"), default="stop")
    p.add_argument("--basis", type=Path)
    p.add_argument("--placement", type=Path, help="Task-bound uniform square resize and lossless placement")
    p.add_argument("--alpha-cleanup-basis", type=Path,
                   help="Opt-in documented detached alpha=1 export normalization; never global threshold")
    p.add_argument("--resample", choices=tuple(check_icon.RESAMPLERS), default="lanczos")
    p = sub.add_parser("audit")
    p.add_argument("capture", type=Path)
    p.add_argument("--master", type=Path, required=True)
    p.add_argument("--preview", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--resample", choices=tuple(check_icon.RESAMPLERS), default="lanczos")
    p = sub.add_parser("verify")
    p.add_argument("record", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--geometry", type=Path, help="Read-only placement replay after the bound pre-placement color receipt")
    args = parser.parse_args(argv)
    try:
        if args.command == "collect":
            record = collect(args.source, args.output, role=args.role, note=args.note,
                             knowledge=args.knowledge, context=args.context)
            result = {"collection": "complete", "source": source_state(record, record["observation"]),
                      "record": descriptor(args.output), "acceptance": "run verify after export/audit"}
            code = 0
        elif args.command == "export":
            result = export(args.capture, args.output_dir, unknown=args.unknown, basis=args.basis, resample=args.resample,
                            alpha_cleanup_basis=args.alpha_cleanup_basis, placement=args.placement)
            code = 0 if result["status"] == "pass" else 1
        elif args.command == "audit":
            result = audit(args.capture, args.master, args.preview, args.output, resample=args.resample)
            code = 0 if result["status"] == "pass" else 1
        else:
            result = verify(args.record, geometry=args.geometry)
            if args.output:
                save_new(args.output, result)
            code = 0 if result["status"] == "pass" else 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return code
    except SourceUnknown as exc:
        print(json.dumps({"status": "unverified", "action": "stopped", "output_created": False,
                          "reason": str(exc)}, ensure_ascii=False))
        return 1
    except (OSError, ValueError, TypeError, KeyError, AttributeError, ImageCms.PyCMSError) as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
