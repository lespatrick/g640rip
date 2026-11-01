"""1D Channel Linearization (LUT) engine for Canon G640.

Provides per-channel tone reproduction curve (TRC) correction
for density linearization before or after ICC transform.
"""

import json
from typing import Dict, List, Optional, Union
import numpy as np


class LinearizationLUT:
    """
    Per-channel 1D Look-Up Table (LUT) for channel linearization.
    Supports arbitrary channel counts (RGB 3-channel, CMYK 4-channel, etc.)
    and 8-bit / 16-bit precision.
    """

    def __init__(self, num_channels: int = 3, table_size: int = 65536):
        self.num_channels = num_channels
        self.table_size = table_size  # 65536 for 16-bit precision
        # Initialize identity curve: f(x) = x
        self.curves: np.ndarray = np.tile(
            np.linspace(0.0, 1.0, table_size, dtype=np.float32), (num_channels, 1)
        )

    @classmethod
    def create_identity(cls, num_channels: int = 3) -> "LinearizationLUT":
        return cls(num_channels=num_channels)

    @classmethod
    def from_control_points(
        cls,
        points: Dict[int, List[tuple]],
        num_channels: int = 3,
        table_size: int = 65536,
    ) -> "LinearizationLUT":
        """
        Create LUT from per-channel control points [(in_val, out_val), ...].
        Values normalized to [0.0, 1.0].
        """
        lut = cls(num_channels=num_channels, table_size=table_size)
        x_eval = np.linspace(0.0, 1.0, table_size, dtype=np.float32)

        for ch, ch_points in points.items():
            if ch >= num_channels:
                continue
            sorted_pts = sorted(ch_points, key=lambda p: p[0])
            xp = [p[0] for p in sorted_pts]
            fp = [p[1] for p in sorted_pts]
            # Interpolate smoothly
            lut.curves[ch] = np.clip(np.interp(x_eval, xp, fp), 0.0, 1.0)

        return lut

    @classmethod
    def from_json(cls, filepath: str) -> "LinearizationLUT":
        """Load linearization curves from JSON file."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        num_channels = data.get("channels", 3)
        curves_data = data.get("curves", {})
        points: Dict[int, List[tuple]] = {}
        for ch_key, pt_list in curves_data.items():
            ch = int(ch_key)
            points[ch] = [(p[0], p[1]) for p in pt_list]
        return cls.from_control_points(points, num_channels=num_channels)

    def save_json(self, filepath: str):
        """Save sample points of current curves to JSON file."""
        # Sample 33 points per channel
        sample_indices = np.linspace(0, self.table_size - 1, 33, dtype=int)
        x_vals = sample_indices / (self.table_size - 1)
        curves_dict = {}
        for ch in range(self.num_channels):
            y_vals = self.curves[ch, sample_indices].tolist()
            curves_dict[str(ch)] = [[round(float(x), 4), round(float(y), 4)] for x, y in zip(x_vals, y_vals)]

        data = {
            "channels": self.num_channels,
            "table_size": self.table_size,
            "curves": curves_dict,
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def apply(self, img_array: np.ndarray) -> np.ndarray:
        """
        Apply linearization to image array in-place or return transformed array.
        Handles both uint8 and uint16 images.
        """
        is_uint8 = img_array.dtype == np.uint8
        num_ch = min(self.num_channels, img_array.shape[-1])

        out = np.empty_like(img_array)
        for c in range(num_ch):
            channel_data = img_array[..., c]
            if is_uint8:
                # 8-bit lookup
                lut_8 = np.clip(
                    self.curves[c, np.linspace(0, self.table_size - 1, 256, dtype=int)] * 255.0,
                    0,
                    255,
                ).astype(np.uint8)
                out[..., c] = lut_8[channel_data]
            else:
                # 16-bit lookup: index directly into 65536 table
                lut_16 = np.clip(self.curves[c] * 65535.0, 0, 65535).astype(np.uint16)
                out[..., c] = lut_16[channel_data]

        # Copy any remaining channels (e.g. alpha) unmodified
        if img_array.shape[-1] > num_ch:
            out[..., num_ch:] = img_array[..., num_ch:]

        return out

