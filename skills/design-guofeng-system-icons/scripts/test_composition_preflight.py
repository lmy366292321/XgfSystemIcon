"""Synthetic geometry/sequence tests; never art acceptance."""
import copy
import json
import unittest
from pathlib import Path
from datetime import datetime, timezone
from PIL import Image
from test_fixture_directory import WorkspaceTemporaryDirectory
import composition_preflight as cp


def fixture(root, standalone=False):
    root.mkdir(parents=True,exist_ok=True)
    basis=root/'basis.txt';basis.write_text('Synthetic fixture only',encoding='utf-8')
    parts=[]
    if not standalone:
        for name,size,offset,z in [('circle',(100,100),[10,10],0),('plate',(120,20),[0,90],2)]:
            p=root/(name+'.png');Image.new('RGBA',size,(200,180,180,255)).save(p)
            parts.append({'id':name,'width':size[0],'height':size[1],'offset':offset,'z':z,'clipping':False,'file':cp.desc(p)})
    layout={'status':'synthetic declared usage','component_bounds':[0,0,120,120],
            'icon_layer':{'width':120,'height':120,'scale':1,'offset':[0,0]},'components':parts}
    p=root/'layout.json';p.write_text(json.dumps(layout),encoding='utf-8')
    c={'schema_version':1,'kind':'standalone' if standalone else 'framed','status':'ready',
       'basis':cp.desc(basis),'placement_intent':'synthetic upper placement','occlusion_reason':'no overlap',
       'subject_bounds':[20,15,100,85],'critical_regions':[{'purpose':'recognition','bounds':[30,25,90,75]}],
       'allow_noncritical_overlap':False,'layouts':[cp.desc(p)],
       'component_roles':{} if standalone else {'frame':'circle','nameplate':'plate'}}
    board=root/'board.png';cp.render(c).save(board);c['board']=cp.desc(board)
    c['review']={'status':'ready','reviewer':'synthetic','observation':'synthetic test only','at':datetime.now(timezone.utc).isoformat()}
    return c


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=WorkspaceTemporaryDirectory(prefix='composition-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.c=fixture(self.root/'inputs')

    def test_real_resources_and_board_required(self):
        self.assertEqual(cp.validate(self.c),'pass')
        for key in ('layouts','board','basis','critical_regions','review'):
            bad=copy.deepcopy(self.c);bad.pop(key)
            with self.subTest(key=key),self.assertRaises((ValueError,KeyError)):cp.validate(bad)

    def test_declared_critical_overlap_blocks_before_generation(self):
        c=copy.deepcopy(self.c);c['subject_bounds']=[20,15,100,105]
        with self.assertRaisesRegex(ValueError,'intersects'):cp.validate(c)
        c['allow_noncritical_overlap']=True
        cp.load_composition(c)  # Only critical regions protected under an explicit overlap policy.
        c['critical_regions'][0]['bounds']=[30,25,90,100]
        with self.assertRaisesRegex(ValueError,'intersects'):cp.load_composition(c)

    def test_stale_board_even_with_updated_hash_is_blocked(self):
        c=copy.deepcopy(self.c);p=Path(c['board']['path'])
        with Image.open(p) as im:
            im.putpixel((0,0),(0,0,0));im.save(self.root/'altered.png')
        c['board']=cp.desc(self.root/'altered.png')
        with self.assertRaisesRegex(ValueError,'does not reproduce'):cp.validate(c)

    def test_changed_nested_resource_is_blocked(self):
        (self.root/'inputs/plate.png').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Invalid layout'):cp.validate(self.c)

    def test_missing_plate_placeholder_and_ui_offset_block(self):
        for field,value in [('components',[]),('status','example-only'),('icon_layer',{'width':120,'height':120,'scale':1,'offset':[0,5]})]:
            c=copy.deepcopy(self.c);p=Path(c['layouts'][0]['path']);layout=json.loads(p.read_bytes());layout[field]=value
            q=self.root/(field+'.json');q.write_text(json.dumps(layout),encoding='utf-8');c['layouts']=[cp.desc(q)]
            with self.subTest(field=field),self.assertRaises(ValueError):cp.validate(c)

    def test_standalone_is_explicit_not_global_circle_requirement(self):
        c=fixture(self.root/'standalone',True);self.assertEqual(cp.validate(c),'pass')
        c=copy.deepcopy(self.c);c['kind']='standalone';c['component_roles']={}
        with self.assertRaisesRegex(ValueError,'cannot hide'):cp.validate(c)


if __name__=='__main__':unittest.main()
