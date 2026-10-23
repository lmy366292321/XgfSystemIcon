"""Regression checks: retain AA/thin parts, reject broad masks, replay real exports."""
import json
import unittest
from PIL import Image
import color_record as cr
from test_color_record import ColorRecordTests


class AlphaTests(ColorRecordTests):
    def test_opt_in_preserves_edge_and_thin_part(self):
        im=Image.new('RGBA',(1024,1024),(14,25,36,0))
        im.putpixel((500,500),(60,70,80,255))
        im.putpixel((508,500),(60,70,80,1))
        im.putpixel((509,500),(60,70,80,1))
        im.putpixel((100,100),(60,70,80,2))
        fixed,count=cr.clean_detached_alpha(im)
        self.assertEqual(count,1)
        self.assertEqual(fixed.getpixel((508,500)),im.getpixel((508,500)))
        self.assertEqual(fixed.getpixel((100,100)),im.getpixel((100,100)))
        self.assertEqual(fixed.getpixel((509,500)),(60,70,80,0))
        self.assertEqual(fixed.convert('RGB').tobytes(),im.convert('RGB').tobytes())

    def test_broad_faint_content_rejected(self):
        with self.assertRaisesRegex(ValueError,'cap'):
            cr.clean_detached_alpha(Image.new('RGBA',(1024,1024),(20,30,40,1)))

    def test_export_cleanup_bound_replay_and_tamper(self):
        self.make(tagged=False)
        with Image.open(self.source) as im:
            im=im.copy()
        im.putpixel((0,0),(30,40,50,1));im.save(self.source)
        self.collect()
        basis=self.root/'decision.txt';basis.write_text('Synthetic test authorization and isolated residual diagnosis')
        original=self.source.read_bytes()
        plain=cr.export(self.capture,self.root/'plain',unknown='preserve')
        clean=cr.export(self.capture,self.root/'clean',unknown='preserve',alpha_cleanup_basis=basis)
        self.assertEqual(self.source.read_bytes(),original)
        self.assertEqual(Image.open(plain['master']['path']).getpixel((0,0))[3],1)
        self.assertEqual(Image.open(clean['master']['path']).getpixel((0,0))[3],0)
        self.assertEqual(clean['status'],'unverified')
        self.assertEqual(clean['source_to_master']['status'],'pass')
        self.assertEqual(clean['master_to_preview']['status'],'pass')
        rec=self.root/'clean/color-export.json'
        self.change_record(rec,lambda r:r['operation']['alpha_cleanup'].update(removed_count=0))
        self.assertEqual(cr.verify(rec)['status'],'fail')


if __name__=='__main__':unittest.main()
