"""Read-only alpha/safety diagnosis. Never converts a diagnostic threshold into acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image


def inspect(path, margin=102):
    path = Path(path).resolve()
    with Image.open(path) as source:
        if source.mode != 'RGBA' or source.size != (1024, 1024):
            raise ValueError('Expected 1024x1024 RGBA master')
        alpha = source.getchannel('A')
    if not 0 <= margin < 512:
        raise ValueError('Invalid margin')
    outer = alpha.copy()
    outer.paste(0, (margin, margin, 1024-margin, 1024-margin))
    hist = outer.histogram()
    return {'file': {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()},
            'margin': margin, 'outside_nonzero': sum(hist[1:]),
            'outside_max_alpha': max((i for i in range(1,256) if hist[i]), default=0),
            'alpha_threshold_bboxes': {str(t): alpha.point(lambda v: 255 if v >= t else 0).getbbox()
                                      for t in (1,2,16,128,254)},
            'default_safety': 'pass' if not sum(hist[1:]) and alpha.getbbox() else 'fail',
            'scope': 'Diagnosis only; alpha thresholds do not relax the nonzero-alpha safety requirement'}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=inspect(args.image)
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False))
