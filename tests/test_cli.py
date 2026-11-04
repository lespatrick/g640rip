"""Unit tests for CLI commands."""

import os
import tempfile
import unittest
from PIL import Image

from g640rip.cli.main import build_parser


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()
        self.temp_dir = tempfile.TemporaryDirectory()

        # Create dummy image
        self.img_path = os.path.join(self.temp_dir.name, "sample.png")
        Image.new("RGB", (50, 50), (255, 0, 0)).save(self.img_path)

        # Create dummy target
        self.targ_path = os.path.join(self.temp_dir.name, "target.tif")
        Image.new("RGB", (60, 60), (0, 255, 0)).save(self.targ_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cli_discover_parser(self):
        args = self.parser.parse_args(["discover"])
        self.assertEqual(args.command, "discover")

    def test_cli_print_target_dry_run(self):
        raster_out = os.path.join(self.temp_dir.name, "target.urf")
        args = self.parser.parse_args([
            "print-target", self.targ_path,
            "--dry-run",
            "--out-raster", raster_out,
            "--media", "luster",
            "--size", "A4",
        ])
        args.func(args)
        self.assertTrue(os.path.exists(raster_out))
        with open(raster_out, "rb") as f:
            header = f.read(8)
            self.assertEqual(header, b"UNIRAST\0")

    def test_cli_print_production_dry_run(self):
        raster_out = os.path.join(self.temp_dir.name, "prod.urf")
        # System sRGB profile
        srgb_path = "/System/Library/ColorSync/Profiles/sRGB Profile.icc"
        if not os.path.exists(srgb_path):
            srgb_path = "/Library/ColorSync/Profiles/sRGB Profile.icc"

        args = self.parser.parse_args([
            "print", self.img_path,
            "--profile", srgb_path,
            "--dry-run",
            "--out-raster", raster_out,
            "--media", "luster",
            "--size", "A4",
            "--quality", "high",
        ])
        args.func(args)
        self.assertTrue(os.path.exists(raster_out))
        with open(raster_out, "rb") as f:
            header = f.read(8)
            self.assertEqual(header, b"UNIRAST\0")

    def test_ui_media_options_paper_sizes(self):
        try:
            from fastapi.testclient import TestClient
            from g640rip.ui.server import app
            client = TestClient(app)
            resp = client.get("/api/media-options")
            self.assertEqual(resp.status_code, 200)
            sizes = resp.json().get("paper_sizes", [])
            self.assertIn("4x6", sizes)
            self.assertNotIn("10x15", sizes)
            self.assertEqual(sizes[0], "4x6")
        except (ImportError, RuntimeError):
            pass


if __name__ == "__main__":
    unittest.main()

