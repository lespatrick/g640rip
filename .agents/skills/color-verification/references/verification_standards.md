# Photographic Color Reproduction & Verification Standards

This document outlines the numerical tolerances, evaluation methods, and visual quality benchmarks used in verifying ICC paper profiles and print output on the Canon PIXMA G640.

---

## 1. Delta E Tolerances (CIEDE2000 vs CIE76)

In photographic fine art and proof printing, **CIEDE2000 ($\Delta E_{00}$)** is the gold standard because it accounts for human perceptual non-linearities in neutral grays, blue-purple hue rotations, and high-chroma saturation shifts.

| Quality Grade | Mean $\Delta E_{00}$ | 95th Percentile $\Delta E_{00}$ | Max Peak $\Delta E_{00}$ | Application |
| :--- | :---: | :---: | :---: | :--- |
| **Master Photographic** | $\le 0.60$ | $\le 1.50$ | $\le 2.20$ | Gallery exhibition prints, critical portraiture, high-end fine art. |
| **ISO 12647-7 Contract Proof** | $\le 1.00$ | $\le 1.80$ | $\le 2.50$ | Commercial contract proofing standards (Fogra Cert). |
| **Good Commercial Print** | $\le 1.80$ | $\le 2.80$ | $\le 4.00$ | Standard lab photo prints, commercial books. |
| **Requires Recalibration** | $> 2.00$ | $> 3.50$ | $> 5.00$ | Noticeable color drift, mismatched paper/ink batches. |

---

## 2. Neutral Axis & Gray Balance Tracking ($\Delta C^*$)

A printer profile can have an acceptable overall $\Delta E$ while still showing disturbing color casts in monochrome or portrait shadows. The neutral gray ramp must be strictly evaluated:

$$\Delta C^* = \sqrt{(a^*)^2 + (b^*)^2}$$

- **Target Chroma**: For a pure neutral gray ramp under D50, ideal $a^* \approx 0.0$ and $b^* \approx 0.0$ (or matching paper base white tint).
- **Tolerance**:
  - Highlights ($L^* > 80$): $\Delta C^* \le 1.2$
  - Midtones ($L^* \in [40, 80]$): $\Delta C^* \le 1.5$
  - Deep Shadows ($L^* < 40$): $\Delta C^* \le 1.8$
- **Cast Identification**:
  - $+a^*$: Magenta / Red cast
  - $-a^*$: Green cast
  - $+b^*$: Warm / Yellow cast
  - $-b^*$: Cool / Blue cast

---

## 3. Dynamic Range & Black Point ($D_{\max}$)

Optical density ($D$) measures the light absorption capability of the printed ink film:

$$D = -\log_{10}\left(\frac{Y}{100}\right)$$

Where $Y$ is the CIE tristimulus value (0 to 100):

| Media Type | Target $L^*_{\min}$ | Minimum $D_{\max}$ | Notes |
| :--- | :---: | :---: | :--- |
| **Photo Glossy II / Luster** | $\le 3.50$ | $\ge 2.25$ | Deepest photographic blacks (Dye ink gloss absorption). |
| **Semi-Gloss / Satin** | $\le 4.50$ | $\ge 2.05$ | Rich blacks with reduced specular glare. |
| **Matte Fine Art Paper** | $\le 14.0$ | $\ge 1.60$ | Uncoated rag/cellulose base scatters light. |

---

## 4. Visual Inspection Checklist under D50 (5000K)

Always evaluate physical prints under standard ISO 3664 viewing conditions (D50, CRI $\ge 95$, 500 lux):
1. **Skin Tones**: Check Caucasian and dark skin tones on the QA Control Strip for unnatural jaundice (excess yellow) or sunburn (excess magenta).
2. **Shadow Separation**: Check the 0% to 5% step wedge. Steps 1% and 2% should be distinguishable from pure black 0% under direct light without crushing.
3. **Highlight Separation**: Check the 95% to 99% step wedge. Steps should have tone distinct from unprinted paper white (100%).
4. **Metamerism & Bronzing**: View the print at an oblique $45^\circ$ angle. The ChromaLife100+ dye ink should show zero bronzing (metallic sheen) on glossy media.

