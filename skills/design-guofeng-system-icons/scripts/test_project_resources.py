import json
import shutil
from pathlib import Path
import unittest
from test_fixture_directory import WorkspaceTemporaryDirectory
import project_resources as pr
from composition_preflight import desc

class ProjectResourcesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=WorkspaceTemporaryDirectory(prefix='project-resources-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.project=self.root/'project';self.project.mkdir()
        self.marker=self.project/'.xgf-project.json'
        self.marker.write_text(json.dumps({'schema_version':1,'project_id':'xgf-entry-icons','usage':'entry-icon'}))
        self.skill=self.root/'skill'
        shutil.copytree(Path(__file__).resolve().parents[1]/'projects',self.skill/'projects')

    def test_fresh_nested_task_finds_and_uses_real_resources(self):
        context=self.project/'tasks'/'new';context.mkdir(parents=True)
        binding=pr.initialize(context/'output',context,self.skill)
        self.assertEqual(binding['project_id'],'xgf-entry-icons')
        c=json.loads((context/'output/inputs/composition.json').read_bytes())
        self.assertEqual(c['layouts'],[binding['layout']])
        self.assertEqual(c['status'],'unverified')
        self.assertIsNone(c['allow_noncritical_overlap'])
        for name,d in binding['resources'].items():
            self.assertEqual(d['sha256'],desc(self.skill/'projects/entry-icons'/name)['sha256'])

    def test_unknown_project_has_no_fallback(self):
        self.marker.write_text(json.dumps({'schema_version':1,'project_id':'another-project','usage':'entry-icon'}))
        with self.assertRaisesRegex(ValueError,'no fallback'):pr.initialize(self.project/'out',self.project,self.skill)
        self.assertFalse((self.project/'out').exists())

    def test_nested_git_boundary_does_not_inherit(self):
        p=self.project/'another';p.mkdir();(p/'.git').write_text('gitdir: unrelated')
        with self.assertRaisesRegex(ValueError,'No explicit project'):pr.discover(p,self.skill)

    def test_nearest_project_binding_wins(self):
        p=self.project/'another';p.mkdir();(p/'.xgf-project.json').write_text(json.dumps({'schema_version':1,'project_id':'another','usage':'entry-icon'}))
        with self.assertRaisesRegex(ValueError,'no fallback'):pr.discover(p,self.skill)

    def test_resource_change_blocks_before_task_creation(self):
        (self.skill/'projects/entry-icons/circle.png').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'resource changed'):pr.initialize(self.project/'out',self.project,self.skill)
        self.assertFalse((self.project/'out').exists())

    def test_existing_task_is_never_overwritten(self):
        p=self.project/'out';p.mkdir();(p/'keep').write_text('unchanged')
        with self.assertRaisesRegex(ValueError,'already exists'):pr.initialize(p,self.project,self.skill)
        self.assertEqual((p/'keep').read_text(),'unchanged')

    def test_output_in_another_project_is_not_silently_bound(self):
        p=self.root/'another';p.mkdir();(p/'.git').mkdir()
        with self.assertRaisesRegex(ValueError,'No explicit project'):
            pr.initialize(p/'out',self.project,self.skill)
        self.assertFalse((p/'out').exists())
