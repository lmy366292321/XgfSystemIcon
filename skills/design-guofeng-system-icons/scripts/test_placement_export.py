"""Technical replay and overlap regressions; not visual acceptance."""
import json
from pathlib import Path
import unittest
from PIL import Image
import color_record as cr
import composition_preflight as cp
import test_color_record as color_tests
from test_composition_preflight import fixture


class PlacementExportTests(unittest.TestCase):
    setUp=color_tests.ColorRecordTests.setUp
    make=color_tests.ColorRecordTests.make
    collect=color_tests.ColorRecordTests.collect
    def placement(self, offset=(35, 20)):
        basis=self.root/'basis.txt';basis.write_text('Synthetic task-specific placement')
        path=self.root/'placement.json'
        path.write_text(json.dumps({'schema_version':1,'resize_side':900,'offset':list(offset),'basis':cr.descriptor(basis)}))
        return path

    def test_uniform_placement_exact_replay(self):
        self.make();self.collect();p=self.placement()
        result=cr.export(self.capture,self.root/'positioned',placement=p)
        self.assertEqual(result['status'],'pass')
        expected=Image.new('RGBA',(1024,1024));expected.paste(Image.open(self.source).resize((900,900),Image.Resampling.LANCZOS),(35,20))
        with Image.open(self.root/'positioned/master-1024.png') as actual:self.assertEqual(actual.tobytes(),expected.tobytes())
        p.write_text(p.read_text().replace('900','899'))
        self.assertEqual(cr.verify(self.root/'positioned/color-export.json')['status'],'fail')

    def test_clipping_opaque_subject_is_rejected(self):
        self.make();self.collect()
        with self.assertRaisesRegex(ValueError,'clip nontransparent'):
            cr.export(self.capture,self.root/'bad',placement=self.placement((-250,0)))

    def test_unknown_placement_never_becomes_verified(self):
        self.make(False);self.collect()
        r=cr.export(self.capture,self.root/'unknown',unknown='preserve',placement=self.placement())
        self.assertEqual(r['source_to_master']['status'],'pass')
        self.assertEqual(r['source']['status'],'unverified')
        self.assertEqual(r['status'],'unverified')

    def test_overlap_policy_affects_actual_request_not_only_prose(self):
        c=fixture(self.root/'composition');c['allow_noncritical_overlap']=True;c['subject_bounds'][3]=100
        self.assertIn('do not shrink the entire subject',cp.instructions(c))
        c['critical_regions'][0]['bounds'][3]=96
        with self.assertRaisesRegex(ValueError,'intersects'):cp.instructions(c)

    def test_unselected_overlap_is_blocked(self):
        c=fixture(self.root/'composition');c['allow_noncritical_overlap']=None
        with self.assertRaisesRegex(ValueError,'Explicitly set'):cp.load_composition(c)

if __name__=='__main__':unittest.main()
