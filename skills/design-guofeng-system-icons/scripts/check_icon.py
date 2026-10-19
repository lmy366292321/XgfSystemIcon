#!/usr/bin/env python3
"""Read-only icon PNG, color-declaration and exact preview checks; requires Pillow."""
import argparse
import hashlib
import io
import json
import struct
import zlib
from pathlib import Path
from PIL import Image, __version__ as PILLOW_VERSION


PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
SRGB_CHRM = (31270, 32900, 64000, 33000, 30000, 60000, 15000, 6000)
RESAMPLERS = {'lanczos': Image.Resampling.LANCZOS,
              'bicubic': Image.Resampling.BICUBIC,
              'bilinear': Image.Resampling.BILINEAR}
COLOR_CHUNKS = (b'sRGB', b'iCCP', b'gAMA', b'cHRM', b'cICP')


def read_png_chunks(data):
    """Read source IHDR/chunks without relying on Pillow's decoded mode."""
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError('Expected PNG signature')
    chunks = []
    offset = len(PNG_SIGNATURE)
    while offset < len(data):
        if len(data) - offset < 12:
            raise ValueError('Truncated PNG chunk')
        length, kind = struct.unpack_from('>I4s', data, offset)
        end = offset + 12 + length
        if end > len(data):
            raise ValueError('Truncated PNG chunk payload')
        payload = data[offset + 8:end - 4]
        stored_crc = struct.unpack_from('>I', data, end - 4)[0]
        if zlib.crc32(kind + payload) & 0xffffffff != stored_crc:
            raise ValueError(f'Invalid PNG CRC for {kind!r}')
        chunks.append((kind, payload))
        offset = end
        if kind == b'IEND':
            if payload or offset != len(data):
                raise ValueError('Invalid IEND or trailing data')
            break
    if not chunks or chunks[0][0] != b'IHDR' or len(chunks[0][1]) != 13:
        raise ValueError('Expected first PNG chunk to be a 13-byte IHDR')
    if chunks[-1][0] != b'IEND' or not any(k == b'IDAT' for k, _ in chunks):
        raise ValueError('PNG is missing IDAT or IEND')
    if sum(k == b'IHDR' for k, _ in chunks) != 1:
        raise ValueError('Duplicate IHDR')
    width, height, depth, color, compression, filtering, interlace = struct.unpack(
        '>IIBBBBB', chunks[0][1])
    if compression != 0 or filtering != 0 or interlace not in (0, 1):
        raise ValueError('Invalid PNG IHDR compression, filter or interlace method')
    return {'width': width, 'height': height, 'bit_depth': depth, 'color_type': color,
            'compression_method': compression, 'filter_method': filtering,
            'interlace_method': interlace}, chunks


