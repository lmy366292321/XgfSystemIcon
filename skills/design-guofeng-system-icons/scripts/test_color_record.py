"""Behavior tests for real collection/replay, unknown policies and tamper rejection."""
import json
import contextlib
from datetime import datetime, timedelta, timezone
import io
from pathlib import Path
import struct
import unittest
from PIL import Image, ImageCms, PngImagePlugin
from test_fixture_directory import WorkspaceTemporaryDirectory
import color_record as cr


class ColorRecordTests(unittest.TestCase):
    def setUp(self):
        self.temp = WorkspaceTemporaryDirectory(prefix="color-record-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.png"
        self.capture = self.root / "capture.json"

    def make(self, tagged=True, icc=None):
        image = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
        image.paste((180, 70, 90, 190), (160, 160, 864, 864))
        info = PngImagePlugin.PngInfo()
        if tagged:
            info.add(b"sRGB", b"\0")
        image.save(self.source, pnginfo=info, icc_profile=icc)

    def collect(self, **kwargs):
        return cr.collect(self.source, self.capture, role=kwargs.pop("role", "original"),
                          note="Synthetic test input, not production evidence", **kwargs)

    def change_record(self, path, function):
        record = json.loads(path.read_text())
        function(record)
        path.write_text(json.dumps(record), encoding="utf-8")

    def test_declared_source_export_and_exact_replay(self):
        self.make(); self.collect()
        original = self.source.read_bytes()
        result = cr.export(self.capture, self.root / "export")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["source_to_master"]["status"], "pass")
        self.assertEqual(self.source.read_bytes(), original)

    def test_unknown_stops_before_creating_output(self):
        self.make(False); self.collect()
        with self.assertRaisesRegex(ValueError, "Source unknown"):
            cr.export(self.capture, self.root / "export")
        self.assertFalse((self.root / "export").exists())

    def test_unknown_preserve_is_complete_but_unverified(self):
        self.make(False); self.collect()
        result = cr.export(self.capture, self.root / "export", unknown="preserve")
        self.assertEqual(result["status"], "unverified")
        self.assertEqual(result["record_integrity"], "pass")
        self.assertEqual(result["master_to_preview"]["status"], "pass")
        self.assertEqual(result["output_metadata"]["master"], "missing")

    def test_assumption_requires_nonempty_written_basis(self):
        self.make(False); self.collect()
        with self.assertRaisesRegex(ValueError, "requires"):
            cr.export(self.capture, self.root / "export", unknown="assume-srgb")

    def test_assumption_never_upgrades_source_even_with_srgb_output(self):
        self.make(False); self.collect()
        basis = self.root / "decision.txt"
        basis.write_text("Test only: interpret untagged values as sRGB; origin unknown.")
        result = cr.export(self.capture, self.root / "export", unknown="assume-srgb", basis=basis)
        self.assertEqual(result["output_metadata"]["status"], "pass")
        self.assertEqual(result["source"]["status"], "unverified")
        self.assertEqual(result["status"], "unverified")
        basis.write_text("changed decision")
        self.assertEqual(cr.verify(self.root / "export/color-export.json")["status"], "fail")

    def test_known_nominal_tag_can_be_explicitly_unknown(self):
        self.make(); self.collect(knowledge="unknown")
        result = cr.export(self.capture, self.root / "export", unknown="preserve")
        self.assertEqual(result["output_metadata"]["status"], "pass")
        self.assertEqual(result["source"]["status"], "unverified")

    def test_working_master_cannot_prove_original_source(self):
        self.make(); self.collect(role="working-master")
        result = cr.export(self.capture, self.root / "export", unknown="preserve")
        self.assertEqual(result["status"], "unverified")

    def test_icc_actual_transform_and_alpha_preservation(self):
        # A deliberately modified synthetic RGB profile retains its old name.
        # Transform behavior must follow tags, not trust the name "sRGB".
        profile = bytearray(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
        count = struct.unpack_from(">I", profile, 128)[0]
        for n in range(count):
            sig, offset, length = struct.unpack_from(">4sII", profile, 132+12*n)
            if sig == b"rXYZ":
                value = struct.unpack_from(">i", profile, offset+8)[0]
                struct.pack_into(">i", profile, offset+8, int(value * .8))
        self.make(False, bytes(profile)); self.collect()
        result = cr.export(self.capture, self.root / "export")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["policy"], "icc-to-srgb")
        with Image.open(self.source) as source, Image.open(self.root / "export/master-1024.png") as target:
            self.assertEqual(source.getchannel("A").tobytes(), target.getchannel("A").tobytes())
            self.assertNotEqual(source.getpixel((200, 200))[:3], target.getpixel((200, 200))[:3])

    def test_invalid_icc_not_fixed_by_assumption(self):
        self.make(False, b"not an ICC profile"); self.collect()
        with self.assertRaisesRegex(ValueError, "Invalid source"):
            cr.export(self.capture, self.root / "export", unknown="assume-srgb")

    def test_source_changes_invalidate_capture(self):
        self.make(); self.collect()
        self.source.write_bytes(self.source.read_bytes()+b"changed")
        with self.assertRaisesRegex(ValueError, "Evidence changed"):
            cr.export(self.capture, self.root / "export")

    def test_fake_observation_rejected(self):
        self.make(False); self.collect()
        self.change_record(self.capture, lambda r:r["observation"].update(space="declared_srgb"))
        with self.assertRaisesRegex(ValueError, "metadata does not match"):
            cr.export(self.capture, self.root / "export")

    def test_rehashed_wrong_pixels_fail_replay(self):
        self.make(); self.collect(); cr.export(self.capture, self.root / "export")
        master = self.root / "export/master-1024.png"
        with Image.open(master) as image:
            im=image.copy()
        im.putpixel((200, 200),(1, 2, 3, 255)); im.save(master)
        receipt=self.root / "export/color-export.json"
        self.change_record(receipt, lambda r:r.update(master=cr.descriptor(master)))
        result=cr.verify(receipt)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["source_to_master"]["status"], "fail")

    def test_readonly_audit_does_not_invent_historical_processing(self):
        self.make(False); self.collect()
        master=self.root/'master.png';preview=self.root/'preview.png'
        with Image.open(self.source) as image:
            im=image.copy()
        im.putpixel((200,200),(1,2,3,255));im.save(master)
        im.resize((120,120),Image.Resampling.LANCZOS).save(preview)
        before=master.read_bytes()
        result=cr.audit(self.capture,master,preview,self.root/'audit.json')
        self.assertEqual(result['source_to_master']['status'],'unverified')
        self.assertEqual(result['master_to_preview']['status'],'pass')
        self.assertEqual(master.read_bytes(),before)

    def test_existing_outputs_and_records_refused(self):
        self.make();self.collect()
        with self.assertRaises(FileExistsError): self.collect()
        cr.export(self.capture,self.root/'export')
        with self.assertRaises(FileExistsError): cr.export(self.capture,self.root/'export')

    def test_legacy_prose_pass_does_not_grant_acceptance(self):
        result=cr.check_item(self.root,{'color_provenance':{'status':'pass','statement':'trust me'}})
        self.assertEqual(result['status'],'unverified')

    def test_record_for_another_asset_is_rejected(self):
        self.make();self.collect();cr.export(self.capture,self.root/'export')
        item={'color_record':cr.descriptor(self.root/'export/color-export.json'),
              'master':cr.descriptor(self.source), 'preview':cr.descriptor(self.root/'export/preview-120.png')}
        self.assertEqual(cr.check_item(self.root,item)['status'],'fail')

    def test_icc_cannot_be_relabelled_by_an_audit(self):
        profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        self.make(False,profile);self.collect()
        with Image.open(self.source) as im: image=im.copy()
        image.info.clear();info=PngImagePlugin.PngInfo();info.add(b'sRGB',b'\0')
        master=self.root/'master.png';preview=self.root/'preview.png'
        image.save(master,pnginfo=info)
        image.resize((120,120),Image.Resampling.LANCZOS).save(preview,pnginfo=info)
        result=cr.audit(self.capture,master,preview,self.root/'audit.json')
        self.assertEqual(result['source_to_master']['status'],'unverified')
        self.assertEqual(result['status'],'unverified')

    def test_icc_cannot_be_overridden_by_unknown_assumption(self):
        self.make(False,ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes())
        self.collect(knowledge='unknown')
        basis=self.root/'decision.txt';basis.write_text('A test assumption cannot override actual ICC.')
        with self.assertRaisesRegex(ValueError,'ICC/cICP'):
            cr.export(self.capture,self.root/'export',unknown='assume-srgb',basis=basis)

    def test_manifest_source_must_match_receipt_even_for_identical_pixels(self):
        self.make();self.collect();cr.export(self.capture,self.root/'export')
        other=self.root/'another-source.png';other.write_bytes(self.source.read_bytes())
        item={'color_record':cr.descriptor(self.root/'export/color-export.json'),
              'master':cr.descriptor(self.root/'export/master-1024.png'),
              'preview':cr.descriptor(self.root/'export/preview-120.png'), 'source':cr.descriptor(other)}
        result=cr.check_item(self.root,item)
        self.assertEqual(result['status'],'fail')
        self.assertIn('another source',result['reason'])
        item['source']=cr.descriptor(self.source)
        self.assertEqual(cr.check_item(self.root,item)['status'],'pass')
        item['source']['sha256']='0'*64
        self.assertEqual(cr.check_item(self.root,item)['status'],'fail')

    def test_missing_collection_time_rejected_even_when_rebound(self):
        self.make();self.collect();cr.export(self.capture,self.root/'export')
        receipt=self.root/'export/color-export.json'
        self.change_record(self.capture,lambda r:r.pop('collected_at'))
        self.change_record(receipt,lambda r:r.update(capture=cr.descriptor(self.capture)))
        result=cr.verify(receipt)
        self.assertEqual(result['record_integrity'],'fail')
        self.assertIn('collected_at',result['reason'])

    def test_record_time_required_with_timezone_not_future_or_before_collection(self):
        self.make();self.collect();cr.export(self.capture,self.root/'export')
        receipt=self.root/'export/color-export.json'
        for value in (None,'bad','2026-01-01T00:00:00',
                      (datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),'2000-01-01T00:00:00+00:00'):
            with self.subTest(value=value):
                self.change_record(receipt,lambda r:r.update(recorded_at=value))
                result=cr.verify(receipt)
                self.assertEqual(result['record_integrity'],'fail')
                self.assertIn('recorded_at',result['reason'])

    def test_default_unknown_cli_is_explicit_unverified_policy_stop(self):
        self.make(False);self.collect()
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            code=cr.main(['export',str(self.capture),'--output-dir',str(self.root/'export')])
        result=json.loads(output.getvalue())
        self.assertEqual(code,1)
        self.assertEqual(result['status'],'unverified')
        self.assertEqual(result['action'],'stopped')
        self.assertFalse(result['output_created'])
        self.assertFalse((self.root/'export').exists())


if __name__ == '__main__':
    unittest.main()
