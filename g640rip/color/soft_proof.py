"""Soft Proofing and Gamut Warning engine using LittleCMS2."""

import os
from typing import Optional, Tuple
import numpy as np
from PIL import Image

from .lcms2_capi import (
    LCMS2Profile,
    LCMS2Transform,
    TYPE_RGB_8,
    INTENT_RELATIVE_COLORIMETRIC,
    INTENT_ABSOLUTE_COLORIMETRIC,
    cmsFLAGS_SOFTPROOFING,
    cmsFLAGS_GAMUTCHECK,
    cmsFLAGS_HIGHRESPRECALC,
    cmsFLAGS_BLACKPOINTCOMPENSATION,
)


def get_display_profile_path() -> Optional[str]:
    """Find macOS active display profile if available."""
    standard_mac_paths = [
        "/Library/ColorSync/Profiles/Displays",
        os.path.expanduser("~/Library/ColorSync/Profiles"),
        "/System/Library/ColorSync/Profiles/Display P3.icc",
        "/System/Library/ColorSync/Profiles/sRGB Profile.icc",
    ]
    for p in standard_mac_paths:
        if os.path.isfile(p):
            return p
        elif os.path.isdir(p):
            for fname in os.listdir(p):
                if fname.endswith(".icc") or fname.endswith(".icm"):
                    return os.path.join(p, fname)
    return None


class SoftProofEngine:
    """
    Renders soft proof simulations (including paper white tint and shadow compression)
    and computes gamut warning masks.
    """

    def __init__(
        self,
        paper_profile_path: Optional[str] = None,
        paper_profile: Optional[LCMS2Profile] = None,
        display_profile_path: Optional[str] = None,
        display_profile: Optional[LCMS2Profile] = None,
        simulate_paper_white: bool = False,
        simulate_black_ink: bool = True,
        use_system_display: bool = False,
    ):
        if paper_profile is not None:
            self.paper_profile = paper_profile
            self.paper_profile_path = paper_profile_path or "memory_profile.icc"
        elif paper_profile_path and os.path.exists(paper_profile_path):
            self.paper_profile_path = paper_profile_path
            self.paper_profile = LCMS2Profile.open_file(paper_profile_path)
        else:
            self.paper_profile_path = paper_profile_path or "default_srgb.icc"
            self.paper_profile = LCMS2Profile.create_srgb()

        if display_profile is not None:
            self.display_profile = display_profile
        elif display_profile_path and os.path.exists(display_profile_path):
            self.display_profile = LCMS2Profile.open_file(display_profile_path)
        elif use_system_display:
            sys_disp = get_display_profile_path()
            if sys_disp and os.path.exists(sys_disp):
                self.display_profile = LCMS2Profile.open_file(sys_disp)
            else:
                self.display_profile = LCMS2Profile.create_srgb()
        else:
            self.display_profile = LCMS2Profile.create_srgb()

        self.simulate_paper_white = simulate_paper_white
        self.simulate_black_ink = simulate_black_ink

    def render_soft_proof(
        self,
        image: Image.Image,
        input_profile: Optional[LCMS2Profile] = None,
        intent: int = INTENT_RELATIVE_COLORIMETRIC,
    ) -> Image.Image:
        """
        Generate soft-proofed image as it will appear on paper when viewed under calibrated display.
        """
        if image.mode != "RGB":
            image = image.convert("RGB")

        if input_profile is None:
            input_profile = LCMS2Profile.create_srgb()

        flags = cmsFLAGS_SOFTPROOFING | cmsFLAGS_HIGHRESPRECALC
        if not self.simulate_paper_white:
            # If not simulating paper white, use Relative Colorimetric for proofing
            proofing_intent = INTENT_RELATIVE_COLORIMETRIC
            flags |= cmsFLAGS_BLACKPOINTCOMPENSATION
        else:
            # Absolute Colorimetric simulates exact paper white tint
            proofing_intent = INTENT_ABSOLUTE_COLORIMETRIC

        transform = LCMS2Transform.create_proofing(
            input_profile=input_profile,
            in_format=TYPE_RGB_8,
            output_profile=self.display_profile,
            out_format=TYPE_RGB_8,
            proofing_profile=self.paper_profile,
            intent=intent,
            proofing_intent=proofing_intent,
            flags=flags,
        )

        in_arr = np.array(image, dtype=np.uint8)
        out_arr = transform.transform(in_arr)
        return Image.fromarray(out_arr, mode="RGB")

    def render_gamut_warning(
        self,
        image: Image.Image,
        input_profile: Optional[LCMS2Profile] = None,
        warning_color: Tuple[int, int, int] = (0, 255, 0),  # Neon green
    ) -> Tuple[Image.Image, np.ndarray]:
        """
        Produce gamut warning mask highlighting out-of-gamut colors.
        Returns:
            (proof_image_with_warning_overlay, boolean_out_of_gamut_mask)
        """
        if image.mode != "RGB":
            image = image.convert("RGB")

        if input_profile is None:
            input_profile = LCMS2Profile.create_srgb()

        flags = cmsFLAGS_GAMUTCHECK | cmsFLAGS_HIGHRESPRECALC

        # LittleCMS gamut transform replaces out of gamut pixels with alarm code
        transform = LCMS2Transform.create_proofing(
            input_profile=input_profile,
            in_format=TYPE_RGB_8,
            output_profile=self.display_profile,
            out_format=TYPE_RGB_8,
            proofing_profile=self.paper_profile,
            intent=INTENT_RELATIVE_COLORIMETRIC,
            proofing_intent=INTENT_ABSOLUTE_COLORIMETRIC,
            flags=flags,
        )

        in_arr = np.array(image, dtype=np.uint8)
        gamut_arr = transform.transform(in_arr)

        # Build soft proof for base
        proof_base = self.render_soft_proof(image, input_profile=input_profile)
        proof_arr = np.array(proof_base, dtype=np.uint8)

        # Gamut check creates a distinct delta from regular transform
        # We also compute color difference deltaE or alarm code match
        mask = np.any(np.abs(gamut_arr.astype(int) - proof_arr.astype(int)) > 15, axis=-1)

        # Apply neon warning color
        overlay_arr = proof_arr.copy()
        overlay_arr[mask] = warning_color

        return Image.fromarray(overlay_arr, mode="RGB"), mask

