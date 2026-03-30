import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from pato import decode, encode


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


if __name__ == "__main__":
    unittest.main()
