#!/usr/bin/env python3
"""Read-only PNG canvas/alpha/safe-area checks; requires Pillow."""
import argparse
import json
from pathlib import Path
from PIL import Image


def inspect(path, size, margin):
    with Image.open(path) as im:
        errors = []
        if im.format != 'PNG':
            errors.append('Expected PNG')
        if im.mode != 'RGBA':
            errors.append('Expected 8-bit RGBA')
        if im.size != (size, size):
            errors.append(f'Expected {size}x{size}')
        alpha = im.convert('RGBA').getchannel('A')
        bbox = alpha.getbbox()  # ALL nonzero alpha, no threshold hiding noise.
        margins = None
        if bbox is None:
            errors.append('Empty transparent image')
        else:
            w, h = im.size
            margins = [bbox[0], bbox[1], w - bbox[2], h - bbox[3]]
            if min(margins) < margin:
                errors.append(f'Expected at least {margin}px transparent margin')
        if alpha.getextrema()[0] != 0:
            errors.append('No fully transparent pixels')
        return {'file': str(path), 'format': im.format, 'mode': im.mode,
                'size': list(im.size), 'alpha_bbox': bbox,
                'margins_ltrb': margins, 'hard_spec_pass': not errors,
                'errors': errors, 'visual_review': 'not_checked',
                'srgb_profile': 'not_checked', 'engine_acceptance': 'not_checked'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--preview', type=Path)
    args = parser.parse_args()
    results = []
    for path, size, margin in [(args.image, 1024, 102)] + ([(args.preview, 120, 0)] if args.preview else []):
        # Safe margin is specified on the 1024 master; report preview margins without inventing a new gate.
        try:
            results.append(inspect(path, size, margin))
        except (OSError, ValueError) as exc:
            results.append({'file': str(path), 'hard_spec_pass': False, 'errors': [str(exc)]})
    print(json.dumps({'results': results, 'preview_margin_note': '102px safe margin applies to 1024 master only; preview margins are reported, not separately gated'}, ensure_ascii=False, indent=2))
    return 0 if all(r['hard_spec_pass'] for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
