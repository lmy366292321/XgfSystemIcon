"""Read-only, hash-bound PNG placement replay. No image files are written.

Default checks remain in check_icon. This optional contract verifies a confirmed
task boundary and a real transform chain, never infers visual/user acceptance.
"""
import hashlib
import io
import json
import math
from fractions import Fraction
from pathlib import Path

from PIL import Image, __version__ as PILLOW_VERSION


def require(ok, message):
    if not ok:
        raise ValueError(message)


def descriptors(value):
    if isinstance(value, dict):
        if 'path' in value and 'sha256' in value:
            yield value
        for child in value.values():
            yield from descriptors(child)
    elif isinstance(value, list):
        for child in value:
            yield from descriptors(child)


def checked(base, desc):
    require(isinstance(desc, dict), 'Expected file descriptor')
    require(isinstance(desc.get('path'), str) and desc['path'].strip(), 'Missing file path')
    p = (base / desc['path']).resolve()
    data = p.read_bytes()
    require(hashlib.sha256(data).hexdigest() == desc.get('sha256'), f'Changed binding: {p}')
    return p, data


def dependencies(path):
    """Include nested layout resources in batch snapshots and review freshness."""
    path = Path(path).resolve()
    record = json.loads(path.read_text(encoding='utf-8-sig'))
    result = {path}
    result.update((path.parent / d['path']).resolve() for d in descriptors(record))
    layout_path, data = checked(path.parent, record['layout'])
    layout = json.loads(data)
    result.update((layout_path.parent / d['path']).resolve() for d in descriptors(layout))
    return result


def layout_dependencies(path):
    path = Path(path).resolve()
    layout = json.loads(path.read_bytes())
    return {path} | {(path.parent / d['path']).resolve() for d in descriptors(layout)}


def verify_layout(path=None, *, geometry=None):
    """Bind the actual layout for every task; never apply its offset to PNG pixels."""
    if path is None and geometry is None:
        return {'status': 'unverified', 'reason': 'Missing bound layout; UI zero offset has not been checked'}
    try:
        if geometry is not None:
            gp = Path(geometry).resolve()
            recipe = json.loads(gp.read_bytes())
            bound_path, bound_data = checked(gp.parent, recipe['layout'])
            require(path is None or Path(path).resolve() == bound_path,
                    'Standalone layout conflicts with geometry layout')
            path = bound_path
        path = Path(path).resolve()
        data = path.read_bytes()
        if geometry is not None:
            require(data == bound_data, 'Geometry layout changed during check')
        layout = json.loads(data)
        inputs = list(descriptors(layout))
        for d in inputs:
            checked(path.parent, d)
        icon = layout['icon_layer']
        require(type(icon['width']) is int and type(icon['height']) is int
                and icon['width'] == 120 and icon['height'] == 120
                and type(icon['scale']) in (int, float) and icon['scale'] == 1,
                'Layout must keep the 120px icon layer at scale 1')
        require(vector(icon['offset'], 2, 'UI offset', integer=False) == [0, 0],
                'UI extra offset must be zero')
        require(path.read_bytes() == data, 'Layout changed during check')
        for d in inputs:
            checked(path.parent, d)
        return {'status': 'pass', 'reason': 'Bound 120px layout has scale 1 and UI extra offset zero',
                'file': {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest()},
                'ui_extra_offset': [0, 0], 'resource_count': len(inputs),
                'scope': 'Configuration and bound resources only; actual UI/occlusion needs visual and engine verification'}
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return {'status': 'fail', 'reason': str(exc)}


def rounded(value, method):
    """Round an exact rational, including negative values and half ties."""
    if method == 'nearest-half-away-from-zero':
        return (1 if value >= 0 else -1) * math.floor(abs(value) + Fraction(1, 2))
    if method == 'floor':
        return math.floor(value)
    if method == 'ceil':
        return math.ceil(value)
    if method == 'toward-zero':
        return math.trunc(value)
    raise ValueError('Missing or unsupported rounding_method')


def verify_translations(contract, moves):
    primary = contract['primary']
    require(primary in ('master', 'preview'), 'Missing primary delivery size')
    target = vector(contract.get('target_translation'), 2, 'primary target_translation')
    method = contract.get('rounding_method')
    sizes = {'master': 1024, 'preview': 120}
    other = 'master' if primary == 'preview' else 'preview'
    ideal = [Fraction(v * sizes[other], sizes[primary]) for v in target]
    expected = [rounded(v, method) for v in ideal]
    require(moves[primary] == target, 'Primary cumulative translation differs from target_translation')
    require(moves[other] == expected, 'Secondary cumulative translation is not the rounded primary target')
    error = [float(Fraction(moves['master'][i]) * Fraction(120, 1024) - moves['preview'][i]) for i in range(2)]
    if 'rounding_error_at_120' in contract:
        declared = vector(contract['rounding_error_at_120'], 2, 'rounding error', integer=False)
        require(all(abs(a - b) < 1e-9 for a, b in zip(declared, error)), 'Incorrect declared rounding error')
    return {'primary': primary, 'target_translation': target, 'rounding_method': method,
            'secondary': other, 'secondary_ideal_translation': [str(v) for v in ideal],
            'secondary_expected_translation': expected, 'actual_translations': moves,
            'rounding_error_at_120': error}


