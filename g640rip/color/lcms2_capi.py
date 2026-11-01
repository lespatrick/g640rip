"""Direct LittleCMS2 (lcms2) 64-bit ctypes wrapper for high-precision color management.

Provides 16-bit transform pipelines, soft proofing with paper simulation,
and gamut check masking.
"""

import ctypes
import os
import sys
from typing import Optional, Tuple
import numpy as np


def _find_liblcms2() -> str:
    """Locate liblcms2 dynamic library on macOS."""
    # Check bundled Pillow dylib
    candidates = [
        # Pillow bundled dylib (Homebrew python)
        os.path.join(sys.prefix, "lib", "python3.14", "site-packages", "PIL", ".dylibs", "liblcms2.2.dylib"),
        os.path.expanduser("~/.local/lib/liblcms2.2.dylib"),
        "/opt/homebrew/lib/liblcms2.dylib",
        "/usr/local/lib/liblcms2.dylib",
    ]
    # Check if PIL is imported
    try:
        import PIL
        pil_dir = os.path.dirname(PIL.__file__)
        candidates.insert(0, os.path.join(pil_dir, ".dylibs", "liblcms2.2.dylib"))
        candidates.insert(1, os.path.join(pil_dir, ".dylibs", "liblcms2.dylib"))
    except Exception:
        pass

    for path in candidates:
        if os.path.exists(path):
            return path

    raise RuntimeError(f"Could not find liblcms2 dylib in candidates: {candidates}")


_LIB_PATH = _find_liblcms2()
_lcms2 = ctypes.CDLL(_LIB_PATH)

# Types
cmsHPROFILE = ctypes.c_void_p
cmsHTRANSFORM = ctypes.c_void_p
cmsContext = ctypes.c_void_p
cmsUInt32Number = ctypes.c_uint32
cmsFloat64Number = ctypes.c_double
cmsBool = ctypes.c_int

def _format_sh(pt: int, channels: int, bytes_per_sample: int, extra: int = 0) -> int:
    return (pt << 16) | (channels << 3) | (extra << 7) | bytes_per_sample

# Pixel Formats
PT_GRAY = 3
PT_RGB = 4
PT_CMYK = 6

TYPE_GRAY_8 = _format_sh(PT_GRAY, 1, 1)
TYPE_GRAY_16 = _format_sh(PT_GRAY, 1, 2)
TYPE_RGB_8 = _format_sh(PT_RGB, 3, 1)
TYPE_RGBA_8 = _format_sh(PT_RGB, 3, 1, extra=1)
TYPE_RGB_16 = _format_sh(PT_RGB, 3, 2)
TYPE_RGBA_16 = _format_sh(PT_RGB, 3, 2, extra=1)
TYPE_CMYK_8 = _format_sh(PT_CMYK, 4, 1)
TYPE_CMYK_16 = _format_sh(PT_CMYK, 4, 2)

# Rendering Intents
INTENT_PERCEPTUAL = 0
INTENT_RELATIVE_COLORIMETRIC = 1
INTENT_SATURATION = 2
INTENT_ABSOLUTE_COLORIMETRIC = 3

# Flags
cmsFLAGS_NOCACHE = 0x0040
cmsFLAGS_NOOPTIMIZE = 0x0100
cmsFLAGS_NULLTRANSFORM = 0x0200
cmsFLAGS_GAMUTCHECK = 0x1000
cmsFLAGS_SOFTPROOFING = 0x4000
cmsFLAGS_BLACKPOINTCOMPENSATION = 0x2000
cmsFLAGS_NOWHITEONWHITEFIXUP = 0x0004
cmsFLAGS_HIGHRESPRECALC = 0x0400

# Function signatures
_lcms2.cmsCreate_sRGBProfile.restype = cmsHPROFILE
_lcms2.cmsCreate_sRGBProfile.argtypes = []

_lcms2.cmsCreateNULLProfile.restype = cmsHPROFILE
_lcms2.cmsCreateNULLProfile.argtypes = []

_lcms2.cmsOpenProfileFromFile.restype = cmsHPROFILE
_lcms2.cmsOpenProfileFromFile.argtypes = [ctypes.c_char_p, ctypes.c_char_p]

_lcms2.cmsOpenProfileFromMem.restype = cmsHPROFILE
_lcms2.cmsOpenProfileFromMem.argtypes = [ctypes.c_char_p, cmsUInt32Number]

_lcms2.cmsCloseProfile.restype = cmsBool
_lcms2.cmsCloseProfile.argtypes = [cmsHPROFILE]

_lcms2.cmsCreateTransform.restype = cmsHTRANSFORM
_lcms2.cmsCreateTransform.argtypes = [
    cmsHPROFILE,
    cmsUInt32Number,
    cmsHPROFILE,
    cmsUInt32Number,
    cmsUInt32Number,
    cmsUInt32Number,
]

