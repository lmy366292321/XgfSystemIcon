#!/usr/bin/env python3
"""Prepare bound design choices and unverified review prompts; never judge artwork."""
import argparse
import copy
import json
from pathlib import Path
from batch_common import read_json

BRANCHES = ('daily', 'collection', 'celebration', 'narrative', 'custom')
FAMILIES = ('flat', 'vessel', 'open_group', 'living', 'custom')
PERSPECTIVES = ('front', 'slight_tilt', 'three_quarter', 'anatomy', 'custom')
GOLD_ROLES = ('none', 'body_color', 'ornament', 'metal', 'mixed')
CHECKS = {'semantics': ('purpose',), 'structure': ('silhouette', 'perspective'),
          'materials': ('material_behavior', 'gold_role'), 'palette': ('value_chroma',)}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def skeleton():
    return {'purpose': {'branch': '', 'reason': ''},
            'hierarchy': {k: '' for k in ('lightest', 'darkest', 'chroma_focus', 'temperature', 'focal_order')},
            'shape': {'family': '', 'silhouette': '', 'perspective': '', 'reason': ''},
            'materials': [{'subject': '', 'material': '', 'behavior': '', 'example_ids': [], 'transfer_limit': ''}],
            'gold': {'role': '', 'reason': ''},
            'method_validation': 'unverified'}


def validate(value, ref_ids):
    require(isinstance(value, dict), 'Missing design_language; prepare a schema 2 plan')
    for group, keys in {'purpose': ('reason',),
                        'hierarchy': ('lightest', 'darkest', 'chroma_focus', 'temperature', 'focal_order'),
                        'shape': ('silhouette', 'reason'), 'gold': ('reason',)}.items():
        row = value.get(group, {})
        require(isinstance(row, dict), f'Invalid design_language.{group}')
        for key in keys:
            require(text(row.get(key)), f'Missing design_language.{group}.{key}')
    for group, field, allowed in [('purpose', 'branch', BRANCHES), ('shape', 'family', FAMILIES),
                                  ('shape', 'perspective', PERSPECTIVES), ('gold', 'role', GOLD_ROLES)]:
        require(value[group].get(field) in allowed, f'Invalid design_language.{group}.{field}')
    materials = value.get('materials')
    require(isinstance(materials, list) and materials, 'Missing material behavior')
    for row in materials:
        require(isinstance(row, dict), 'Invalid material row')
        for key in ('subject', 'material', 'behavior', 'transfer_limit'):
            require(text(row.get(key)), f'Missing material.{key}')
        ids = row.get('example_ids')
        require(isinstance(ids, list) and all(isinstance(x, str) for x in ids)
                and len(set(ids)) == len(ids) and set(ids) <= set(ref_ids), 'Material examples must bind selected references')
        # Empty examples are allowed: the transfer_limit must describe the missing analogue.
        # Text cannot establish that the proposed material has been validated.
    require(value.get('method_validation') == 'unverified',
            'Design method effectiveness remains unverified; resource review cannot promote it')
    if 'ui_bridge' in value:
        bridge = value['ui_bridge']
        require(isinstance(bridge, dict) and all(text(bridge.get(k)) for k in ('basis', 'adopt', 'exclude')),
                'Optional ui_bridge needs basis/adopt/exclude')


def review_status(review):
    statuses = []
    for dimension, checks in CHECKS.items():
        entries = review.get('items', {}).get(dimension, {}).get('design_checks', {})
        for key in checks:
            row = entries.get(key, {})
            require(row.get('status') in ('pass', 'fail', 'unverified')
                    and text(row.get('observation')) and text(row.get('location')),
                    f'Missing design review: {dimension}/{key}')
            statuses.append(row['status'])
    return statuses


def review_template(plan):
    return {i['id']: {d: {'design_checks': {k: {'status': 'unverified', 'observation': '', 'location': ''}
                for k in keys}} for d, keys in CHECKS.items()} for i in plan['items']}


def output_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        if isinstance(value, str):
            stream.write(value)
        else:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')


def draft(plan_path, output):
    plan = read_json(plan_path)
    output_new(output, {'items': [{'id': i['id'], 'design_language': skeleton()} for i in plan['items']]})


def prepare(plan_path, choices_path, output_dir):
    from review_workflow import validate_plan
    plan = copy.deepcopy(read_json(plan_path))
    choices = read_json(choices_path)['items']
    require([x['id'] for x in choices] == [i['id'] for i in plan['items']], 'Choice coverage/order differs')
    for item, choice in zip(plan['items'], choices):
        item['design_language'] = choice['design_language']
    plan['schema_version'] = 2
    validate_plan(plan)
    output = Path(output_dir).resolve()
    require(not output.exists(), 'Output directory exists; choose a new task directory')
    output.mkdir(parents=True)
    output_new(output / 'design-plan.json', plan)
    output_new(output / 'design-review-template.json', review_template(plan))
    rows = ['# 本次图标设计选择', '', '结构已验证；设计方法效果未验证。空白审核模板不得作为通过证据。', '']
    for item in plan['items']:
        rows += [f"## {item['id']}", '', '```json', json.dumps(item['design_language'], ensure_ascii=False, indent=2), '```', '']
    output_new(output / 'design-brief.md', '\n'.join(rows))
    return {'plan': str(output / 'design-plan.json'), 'structure_status': 'pass',
            'method_effectiveness': 'unverified', 'resource_acceptance': 'not_run'}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest='command', required=True)
    d = commands.add_parser('draft'); d.add_argument('plan', type=Path); d.add_argument('--output', type=Path, required=True)
    s = commands.add_parser('prepare'); s.add_argument('plan', type=Path); s.add_argument('--choices', type=Path, required=True)
    s.add_argument('--output-dir', type=Path, required=True)
    args = p.parse_args(argv)
    try:
        result = draft(args.plan, args.output) if args.command == 'draft' else prepare(args.plan, args.choices, args.output_dir)
        print(json.dumps(result or {'draft': str(args.output), 'status': 'unverified'}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(json.dumps({'status': 'error', 'error': str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