def vector(value, length, label, integer=True):
    require(isinstance(value, list) and len(value) == length, f'Invalid {label}')
    require(all(type(x) is int if integer else type(x) in (int, float) and math.isfinite(x)
                for x in value), f'Invalid numeric {label}')
    return value


def pixels_different(left, right):
    if left.size != right.size:
        return None
    a, b = left.tobytes(), right.tobytes()
    return sum(1 for i in range(0, len(a), 4)
               if (a[i + 3] or b[i + 3]) and a[i:i + 4] != b[i:i + 4])


def read_image(base, desc):
    import check_icon
    path, data = checked(base, desc)
    header, chunks = check_icon.read_png_chunks(data)
    require(header['bit_depth'] == 8 and header['color_type'] == 6,
            'Geometry replay requires 8-bit RGBA PNG')
    with Image.open(io.BytesIO(data)) as im:
        im.load()
        image = im.convert('RGBA')
    colors = [(k, v) for k, v in chunks if k in check_icon.COLOR_CHUNKS]
    return path, image, colors


def confirmed(base, value, label):
    require(isinstance(value, dict) and value.get('status') == 'confirmed', f'{label} is not confirmed')
    require(isinstance(value.get('scope'), str) and value['scope'].strip(), f'{label} needs scope')
    _, data = checked(base, value['basis'])
    require(bool(data.strip()), f'{label} basis is empty')


def replay(base, source, operations, resample):
    import check_icon
    _, image, colors = read_image(base, source)
    require(isinstance(operations, list), 'operations must be an ordered list')
    losses, displacement = [], [0, 0]
    for op in operations:
        require(isinstance(op, dict), 'Invalid operation')
        kind = op.get('op')
        if kind == 'resize':
            size = vector(op.get('size'), 2, 'resize size')
            require(size in ([1024, 1024], [120, 120]) and image.width == image.height,
                    'Only complete square canvas resize to 1024 or 120 is supported')
            factor = size[0] / image.width
            displacement = [v * factor for v in displacement]
            image = image.resize(tuple(size), check_icon.RESAMPLERS[resample],
                                 box=(0, 0, image.width, image.height), reducing_gap=None)
        elif kind == 'translate':
            dx, dy = vector(op.get('offset'), 2, 'integer translation')
            w, h = image.size
            require(abs(dx) <= w and abs(dy) <= h, 'Translation exceeds canvas')
            # Keep all retained RGBA samples; no mask blending or alpha threshold.
            out = Image.new('RGBA', image.size)
            x0, y0, x1, y1 = max(0, -dx), max(0, -dy), min(w, w - dx), min(h, h - dy)
            alpha = image.getchannel('A')
            lost = alpha.copy()
            if x1 > x0 and y1 > y0:
                out.paste(image.crop((x0, y0, x1, y1)), (x0 + dx, y0 + dy))
                lost.paste(0, (x0, y0, x1, y1))
            hist = lost.histogram()
            actual = {'count': sum(hist[1:]), 'max_alpha': max((i for i in range(1, 256) if hist[i]), default=0),
                      'alpha_sum': sum(i * n for i, n in enumerate(hist))}
            expected = op.get('expected_clipped', {'count': 0, 'max_alpha': 0, 'alpha_sum': 0})
            require(isinstance(expected, dict) and set(expected) == {'count', 'max_alpha', 'alpha_sum'}
                    and all(type(v) is int and v >= 0 for v in expected.values()), 'Invalid clipped-alpha declaration')
            require(actual == expected, f'Clipped alpha differs from declared values: {actual}')
            accepted = actual['count'] == 0
            if actual['count'] and op.get('loss_acceptance'):
                confirmed(base, op['loss_acceptance'], 'Pixel-loss exception')
                accepted = True
            losses.append({**actual, 'status': 'pass' if accepted else 'unverified'})
            image = out
            displacement = [displacement[0] + dx, displacement[1] + dy]
        else:
            raise ValueError(f'Unsupported geometry operation: {kind}')
    return image, colors, losses, displacement


