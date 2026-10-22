"""Behavior tests for explicit geometry exceptions; production PNGs stay read-only."""
import copy
import json
import unittest
from pathlib import Path

from PIL import Image, PngImagePlugin, __version__ as PILLOW_VERSION
import batch_common as common
import check_icon
import check_batch
import color_record
import geometry_contract as gc
from test_fixture_directory import WorkspaceTemporaryDirectory


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.temp = WorkspaceTemporaryDirectory(prefix='geometry-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.info = PngImagePlugin.PngInfo()
        self.info.add(b'sRGB', b'\0')
        original = Image.new('RGBA', (1024, 1024))
        original.paste((50, 160, 100, 255), (112, 133, 912, 891))
        original.paste((220, 50, 100, 128), (220, 220, 440, 500))
        self.sm = self.save_png('source-master.png', original)
        self.sp = self.save_png('source-preview.png', original.resize((120, 120), Image.Resampling.LANCZOS))
        self.master = self.translate_file(self.sm, 'master.png', -51)
        self.preview = self.translate_file(self.sp, 'preview.png', -6)
        self.basis = self.root / 'confirmation.md'
        self.basis.write_text('Synthetic confirmed placement fixture, not user approval of a real asset.', encoding='utf-8')
        self.layout = self.root / 'layout.json'
        self.layout.write_text(json.dumps({'icon_layer': {'width': 120, 'height': 120, 'scale': 1, 'offset': [0, 0]}}))
        self.contract = {
            'schema_version': 2, 'kind': 'icon_geometry', 'library': 'Pillow', 'version': PILLOW_VERSION,
            'resample': 'lanczos', 'mode': 'independent-translations', 'primary': 'preview',
            'confirmation': {'status': 'confirmed', 'scope': 'synthetic test only', 'basis': self.desc(self.basis)},
            'layout': self.desc(self.layout), 'allowed_bounds': {'master': [0, 0, 1024, 1024], 'preview': [0, 0, 120, 120]},
            'outputs': {'master': self.desc(self.master), 'preview': self.desc(self.preview)},
            'chains': {'master': {'source': self.desc(self.sm), 'operations': [{'op': 'translate', 'offset': [0, -51]}]},
                       'preview': {'source': self.desc(self.sp), 'operations': [{'op': 'translate', 'offset': [0, -6]}]}},
            'target_translation': [0, -6], 'rounding_method': 'nearest-half-away-from-zero',
            'rounding_error_at_120': [0, 0.0234375]}
        self.path = self.root / 'geometry.json'
        self.write()

    def desc(self, path):
        return {'path': str(path), 'sha256': common.digest(path.read_bytes())}

    def save_png(self, name, image):
        path = self.root / name
        image.save(path, pnginfo=self.info)
        return path

    def translate_file(self, path, name, dy):
        with Image.open(path) as source:
            out = Image.new('RGBA', source.size)
            out.paste(source, (0, dy))
        return self.save_png(name, out)

    def write(self):
        self.path.write_text(json.dumps(self.contract), encoding='utf-8')

    def verify(self):
        self.write()
        return gc.verify(self.path, self.master, self.preview)

    def test_default_is_unchanged_and_task_exception_replays_without_writes(self):
        before = {p: p.read_bytes() for p in self.root.iterdir() if p.is_file()}
        default = check_icon.check_files(self.master, self.preview)
        self.assertFalse(default['hard_spec_pass'])
        task = check_icon.check_files(self.master, self.preview, geometry=self.path)
        self.assertFalse(task['default_hard_spec_pass'])
        self.assertTrue(task['hard_spec_pass'])
        self.assertTrue(task['overall_check_pass'])
        self.assertGreater(task['geometry']['direct_resize_different_pixels'], 0)
        self.assertEqual(task['geometry']['results']['preview']['different_pixels'], 0)
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_default_direct_export_after_positioning(self):
        with Image.open(self.master) as im:
            self.save_png('preview.png', im.resize((120, 120), Image.Resampling.LANCZOS))
        self.contract.update(mode='master-to-preview', primary='master')
        self.contract['outputs']['preview'] = self.desc(self.preview)
        self.contract['chains']['preview'] = {'source': self.desc(self.master), 'operations': [{'op': 'resize', 'size': [120, 120]}]}
        self.assertEqual(self.verify()['status'], 'pass')

    def test_confirmation_missing_or_ui_offset_nonzero_is_rejected(self):
        self.contract['confirmation']['status'] = 'pending'
        self.assertEqual(self.verify()['status'], 'fail')
        self.contract['confirmation']['status'] = 'confirmed'
        self.layout.write_text(json.dumps({'icon_layer': {'width': 120, 'height': 120, 'scale': 1, 'offset': [0, -6]}}))
        self.contract['layout'] = self.desc(self.layout)
        self.assertEqual(self.verify()['status'], 'fail')

    def test_stale_nested_confirmation_and_resource_rejected(self):
        self.basis.write_text('changed')
        self.assertEqual(self.verify()['status'], 'fail')

    def test_nested_layout_resource_is_bound_and_snapshotted(self):
        resource = self.root / 'frame.txt'
        resource.write_text('synthetic frame identity')
        layout = json.loads(self.layout.read_text())
        layout['frame'] = self.desc(resource)
        self.layout.write_text(json.dumps(layout))
        self.contract['layout'] = self.desc(self.layout)
        self.assertEqual(self.verify()['status'], 'pass')
        self.assertIn(resource, gc.dependencies(self.path))
        resource.write_text('changed resource')
        self.assertEqual(self.verify()['status'], 'fail')

    def test_wrong_version_and_changed_color_declaration_rejected(self):
        self.contract['version'] = 'unavailable-version'
        self.assertEqual(self.verify()['status'], 'fail')
        self.contract['version'] = PILLOW_VERSION
        with Image.open(self.preview) as im:
            im.save(self.preview)  # Remove sRGB metadata only, leaving RGBA unchanged.
        self.contract['outputs']['preview'] = self.desc(self.preview)
        self.assertEqual(self.verify()['status'], 'fail')

    def test_tampered_output_cannot_pass_even_with_updated_hash(self):
        with Image.open(self.preview) as im:
            im.putpixel((60, 60), (1, 2, 3, 255))
            self.save_png('preview.png', im)
        self.contract['outputs']['preview'] = self.desc(self.preview)
        self.assertEqual(self.verify()['status'], 'fail')

    def test_unrelated_sources_wrong_rounding_and_operation_order_rejected(self):
        original = copy.deepcopy(self.contract)
        self.contract['rounding_error_at_120'] = [0, 0]
        self.assertEqual(self.verify()['status'], 'fail')
        self.contract = copy.deepcopy(original)
        self.contract['chains']['preview']['operations'] = [{'op': 'resize', 'size': [120, 120]}]
        self.assertEqual(self.verify()['status'], 'fail')
        self.contract = original
        self.contract['chains']['preview']['source'] = self.desc(self.preview)
        self.assertEqual(self.verify()['status'], 'fail')

    def test_wrong_bounds_and_unsupported_operation_rejected(self):
        self.contract['allowed_bounds']['master'] = [102, 102, 922, 922]
        self.assertEqual(self.verify()['status'], 'fail')
        self.contract['allowed_bounds']['master'] = [0, 0, 1024, 1024]
        self.contract['chains']['master']['operations'] = [{'op': 'crop', 'box': [0, 0, 1024, 1024]}]
        self.assertEqual(self.verify()['status'], 'fail')

    def test_loss_is_counted_and_not_automatically_accepted(self):
        with Image.open(self.sm) as im:
            im.putpixel((0, 0), (10, 20, 30, 1))
            self.save_png('source-master.png', im)
            self.save_png('source-preview.png', im.resize((120, 120), Image.Resampling.LANCZOS))
        self.translate_file(self.sp, 'preview.png', -6)
        self.contract['outputs']['preview'] = self.desc(self.preview)
        self.contract['chains']['master']['source'] = self.desc(self.sm)
        self.contract['chains']['preview']['source'] = self.desc(self.sp)
        self.assertEqual(self.verify()['status'], 'fail')
        self.contract['chains']['master']['operations'][0]['expected_clipped'] = {'count': 1, 'max_alpha': 1, 'alpha_sum': 1}
        result = self.verify()
        self.assertTrue(result['replay_pass'])
        self.assertEqual(result['status'], 'unverified')
        self.assertEqual(result['results']['master']['clipping'][0]['count'], 1)

    def test_color_receipt_keeps_origin_and_uncertainty(self):
        for role, expected in [('original', 'pass'), ('working-master', 'unverified')]:
            capture, receipt = self.root / (role + '-capture.json'), self.root / (role + '-receipt.json')
            color_record.collect(self.sm, capture, role=role, note='Synthetic test only')
            color_record.audit(capture, self.sm, self.sp, receipt)
            result = color_record.verify(receipt, geometry=self.path)
            self.assertEqual(result['status'], expected)
            self.assertEqual(result['source_file']['path'], str(self.sm.resolve()))
            self.assertEqual(result['preview'], self.desc(self.preview))
        self.contract['chains']['master']['source'] = self.desc(self.master)
        self.write()
        self.assertEqual(color_record.verify(receipt, geometry=self.path)['status'], 'fail')

    def manifest(self):
        return {'schema_version': 1, 'batch_id': 'geometry-test', 'expected_ids': ['one'],
                'skill': self.desc(self.basis), 'rules': [{'id': 'one', 'file': self.desc(self.basis)}],
                'references': [{'id': 'R01', 'file': self.desc(self.sm), 'purpose': 'test', 'limits': 'test'}],
                'items': [{'id': 'one', 'name': 'test', 'version': 'one',
                           'requirements': {'action': 'test', 'subject': 'test', 'keep': ['pixels'], 'name_dependency': 'test'},
                           'control_card': self.desc(self.basis), 'master': self.desc(self.master), 'preview': self.desc(self.preview),
                           'geometry': self.desc(self.path),
                           'export': {'library': 'Pillow', 'version': PILLOW_VERSION, 'resample': 'lanczos',
                                      'complete_canvas': True, 'alpha_handling': 'geometry-contract', 'color_conversion': 'none'}}]}

    def test_batch_uses_task_contract_and_does_not_grant_delivery(self):
        m = self.manifest()
        path = self.root / 'manifest.json'
        common.write_json(path, m)
        result = check_batch.check_batch(path, delivery=False)
        row = result['items'][0]
        self.assertEqual(row['hard_specs']['status'], 'pass')
        self.assertEqual(row['hard_specs']['default']['status'], 'fail')
        self.assertEqual(row['derivation']['status'], 'pass')
        self.assertNotEqual(result['exit_code'], 0)
        before = common.snapshot(path, m)
        before_binding = common.item_binding(path.parent, m['items'][0], common.context(path, m, before), before)
        self.basis.write_text('changed confirmation')
        after = common.snapshot(path, m)
        self.assertIn(str(self.basis), common.changed_inputs(before, after))
        after_binding = common.item_binding(path.parent, m['items'][0], common.context(path, m, after), after)
        self.assertNotEqual(before_binding, after_binding)
        result = check_batch.check_batch(path, delivery=False)
        self.assertEqual(result['items'][0]['derivation']['status'], 'fail')

    def test_batch_rejects_conflicting_export_recipe_and_geometry_identity(self):
        path = self.root / 'manifest.json'
        m = self.manifest()
        m['items'][0]['export']['alpha_handling'] = 'Pillow RGBA resize'
        common.write_json(path, m)
        self.assertEqual(check_batch.check_batch(path, delivery=False)['items'][0]['derivation']['status'], 'fail')
        m = self.manifest()
        m['items'][0]['geometry']['sha256'] = '0' * 64
        common.write_json(path, m)
        self.assertEqual(check_batch.check_batch(path, delivery=False)['items'][0]['integrity']['status'], 'fail')


if __name__ == '__main__':
    unittest.main()