def inspect_color(chunks):
    """Check declarations, not pixel provenance or ICC profile equivalence.

    PNG 3 sections 11.3.2.2–6: https://www.w3.org/TR/png-3/
    An ICC profile's name/description is never evidence of sRGB equivalence.
    """
    found = {kind: [] for kind in COLOR_CHUNKS}
    invalid, conflicts = [], []
    image_data_seen = False
    for kind, payload in chunks:
        if kind in (b'PLTE', b'IDAT'):
            image_data_seen = True
        if kind in found:
            found[kind].append(payload)
            if image_data_seen:
                invalid.append(f'{kind.decode()} must precede PLTE and IDAT')
    for kind, values in found.items():
        if len(values) > 1:
            invalid.append(f'Duplicate {kind.decode()} chunk')
    metadata = {'chunks_present': [k.decode() for k, v in found.items() if v]}
    srgb = found[b'sRGB']
    if srgb:
        if len(srgb[0]) != 1 or srgb[0][0] not in range(4):
            invalid.append('sRGB must contain one rendering-intent byte from 0 to 3')
        else:
            metadata['srgb_rendering_intent'] = srgb[0][0]
    gamma = found[b'gAMA']
    if gamma:
        if len(gamma[0]) != 4:
            invalid.append('gAMA must contain four bytes')
        else:
            metadata['gamma_times_100000'] = struct.unpack('>I', gamma[0])[0]
            if metadata['gamma_times_100000'] == 0:
                invalid.append('gAMA must be nonzero')
            elif srgb and metadata['gamma_times_100000'] != 45455:
                conflicts.append('gAMA disagrees with the sRGB compatibility value 45455')
    chrm = found[b'cHRM']
    if chrm:
        if len(chrm[0]) != 32:
            invalid.append('cHRM must contain 32 bytes')
        else:
            metadata['chromaticities_times_100000'] = list(struct.unpack('>8I', chrm[0]))
            if srgb and tuple(metadata['chromaticities_times_100000']) != SRGB_CHRM:
                conflicts.append('cHRM disagrees with the sRGB compatibility chromaticities')
    icc = found[b'iCCP']
    if icc:
        metadata['icc_validation'] = 'not_checked'
        if srgb:
            conflicts.append('sRGB and iCCP coexist; ICC equivalence is not validated')
    cicp = found[b'cICP']
    if cicp:
        metadata['cicp_validation'] = 'not_checked'
        if len(cicp[0]) != 4:
            invalid.append('cICP must contain four bytes')
    if invalid:
        status = 'invalid_metadata'
    elif conflicts:
        status = 'conflicting'
    elif icc:
        status = 'icc_unverified'
    elif cicp:
        # cICP has higher precedence than sRGB; do not silently ignore it.
        status = 'metadata_unverified'
    elif srgb:
        status = 'declared_srgb'
    else:
        status = 'missing'
    return {'status': status, 'srgb_check_pass': status == 'declared_srgb',
            'metadata': metadata, 'issues': invalid + conflicts,
            'scope': 'Metadata declaration only; pixel colorimetry is not independently verified',
            'strict_mode_limit': 'Requires a valid PNG sRGB chunk without conflicts; ICC-only '
                                 'and cICP declarations are not validated by this checker'}


def load_and_inspect(path, size, margin):
    """Read once: hashes, metadata and decoded pixels refer to the same snapshot."""
    result = {'file': str(path), 'sha256': None, 'hard_spec_pass': False, 'errors': [],
              'color_metadata': {'status': 'not_checked', 'srgb_check_pass': False},
              'visual_review': 'not_checked', 'engine_acceptance': 'not_checked'}
    try:
        data = Path(path).read_bytes()
        result['sha256'] = hashlib.sha256(data).hexdigest()
        header, chunks = read_png_chunks(data)
        result.update(format='PNG', png_header=header, color_metadata=inspect_color(chunks))
        errors = result['errors']
        if header['bit_depth'] != 8 or header['color_type'] != 6:
            errors.append('Expected source PNG IHDR bit depth 8 and color type 6 (RGBA)')
        if (header['width'], header['height']) != (size, size):
            errors.append(f'Expected {size}x{size}')
        with Image.open(io.BytesIO(data)) as im:
            result.update(mode=im.mode, size=list(im.size))
            im.load()
            rgba = im.convert('RGBA')
        # Down-converted 16-bit alpha cannot prove the source's safe margins.
        if header['bit_depth'] == 8 and header['color_type'] == 6:
            alpha = rgba.getchannel('A')
            bbox = alpha.getbbox()  # All nonzero alpha counts, including 1.
            margins = None
            if bbox is None:
                errors.append('Empty transparent image')
            else:
                w, h = rgba.size
                margins = [bbox[0], bbox[1], w - bbox[2], h - bbox[3]]
                if min(margins) < margin:
                    errors.append(f'Expected at least {margin}px transparent margin')
            if alpha.getextrema()[0] != 0:
                errors.append('No fully transparent pixels')
            result.update(alpha_bbox=bbox, margins_ltrb=margins, alpha_check='checked')
        else:
            result['alpha_check'] = 'not_checked_unsupported_source_format'
        result['hard_spec_pass'] = not errors
        return result, rgba
    except (OSError, ValueError, SyntaxError, struct.error, IndexError,
            Image.DecompressionBombError) as exc:
        result['errors'].append(str(exc))
        return result, None


