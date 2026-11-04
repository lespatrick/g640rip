# Canon G640 Color Calibration & Profiling Architecture

This document covers the deep technical details of the Canon PIXMA G640 profiling pipeline: flatbed scanner compensation, chromatic adaptation, cLUT optimization, and ink limiting.

---

## 1. Zero Color Management Target Printing

To capture the true physical response of the printer hardware, paper, and dye ink:
- **Quartz / ColorSync Bypass**: macOS ColorSync must NOT alter RGB values before printing.
- **Apple Raster (URF) 600 DPI**: The Micro-RIP encodes uncompressed Apple Raster streams sent directly over IPP or raw CUPS queue (`-o raw`).
- **Media Settings**:
  - `glossy` / `plus_glossy_ii`: Maps to Canon BJL media code `com.canon.mtgr` (Photo Paper Plus Glossy II).
  - Print Quality: `high` (Mode 4 high-density micro-droplet pass).

---

## 2. Flatbed Scanner vs. Spectrophotometer Profiling

### Why Flatbed Scanners Require Mathematical Compensation:
1. **Optical Flare (Stray Light Reflections)**:
   Glossy photo paper on platen glass causes internal reflections between the scanner CCD lamp and paper surface. This falsely elevates deep black from true $L^* \approx 3.0$ ($Y \approx 0.35\%$) up to $L^* \approx 8.0$ ($Y \approx 0.90\%$).
   *Fix*: `flare_compensate_xyz()` in `process_scan_and_make_icc.py` subtracts optical flare from low-luminance patches, restoring true deep photographic Dmax ($D \ge 2.40$).
2. **Illuminant Mismatch (D65 to D50)**:
   Scanners use LED/CCFL lamps calibrated to CIE D65 ($6500K$). ICC profile PCS (Profile Connection Space) requires CIE D50 ($5000K$).
   *Fix*: Bradford Chromatic Adaptation Matrix transforms scanned XYZ coordinates accurately to D50.
3. **Sensor Chromatic Bias (Neutral Axis Drift)**:
   RGB scanner sensors often introduce slight chromatic bias (e.g. slight warm or cool shift) across neutral tones.
   *Fix*: `--bias-factor` parameter (default `0.50`) evaluates the neutral gray step wedge ($R=G=B$) and neutralizes scanner sensor drift across lightness $L^* \in [0, 100]$.

---

## 3. ArgyllCMS `colprof` Parameter Optimization

When building the final ICC cLUT (color lookup table) via `colprof`, the following flags are optimized for photographic output on the G640:

```bash
colprof \
  -v \
  -D "Canon G640 10x15 Photo Paper Plus Glossy II" \
  -qm \          # Medium quality cLUT grid (33x33x33 nodes)
  -al \          # Lab cLUT PCS algorithm (smoother gradients than XYZ)
  -cmt \         # Monitor viewing environment (typical D50 proofing)
  -dpc \         # Critical print evaluation environment P1 (shadow contrast preservation)
  -V 2.0 \       # Dark region cLUT density emphasis (prevents shadow crushing)
  -O output.icc \
  target_base
```

### Key Parameters:
- `-al`: Lab-based PCS interpolation ensures perceptual linearity in smooth skin tones and gradient ramps.
- `-dpc`: Selects critical print evaluation intent, preserving tone separation in dark shadows ($L^* < 15$).
- `-V 2.0`: Increases grid density in shadow regions to exploit the high dynamic range ($D_{\max} \ge 2.4$) of ChromaLife100+ black ink.

---

## 4. Fine-Tuning Parameters

| Parameter | Tool / Flag | Range | Description |
| :--- | :--- | :---: | :--- |
| **Color Correction Strength** | `--strength` (`-s`) | `0.1` - `1.0` | Blends nominal target values with measured scan in Lab space. Default `1.0` (100% correction). Setting `0.70` (70%) retains more native warmth while correcting hue errors. |
| **Scanner Neutral Bias** | `--bias-factor` | `0.0` - `1.0` | Fraction of neutral axis scanner chromatic bias neutralized. `0.50` (50%) is the calibrated balance between raw scan and full neutral correction. |
| **Warmth Offset** | `--warmth` | `-2.0` - `+2.0` | Fine manual bias in $b^*$ and $a^*$ to inject additional yellow/red dye ink into portraits. |
| **Total Ink Limit (TIL)** | `--ink-limit` | `0.50` - `1.0` | Restricts maximum multi-channel ink volume to prevent ink pooling or bleeding on lighter paper stocks. |
| **Contrast Boost** | `--contrast` | `0.0` - `0.25` | S-curve contrast gamma boost applied in production engine without clipping white or black points. |