_lcms2.cmsCreateProofingTransform.restype = cmsHTRANSFORM
_lcms2.cmsCreateProofingTransform.argtypes = [
    cmsHPROFILE,
    cmsUInt32Number,
    cmsHPROFILE,
    cmsUInt32Number,
    cmsHPROFILE,
    cmsUInt32Number,
    cmsUInt32Number,
    cmsUInt32Number,
]

_lcms2.cmsDeleteTransform.restype = None
_lcms2.cmsDeleteTransform.argtypes = [cmsHTRANSFORM]

_lcms2.cmsDoTransform.restype = None
_lcms2.cmsDoTransform.argtypes = [
    cmsHTRANSFORM,
    ctypes.c_void_p,
    ctypes.c_void_p,
    cmsUInt32Number,
]

_lcms2.cmsSetAlarmCodes.restype = None
_lcms2.cmsSetAlarmCodes.argtypes = [ctypes.POINTER(ctypes.c_uint16)]


class LCMS2Profile:
    """Wrapper around LittleCMS2 cmsHPROFILE handle."""

    def __init__(self, handle: cmsHPROFILE, owned: bool = True):
        self._handle = handle
        self._owned = owned

    @property
    def handle(self) -> cmsHPROFILE:
        return self._handle

    @classmethod
    def create_srgb(cls) -> "LCMS2Profile":
        h = _lcms2.cmsCreate_sRGBProfile()
        if not h:
            raise RuntimeError("Failed to create sRGB profile in LittleCMS2")
        return cls(h)

    @classmethod
    def open_file(cls, path: str) -> "LCMS2Profile":
        if not os.path.exists(path):
            raise FileNotFoundError(f"ICC Profile not found at: {path}")
        h = _lcms2.cmsOpenProfileFromFile(path.encode("utf-8"), b"r")
        if not h:
            raise RuntimeError(f"LittleCMS2 could not parse ICC profile: {path}")
        return cls(h)

    @classmethod
    def open_bytes(cls, data: bytes) -> "LCMS2Profile":
        h = _lcms2.cmsOpenProfileFromMem(data, len(data))
        if not h:
            raise RuntimeError("LittleCMS2 could not parse ICC profile bytes")
        return cls(h)

    def close(self):
        if self._owned and self._handle:
            _lcms2.cmsCloseProfile(self._handle)
            self._handle = None

    def __del__(self):
        self.close()


class LCMS2Transform:
    """High-performance 16-bit / 8-bit color transform using LittleCMS2."""

    def __init__(self, handle: cmsHTRANSFORM):
        self._handle = handle

    @classmethod
    def create(
        cls,
        input_profile: LCMS2Profile,
        in_format: int,
        output_profile: LCMS2Profile,
        out_format: int,
        intent: int = INTENT_RELATIVE_COLORIMETRIC,
        flags: int = cmsFLAGS_BLACKPOINTCOMPENSATION | cmsFLAGS_HIGHRESPRECALC,
    ) -> "LCMS2Transform":
        h = _lcms2.cmsCreateTransform(
            input_profile.handle,
            in_format,
            output_profile.handle,
            out_format,
            intent,
            flags,
        )
        if not h:
            raise RuntimeError("Failed to create LittleCMS2 transform")
        return cls(h)

    @classmethod
    def create_proofing(
        cls,
        input_profile: LCMS2Profile,
        in_format: int,
        output_profile: LCMS2Profile,
        out_format: int,
        proofing_profile: LCMS2Profile,
        intent: int = INTENT_RELATIVE_COLORIMETRIC,
        proofing_intent: int = INTENT_ABSOLUTE_COLORIMETRIC,
        flags: int = cmsFLAGS_SOFTPROOFING | cmsFLAGS_HIGHRESPRECALC,
    ) -> "LCMS2Transform":
        h = _lcms2.cmsCreateProofingTransform(
            input_profile.handle,
            in_format,
            output_profile.handle,
            out_format,
            proofing_profile.handle,
            intent,
            proofing_intent,
            flags,
        )
        if not h:
            raise RuntimeError("Failed to create LittleCMS2 proofing transform")
        return cls(h)

    def transform(self, input_arr: np.ndarray, output_arr: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Execute color transformation on numpy array.
        Supports 8-bit (uint8) and 16-bit (uint16) buffers.
        """
        if not input_arr.flags["C_CONTIGUOUS"]:
            input_arr = np.ascontiguousarray(input_arr)

        num_pixels = int(np.prod(input_arr.shape[:-1]))

        if output_arr is None:
            output_arr = np.empty_like(input_arr)
        elif not output_arr.flags["C_CONTIGUOUS"]:
            output_arr = np.ascontiguousarray(output_arr)

        in_ptr = input_arr.ctypes.data_as(ctypes.c_void_p)
        out_ptr = output_arr.ctypes.data_as(ctypes.c_void_p)

        _lcms2.cmsDoTransform(self._handle, in_ptr, out_ptr, num_pixels)
        return output_arr

    def close(self):
        if self._handle:
            _lcms2.cmsDeleteTransform(self._handle)
            self._handle = None

    def __del__(self):
        self.close()