def verify(path, master, preview):
    """Return defaults separately at caller; failure never falls back silently."""
    try:
        import check_icon
        path = Path(path).resolve()
        base = path.parent
        data = path.read_bytes()
        contract = json.loads(data)
        require(contract.get('schema_version') == 2 and contract.get('kind') == 'icon_geometry',
                'Expected geometry schema_version=2; migrate the record, never re-export the PNGs')
        require(contract.get('library') == 'Pillow' and contract.get('version') == PILLOW_VERSION,
                'Geometry replay Pillow version unavailable')
        resample = contract.get('resample')
        require(resample in check_icon.RESAMPLERS, 'Unsupported resampler')
        confirmed(base, contract.get('confirmation'), 'Layout exception')
        inputs = [(base, d) for d in descriptors(contract)]
        for directory, d in inputs:
            checked(directory, d)
        layout_path, layout_data = checked(base, contract['layout'])
        layout = json.loads(layout_data)
        inputs += [(layout_path.parent, d) for d in descriptors(layout)]
        for directory, d in inputs:
            checked(directory, d)
        layout_check = verify_layout(geometry=path)
        require(layout_check['status'] == 'pass', layout_check['reason'])
        chains, outputs = contract['chains'], contract['outputs']
        for role, current in [('master', master), ('preview', preview)]:
            require(current is not None, 'Geometry contract requires both output files')
            p, _ = checked(base, outputs[role])
            require(p == Path(current).resolve(), f'Geometry contract belongs to another {role}')
        mode = contract['mode']
        require(mode in ('master-to-preview', 'independent-translations'), 'Unsupported geometry mode')
        if mode == 'master-to-preview':
            require(contract.get('primary') == 'master', 'Direct export primary must be master')
            require(checked(base, chains['preview']['source'])[0] == Path(master).resolve(),
                    'Direct preview must start from delivered master')
            require(chains['preview']['operations'] == [{'op': 'resize', 'size': [120, 120]}],
                    'Direct preview must resize the whole delivered master once')
        else:
            require(contract.get('primary') in ('master', 'preview'), 'Missing primary delivery size')
            # Two unrelated pictures cannot be admitted just by claiming two chains.
            _, sm, sm_colors = read_image(base, chains['master']['source'])
            _, sp, sp_colors = read_image(base, chains['preview']['source'])
            require(sm.size == (1024, 1024) and sp.size == (120, 120), 'Independent source sizes must be 1024/120')
            require(pixels_different(sm.resize((120, 120), check_icon.RESAMPLERS[resample]), sp) == 0,
                    'Independent sources are not a matching complete-canvas pair')
            require(sm_colors == sp_colors, 'Independent source pair has different color declarations')
            for role in ('master', 'preview'):
                require(all(op.get('op') == 'translate' for op in chains[role]['operations']),
                        'Independent branches support integer translations only')
        results, actual_images, moves = {}, {}, {}
        for role, size in [('master', 1024), ('preview', 120)]:
            chain = chains[role]
            expected, colors, losses, move = replay(base, chain['source'], chain['operations'], resample)
            _, actual, output_colors = read_image(base, outputs[role])
            require(actual.size == (size, size) and expected.size == actual.size, f'Wrong {role} canvas')
            require(colors == output_colors, f'{role} geometry changed color declarations')
            bounds = vector(contract['allowed_bounds'][role], 4, role + ' allowed bounds')
            x0, y0, x1, y1 = bounds
            require(0 <= x0 < x1 <= size and 0 <= y0 < y1 <= size, 'Bounds outside canvas')
            bbox = actual.getchannel('A').getbbox()
            require(bbox is not None and actual.getchannel('A').getextrema()[0] == 0, 'Empty or opaque output')
            inside = x0 <= bbox[0] and y0 <= bbox[1] and bbox[2] <= x1 and bbox[3] <= y1
            difference = pixels_different(expected, actual)
            results[role] = {'different_pixels': difference, 'replay_pass': difference == 0,
                             'bounds_pass': inside, 'alpha_bbox': list(bbox), 'allowed_bounds': bounds,
                             'clipping': losses, 'color_declarations_preserved': True}
            actual_images[role], moves[role] = actual, move
        rounding, translation_check = None, None
        if mode == 'independent-translations':
            translation_check = verify_translations(contract, moves)
            rounding = translation_check['rounding_error_at_120']
        direct_difference = pixels_different(actual_images['master'].resize((120, 120), check_icon.RESAMPLERS[resample]),
                                             actual_images['preview'])
        # Detect changes during replay, including nested resource and confirmation files.
        require(path.read_bytes() == data, 'Geometry contract changed during replay')
        for directory, d in inputs:
            checked(directory, d)
        replay_pass = all(r['replay_pass'] for r in results.values())
        bounds_pass = all(r['bounds_pass'] for r in results.values())
        clipping_pass = all(v['status'] == 'pass' for r in results.values() for v in r['clipping'])
        status = 'fail' if not replay_pass or not bounds_pass else 'pass' if clipping_pass else 'unverified'
        return {'status': status, 'replay_pass': replay_pass, 'bounds_pass': bounds_pass,
                'clipping_status': 'pass' if clipping_pass else 'unverified', 'mode': mode,
                'primary': contract['primary'], 'rounding_error_at_120': rounding, 'results': results,
                'translation_check': translation_check, 'layout_check': layout_check,
                'direct_resize_different_pixels': direct_difference, 'ui_extra_offset': [0, 0],
                'record_sha256': hashlib.sha256(data).hexdigest(),
                'scope': 'Bound geometry and exact pixels only; confirmation basis is recorded, not independently authenticated; visual/color origin/engine acceptance remain separate'}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError,
            SyntaxError, Image.DecompressionBombError) as exc:
        return {'status': 'fail', 'replay_pass': False, 'bounds_pass': False, 'reason': str(exc)}
