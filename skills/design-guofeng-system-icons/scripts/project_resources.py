"""Resolve explicitly bound project resources, never infer a global component default."""
import json
import shutil
from pathlib import Path
from composition_preflight import desc, require
from geometry_contract import verify_layout


def discover(context,skill=None):
    context=Path(context).resolve()
    require(context.is_dir(),'Task context must be an existing directory')
    skill=Path(skill or Path(__file__).resolve().parents[1]).resolve()
    marker=None
    for directory in (context,*context.parents):
        p=directory/'.xgf-project.json'
        if p.is_file():marker=p;break
        if (directory/'.git').exists():break
    require(marker is not None,'No explicit project binding found; do not reuse another project or ask for component PNGs before checking project identity')
    binding=json.loads(marker.read_bytes())
    require(binding.get('schema_version')==1 and binding.get('usage')=='entry-icon','Unsupported project binding or usage')
    require(binding.get('project_id')=='xgf-entry-icons','No registered component profile for this project; no fallback')
    bundle=skill/'projects/entry-icons'
    profile=json.loads((bundle/'profile.json').read_bytes())
    require(profile.get('project_id')==binding['project_id'] and profile.get('usage')==binding['usage'],'Profile/project mismatch')
    require({'circle.png','nameplate.png','layout.json','basis.md','reuse-authorization.txt'}<=set(profile['files']),'Incomplete component profile')
    for name,sha in profile['files'].items():
        p=(bundle/name).resolve()
        require(p.parent==bundle,'Unsafe component path')
        require(desc(p)['sha256']==sha,'Registered resource changed: '+name)
    layout=bundle/profile['layout']
    require(verify_layout(layout)['status']=='pass','Registered layout invalid')
    return {'marker':desc(marker),'profile':desc(bundle/'profile.json'),'project_id':binding['project_id'],
            'bundle':str(bundle),'layout':desc(layout),'component_roles':profile['component_roles']}


def initialize(task_root,context=None,skill=None):
    task_root=Path(task_root).resolve()
    resolved=discover(context or Path.cwd(),skill)
    require(not task_root.exists(),'Task directory already exists; never overwrite a task')
    ancestor=task_root.parent
    while not ancestor.exists():ancestor=ancestor.parent
    destination=discover(ancestor,skill)
    require(destination['marker']==resolved['marker'],'Task destination belongs to another project binding')
    profile=json.loads(Path(resolved['profile']['path']).read_bytes())
    # Validate everything before creating the task. All resource copies keep original bytes.
    resources=task_root/'resources';resources.mkdir(parents=True)
    for name in profile['files']:shutil.copyfile(Path(resolved['bundle'])/name,resources/name)
    inputs=task_root/'inputs';inputs.mkdir()
    binding={**resolved,'layout':desc(resources/profile['layout']),
             'resources':{name:desc(resources/name) for name in profile['files']},'status':'resolved; no user component question needed'}
    (inputs/'component-binding.json').write_text(json.dumps(binding,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    composition={'schema_version':1,'kind':'framed','status':'unverified',
        'basis':desc(resources/'reuse-authorization.txt'),'layouts':[binding['layout']],
        'component_roles':resolved['component_roles'],'placement_intent':'','occlusion_reason':'',
        'subject_bounds':[],'critical_regions':[],'allow_noncritical_overlap':False,
        'quality_goals':{'basis_kind':'task_reasoning','basis':desc(resources/'reuse-authorization.txt'),
                         'occupancy_target':'','optical_balance':'','verification_method':''}}
    (inputs/'composition.json').write_text(json.dumps(composition,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return binding


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('task_root',type=Path);p.add_argument('--context',type=Path,default=Path.cwd())
    a=p.parse_args()
    try:print(json.dumps(initialize(a.task_root,a.context),ensure_ascii=False,indent=2))
    except (OSError,ValueError,KeyError,TypeError) as e:
        print(json.dumps({'status':'blocked','reason':str(e)},ensure_ascii=False));raise SystemExit(2)
