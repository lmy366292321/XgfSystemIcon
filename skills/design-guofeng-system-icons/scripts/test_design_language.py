"""Behavioral contract tests. Synthetic fixtures cannot validate art methods."""
import copy
import unittest
import design_language as language
import review_workflow as workflow
import batch_common as common
import test_workflow


class DesignLanguageTests(unittest.TestCase):
    def setUp(self):
        self.w = test_workflow.WorkflowTests()
        self.w.setUp()
        self.addCleanup(self.w.doCleanups)

    def test_no_ui_neighbors_or_badge_inputs_needed_for_complete_delivery(self):
        result = self.w.complete()
        self.assertEqual(result['delivery']['status'], 'pass')
        self.assertEqual(result['delivery']['design_method_effectiveness'], 'unverified')

    def test_every_new_decision_is_required_before_start(self):
        self.w.prepare()
        for group, keys in {'purpose': ['branch', 'reason'], 'hierarchy': ['lightest', 'darkest', 'chroma_focus', 'temperature', 'focal_order'],
                            'shape': ['family', 'silhouette', 'perspective', 'reason'], 'gold': ['role', 'reason']}.items():
            for key in keys:
                plan = copy.deepcopy(self.w.plan)
                del plan['items'][0]['design_language'][group][key]
                with self.subTest(group=group, key=key), self.assertRaises(ValueError):
                    workflow.validate_plan(plan)

    def test_main_gold_and_front_view_allowed_with_reason(self):
        self.w.prepare()
        for branch in language.BRANCHES:
            plan = copy.deepcopy(self.w.plan)
            value = plan['items'][0]['design_language']
            value['purpose']['branch'] = branch
            value['gold']['role'] = 'body_color'
            value['shape']['perspective'] = 'front'
            workflow.validate_plan(plan)

    def test_unvalidated_material_can_be_declared_without_fake_example(self):
        value = test_workflow.design_fixture()
        value['materials'][0].update(material='bamboo', example_ids=[], transfer_limit='No matching formal bamboo example; candidate')
        language.validate(value, ['R01'])
        value['materials'][0]['example_ids'] = ['R99']
        with self.assertRaises(ValueError): language.validate(value, ['R01'])

    def test_method_pass_cannot_be_claimed_in_plan(self):
        value = test_workflow.design_fixture(); value['method_validation'] = 'pass'
        with self.assertRaisesRegex(ValueError, 'effectiveness'): language.validate(value, ['R01'])

    def test_missing_subcheck_blocks_final_delivery(self):
        self.w.complete()
        for dimension, keys in language.CHECKS.items():
            for key in keys:
                saved = copy.deepcopy(self.w.m)
                del self.w.m['items'][0]['visual_recheck']['items'][dimension]['design_checks'][key]
                with self.subTest(key=key): self.assertNotEqual(self.w.final()['delivery']['status'], 'pass')
                self.w.m = saved

    def test_missing_subcheck_cannot_show_primary_visual_pass(self):
        self.w.complete()
        del self.w.m['items'][0]['visual_review']['items']['materials']['design_checks']['gold_role']
        report = self.w.final()
        self.assertEqual(report['items'][0]['visual']['status'], 'unverified')
        self.assertEqual(report['exit_code'], 1)

    def test_optional_ui_language_source_is_bound_when_used(self):
        self.w.prepare()
        source = self.w.root/'ui-language.md'; source.write_text('Synthetic UI language', encoding='utf-8')
        self.w.plan['items'][0]['design_language']['ui_bridge'] = dict(
            basis='Synthetic UI language only', adopt='value hierarchy', exclude='background', sources=[self.w.desc(source)])
        workflow.validate_plan(self.w.plan)
        source.write_text('changed language', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'changed'): workflow.validate_plan(self.w.plan)

    def test_unverified_or_failed_subcheck_cannot_hide_under_dimension_pass(self):
        self.w.prepare(); self.w.add_provenance(); self.w.advance('files'); self.w.build_sheets(); self.w.reviews()
        self.w.m['items'][0]['visual_review']['items']['palette']['design_checks']['value_chroma']['status'] = 'unverified'
        result = self.w.advance('visual')
        self.assertEqual(result['events'][-1]['status'], 'unverified')
        self.w.reviews(second=True); self.w.advance('recheck')
        self.assertNotEqual(self.w.final()['delivery']['status'], 'pass')

    def test_old_plan_not_silently_promoted(self):
        self.w.prepare(); self.w.plan['schema_version'] = 1
        with self.assertRaisesRegex(ValueError, 'schema_version=2'): workflow.validate_plan(self.w.plan)

    def test_prepare_generates_sealable_plan_and_unverified_prompts(self):
        self.w.prepare()
        choices = self.w.root/'choices.json'
        common.write_json(choices, {'items': [{'id': i['id'], 'design_language': i['design_language']} for i in self.w.plan['items']]})
        out = self.w.root/'prepared'
        result = language.prepare(self.w.plan_path, choices, out)
        self.assertEqual(result['resource_acceptance'], 'not_run')
        self.assertEqual(result['method_effectiveness'], 'unverified')
        workflow.start(out/'design-plan.json', self.w.root/'new-records'/'plan.json', 'fixture')
        template = common.read_json(out/'design-review-template.json')
        self.assertEqual(template['01']['palette']['design_checks']['value_chroma']['status'], 'unverified')
        with self.assertRaises(ValueError): language.prepare(self.w.plan_path, choices, out)

    def test_draft_never_defaults_a_hue_or_purpose_and_cannot_seal(self):
        self.w.prepare(); path = self.w.root/'draft.json'
        language.draft(self.w.plan_path, path)
        values = common.read_json(path)['items']
        self.assertEqual(values[0]['design_language']['purpose']['branch'], '')
        with self.assertRaises(ValueError): language.prepare(self.w.plan_path, path, self.w.root/'invalid')
        self.assertFalse((self.w.root/'invalid').exists())

    def test_reference_mutation_invalidates_prepared_plan(self):
        self.w.prepare()
        p = self.w.plan['references'][0]['file']['path']
        from pathlib import Path
        Path(p).write_bytes(b'changed synthetic reference')
        with self.assertRaisesRegex(ValueError, 'changed'): workflow.validate_plan(self.w.plan)
