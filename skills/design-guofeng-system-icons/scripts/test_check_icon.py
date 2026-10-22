#!/usr/bin/env python3
"""Regression tests using temporary synthetic PNGs; existing assets stay read-only."""
import contextlib
import hashlib
import io
import json
import struct
import sys
import unittest
from test_fixture_directory import WorkspaceTemporaryDirectory
import zlib
from pathlib import Path

sys.dont_write_bytecode = True
from PIL import Image
import check_icon as checker


def png_chunk(kind, payload):
    return (struct.pack('>I', len(payload)) + kind + payload
            + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff))


class IconChecks(unittest.TestCase):
    def setUp(self):
        self.temp = WorkspaceTemporaryDirectory(prefix='check-icon-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.master = Image.new('RGBA', (1024, 1024))
        self.master.paste((80, 160, 200, 255), (112, 140, 900, 880))
        self.master.paste((230, 90, 60, 128), (310, 230, 740, 700))
        self.master_path = self.save(self.master, 'master.png')
        self.layout = self.root / 'layout.json'
        self.layout.write_text(json.dumps({'icon_layer': {'width': 120, 'height': 120, 'scale': 1, 'offset': [0, 0]}}))

    def check(self, *args, **kwargs):
        return checker.check_files(*args, layout=self.layout, **kwargs)

    def save(self, image, name, chunks=()):
        path = self.root / name
        image.save(path)
        if chunks:
            # Inject exact chunks; Pillow's encoder suppresses duplicates/iCCP in pnginfo.
            data = path.read_bytes()
            path.write_bytes(data[:33] + b''.join(png_chunk(k, p) for k, p in chunks) + data[33:])
        return path

    def preview(self, method='lanczos'):
        # Use Pillow independently, not the production comparison helper.
        return self.master.resize((120, 120), getattr(Image.Resampling, method.upper()))

    def color_report(self, chunks, strict=True):
        path = self.save(self.master, 'color.png', chunks)
        return self.check(path, require_srgb=strict)

    def test_16_bit_source_is_rejected_despite_rgba_pillow_mode(self):
        clear = struct.pack('>4H', 0, 0, 0, 0)
        fill = struct.pack('>4H', 65535, 30000, 10000, 65535)
        rows = [b'\0' + (clear * 112 + fill * 800 + clear * 112
                        if 112 <= y < 912 else clear * 1024) for y in range(1024)]
        path = self.root / '16-bit.png'
        path.write_bytes(checker.PNG_SIGNATURE
                         + png_chunk(b'IHDR', struct.pack('>IIBBBBB', 1024, 1024, 16, 6, 0, 0, 0))
                         + png_chunk(b'IDAT', zlib.compress(b''.join(rows)))
                         + png_chunk(b'IEND', b''))
        with Image.open(path) as im:
            self.assertEqual(im.mode, 'RGBA')
        report = self.check(path)
        self.assertFalse(report['overall_check_pass'])
        self.assertEqual(report['results'][0]['png_header']['bit_depth'], 16)
        self.assertEqual(report['results'][0]['alpha_check'], 'not_checked_unsupported_source_format')

    def test_rgb_source_is_not_rgba(self):
        path = self.save(self.master.convert('RGB'), 'rgb.png')
        self.assertFalse(self.check(path)['hard_spec_pass'])

    def test_wrong_dimensions_fail(self):
        path = self.save(self.master.resize((512, 512)), '512.png')
        self.assertFalse(self.check(path)['hard_spec_pass'])

    def test_empty_and_opaque_images_fail(self):
        for name, color in [('empty', (0, 0, 0, 0)), ('opaque', (20, 40, 60, 255))]:
            with self.subTest(name=name):
                path = self.save(Image.new('RGBA', (1024, 1024), color), name + '.png')
                self.assertFalse(self.check(path)['hard_spec_pass'])

    def test_exact_safe_boundary_passes_but_alpha_one_outside_fails(self):
        image = Image.new('RGBA', (1024, 1024))
        image.paste((80, 90, 100, 255), (102, 102, 922, 922))
        path = self.save(image, 'boundary.png')
        result = self.check(path)['results'][0]
        self.assertTrue(result['hard_spec_pass'])
        self.assertEqual(result['margins_ltrb'], [102, 102, 102, 102])
        image.putpixel((101, 400), (20, 30, 40, 1))
        path = self.save(image, 'stray-alpha-one.png')
        self.assertFalse(self.check(path)['hard_spec_pass'])

    def test_correct_full_canvas_derivation_for_each_filter(self):
        for method in ('lanczos', 'bicubic', 'bilinear'):
            with self.subTest(method=method):
                path = self.save(self.preview(method), method + '.png')
                report = self.check(self.master_path, path, resample=method)
                self.assertTrue(report['overall_check_pass'])
                self.assertEqual(report['derivation_check']['different_pixels'], 0)
                self.assertEqual(report['derivation_check']['parameters']['resample'], method)

    def test_wrong_pair_and_tightly_cropped_preview_fail(self):
        unrelated = Image.new('RGBA', (120, 120))
        unrelated.paste((255, 0, 0, 255), (0, 0, 119, 119))
        cropped = self.master.crop((112, 140, 900, 880)).resize((120, 120))
        cropped.putpixel((0, 0), (0, 0, 0, 0))
        for name, image in [('unrelated', unrelated), ('cropped', cropped)]:
            with self.subTest(name=name):
                path = self.save(image, name + '.png')
                report = self.check(self.master_path, path)
                self.assertTrue(report['hard_spec_pass'])
                self.assertFalse(report['overall_check_pass'])
                self.assertEqual(report['derivation_check']['status'], 'fail')

    def test_wrong_filter_fails(self):
        path = self.save(self.preview('bilinear'), 'bilinear.png')
        self.assertFalse(self.check(self.master_path, path)['overall_check_pass'])

    def test_hidden_rgb_in_fully_transparent_preview_is_ignored(self):
        preview = self.preview()
        preview.putpixel((0, 0), (211, 17, 99, 0))
        path = self.save(preview, 'hidden-rgb.png')
        self.assertTrue(self.check(self.master_path, path)['overall_check_pass'])

    def test_hidden_rgb_in_master_does_not_change_derivation(self):
        preview_path = self.save(self.preview(), 'preview.png')
        self.master.putpixel((0, 0), (211, 17, 99, 0))
        master_path = self.save(self.master, 'hidden-master.png')
        self.assertTrue(self.check(master_path, preview_path)['overall_check_pass'])

    def test_visible_rgb_and_alpha_changes_are_not_ignored(self):
        original = self.preview()
        for name, xy, pixel in [('rgb', (50, 50), (2, 3, 4, original.getpixel((50, 50))[3])),
                                ('alpha', (0, 0), (0, 0, 0, 1))]:
            with self.subTest(name=name):
                preview = original.copy()
                preview.putpixel(xy, pixel)
                path = self.save(preview, name + '.png')
                report = self.check(self.master_path, path)
                self.assertFalse(report['overall_check_pass'])
                self.assertEqual(report['derivation_check']['different_pixels'], 1)

    def test_no_preview_is_not_checked_and_hashes_are_recorded(self):
        report = self.check(self.master_path)
        self.assertEqual(report['derivation_check']['status'], 'not_checked')
        self.assertIsNone(report['derivation_check']['derivation_pass'])
        self.assertEqual(report['results'][0]['sha256'],
                         hashlib.sha256(self.master_path.read_bytes()).hexdigest())
        self.assertEqual(report['pillow_version'], checker.PILLOW_VERSION)

    def test_missing_srgb_is_optional_but_fails_strict_mode(self):
        report = self.check(self.master_path)
        self.assertTrue(report['overall_check_pass'])
        self.assertFalse(report['color_metadata_pass'])
        self.assertEqual(report['results'][0]['color_metadata']['status'], 'missing')
        strict = self.check(self.master_path, require_srgb=True)
        self.assertTrue(strict['hard_spec_pass'])
        self.assertFalse(strict['overall_check_pass'])

    def test_valid_srgb_with_compatible_optional_chunks_passes(self):
        for extra in [[], [(b'gAMA', struct.pack('>I', 45455)),
                           (b'cHRM', struct.pack('>8I', *checker.SRGB_CHRM))]]:
            report = self.color_report([(b'sRGB', b'\0')] + extra)
            self.assertTrue(report['overall_check_pass'])
            self.assertEqual(report['results'][0]['color_metadata']['status'], 'declared_srgb')

    def test_compatible_gamma_and_chromaticities_alone_do_not_declare_srgb(self):
        report = self.color_report([(b'gAMA', struct.pack('>I', 45455)),
                                    (b'cHRM', struct.pack('>8I', *checker.SRGB_CHRM))])
        self.assertFalse(report['overall_check_pass'])
        self.assertEqual(report['results'][0]['color_metadata']['status'], 'missing')

    def test_unknown_icc_named_srgb_is_unverified(self):
        # A convenient profile name is not proof of the profile's transfer functions.
        icc = b'sRGB\0\0' + zlib.compress(b'Unvalidated ICC bytes; description: sRGB')
        report = self.color_report([(b'iCCP', icc)])
        self.assertEqual(report['results'][0]['color_metadata']['status'], 'icc_unverified')
        self.assertFalse(report['overall_check_pass'])

    def test_srgb_and_icc_coexistence_is_conservatively_conflicting(self):
        icc = b'sRGB\0\0' + zlib.compress(b'Unvalidated ICC bytes')
        report = self.color_report([(b'sRGB', b'\0'), (b'iCCP', icc)])
        self.assertEqual(report['results'][0]['color_metadata']['status'], 'conflicting')
        self.assertFalse(report['overall_check_pass'])

    def test_srgb_gamma_and_chromaticity_conflicts_fail_strict_mode(self):
        for chunk in [(b'gAMA', struct.pack('>I', 100000)),
                      (b'cHRM', struct.pack('>8I', *([10000] * 8)))]:
            with self.subTest(chunk=chunk[0]):
                report = self.color_report([(b'sRGB', b'\0'), chunk])
                self.assertTrue(report['hard_spec_pass'])
                self.assertEqual(report['results'][0]['color_metadata']['status'], 'conflicting')
                self.assertFalse(report['overall_check_pass'])

    def test_invalid_intent_and_duplicate_srgb_fail(self):
        for chunks in [[(b'sRGB', b'\x04')], [(b'sRGB', b'\0'), (b'sRGB', b'\0')]]:
            report = self.color_report(chunks)
            self.assertEqual(report['results'][0]['color_metadata']['status'], 'invalid_metadata')
            self.assertFalse(report['overall_check_pass'])

    def test_late_srgb_chunk_fails_strict_check(self):
        data = self.master_path.read_bytes()
        self.master_path.write_bytes(data[:-12] + png_chunk(b'sRGB', b'\0') + data[-12:])
        report = self.check(self.master_path, require_srgb=True)
        self.assertEqual(report['results'][0]['color_metadata']['status'], 'invalid_metadata')
        self.assertFalse(report['overall_check_pass'])

    def test_higher_precedence_cicp_is_not_silently_ignored(self):
        report = self.color_report([(b'sRGB', b'\0'), (b'cICP', bytes([12, 13, 0, 1]))])
        self.assertEqual(report['results'][0]['color_metadata']['status'], 'metadata_unverified')
        self.assertFalse(report['overall_check_pass'])

    def test_strict_color_check_applies_to_preview_too(self):
        master = self.save(self.master, 'srgb-master.png', [(b'sRGB', b'\0')])
        preview = self.save(self.preview(), 'untagged-preview.png')
        report = self.check(master, preview, require_srgb=True)
        self.assertTrue(report['derivation_check']['derivation_pass'])
        self.assertFalse(report['overall_check_pass'])

    def test_invalid_crc_and_unreadable_file_fail_without_tracebacks(self):
        data = bytearray(self.master_path.read_bytes())
        data[29] ^= 1
        self.master_path.write_bytes(data)
        for path in (self.master_path, self.root / 'absent.png'):
            report = self.check(path)
            self.assertFalse(report['overall_check_pass'])
            self.assertTrue(report['results'][0]['errors'])

    def test_invalid_ihdr_compression_method_is_rejected(self):
        data = self.master_path.read_bytes()
        header = bytearray(data[16:29])
        header[10] = 1
        self.master_path.write_bytes(data[:8] + png_chunk(b'IHDR', header) + data[33:])
        self.assertFalse(self.check(self.master_path)['overall_check_pass'])

    def test_malformed_late_color_chunks_return_json_instead_of_raising(self):
        data = self.master_path.read_bytes()
        for kind, payload in [(b'cHRM', b'\0'), (b'gAMA', b'\0'), (b'iCCP', b'')]:
            with self.subTest(kind=kind):
                self.master_path.write_bytes(data[:-12] + png_chunk(kind, payload) + data[-12:])
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = checker.main([str(self.master_path), '--layout', str(self.layout)])
                self.assertEqual(code, 1)
                report = json.loads(out.getvalue())
                self.assertFalse(report['overall_check_pass'])
                self.assertEqual(report['results'][0]['color_metadata']['status'], 'invalid_metadata')

    def test_cli_exit_status_json_and_read_only_behavior(self):
        preview = self.save(self.preview(), 'preview.png')
        before = {p: p.read_bytes() for p in (self.master_path, preview)}
        for strict, expected_exit in [(False, 0), (True, 1)]:
            out = io.StringIO()
            args = [str(self.master_path), '--preview', str(preview)]
            if strict:
                args.append('--require-srgb')
            with contextlib.redirect_stdout(out):
                actual_exit = checker.main(args + ['--layout', str(self.layout)])
            self.assertEqual(actual_exit, expected_exit)
            report = json.loads(out.getvalue())
            self.assertEqual(report['derivation_check']['preview_sha256'],
                             hashlib.sha256(before[preview]).hexdigest())
        for path, original in before.items():
            self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
