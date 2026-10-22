"""Layout and rounding gates; only isolated synthetic fixtures are written."""
import copy
import contextlib
from fractions import Fraction
import io
import json
import unittest

import batch_common as common
import check_icon
import check_batch
import geometry_contract as gc
import test_batch
import test_geometry_contract


class LayoutTests(unittest.TestCase):
    setUp = test_batch.BatchTests.setUp
    srgb = staticmethod(test_batch.BatchTests.srgb)
    make_png = test_batch.BatchTests.make_png
    desc = test_batch.BatchTests.desc
    save = test_batch.BatchTests.save
    run_check = test_batch.BatchTests.run_check
    add_reviews = test_batch.BatchTests.add_reviews

    def test_default_layout_pass_keeps_existing_pngs_unchanged(self):
        item = self.m['items'][0]
        paths = [self.inputs / 'master-0.png', self.inputs / 'preview-0.png']
        before = [p.read_bytes() for p in paths]
        result = check_icon.check_files(*paths, layout=self.layout)
        self.assertTrue(result['overall_check_pass'])
        self.assertTrue(result['hard_spec_pass'])
        self.assertTrue(result['derivation_check']['derivation_pass'])
        self.assertEqual(result['layout_check']['file'], item['layout'])
        self.assertEqual(before, [p.read_bytes() for p in paths])

    def test_missing_layout_blocks_cli_and_batch_but_keeps_file_diagnostics(self):
        paths = [str(self.inputs / 'master-0.png'), str(self.inputs / 'preview-0.png')]
        result = check_icon.check_files(*paths)
        self.assertTrue(result['file_check_pass'])
        self.assertFalse(result['overall_check_pass'])
        self.assertEqual(result['layout_check']['status'], 'unverified')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(check_icon.main([paths[0], '--preview', paths[1]]), 1)
            self.assertEqual(check_icon.main([paths[0], '--preview', paths[1], '--layout', str(self.layout)]), 0)
        self.add_reviews()
        del self.m['items'][0]['layout']
        result = self.run_check()
        self.assertEqual(result['items'][0]['layout']['status'], 'unverified')
        self.assertEqual(result['items'][0]['visual']['freshness'], 'stale')
        self.assertNotEqual(result['machine_status'], 'pass')

    def test_nonzero_offset_and_invalid_layer_cannot_pass_even_with_fresh_hash(self):
        for field, value in [('offset', [0, -6]), ('offset', [1, 0]), ('scale', 0.9), ('width', 119), ('offset', [False, 0])]:
            with self.subTest(field=field, value=value):
                layout = {'icon_layer': {'width': 120, 'height': 120, 'scale': 1, 'offset': [0, 0]}}
                layout['icon_layer'][field] = value
                common.write_json(self.layout, layout)
                for item in self.m['items']:
                    item['layout'] = self.desc(self.layout)
                report = self.run_check()
                self.assertEqual(report['summary']['layout'], {'fail': 2})
                self.assertEqual(report['summary']['hard_specs'], {'pass': 2})
                self.assertEqual(report['machine_status'], 'fail')

    def test_layout_identity_and_nested_resources_expire_reviews(self):
        resource = self.root / 'frame.txt'
        resource.write_text('fixture version one')
        layout = common.read_json(self.layout)
        layout['frame'] = {'path': 'frame.txt', 'sha256': self.desc(resource)['sha256']}
        common.write_json(self.layout, layout)
        for item in self.m['items']:
            item['layout'] = self.desc(self.layout)
        self.add_reviews()
        before = self.run_check()
        self.assertEqual(before['machine_status'], 'pass')
        resource.write_text('fixture version two')
        after = self.run_check()
        self.assertEqual(after['summary']['layout'], {'fail': 2})
        self.assertEqual(after['items'][0]['visual']['freshness'], 'stale')
        self.assertNotEqual(before['items'][0]['binding_for_review'], after['items'][0]['binding_for_review'])
        self.assertIn(str(resource), after['input_snapshot'])
        self.m['items'][0]['layout']['sha256'] = '0' * 64
        self.assertEqual(self.run_check()['items'][0]['integrity']['status'], 'fail')


class TranslationTests(unittest.TestCase):
    setUp = test_geometry_contract.GeometryTests.setUp
    desc = test_geometry_contract.GeometryTests.desc
    save_png = test_geometry_contract.GeometryTests.save_png
    translate_file = test_geometry_contract.GeometryTests.translate_file
    write = test_geometry_contract.GeometryTests.write
    verify = test_geometry_contract.GeometryTests.verify

    def test_self_declared_six_pixel_error_cannot_authorize_unmoved_master(self):
        self.contract['chains']['master']['operations'] = []
        self.contract['outputs']['master'] = self.desc(self.sm)
        self.contract['rounding_error_at_120'] = [0, 6]
        self.master = self.sm
        result = self.verify()
        self.assertEqual(result['status'], 'fail')
        self.assertIn('rounded primary target', result['reason'])

    def test_target_and_rounding_are_required_and_primary_is_enforced(self):
        baseline = copy.deepcopy(self.contract)
        for field in ('target_translation', 'rounding_method'):
            self.contract = copy.deepcopy(baseline)
            del self.contract[field]
            self.assertEqual(self.verify()['status'], 'fail')
        for patch in ({'target_translation': [0, -5]}, {'rounding_method': 'floor'},
                      {'schema_version': 1}, {'rounding_method': 'bankers'},
                      {'target_translation': [0, -6.0]}):
            self.contract = {**copy.deepcopy(baseline), **patch}
            self.assertEqual(self.verify()['status'], 'fail')

    def test_primary_master_and_multi_operation_cumulative_moves(self):
        self.contract.update(primary='master', target_translation=[0, -51])
        self.assertEqual(self.verify()['status'], 'pass')
        self.contract.update(primary='preview', target_translation=[0, -6])
        self.contract['chains']['master']['operations'] = [{'op': 'translate', 'offset': [0, -20]}, {'op': 'translate', 'offset': [0, -31]}]
        result = self.verify()
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['translation_check']['secondary_ideal_translation'], ['0', '-256/5'])
        self.assertEqual(result['translation_check']['secondary_expected_translation'], [0, -51])

    def test_explicit_rounding_methods_for_signed_half_ties(self):
        expected = {'nearest-half-away-from-zero': [8, -8], 'floor': [7, -8],
                    'ceil': [8, -7], 'toward-zero': [7, -7]}
        for method, values in expected.items():
            self.assertEqual([gc.rounded(Fraction(15, 2), method), gc.rounded(Fraction(-15, 2), method)], values)
            contract = {'primary': 'master', 'target_translation': [64, -64], 'rounding_method': method}
            self.assertEqual(gc.verify_translations(contract, {'master': [64, -64], 'preview': values})['secondary_expected_translation'], values)
        with self.assertRaises(ValueError):
            gc.verify_translations({'primary': 'master', 'target_translation': [64, -64], 'rounding_method': 'nearest-half-away-from-zero'},
                                   {'master': [64, -64], 'preview': [7, -7]})

    def test_explicit_layout_cannot_conflict_with_geometry_layout(self):
        alternate = self.root / 'other-layout.json'
        alternate.write_bytes(self.layout.read_bytes())
        self.assertFalse(check_icon.check_files(self.master, self.preview, geometry=self.path, layout=alternate)['overall_check_pass'])
        self.assertTrue(check_icon.check_files(self.master, self.preview, geometry=self.path, layout=self.layout)['overall_check_pass'])


if __name__ == '__main__':
    unittest.main()
