import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from pato import decode, encode, extract_visual_image


class PatoDNATestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tmpdir.name)
        self.input_path = self.base / "input.png"
        self.output_path = self.base / "encoded.png"
        self.recovered_path = self.base / "recovered.png"

        y, x = np.indices((48, 64))
        image = np.stack(
            [
                (x * 4) % 256,
                (y * 5) % 256,
                ((x + y) * 3) % 256,
            ],
            axis=-1,
        ).astype(np.uint8)
        Image.fromarray(image, "RGB").save(self.input_path)
        self.original = image

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_encode_decode_roundtrip(self):
        code = "1234567890"
        returned_code = encode(
            img_path=self.input_path,
            output_png=self.output_path,
            code=code,
        )

        self.assertEqual(returned_code, code)
        self.assertTrue(self.output_path.exists())

        ok = decode(
            code,
            png_path=self.output_path,
            out_path=self.recovered_path,
        )
        self.assertTrue(ok)
        self.assertTrue(self.recovered_path.exists())

        recovered = np.array(Image.open(self.recovered_path).convert("RGB"))
        self.assertTrue(np.array_equal(recovered, self.original))

    def test_decode_rejects_wrong_code(self):
        encode(
            img_path=self.input_path,
            output_png=self.output_path,
            code="1234567890",
        )

        ok = decode(
            "0000000000",
            png_path=self.output_path,
            out_path=self.recovered_path,
        )
        self.assertFalse(ok)

    def test_encoded_output_has_no_large_visible_footer(self):
        encode(
            img_path=self.input_path,
            output_png=self.output_path,
            code="1234567890",
        )

        encoded = Image.open(self.output_path).convert("RGB")
        visual = extract_visual_image(self.output_path).convert("RGB")

        self.assertEqual(encoded.size, visual.size)

    def test_decode_works_with_code_only_from_server_store(self):
        code = "1234567890"
        _, payload_id = encode(
            img_path=self.input_path,
            output_png=self.output_path,
            code=code,
            return_payload_id=True,
        )

        ok = decode(
            code,
            png_path=None,
            payload_id=payload_id,
            out_path=self.recovered_path,
        )
        self.assertTrue(ok)

    def test_roundtrip_respects_exif_orientation(self):
        oriented_path = self.base / "phone_photo.jpg"
        exif = Image.Exif()
        exif[274] = 6
        Image.fromarray(self.original, "RGB").save(
            oriented_path,
            format="JPEG",
            exif=exif,
        )

        expected = np.array(
            ImageOps.exif_transpose(Image.open(oriented_path)).convert("RGB")
        )

        encode(
            img_path=oriented_path,
            output_png=self.output_path,
            code="1234567890",
        )
        ok = decode(
            "1234567890",
            png_path=self.output_path,
            out_path=self.recovered_path,
        )

        self.assertTrue(ok)
        recovered = np.array(Image.open(self.recovered_path).convert("RGB"))
        self.assertEqual(recovered.shape, expected.shape)
        self.assertTrue(np.array_equal(recovered, expected))


if __name__ == "__main__":
    unittest.main()