def inspect(path, size, margin):
    """Compatibility helper for one-file, read-only inspection."""
    return load_and_inspect(path, size, margin)[0]


def compare_preview(master, preview, master_result, preview_result, resample):
    result = {'status': 'not_checked', 'derivation_pass': None,
              'master_sha256': master_result['sha256'],
              'preview_sha256': preview_result['sha256'],
              'parameters': {
                  'library': 'Pillow', 'pillow_version': PILLOW_VERSION,
                  'resample': resample, 'source_box': [0, 0, 1024, 1024],
                  'target_size': [120, 120], 'mode': 'RGBA', 'reducing_gap': None,
                  'color_conversion': 'none',
                  'alpha_handling': 'Pillow RGBA resize (premultiplied-alpha internally)',
                  'comparison': 'Exact RGBA; ignore RGB only where both alpha values are zero'},
              'errors': []}
    if not master_result['hard_spec_pass'] or not preview_result['hard_spec_pass']:
        result.update(status='blocked', derivation_pass=False)
        result['errors'].append('Derivation comparison requires both files to pass hard specs')
        return result
    expected = master.resize((120, 120), resample=RESAMPLERS[resample],
                             box=(0, 0, 1024, 1024), reducing_gap=None)
    different = 0
    first = None
    expected_bytes, actual_bytes = expected.tobytes(), preview.tobytes()
    for offset in range(0, len(expected_bytes), 4):
        left, right = expected_bytes[offset:offset + 4], actual_bytes[offset:offset + 4]
        if left[3] == right[3] == 0:
            continue
        if left != right:
            different += 1
            if first is None:
                index = offset // 4
                first = {'xy': [index % 120, index // 120],
                         'expected_rgba': list(left), 'actual_rgba': list(right)}
    result.update(status='pass' if different == 0 else 'fail',
                  derivation_pass=different == 0, different_pixels=different,
                  first_difference=first)
    if different:
        result['errors'].append('Preview pixels do not match this master resized with the reported parameters')
    return result


def check_files(image, preview=None, resample='lanczos', require_srgb=False):
    master_result, master = load_and_inspect(image, 1024, 102)
    results = [master_result]
    derivation = {'status': 'not_checked', 'derivation_pass': None,
                  'reason': 'No --preview supplied'}
    if preview is not None:
        preview_result, preview_image = load_and_inspect(preview, 120, 0)
        results.append(preview_result)
        derivation = compare_preview(master, preview_image, master_result, preview_result, resample)
    hard_pass = all(r['hard_spec_pass'] for r in results)
    color_pass = all(r['color_metadata']['srgb_check_pass'] for r in results)
    overall = hard_pass and (not require_srgb or color_pass) and (
        preview is None or derivation['derivation_pass'] is True)
    return {'pillow_version': PILLOW_VERSION, 'results': results,
            'hard_spec_pass': hard_pass, 'color_metadata_pass': color_pass,
            'require_srgb': require_srgb, 'derivation_check': derivation,
            'overall_check_pass': overall,
            'scope': 'Only the requested script checks; not visual, engine or release acceptance',
            'preview_margin_note': '102px safe margin applies to the 1024 master only; '
                                   'preview margins are reported, not separately gated'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--preview', type=Path,
                        help='Check exact 120px derivation from the full master canvas')
    parser.add_argument('--resample', choices=RESAMPLERS, default='lanczos',
                        help='Pillow resize filter for preview comparison (default: lanczos)')
    parser.add_argument('--require-srgb', action='store_true',
                        help='Require a valid, nonconflicting PNG sRGB declaration for each file; '
                             'ICC profiles are not validated')
    args = parser.parse_args(argv)
    report = check_files(args.image, args.preview, args.resample, args.require_srgb)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['overall_check_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
