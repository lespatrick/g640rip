"""Total Ink Limit (TIL) and saturation limiter for Canon G640."""

from typing import Optional
import numpy as np


class InkLimiter:
    """
    Limits maximum ink deposition to prevent puddling, bronzing, or bleeding
    on specific media types (e.g., fine-art rag, uncoated, or heavy photo paper).
    """

    def __init__(self, max_total_ink: float = 1.0, soft_knee: Optional[float] = None):
        """
        Parameters:
            max_total_ink: Maximum allowed total ink density [0.4 to 1.0].
                           1.0 means no limit (100% full black, standard for photo paper).
                           0.85 means max 85% total ink deposition (for uncoated or rag paper).
            soft_knee: Threshold where soft roll-off starts [0.0 to max_total_ink].
        """
        self.max_total_ink = float(np.clip(max_total_ink, 0.40, 1.0))
        knee = (self.max_total_ink - 0.10) if soft_knee is None else soft_knee
        self.soft_knee = float(np.clip(knee, 0.30, self.max_total_ink))

    def apply_rgb(self, rgb_array: np.ndarray) -> np.ndarray:
        """
        Apply ink limit to RGB array (uint8 or uint16).
        In RGB, (0, 0, 0) represents 100% ink, and (MAX, MAX, MAX) represents 0% ink.
        """
        if self.max_total_ink >= 1.0:
            return rgb_array

        is_uint8 = rgb_array.dtype == np.uint8
        max_val = 255.0 if is_uint8 else 65535.0

        # Invert to ink space [0.0 = white/no ink, 1.0 = full black/max ink]
        float_rgb = rgb_array[..., :3].astype(np.float32) / max_val
        ink_channels = 1.0 - float_rgb  # C, M, Y equivalent ink densities

        # Calculate average/peak ink deposition per pixel (shape: [..., 1])
        total_ink = np.mean(ink_channels, axis=-1, keepdims=True)

        # Vectorized soft compression curve
        excess = np.maximum(0.0, total_ink - self.soft_knee)
        span = max(1e-5, 1.0 - self.soft_knee)
        allowed_span = self.max_total_ink - self.soft_knee
        compressed_excess = allowed_span * np.tanh(excess / span)
        new_total = self.soft_knee + compressed_excess

        scale = np.where(total_ink > self.soft_knee, new_total / np.maximum(total_ink, 1e-5), 1.0)
        scale = np.clip(scale, 0.0, 1.0)

        # Scale channels preserving hue and chromatic balance
        ink_channels *= scale

        # Convert back to RGB
        clipped_ink = np.clip(ink_channels, 0.0, 1.0)
        out_rgb = ((1.0 - clipped_ink) * max_val)

        if is_uint8:
            result = np.clip(out_rgb + 0.5, 0, 255).astype(np.uint8)
        else:
            result = np.clip(out_rgb + 0.5, 0, 65535).astype(np.uint16)

        if rgb_array.shape[-1] > 3:
            # Preserve alpha if present
            full_out = np.empty_like(rgb_array)
            full_out[..., :3] = result
            full_out[..., 3:] = rgb_array[..., 3:]
            return full_out

        return result

    def apply_cmyk(self, cmyk_array: np.ndarray) -> np.ndarray:
        """
        Apply Total Area Coverage (TAC) limit to CMYK array [0.0 .. 1.0] or [0 .. 255].
        """
        is_uint8 = cmyk_array.dtype == np.uint8
        max_val = 255.0 if is_uint8 else (65535.0 if cmyk_array.dtype == np.uint16 else 1.0)
        float_cmyk = cmyk_array.astype(np.float32) / max_val

        # TAC is sum of C + M + Y + K (range: 0.0 to 4.0)
        tac = np.sum(float_cmyk, axis=-1, keepdims=True)
        max_tac = self.max_total_ink * 4.0

        scale = np.where(tac > max_tac, max_tac / np.maximum(tac, 1e-5), 1.0)
        scale = np.clip(scale, 0.0, 1.0)
        float_cmyk *= scale

        out = np.clip(float_cmyk * max_val, 0, max_val)
        return out.astype(cmyk_array.dtype)

