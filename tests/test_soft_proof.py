import unittest
import numpy as np
from PIL import Image

from g640rip.color.soft_proof import SoftProofEngine
from g640rip.color.lcms2_capi import LCMS2Profile


class TestSoftProof(unittest.TestCase):
    def setUp(self):
        self.profile_path = "targets/Canon_G640_10x15_Glossy2_70corr.icc"

    def test_soft_proof_warmth_and_saturation(self):
        engine = SoftProofEngine(
            paper_profile_path=self.profile_path,
            simulate_paper_white=False,
        )

        # Test skin tone
        skin_img = Image.new("RGB", (10, 10), color=(230, 180, 150))
        proof_img = engine.render_soft_proof(skin_img)
        proof_arr = np.array(proof_img)
        mean_pixel = proof_arr.mean(axis=(0, 1))

        # Ensure warm skin tone is preserved (R > G > B, warmth retained)
        self.assertGreater(mean_pixel[0], mean_pixel[1])
        self.assertGreater(mean_pixel[1], mean_pixel[2])
        self.assertAlmostEqual(mean_pixel[0], 230, delta=10)

    def test_gamut_warning_generation(self):
        engine = SoftProofEngine(
            paper_profile_path=self.profile_path,
            simulate_paper_white=False,
        )

        test_img = Image.new("RGB", (20, 20), color=(255, 0, 255))
        overlay, mask = engine.render_gamut_warning(test_img)
        self.assertIsInstance(mask, np.ndarray)
        self.assertEqual(mask.shape, (20, 20))
        self.assertEqual(overlay.size, (20, 20))


if __name__ == "__main__":
    unittest.main()

