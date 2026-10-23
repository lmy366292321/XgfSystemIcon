import copy
import unittest
from pathlib import Path
from test_fixture_directory import WorkspaceTemporaryDirectory
from test_composition_preflight import fixture
import composition_quality as q
import composition_preflight as cp

class QualityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=WorkspaceTemporaryDirectory(prefix='quality-');self.addCleanup(self.tmp.cleanup)
        self.c=fixture(Path(self.tmp.name)/'input')
        self.c['quality_goals']={'basis_kind':'task_reasoning','basis':self.c['basis'],
            'occupancy_target':'Match the task-specific visual mass',
            'optical_balance':'Assess unequal light/dark masses, not bounding box center',
            'verification_method':'Same-size actual component comparison'}
        self.review={'same_size':True,'layouts':self.c['layouts'],'evidence':self.c['board'],
            'occupancy':{'status':'pass','observation':'synthetic','location':'tile'},
            'optical_balance':{'status':'pass','observation':'synthetic','location':'tile'}}

    def test_missing_quality_goals_block(self):
        for key in self.c['quality_goals']:
            c=copy.deepcopy(self.c);del c['quality_goals'][key]
            with self.subTest(key=key),self.assertRaises(ValueError):q.validate_goals(c)

    def test_targets_reach_generation_prompt_without_default_transform(self):
        text=cp.instructions(self.c)
        self.assertIn(self.c['quality_goals']['occupancy_target'],text)
        self.assertIn(self.c['quality_goals']['optical_balance'],text)
        self.assertNotIn('16 percent',text)

    def test_both_checks_required_and_failure_is_preserved(self):
        self.assertEqual(q.validate_review(self.review,self.c),'pass')
        for key in ('occupancy','optical_balance'):
            r=copy.deepcopy(self.review);del r[key]
            with self.assertRaises(ValueError):q.validate_review(r,self.c)
            r=copy.deepcopy(self.review);r[key]['status']='fail'
            self.assertEqual(q.validate_review(r,self.c),'fail')

    def test_component_scale_layout_and_pixels_are_bound(self):
        for key,value in [('same_size',False),('layouts',[])]:
            r=copy.deepcopy(self.review);r[key]=value
            with self.assertRaises(ValueError):q.validate_review(r,self.c)
        Path(self.c['board']['path']).write_bytes(b'changed')
        with self.assertRaises(ValueError):q.validate_review(self.review,self.c)

    def test_unverified_does_not_become_visual_pass(self):
        self.review['optical_balance']['status']='unverified'
        self.assertEqual(q.validate_review(self.review,self.c),'unverified')
