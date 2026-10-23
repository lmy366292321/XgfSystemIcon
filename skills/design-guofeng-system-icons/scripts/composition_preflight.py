"""Pre-production composition checks and a reproducible planning board.

Validates bound resources and declared geometry, not aesthetic judgment or the
truth of a user's approval. Never edits source assets. No generation is invoked.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageChops
from geometry_contract import checked, verify_layout


def require(ok, message):
    if not ok:
        raise ValueError(message)


def nonempty(v):
    return isinstance(v, str) and bool(v.strip())


def desc(path):
    p=Path(path).resolve()
    return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}


def bound(d):
    require(isinstance(d,dict) and Path(d.get('path','')).is_absolute(),
            'Composition evidence must use absolute bound paths')
    return checked(Path.cwd(),d)[0]


def rect(v, label, limit=None):
    require(isinstance(v,list) and len(v)==4 and all(type(x) is int for x in v),label+': expected four integers')
    x,y,r,b=v
    require(x<r and y<b,label+': empty or reversed region')
    if limit:
        require(limit[0]<=x<r<=limit[2] and limit[1]<=y<b<=limit[3],label+': outside bounds')
    return v


def load_composition(c):
    require(isinstance(c,dict) and c.get('schema_version')==1,'Missing composition preflight schema_version=1')
    require(c.get('kind') in ('framed','standalone'),'Declare framed or standalone usage')
    require(c.get('status')=='ready','Composition is not ready; resolve actual component data first')
    bound(c.get('basis'))
    for key in ('placement_intent','occlusion_reason'):
        require(nonempty(c.get(key)),'Missing composition.'+key)
    subject=rect(c.get('subject_bounds'),'subject_bounds',[0,0,120,120])
    critical=c.get('critical_regions')
    require(isinstance(critical,list) and critical,'Plan critical recognition regions before generation')
    for region in critical:
        require(nonempty(region.get('purpose')),'Name each critical recognition feature')
        rect(region.get('bounds'),'critical region',subject)
    require(type(c.get('allow_noncritical_overlap')) is bool,'Explicitly set overlap policy')
    layouts=c.get('layouts')
    require(isinstance(layouts,list) and layouts,'Bind actual layout(s) before production')
    require(len({d.get('path') for d in layouts})==len(layouts),'Duplicate usage-state layouts')
    states=[]
    for d in layouts:
        p=bound(d);layout=json.loads(p.read_bytes())
        require(verify_layout(p)['status']=='pass','Invalid layout or UI offset')
        status=str(layout.get('status','')).lower()
        require(status and not any(x in status for x in ('example','tentative','unverified','placeholder')),
                'Example/tentative layout cannot authorize production')
        bounds=rect(layout.get('component_bounds'),'component_bounds')
        require(bounds[0]<=0 and bounds[1]<=0 and bounds[2]>=120 and bounds[3]>=120,
                'Component canvas must contain the full icon layer')
        require(bounds[2]-bounds[0]<=2048 and bounds[3]-bounds[1]<=2048,'Component canvas too large')
        components=layout.get('components')
        require(isinstance(components,list),'Missing layout components')
        require(len({x.get('id') for x in components})==len(components),'Duplicate component IDs')
        roles=c.get('component_roles',{})
        if c['kind']=='framed':
            require(set(roles)=={'frame','nameplate'} and roles['frame']!=roles['nameplate'],
                    'Bind distinct actual frame and nameplate IDs')
            require(set(roles.values())<={x.get('id') for x in components},'Actual frame/nameplate missing')
        else:
            require(not components and not roles,'Standalone usage cannot hide framed resources')
        loaded=[];occluder=Image.new('L',(120,120),0)
        for x in components:
            require(nonempty(x.get('id')),'Missing component ID')
            for key in ('width','height'):
                require(type(x.get(key)) is int and x[key]>0,'Invalid component dimensions')
            off=x.get('offset')
            require(isinstance(off,list) and len(off)==2 and all(type(v) is int for v in off),'Component offset must be integer pixels')
            require(type(x.get('z')) is int and x['z']!=1,'Use z<1 behind icon, z>1 in front')
            require(x.get('clipping') is False,'Unsupported component clipping; resolve before planning')
            rect([off[0],off[1],off[0]+x['width'],off[1]+x['height']],'component extent',bounds)
            fp,_=checked(p.parent,x['file'])
            with Image.open(fp) as im:
                require(im.size==(x['width'],x['height']),'Resource dimensions do not match layout')
                require(im.mode=='RGBA','Component resource must have explicit RGBA alpha')
                require(im.getchannel('A').getbbox() is not None,'Actual component cannot be fully transparent')
                im=im.copy()
            if x['id']==roles.get('frame'):require(x['z']<1,'Frame must be behind the icon')
            if x['id']==roles.get('nameplate'):require(x['z']>1,'Nameplate must be in front of the icon')
            if x['z']>1:
                layer=Image.new('L',(120,120));layer.paste(im.getchannel('A'),tuple(off))
                occluder=ImageChops.lighter(occluder,layer)
            loaded.append((x,im))
        regions=[r['bounds'] for r in critical] if c['allow_noncritical_overlap'] else [subject]
        for r in regions:
            require(occluder.crop(tuple(r)).getbbox() is None,
                    'Planned protected region intersects actual foreground alpha; revise composition before generation')
        states.append((layout,loaded))
    return states


def render(c):
    states=load_composition(c)
    w=max(s[0]['component_bounds'][2]-s[0]['component_bounds'][0] for s in states)
    h=max(s[0]['component_bounds'][3]-s[0]['component_bounds'][1] for s in states)
    board=Image.new('RGB',(max(620,w*4+80),(h*4+95)*len(states)),(244,237,225))
    draw=ImageDraw.Draw(board)
    for n,(layout,parts) in enumerate(states):
        l,t,r,b=layout['component_bounds'];tile=Image.new('RGBA',(r-l,b-t),(0,0,0,0))
        for x,im in sorted(parts,key=lambda v:v[0]['z']):
            if x['z']<1:tile.alpha_composite(im,(x['offset'][0]-l,x['offset'][1]-t))
        # Schematic footprint, never a substitute for generated artwork.
        region=Image.new('RGBA',tile.size);rd=ImageDraw.Draw(region)
        a=c['subject_bounds'];rd.rectangle((a[0]-l,a[1]-t,a[2]-l-1,a[3]-t-1),fill=(40,150,180,75),outline=(15,110,150,255))
        for q in c['critical_regions']:
            a=q['bounds'];rd.rectangle((a[0]-l,a[1]-t,a[2]-l-1,a[3]-t-1),outline=(170,50,130,255))
        tile.alpha_composite(region)
        for x,im in sorted(parts,key=lambda v:v[0]['z']):
            if x['z']>1:tile.alpha_composite(im,(x['offset'][0]-l,x['offset'][1]-t))
        y=n*(h*4+95)
        draw.text((12,y+8),f'STATE {n+1} - composition plan, NOT artwork - 4x view',fill=(40,40,40))
        big=tile.resize((tile.width*4,tile.height*4),Image.Resampling.NEAREST)
        board.paste(big,(12,y+30),big)
        draw.text((12,y+h*4+40),'Cyan: subject footprint. Magenta: critical features. Actual frame/plate.',fill=(40,40,40))
        draw.text((12,y+h*4+58),'Coordinates use the 120px icon layer. UI compensation remains zero.',fill=(40,40,40))
    return board


def validate(c):
    expected=render(c)
    p=bound(c.get('board'))
    with Image.open(p) as actual:
        require(actual.mode==expected.mode and actual.size==expected.size and actual.tobytes()==expected.tobytes(),
                'Planning board does not reproduce current component resources and regions')
    review=c.get('review',{})
    require(review.get('status')=='ready' and nonempty(review.get('reviewer')) and nonempty(review.get('observation')),
            'Actually review the planning board before production')
    at=datetime.fromisoformat(review.get('at','').replace('Z','+00:00'))
    require(at.tzinfo and at<=datetime.now(timezone.utc),'Invalid planning review time')
    return 'pass'


def instructions(c):
    load_composition(c)
    return ('\n\nCOMPOSITION CONTRACT (not a drawing of the UI):\n'
            'Output only the transparent icon; do not paint the frame, nameplate, labels or planning rectangles.\n'
            'The supplied planning board shows actual UI resources. Its diagram is enlarged 4x; coordinates below use a 120x120 full icon layer.\n'
            f'Subject footprint at 120px: {c["subject_bounds"]}; multiply coordinates by 1024/120 for the 1024 canvas.\n'
            f'Critical recognition regions: {json.dumps(c["critical_regions"],ensure_ascii=False)}.\n'
            f'Placement: {c["placement_intent"]}. Overlap policy: {c["occlusion_reason"]}.\n'
            'Keep transparent padding consistent with this plan. This is a generation target, not a guarantee; verify the returned pixels in the actual component.')


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('composition',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();c=json.loads(a.composition.read_bytes());im=render(c)
    require(not a.output.exists(),'Do not overwrite existing planning evidence')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('xb') as stream:im.save(stream,format='PNG')
    print(json.dumps(desc(a.output),ensure_ascii=False))


if __name__=='__main__':main()
