"""Behavioral regression tests; all mutations stay inside newly created temp fixtures."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from test_fixture_directory import WorkspaceTemporaryDirectory

from PIL import Image, ImageDraw, PngImagePlugin, __version__ as PILLOW_VERSION
import batch_common as common
import check_batch
import build_qa_sheet
import build_relation_sheet
import color_record
import design_language


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = WorkspaceTemporaryDirectory(prefix="batch-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = self.root / "inputs"
        self.inputs.mkdir()
        self.manifest = self.root / "manifest.json"
        self.rule = self.root / "rule.md"
        self.rule.write_text("fixture rules", encoding="utf-8")
        self.control = self.root / "control.md"
        self.control.write_text("fixture card", encoding="utf-8")
        refs = []
        for n in range(10):
            path = self.inputs / f"ref-{n}.png"
            self.make_png(path, n + 5)
            refs.append({"id": f"R{n + 1:02}", "file": self.desc(path),
                         "purpose": "fixture", "limits": "fixture only"})
        self.m = {"schema_version": 1, "batch_id": "fixture",
                  "expected_ids": ["01", "02"], "skill": self.desc(self.rule),
                  "rules": [{"id": "rules", "file": self.desc(self.rule)}],
                  "references": refs, "inventory_dirs": [str(self.inputs)], "items": []}
        for n in range(2):
            master = self.inputs / f"master-{n}.png"
            preview = self.inputs / f"preview-{n}.png"
            self.make_png(master, n)
            with Image.open(master) as image:
                image.resize((120, 120), Image.Resampling.LANCZOS).save(preview, pnginfo=self.srgb())
            self.m["items"].append({
                "id": f"{n + 1:02}", "name": f"测试{n}", "version": "v1",
                "requirements": {"action": "open", "subject": "fixture",
                                 "keep": ["shape"], "name_dependency": "label"},
                "control_card": self.desc(self.control),
                "master": self.desc(master), "preview": self.desc(preview),
                "export": {"library": "Pillow", "version": PILLOW_VERSION, "resample": "lanczos",
                           "complete_canvas": True, "alpha_handling": "Pillow RGBA resize",
                           "color_conversion": "none"}})
        self.save()

    @staticmethod
    def srgb():
        info = PngImagePlugin.PngInfo()
        info.add(b"sRGB", b"\0")
        return info

    def make_png(self, path, n=0, size=1024, srgb=True):
        image = Image.new("RGBA", (size, size))
        ImageDraw.Draw(image).rectangle((150, 150, size - 151, size - 151),
                                       fill=(60 + n * 5, 130, 180, 255))
        image.save(path, pnginfo=self.srgb() if srgb else None)

    def desc(self, path):
        return {"path": str(path), "sha256": common.digest(path.read_bytes())}

    def save(self):
        common.write_json(self.manifest, self.m)

    def run_check(self):
        self.save()
        # Legacy tests exercise machine diagnostics; delivery has its own tests.
        return check_batch.check_batch(self.manifest, delivery=False)

    def add_reviews(self):
        for item in self.m["items"]:
            capture = self.root / ("color-capture-" + item["id"] + ".json")
            receipt = self.root / ("color-export-" + item["id"] + ".json")
            if not receipt.exists():
                color_record.collect(item["master"]["path"], capture, role="original", note="Synthetic sRGB fixture")
                color_record.audit(capture, item["master"]["path"], item["preview"]["path"], receipt)
            item["color_record"] = self.desc(receipt)
        initial = self.run_check()
        evidence = self.root / "review.md"
        evidence.write_text("Fixture review only; no production acceptance.", encoding="utf-8")
        sheets = build_qa_sheet.build_sheets(self.manifest, self.root / "review-sheets")
        sheet_files = [self.desc(self.root / "review-sheets" / s["path"]) for s in sheets["pages"]]
        for item, row in zip(self.m["items"], initial["items"]):
            shared = {"status": "pass", "bound": row["binding_for_review"],
                      "reviewer": "fixture reviewer", "reviewed_at": "2026-10-20",
                      "evidence": self.desc(evidence)}
            item["color_provenance"] = {**shared, "statement": "Fixture pixels authored in sRGB"}
            item["visual_review"] = {
                **shared, "sheets": sheet_files,
                "items": {k: {"status": "pass", "observation": "fixture",
                              "location": "whole tile"} for k in common.VISUAL_FIELDS}}
            for dimension, keys in design_language.CHECKS.items():
                item['visual_review']['items'][dimension]['design_checks'] = {
                    k: dict(status='pass', observation='Synthetic fixture only', location='whole tile') for k in keys}

    def test_hard_specs_and_replay_do_not_invent_color_provenance_or_visual_acceptance(self):
        r = self.run_check()
        self.assertEqual(r["covered_count"], 2)
        self.assertEqual(r["summary"]["hard_specs"], {"pass": 2})
        self.assertEqual(r["summary"]["derivation"], {"pass": 2})
        self.assertEqual(r["summary"]["color_metadata"], {"pass": 2})
        self.assertEqual(r["summary"]["color_provenance"], {"unverified": 2})
        self.assertEqual(r["summary"]["visual"], {"unverified": 2})
        self.assertEqual(r["exit_code"], 1)

    def test_valid_bound_review_can_be_imported_without_claiming_new_review(self):
        self.add_reviews()
        r = self.run_check()
        self.assertEqual(r["exit_code"], 0)
        self.assertEqual(r["items"][0]["visual"]["freshness"], "current")
        self.assertEqual(r["items"][0]["visual"]["basis"], "imported_review_not_machine_judgment")

    def test_missing_preview_keeps_denominator_and_checks_other_item(self):
        Path(self.m["items"][0]["preview"]["path"]).unlink()
        r = self.run_check()
        self.assertEqual(r["expected_count"], 2)
        self.assertEqual(r["readable_file_pair_count"], 1)
        self.assertEqual(len(r["items"]), 2)
        self.assertEqual(r["items"][0]["hard_specs"]["status"], "error")
        self.assertEqual(r["items"][1]["hard_specs"]["status"], "pass")
        self.assertEqual(r["exit_code"], 2)

    def test_duplicate_item_id_is_error_not_silently_first_wins(self):
        self.m["items"].append(copy.deepcopy(self.m["items"][0]))
        r = self.run_check()
        self.assertEqual(r["covered_count"], 1)
        self.assertEqual(r["items"][0]["machine_status"], "error")
        self.assertEqual(r["items"][1]["hard_specs"]["status"], "pass")

    def test_unlisted_draft_is_visible_and_not_counted(self):
        self.make_png(self.inputs / "extra.png", 23)
        r = self.run_check()
        self.assertEqual(r["expected_count"], 2)
        self.assertIn(str(self.inputs / "extra.png"), r["extra_files_not_counted"])

    def test_wrong_preview_pair_fails_even_when_manifest_hashes_match(self):
        self.m["items"][0]["preview"] = copy.deepcopy(self.m["items"][1]["preview"])
        r = self.run_check()
        self.assertEqual(r["items"][0]["integrity"]["status"], "pass")
        self.assertEqual(r["items"][0]["hard_specs"]["status"], "pass")
        self.assertEqual(r["items"][0]["derivation"]["status"], "fail")

    def test_corrupt_and_wrong_size_have_different_states(self):
        p = Path(self.m["items"][0]["master"]["path"])
        p.write_bytes(b"not a png")
        self.m["items"][0]["master"] = self.desc(p)
        p = Path(self.m["items"][1]["master"]["path"])
        self.make_png(p, size=1000)
        self.m["items"][1]["master"] = self.desc(p)
        r = self.run_check()
        self.assertEqual(r["items"][0]["hard_specs"]["status"], "error")
        self.assertEqual(r["items"][1]["hard_specs"]["status"], "fail")

    def test_missing_srgb_is_unverified_not_hard_spec_failure(self):
        p = Path(self.m["items"][0]["master"]["path"])
        self.make_png(p, srgb=False)
        self.m["items"][0]["master"] = self.desc(p)
        r = self.run_check()
        self.assertEqual(r["items"][0]["hard_specs"]["status"], "pass")
        self.assertEqual(r["items"][0]["color_metadata"]["status"], "unverified")

    def test_asset_change_invalidates_prior_visual_review(self):
        self.add_reviews()
        p = Path(self.m["items"][0]["master"]["path"])
        self.make_png(p, 25)
        self.m["items"][0]["master"] = self.desc(p)
        r = self.run_check()
        self.assertEqual(r["items"][0]["visual"]["freshness"], "stale")
        self.assertEqual(r["items"][1]["visual"]["freshness"], "current")

    def test_rule_change_invalidates_even_after_manifest_hash_is_updated(self):
        self.add_reviews()
        self.rule.write_text("new rule", encoding="utf-8")
        self.m["skill"] = self.desc(self.rule)
        self.m["rules"][0]["file"] = self.desc(self.rule)
        r = self.run_check()
        self.assertEqual(r["summary"]["visual"], {"unverified": 2})

    def test_duplicate_sheet_cannot_supply_two_backgrounds(self):
        self.add_reviews()
        review = self.m["items"][0]["visual_review"]
        review["sheets"][1] = copy.deepcopy(review["sheets"][0])
        self.assertEqual(self.run_check()["items"][0]["visual"]["status"], "unverified")

    def test_control_card_and_requirements_change_invalidate_review(self):
        self.add_reviews()
        self.m["items"][0]["requirements"]["subject"] = "changed"
        r = self.run_check()
        self.assertEqual(r["items"][0]["visual"]["freshness"], "stale")
        self.control.write_text("new control card", encoding="utf-8")
        for item in self.m["items"]:
            item["control_card"] = self.desc(self.control)
        r = self.run_check()
        self.assertEqual(r["items"][1]["visual"]["freshness"], "stale")

    def test_reference_change_invalidates_review(self):
        self.add_reviews()
        p = Path(self.m["references"][0]["file"]["path"])
        self.make_png(p, 30)
        self.m["references"][0]["file"] = self.desc(p)
        self.assertEqual(self.run_check()["summary"]["visual"], {"unverified": 2})

    def add_sharp_record(self):
        item = self.m["items"][0]
        evidence = self.root / "sharp.json"
        common.write_json(evidence, [{
            "name": "fixture-sharp", "sha256_1024": item["master"]["sha256"],
            "sha256_120": item["preview"]["sha256"],
            "preview_export": {"library": "sharp", "version": "0.35.5", "kernel": "lanczos3",
                               "complete_canvas": True, "exact_replay_pixels_equal": True}}])
        item["export"].update(library="sharp", version="0.35.5", resample="lanczos3",
                              evidence=self.desc(evidence), record_name="fixture-sharp")
        return evidence

    def test_sharp_record_is_linked_but_not_fresh_replay(self):
        self.add_sharp_record()
        d = self.run_check()["items"][0]["derivation"]
        self.assertEqual(d["status"], "unverified")
        self.assertEqual(d["external_record"]["status"], "pass")
        self.assertFalse(d["replayed"])

    def test_sharp_stale_pair_or_missing_version_is_not_accepted(self):
        evidence = self.add_sharp_record()
        records = common.read_json(evidence)
        records[0]["sha256_120"] = "0" * 64
        common.write_json(evidence, records)
        self.m["items"][0]["export"]["evidence"] = self.desc(evidence)
        self.assertEqual(self.run_check()["items"][0]["derivation"]["status"], "fail")
        del self.m["items"][0]["export"]["version"]
        with self.assertRaises(ValueError):
            self.run_check()

    def test_pillow_version_mismatch_does_not_claim_reproducibility(self):
        self.m["items"][0]["export"]["version"] = "0.0"
        d = self.run_check()["items"][0]["derivation"]
        self.assertEqual(d["status"], "unverified")
        self.assertFalse(d["replayed"])

    def test_outputs_cannot_enter_input_directory_or_overwrite_previous_run(self):
        with self.assertRaises(ValueError):
            common.prepare_output(self.manifest, self.m, self.inputs / "reports")
        out = common.prepare_output(self.manifest, self.m, self.root / "reports")
        marker = out / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        with self.assertRaises(ValueError):
            common.prepare_output(self.manifest, self.m, out)
        self.assertEqual(marker.read_text(), "keep")

    def test_both_sheets_preserve_delivered_pixels_and_120px_tiles(self):
        before = common.snapshot(self.manifest, self.m)
        index = build_qa_sheet.build_sheets(self.manifest, self.root / "sheets")
        self.assertEqual(len(index["pages"]), 2)
        self.assertTrue(index["inputs_unchanged"])
        for page in index["pages"]:
            self.assertEqual(len([t for t in page["tiles"] if t["role"] == "reference"]), 10)
            with Image.open(self.root / "sheets" / page["path"]) as sheet:
                for tile in page["tiles"]:
                    x, y, w, h = tile["box_xywh"]
                    self.assertEqual((w, h), (120, 120))
                    if tile["role"] != "candidate":
                        continue
                    with Image.open(tile["source"]["path"]) as source:
                        expected = Image.new("RGBA", (120, 120), page["background"])
                        expected.alpha_composite(source.convert("RGBA"))
                    self.assertEqual(sheet.crop((x, y, x + w, y + h)).tobytes(), expected.tobytes())
        self.assertEqual(before, common.snapshot(self.manifest, self.m))

    def test_previous_candidate_and_pagination_never_replace_reference_slots(self):
        self.m["items"][0]["previous_preview"] = copy.deepcopy(self.m["items"][1]["preview"])
        for n in range(3, 12):
            item = copy.deepcopy(self.m["items"][1])
            item["id"] = f"{n:02}"
            self.m["items"].append(item)
            self.m["expected_ids"].append(item["id"])
        self.save()
        index = build_qa_sheet.build_sheets(self.manifest, self.root / "pages")
        self.assertEqual(len(index["pages"]), 4)
        for page in index["pages"]:
            self.assertEqual(sum(t["role"] == "reference" for t in page["tiles"]), 10)
        light = [p for p in index["pages"] if p["background"] == "#F4EDE1"]
        self.assertEqual(sum(t["role"] == "candidate" for p in light for t in p["tiles"]), 11)
        self.assertEqual(sum(t["role"] == "previous" for p in light for t in p["tiles"]), 1)

    def test_input_change_during_check_invalidates_batch(self):
        original = check_batch.inspect_file
        fired = False

        def mutate(*args, **kwargs):
            nonlocal fired
            result = original(*args, **kwargs)
            if not fired:
                self.control.write_text("changed during run", encoding="utf-8")
                fired = True
            return result

        with patch.object(check_batch, "inspect_file", mutate):
            r = self.run_check()
        self.assertEqual(r["exit_code"], 2)
        self.assertFalse(r["inputs_unchanged"])
        self.assertTrue(r["changed_inputs"])

    def test_cli_reports_errors_without_touching_inputs(self):
        before = common.snapshot(self.manifest, self.m)
        rc = check_batch.main([str(self.manifest), "--output-dir", str(self.root / "cli-report")])
        self.assertEqual(rc, 1)
        self.assertTrue((self.root / "cli-report" / "batch-report.md").is_file())
        self.assertEqual(before, common.snapshot(self.manifest, self.m))

    def test_user_rejection_remains_visible_despite_passing_file_checks(self):
        self.m["items"][0]["other_states"] = {
            "user_acceptance": {"status": "fail", "scope": "whole group",
                                "note": "User rejected this candidate group"}}
        report = self.run_check()
        self.assertEqual(report["items"][0]["hard_specs"]["status"], "pass")
        self.assertEqual(report["items"][0]["other_recorded_states"]["user_acceptance"]["status"], "fail")
        self.assertIn("User rejected this candidate group", check_batch.markdown(report))

    def add_relation_group(self):
        self.m["comparison_groups"] = [{
            "id": "G01", "purpose": "Distinguish fixtures",
            "members": [{"role": "reference", "id": "R01"},
                        {"role": "candidate", "id": "01"},
                        {"role": "candidate", "id": "02"}]}]
        self.save()

    def test_relation_panels_have_both_backgrounds_and_exact_full_canvas_pixels(self):
        self.add_relation_group()
        before = common.snapshot(self.manifest, self.m)
        out = self.root / "relations"
        result = build_relation_sheet.build_relations(self.manifest, out)
        self.assertEqual({p["background"] for p in result["pages"]}, {"#F4EDE1", "#293139"})
        self.assertEqual(len(result["pages"]), 2)
        for page in result["pages"]:
            with Image.open(out / page["path"]) as sheet:
                for tile in page["tiles"]:
                    self.assertEqual(tile["box_xywh"][2:], [120, 120])
                    with Image.open(tile["source"]["path"]) as source:
                        im = source.convert("RGBA")
                        if tile["role"] == "reference":
                            im = im.resize((120, 120), Image.Resampling.LANCZOS)
                        expected = Image.new("RGBA", (120, 120), page["background"])
                        expected.alpha_composite(im)
                    x, y, w, h = tile["box_xywh"]
                    self.assertEqual(sheet.crop((x, y, x + w, y + h)).tobytes(), expected.tobytes())
        self.assertEqual(before, common.snapshot(self.manifest, self.m))
        self.assertEqual(result["visual_acceptance"], "unverified")

    def test_invalid_relation_members_duplicates_and_oversized_groups_are_rejected(self):
        self.add_relation_group()
        valid = copy.deepcopy(self.m["comparison_groups"])
        invalid_members = [
            [{"role": "candidate", "id": "99"}, {"role": "candidate", "id": "01"}],
            [{"role": "candidate", "id": "01"}] * 2,
            [{"role": "reference", "id": f"R{i:02}"} for i in range(1, 7)],
            [{"role": "reference", "id": "R01"}, {"role": "reference", "id": "R02"}],
        ]
        for members in invalid_members:
            with self.subTest(members=members):
                self.m["comparison_groups"] = copy.deepcopy(valid)
                self.m["comparison_groups"][0]["members"] = members
                self.save()
                with self.assertRaises(ValueError):
                    build_relation_sheet.build_relations(self.manifest, self.root / "bad")
                self.assertFalse((self.root / "bad").exists())

    def test_relation_filename_traversal_and_duplicate_group_ids_are_rejected(self):
        self.add_relation_group()
        for gid in ("../escape", "", "a/b"):
            self.m["comparison_groups"][0]["id"] = gid
            self.save()
            with self.assertRaises(ValueError):
                common.load_manifest(self.manifest)
        self.add_relation_group()
        self.m["comparison_groups"] *= 2
        self.save()
        with self.assertRaises(ValueError):
            common.load_manifest(self.manifest)

    def test_changed_group_invalidates_bound_reviews_without_rejudging_art(self):
        self.add_relation_group()
        self.add_reviews()
        self.assertEqual(self.run_check()["items"][0]["visual"]["status"], "pass")
        self.m["comparison_groups"][0]["purpose"] = "A different question"
        r = self.run_check()
        self.assertEqual(r["items"][0]["visual"]["status"], "unverified")
        self.assertEqual(r["items"][0]["visual"]["freshness"], "stale")

    def test_relation_panels_refuse_stale_inputs_and_protected_output(self):
        self.add_relation_group()
        with self.assertRaises(ValueError):
            build_relation_sheet.build_relations(self.manifest, self.inputs / "relations")
        self.control.write_text("changed control", encoding="utf-8")
        with self.assertRaises(ValueError):
            build_relation_sheet.build_relations(self.manifest, self.root / "bad")
        self.assertFalse((self.root / "bad").exists())

    def test_relation_panels_refuse_overwriting_an_existing_run(self):
        self.add_relation_group()
        out = self.root / "relations"
        build_relation_sheet.build_relations(self.manifest, out)
        before = {p.name: common.digest(p.read_bytes()) for p in out.iterdir()}
        with self.assertRaises(ValueError):
            build_relation_sheet.build_relations(self.manifest, out)
        self.assertEqual(before, {p.name: common.digest(p.read_bytes()) for p in out.iterdir()})


if __name__ == "__main__":
    unittest.main()
