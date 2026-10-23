"""Evidence completeness for occupancy/optical balance, never an aesthetic score."""
from PIL import Image
from composition_preflight import bound, require, nonempty


def validate_goals(c):
    goals=c.get('quality_goals',{})
    for key in ('occupancy_target','optical_balance','verification_method'):
        require(nonempty(goals.get(key)), 'Missing composition quality goal: '+key)
    require(goals.get('basis_kind') in ('reference','task_reasoning'),'Declare occupancy reference or task reasoning')
    bound(goals.get('basis'))
    return goals


def prompt(c):
    goals=validate_goals(c)
    return ('\nCOMPOSITION QUALITY TARGETS:\n'
            'Occupancy: '+goals['occupancy_target']+'\n'
            'Optical balance: '+goals['optical_balance']+'\n'
            'Verification: '+goals['verification_method']+'\n'
            'Do not shrink the subject merely to avoid occlusion. A bounding-box center or alpha centroid is not proof of optical balance.\n')


def validate_review(review,c):
    validate_goals(c)
    require(isinstance(review,dict),'Missing actual component quality review')
    require(review.get('same_size') is True,'Compare actual components at the same display scale')
    require(review.get('layouts')==c['layouts'],'Component review must bind all planned layout states')
    evidence=bound(review.get('evidence'))
    with Image.open(evidence) as im:
        im.verify()
    statuses=[]
    for key in ('occupancy','optical_balance'):
        row=review.get(key,{})
        require(row.get('status') in ('pass','fail','unverified'),'Missing component check: '+key)
        require(nonempty(row.get('observation')) and nonempty(row.get('location')),'Missing specific observation: '+key)
        statuses.append(row['status'])
    return 'fail' if 'fail' in statuses else 'unverified' if 'unverified' in statuses else 'pass'
