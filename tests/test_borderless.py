import unittest
import numpy as np
from PIL import Image

from g640rip.color.engine import ColorEngine
from g640rip.transport.constants import PAPER_SIZES, get_paper_spec
from g640rip.transport.ipp_client import IPPClient


class TestBorderless(unittest.TestCase):
    def test_paper_spec_borderless(self):
        spec_4x6 = get_paper_spec("4x6")
        self.assertTrue(spec_4x6["supports_borderless"])
        self.assertEqual(spec_4x6["media_fullbleed"], "4x6.Fullbleed")
        self.assertEqual(spec_4x6["width_600dpi"], 2400)
        self.assertEqual(spec_4x6["height_600dpi"], 3600)

        spec_10x15 = get_paper_spec("10x15")
        self.assertEqual(spec_10x15["media_fullbleed"], "Postcard.Fullbleed")
        self.assertEqual(spec_10x15["width_mm"], 100.0)
        self.assertEqual(spec_10x15["height_mm"], 149.0)
        self.assertEqual(spec_10x15["width_600dpi"], 2362)
        self.assertEqual(spec_10x15["height_600dpi"], 3520)

        spec_a4 = get_paper_spec("A4")
        self.assertTrue(spec_a4["supports_borderless"])
        self.assertEqual(spec_a4["media_fullbleed"], "A4.Fullbleed")

    def test_layout_borderless_fill(self):
        # Landscape 4:3 photo (e.g. 4000x3000)
        img = Image.new("RGB", (4000, 3000), color=(200, 100, 50))
        # Framed to 4x6" (2400x3600) borderless fill
        framed = ColorEngine.prepare_image_layout(
            img,
            page_size_name="4x6",
            borderless=True,
            fit_mode="fill",
            bleed_pct=1.5,
            auto_rotate=True,
            dpi=600,
        )

        self.assertEqual(framed.size, (2400, 3600))
        arr = np.array(framed)
        self.assertEqual(arr.shape, (3600, 2400, 3))
        # Ensure image completely fills canvas without white bars
        self.assertEqual(arr[0, 0, 0], 200)
        self.assertEqual(arr[3599, 2399, 0], 200)

    def test_layout_borderless_fit(self):
        img = Image.new("RGB", (2000, 2000), color=(10, 20, 30))
        framed = ColorEngine.prepare_image_layout(
            img,
            page_size_name="4x6",
            borderless=True,
            fit_mode="fit",
            auto_rotate=True,
            dpi=600,
        )
        self.assertEqual(framed.size, (2400, 3600))
        arr = np.array(framed)
        # In fit mode, square image inside 2400x3600 has white letterbox at top/bottom
        self.assertEqual(list(arr[0, 0]), [255, 255, 255])
        # Center has image content
        self.assertEqual(list(arr[1800, 1200]), [10, 20, 30])

    def test_layout_borderless_compensate(self):
        # 10x15 photo with distinct value in every column to verify zero repeated columns
        w, h = 2362, 3520
        grad = np.tile(np.arange(w, dtype=np.uint16) % 256, (h, 1)).astype(np.uint8)
        rgb = np.stack([grad, grad, grad], axis=2)
        img = Image.fromarray(rgb, mode="RGB")

        framed = ColorEngine.prepare_image_layout(
            img,
            page_size_name="10x15",
            borderless=True,
            fit_mode="compensate",
            comp_x_pct=0.0,
            comp_y_pct=5.0,
            auto_rotate=True,
            dpi=600,
        )
        self.assertEqual(framed.size, (2362, 3520))
        arr = np.array(framed)

        # Safe area height: 95% of 3520 = 3344
        safe_h = int(round(3520 * 0.95))

        # Check left edge: authentic image gradient, NOT repeated pixels
        self.assertFalse(np.array_equal(arr[:safe_h, 0], arr[:safe_h, 1]))

        # Check right edge: authentic image gradient, NOT repeated pixels
        self.assertFalse(np.array_equal(arr[:safe_h, -1], arr[:safe_h, -2]))

        # Bottom cut-off zone (3344..3520) is padded for feed roller absorption
        self.assertTrue(np.array_equal(arr[safe_h, :], arr[safe_h - 1, :]))
        self.assertTrue(np.array_equal(arr[-1, :], arr[safe_h - 1, :]))

    def test_layout_hardware_scaling_and_offset(self):
        # Test that hardware scaling factors and offsets apply cleanly
        img = Image.new("RGB", (2362, 3520), color=(100, 150, 200))
        framed = ColorEngine.prepare_image_layout(
            img,
            page_size_name="10x15",
            borderless=True,
            fit_mode="compensate",
            scale_x_pct=-1.0,
            scale_y_pct=0.59,
            offset_x_pct=-0.25,
            offset_y_pct=-1.59,
            dpi=600,
        )
        self.assertEqual(framed.size, (2362, 3520))



if __name__ == "__main__":
    unittest.main()

