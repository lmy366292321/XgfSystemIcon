"""Read-only replay of an archived real trial, never invokes generation or accepts art."""
from pathlib import Path
import copy
import hashlib
import json
from PIL import Image, ImageChops
import composition_preflight as cp


def replay(case):
    case=Path(case).resolve()
    files=json.loads((case/'files.json').read_bytes())
    for name,expected in files.items():
        p=(case/name).resolve()
        cp.require(p.parent==case,'Evidence path outside case directory')
        cp.require(hashlib.sha256(p.read_bytes()).hexdigest()==expected,'Archived evidence changed: '+name)
    c=json.loads((case/'composition-portable.json').read_bytes())
    for d in [c['basis'],c['board'],*c['layouts']]:d['path']=str((case/d['path']).resolve())
    cp.validate(c)
    negative=[]
    for name,key in [('missing board','board'),('missing actual layout','layouts')]:
        bad=copy.deepcopy(c);bad.pop(key)
        try:cp.validate(bad)
        except ValueError:negative.append(name)
        else:raise ValueError('Negative unexpectedly passed: '+name)
    bad=copy.deepcopy(c);bad['subject_bounds']=[19,13,102,110]
    try:cp.validate(bad)
    except ValueError:negative.append('actual nameplate overlap')
    else:raise ValueError('Overlap unexpectedly passed')
    with Image.open(case/'trial-source.png') as source:
        preview=source.convert('RGBA').resize((120,120),Image.Resampling.LANCZOS)
    with Image.open(case/'trial-120.png') as saved:
        cp.require(saved.tobytes()==preview.tobytes(),'Trial was repositioned or changed after generation')
    a=preview.getchannel('A');mask=Image.new('L',(120,120),0)
    for x,im in cp.load_composition(c)[0][1]:
        if x['z']>1:
            m=Image.new('L',(120,120));m.paste(im.getchannel('A'),tuple(x['offset']));mask=ImageChops.lighter(mask,m)
    intersection=ImageChops.multiply(a,mask).getbbox()
    facts=json.loads((case/'result-facts.json').read_bytes())
    cp.require(list(a.getbbox())==facts['preview_bbox_alpha_gt0'],'Trial alpha bounds changed')
    cp.require((list(intersection) if intersection else None)==facts['overlap_alpha_product_bbox'],'Trial overlap changed')
    return {'process_replay':'pass','negative_cases_blocked':negative,'trial_pixel_bounds':'fail',
            'preview_alpha_bounds':list(a.getbbox()),'planned_subject_bounds':c['subject_bounds'],
            'actual_foreground_overlap':intersection,'art_acceptance':'not claimed; faint edges exceed the plan',
            'scope':'One archived real trial; no new tool call, no general success-rate claim.'}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('case',nargs='?',type=Path,default=Path(__file__).resolve().parents[1]/'references/cases/composition-preflight-20261023')
    print(json.dumps(replay(p.parse_args().case),ensure_ascii=False,indent=2))
