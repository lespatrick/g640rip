"""Unit tests for Color & Linearization Engine."""

import unittest
import numpy as np
from PIL import Image

from g640rip.color import (
    ColorEngine,
    LinearizationLUT,
    InkLimiter,
    LCMS2Profile,
    LCMS2Transform,
    TYPE_RGB_16,
    INTENT_RELATIVE_COLORIMETRIC,
    cmsFLAGS_BLACKPOINTCOMPENSATION,
)


class TestColorEngine(unittest.TestCase):
    def test_calibration_target_mode_exact_preservation(self):
        """Verify calibration target pixels are copied byte-for-byte with zero change."""
        engine = ColorEngine()
        target = Image.new("RGB", (20, 20), (123, 45, 67))
        canvas = engine.process_calibration_target(target, page_size_name="A4")

        arr = np.array(canvas)
        mask = np.any(arr != 255, axis=-1)
        self.assertTrue(np.all(arr[mask] == [123, 45, 67]))

    def test_16bit_lcms2_transform(self):
        """Verify 16-bit precision transform via direct ctypes wrapper."""
        srgb = LCMS2Profile.create_srgb()
        t = LCMS2Transform.create(
            srgb, TYPE_RGB_16,
            srgb, TYPE_RGB_16,
            intent=INTENT_RELATIVE_COLORIMETRIC,
            flags=cmsFLAGS_BLACKPOINTCOMPENSATION,
        )
        sample = np.array([[[65535, 32768, 16384]]], dtype=np.uint16)
        out = t.transform(sample)
        self.assertTrue(np.allclose(sample, out, atol=10))

    def test_linearization_lut(self):
        lut = LinearizationLUT.create_identity()
        # Scale green channel down by half
        lut.curves[1] *= 0.5
        img = np.array([[[200, 200, 200]]], dtype=np.uint8)
        res = lut.apply(img)
        self.assertEqual(res[0, 0, 0], 200)
        self.assertEqual(res[0, 0, 1], 100)
        self.assertEqual(res[0, 0, 2], 200)

    def test_ink_limiter_rgb(self):
        limiter = InkLimiter(max_total_ink=0.85)
        # Deep black: 100% ink
        full_black = np.array([[[0, 0, 0]]], dtype=np.uint8)
        limited = limiter.apply_rgb(full_black)
        # Inverted back to RGB, values should be raised > 0 to limit total ink
        self.assertTrue(np.all(limited > 0))
        # Pure white (255, 255, 255): 0% ink, must remain untouched
        white = np.array([[[255, 255, 255]]], dtype=np.uint8)
        self.assertTrue(np.array_equal(limiter.apply_rgb(white), white))

        # Default 1.0 (no limiter) must preserve full black [0, 0, 0]
        limiter_full = InkLimiter(max_total_ink=1.0)
        self.assertTrue(np.array_equal(limiter_full.apply_rgb(full_black), full_black))

    def test_contrast_s_curve(self):
        # Normal (0.0): identity
        img = Image.new("RGB", (3, 1))
        img.putpixel((0, 0), (0, 0, 0))
        img.putpixel((1, 0), (128, 128, 128))
        img.putpixel((2, 0), (255, 255, 255))

        same = ColorEngine.apply_contrast_curve(img, contrast=0.0)
        self.assertTrue(np.array_equal(np.array(img), np.array(same)))

        # Boosted (+0.25): deepens shadows, lifts highlights, keeps endpoints
        boosted = ColorEngine.apply_contrast_curve(img, contrast=0.25)
        arr = np.array(boosted)
        self.assertEqual(tuple(arr[0, 0]), (0, 0, 0))        # Pure black intact
        self.assertEqual(tuple(arr[0, 2]), (255, 255, 255))  # Pure white intact
        self.assertAlmostEqual(arr[0, 1, 0], 128, delta=2)   # Midpoint centered

        # Test shadow deepening and highlight lifting
        step_img = Image.new("RGB", (2, 1))
        step_img.putpixel((0, 0), (64, 64, 64))     # shadow
        step_img.putpixel((1, 0), (192, 192, 192))  # highlight
        boosted_step = np.array(ColorEngine.apply_contrast_curve(step_img, contrast=0.20))
        self.assertLess(boosted_step[0, 0, 0], 64)      # shadow deepened
        self.assertGreater(boosted_step[0, 1, 0], 192)  # highlight lifted


if __name__ == "__main__":
    unittest.main()

