"""Workflow behavior with explicitly synthetic pixels/reviews; not art acceptance."""
import copy
from datetime import datetime, timezone
from pathlib import Path
import unittest

import batch_common as common
import check_batch
import build_qa_sheet
import build_relation_sheet
import review_workflow as workflow
import test_batch
import color_record


class WorkflowTests(unittest.TestCase):
    setUp = test_batch.BatchTests.setUp
    srgb = staticmethod(test_batch.BatchTests.srgb)
    make_png = test_batch.BatchTests.make_png
    desc = test_batch.BatchTests.desc
    save = test_batch.BatchTests.save

    def now(self):
        return datetime.now(timezone.utc).isoformat()

    def record_path(self, stage):
        self.counter += 1
        return self.root / 'records' / f'{self.counter}-{stage}.json'

    def prepare(self, mode='review', colors=None):
        self.counter = 0
        self.plan_path = self.root / 'plan' / 'plan.json'
        self.plan_path.parent.mkdir()
        self.plan = {
            'schema_version': 1, 'mode': mode, 'batch_id': self.m['batch_id'],
            'batch_palette_reason': 'Synthetic test only; deliberate repeated blue is allowed with reason.',
            'references': copy.deepcopy(self.m['references']), 'items': []}
        for n, item in enumerate(self.m['items']):
            self.plan['items'].append({
                'id': item['id'], 'control_card': item['control_card'],
                'palette': {'dominant': (colors or ['blue', 'blue'])[n], 'secondary': [], 'accent': [],
                            'reason': 'Fixture semantics', 'color_source': 'Synthetic authored pixels',
                            'hierarchy': 'One continuous main block', 'preserve_existing': mode == 'review'},
                'style_reference_ids': ['R01'], 'color_reference_ids': [],
                'generation_inputs': [] if mode == 'review' else [{
                    'role': 'style', 'file': self.m['references'][0]['file'],
                    'purpose': 'fixture shape only', 'limits': 'do not inherit color'}]})
        if mode != 'review':
            from test_composition_preflight import fixture
            self.plan['schema_version'] = 2
            composition = fixture(self.root / 'composition', standalone=True)
            for item, target in zip(self.plan['items'], self.m['items']):
                item['composition'] = copy.deepcopy(composition)
                item['brief'] = 'Synthetic workflow test only'
                card = self.root / 'plan' / ('control-' + item['id'] + '.json')
                common.write_json(card, {'composition': item['composition']})
                item['control_card'] = self.desc(card)
                target['control_card'] = self.desc(card)
                target['layout'] = composition['layouts'][0]
        common.write_json(self.plan_path, self.plan)
        self.m['design_plan'] = self.desc(self.plan_path)
        self.m['comparison_groups'] = [{'id': 'pair', 'purpose': 'Compare two fixtures',
                                       'members': [{'role': 'candidate', 'id': i['id']} for i in self.m['items']]}]
        self.save()
        self.latest = self.record_path('plan')
        workflow.start(self.plan_path, self.latest, 'fixture author')

    def advance(self, stage, evidence=None):
        self.save()
        output = self.record_path(stage)
        record = workflow.advance(self.latest, self.manifest, stage, output, 'fixture reviewer', evidence)
        self.latest = output
        return record

    def add_provenance(self):
        self.save()
        report = check_batch.check_batch(self.manifest, delivery=False)
        self.evidence_dir = self.root / 'evidence'
        self.evidence_dir.mkdir(exist_ok=True)
        p = self.evidence_dir / 'source.md'
        p.write_text('Synthetic RGB authored in sRGB for tests, no real asset claim.', encoding='utf-8')
        for item, row in zip(self.m['items'], report['items']):
            item['color_provenance'] = {'status': 'pass', 'statement': 'Synthetic sRGB source',
                'reviewer': 'fixture', 'reviewed_at': self.now(), 'bound': row['binding_for_review'], 'evidence': self.desc(p)}
            capture = self.evidence_dir / ('color-capture-' + item['id'] + '.json')
            receipt = self.evidence_dir / ('color-export-' + item['id'] + '.json')
            color_record.collect(item['master']['path'], capture, role='original', note='Synthetic sRGB fixture')
            color_record.audit(capture, item['master']['path'], item['preview']['path'], receipt)
            item['color_record'] = self.desc(receipt)

    def build_sheets(self):
        self.save()
        build_qa_sheet.build_sheets(self.manifest, self.root / 'qa')
        build_relation_sheet.build_relations(self.manifest, self.root / 'relations')
        self.m['qa_index'] = self.desc(self.root / 'qa' / 'sheet-index.json')
        self.m['relation_index'] = self.desc(self.root / 'relations' / 'relation-index.json')

    def reviews(self, second=False, palette_status='pass'):
        self.save()
        report = check_batch.check_batch(self.manifest, delivery=False)
        bound = workflow.current_binding(self.manifest, self.m, report, self.plan)
        p = self.evidence_dir / ('second.md' if second else 'first.md')
        p.write_text('Synthetic second observations' if second else 'Synthetic first observations', encoding='utf-8')
        pages = common.read_json(self.root / 'qa' / 'sheet-index.json')['pages']
        sheets = [self.desc(self.root / 'qa' / x['path']) for x in pages]
        for item, row in zip(self.m['items'], report['items']):
            review = {'reviewer': 'fixture reviewer', 'reviewed_at': self.now(), 'bound': row['binding_for_review'],
                      'evidence': self.desc(p), 'sheets': sheets,
                      'items': {k: {'status': 'pass', 'observation': 'Synthetic observation', 'location': 'Whole tile'} for k in common.VISUAL_FIELDS}}
            review['items']['palette']['status'] = palette_status
            if second:
                review['method'] = 'same_reviewer_second_pass'
            item['visual_recheck' if second else 'visual_review'] = review
        self.m['palette_recheck' if second else 'palette_review'] = {
            'bound': bound, 'reviewer': 'fixture reviewer', 'reviewed_at': self.now(), 'status': palette_status,
            'observation': 'Two blue synthetic blocks', 'location': 'Candidate row',
            'repetition_reason': 'Deliberate synthetic family', 'hierarchy': 'Main blocks visible',
            'item_ids': self.m['expected_ids'], 'evidence': self.desc(p),
            'sheets': [{'background': page['background'], 'file': d} for page, d in zip(pages, sheets)],
            'relations': {'pair': {'status': 'pass', 'observation': 'Fixture comparison', 'location': 'Both cells'}}}
        self.save()

    def complete(self, palette_status='pass'):
        self.prepare()
        self.add_provenance()
        self.advance('files')
        self.build_sheets()
        self.reviews(palette_status=palette_status)
        self.advance('visual')
        self.reviews(second=True, palette_status=palette_status)
        self.advance('recheck')
        return self.final()

    def final(self):
        self.m['workflow'] = self.desc(self.latest)
        self.save()
        return check_batch.check_batch(self.manifest)

    def test_complete_review_route_passes_without_claiming_generation_or_user_acceptance(self):
        report = self.complete()
        self.assertEqual(report['delivery']['status'], 'pass', report['delivery'])
        self.assertEqual(report['exit_code'], 0)
        self.assertFalse(report['delivery']['automated_visual_judgment'])
        self.assertNotIn('generated', [e['stage'] for e in common.read_json(self.latest)['events']])

    def test_missing_workflow_never_passes_despite_machine_pass(self):
        self.complete()
        del self.m['workflow']
        self.save()
        report = check_batch.check_batch(self.manifest)
        self.assertEqual(report['machine_status'], 'pass')
        self.assertEqual(report['exit_code'], 1)

    def test_complete_route_loses_acceptance_when_layout_removed(self):
        self.assertEqual(self.complete()['exit_code'], 0)
        del self.m['items'][0]['layout']
        report = self.final()
        self.assertEqual(report['items'][0]['layout']['status'], 'unverified')
        self.assertNotEqual(report['delivery']['status'], 'pass')

    def test_complete_route_loses_acceptance_when_ui_offset_reintroduced(self):
        self.assertEqual(self.complete()['exit_code'], 0)
        layout = common.read_json(self.layout)
        layout['icon_layer']['offset'] = [0, -6]
        common.write_json(self.layout, layout)
        for item in self.m['items']:
            item['layout'] = self.desc(self.layout)
        report = self.final()
        self.assertEqual(report['summary']['layout'], {'fail': 2})
        self.assertNotEqual(report['delivery']['status'], 'pass')

    def test_second_review_missing_never_passes(self):
        self.complete()
        del self.m['items'][1]['visual_recheck']
        self.assertEqual(self.final()['exit_code'], 1)

    def test_missing_single_dimension_is_blocked(self):
        self.complete()
        del self.m['items'][0]['visual_review']['items']['palette']
        self.assertNotEqual(self.final()['delivery']['status'], 'pass')

    def test_palette_failure_blocks_otherwise_complete_delivery(self):
        report = self.complete('fail')
        self.assertEqual(report['machine_status'], 'pass')
        self.assertEqual(report['delivery']['status'], 'fail')
        self.assertEqual(report['exit_code'], 1)

    def test_skip_stage_is_refused(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, 'skip'):
            self.advance('recheck')

    def test_all_same_color_is_allowed_when_reviewed_not_mechanically_rejected(self):
        self.assertEqual(self.complete()['delivery']['status'], 'pass')

    def test_plan_missing_palette_cannot_start(self):
        self.prepare()
        del self.plan['items'][0]['palette']['reason']
        common.write_json(self.plan_path, self.plan)
        with self.assertRaisesRegex(ValueError, 'palette.reason'):
            workflow.start(self.plan_path, self.record_path('bad'), 'fixture')

    def test_plan_changed_after_review_invalidates_delivery(self):
        self.complete()
        self.plan['items'][0]['palette']['dominant'] = 'violet'
        common.write_json(self.plan_path, self.plan)
        self.m['design_plan'] = self.desc(self.plan_path)
        self.assertNotEqual(self.final()['delivery']['status'], 'pass')

    def test_copied_first_review_cannot_be_second_pass(self):
        self.complete()
        self.m['items'][0]['visual_recheck'] = copy.deepcopy(self.m['items'][0]['visual_review'])
        self.m['items'][0]['visual_recheck']['method'] = 'same_reviewer_second_pass'
        self.assertNotEqual(self.final()['delivery']['status'], 'pass')

    def test_same_reviewer_cannot_claim_independence(self):
        self.complete()
        self.m['items'][0]['visual_recheck']['method'] = 'independent'
        with self.assertRaisesRegex(ValueError, 'independence'):
            self.advance('recheck')

    def test_renamed_copy_of_first_observations_is_not_second_review(self):
        self.complete()
        p = self.evidence_dir / 'renamed-first.md'
        p.write_bytes((self.evidence_dir / 'first.md').read_bytes())
        self.m['items'][0]['visual_recheck']['evidence'] = self.desc(p)
        with self.assertRaisesRegex(ValueError, 'identical observation'):
            self.advance('recheck')

    def test_whitespace_observation_is_incomplete(self):
        self.complete()
        self.m['items'][0]['visual_review']['items']['structure']['observation'] = '  '
        self.assertNotEqual(self.final()['delivery']['status'], 'pass')

    def test_background_file_form_is_accepted_for_item_sheets(self):
        self.complete()
        for item in self.m['items']:
            item['visual_review']['sheets'] = [
                {'background': bg, 'file': d} for bg, d in zip(('#F4EDE1', '#293139'), item['visual_review']['sheets'])]
        # An edited review invalidates its recorded stage until explicitly re-recorded.
        self.assertNotEqual(self.final()['delivery']['status'], 'pass')
        self.advance('visual')
        self.reviews(second=True)
        self.advance('recheck')
        self.assertEqual(self.final()['delivery']['status'], 'pass')

    def test_bad_sheet_shape_keeps_machine_facts_and_reports_field(self):
        self.complete()
        self.m['items'][0]['visual_review']['sheets'] = [{'background': '#F4EDE1'}]
        report = self.final()
        self.assertEqual(report['items'][0]['hard_specs']['status'], 'pass')
        self.assertIn('visual_review.sheets[0]', report['items'][0]['visual']['reason'])
        self.assertEqual(report['exit_code'], 1)

    def test_missing_dark_sheet_or_relation_observation_blocks(self):
        self.complete()
        self.m['palette_review']['sheets'] = self.m['palette_review']['sheets'][:1]
        self.assertNotEqual(self.final()['delivery']['status'], 'pass')
        del self.m['palette_recheck']['relations']['pair']
        self.assertNotEqual(self.final()['delivery']['status'], 'pass')

    def test_sheet_pixels_changed_even_with_new_file_hash_are_rejected(self):
        self.complete()
        p = self.root / 'qa' / 'qa-light-01.png'
        self.make_png(p, 20)
        self.assertNotEqual(self.final()['delivery']['status'], 'pass')

    def test_production_cannot_skip_generated_and_rejects_candidate_as_style(self):
        self.prepare('create')
        with self.assertRaisesRegex(ValueError, 'skip'):
            self.advance('files')
        self.plan['items'][0]['generation_inputs'][0]['file'] = self.m['items'][0]['master']
        with self.assertRaisesRegex(ValueError, 'official references'):
            workflow.validate_plan(self.plan)

    def test_production_route_runs_with_receipts_and_detects_input_substitution(self):
        self.prepare('create')
        for item in self.m['items']:
            item['source'] = item['master']
        logs = self.root / 'calls'
        logs.mkdir()
        log = {'calls': []}
        for item, plan_item in zip(self.m['items'], self.plan['items']):
            request_path = self.root / 'requests' / (item['id'] + '.json')
            request = workflow.prepare_request(self.latest, item['id'], request_path, 'synthetic')
            receipt = logs / (item['id'] + '-receipt.json')
            common.write_json(receipt, {'arguments': request['arguments'], 'scope': 'Synthetic, no real call'})
            log['calls'].append({'item_id': item['id'], 'at': self.now(), 'tool': 'synthetic-test-only',
                                'outcome': 'success', 'inputs': plan_item['generation_inputs'],
                                'request': self.desc(request_path), 'arguments': request['arguments'],
                                'receipt': self.desc(receipt), 'output': item['master']})
        log_path = logs / 'calls.json'
        common.write_json(log_path, log)
        self.add_provenance()
        self.advance('generated', log_path)
        self.advance('files')
        self.build_sheets()
        self.reviews()
        self.advance('visual')
        self.reviews(second=True)
        self.advance('recheck')
        self.assertEqual(self.final()['delivery']['status'], 'pass')
        log['calls'][0]['inputs'][0]['file'] = self.m['items'][0]['master']
        common.write_json(log_path, log)
        self.assertNotEqual(self.final()['delivery']['status'], 'pass')

    def test_old_resource_confirmation_cannot_override_missing_workflow(self):
        self.prepare()
        self.m['items'][0]['other_states'] = {'user_acceptance': 'pass'}
        self.assertNotEqual(self.final()['delivery']['status'], 'pass')

    def test_prepared_composition_cannot_be_omitted_from_actual_call(self):
        self.prepare('create')
        request_path = self.root / 'requests' / '01.json'
        request = workflow.prepare_request(self.latest, '01', request_path, 'fixture')
        receipt = self.root / 'receipts' / '01.json'
        receipt.parent.mkdir()
        common.write_json(receipt, {'arguments': request['arguments']})
        call = {'item_id': '01', 'at': self.now(), 'request': self.desc(request_path),
                'arguments': copy.deepcopy(request['arguments']), 'receipt': self.desc(receipt)}
        plan_time = workflow.timestamp(common.read_json(self.latest)['events'][0]['at'])
        workflow.validate_generation_request(self.plan, call, plan_time)
        call['arguments']['referenced_image_paths'].pop()
        with self.assertRaisesRegex(ValueError, 'Actual arguments'):
            workflow.validate_generation_request(self.plan, call, plan_time)
        call['arguments'] = request['arguments']
        common.write_json(receipt, {'arguments': {}})
        call['receipt'] = self.desc(receipt)
        with self.assertRaisesRegex(ValueError, 'Receipt arguments'):
            workflow.validate_generation_request(self.plan, call, plan_time)

    def test_legacy_production_start_and_review_request_blocked(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, 'Only production v2'):
            workflow.prepare_request(self.latest, '01', self.root / 'requests' / '01.json', 'fixture')
        self.plan['mode'] = 'create'
        common.write_json(self.plan_path, self.plan)
        with self.assertRaisesRegex(ValueError, 'requires v2'):
            workflow.start(self.plan_path, self.root / 'new-records' / 'plan.json', 'fixture')

    def test_production_output_cannot_switch_layout_after_planning(self):
        self.prepare('create')
        report = {'items': [{'binding_for_review': 'synthetic'} for _ in self.m['items']], 'errors': []}
        workflow.current_binding(self.manifest, self.m, report, self.plan)
        self.m['items'][0]['layout'] = self.desc(self.layout)
        with self.assertRaisesRegex(ValueError, 'Output layout differs'):
            workflow.current_binding(self.manifest, self.m, report, self.plan)

    def test_removing_color_record_never_passes_complete_visual_review(self):
        self.complete()
        del self.m['items'][0]['color_record']
        report = self.final()
        self.assertEqual(report['items'][0]['color_provenance']['status'], 'unverified')
        self.assertNotEqual(report['delivery']['status'], 'pass')

    def test_new_color_receipt_invalidates_previous_stage_binding(self):
        self.complete()
        item = self.m['items'][0]
        receipt = common.read_json(item['color_record']['path'])
        receipt['scope'] += '; revised description'
        path = self.root / 'replacement-color.json'
        common.write_json(path, receipt)
        item['color_record'] = self.desc(path)
        report = self.final()
        self.assertEqual(report['items'][0]['color_provenance']['status'], 'pass')
        self.assertNotEqual(report['delivery']['status'], 'pass')


if __name__ == '__main__':
    unittest.main()
