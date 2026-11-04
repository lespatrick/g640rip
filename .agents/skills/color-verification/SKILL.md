---
name: color-verification
description: >-
  Use this skill when the user asks to verify, validate, or audit color reproduction accuracy, compute Delta E (ΔE00/ΔE76) error statistics, evaluate neutral gray balance, test maximum black density (Dmax), or perform soft proofing and gamut checks for the Canon G640.
---

# Color Reproduction & Profile Verification

This skill provides the complete verification runbook and tooling to audit color rendition, quantify profile accuracy ($\Delta E_{00}$), inspect neutral gray balance, and visually validate physical prints produced by the Canon PIXMA G640 Micro-RIP.

---

## Quick Reference Commands

| Task | Command |
| :--- | :--- |
| **Verify Closed-Loop Print Scan** | `python3 .agents/skills/color-verification/scripts/verify_scan_reproduction.py --scan <scan.tif>` |
| **Verify QA Control Strip Colors** | `python3 .agents/skills/color-verification/scripts/verify_control_strip.py <scan.tif>` |
| **Calculate Print Offsets & Margins** | `python3 .agents/skills/color-verification/scripts/calculate_scan_offsets.py <scan.tif>` |
| **Verify ICC Profile (Data vs Profile)** | `python3 .agents/skills/color-verification/scripts/verify_profile.py <profile.icc>` |
| **Interactive 3D Gamut** | `python3 .agents/skills/color-verification/scripts/verify_profile.py <profile.icc> --html-gamut` |
| **Argyll profcheck** | `profcheck -v2 -k targets/<target>.ti3 targets/<profile>.icc` |
| **Soft Proof & Gamut Check** | `./g640rip_cli.py proof <image.tif> --profile targets/<profile>.icc --out-proof proof.png --out-gamut gamut.png` |
| **Generate Visual QA Target** | `python3 .agents/skills/color-verification/scripts/generate_control_strip.py --size 4x6` |
| **Print QA Target** | `./g640rip_cli.py print targets/QA_Control_Strip_4x6.png --profile targets/<profile>.icc --media glossy --size 4x6` |

---

## Verification Workflows

### 1. Closed-Loop Physical Print Verification (From Scan)

When evaluating a verification target printed **WITH** an active ICC profile:

```bash
python3 .agents/skills/color-verification/scripts/verify_scan_reproduction.py \
  --scan verification_scan.tif \
  --ti2 targets/G640_10x15_80p_i1.ti2 \
  --out-json targets/verification_residuals.json
```

- Samples all 88 patches from the 600 DPI scan.
- Corrects for scanner optical flare and adapts to D50.
- Compares measured physical print Lab against nominal target Lab from `.ti2`.
- Outputs full CIEDE2000 statistics, neutral tracking, and exports residual vectors for iterative profile refinement.

---

### 2. Numerical Profile Verification (Data vs Profile)

Run the verification tool on any generated ICC profile:

```bash
python3 .agents/skills/color-verification/scripts/verify_profile.py targets/<profile>.icc
```

#### What it measures:
1. **Mean $\Delta E_{00}$**: Average perceptual color error across all target patches.
   - $\le 0.80$: **PASS** (Master Photographic Quality).
   - $0.80 - 1.50$: Good commercial proofing.
   - $> 2.00$: Noticeable drift; re-profiling recommended.
2. **Peak $\Delta E_{00}$ (Max)**: Worst-case outlier patch error (tolerance $\le 3.00$).
3. **95th Percentile $\Delta E_{00}$**: 95% of all colors fall below this value (tolerance $\le 1.80$).
4. **Minimum Black Level ($L^*_{\min}$)** & **Maximum Optical Density ($D_{\max}$)**:
   - Evaluates black depth on glossy/luster paper ($L^* \le 3.5$, $D_{\max} \ge 2.20$).
5. **Neutral Gray Balance ($\Delta C^*$)**:
   - Assesses chromatic cast ($a^*, b^*$) along the 21-step neutral axis from deep shadow to paper white.

---

### 2. Digital Soft Proofing & Gamut Audit

Before sending files to the printer, verify how out-of-gamut colors will compress and how paper base white affects highlights.

#### Relative Colorimetric + BPC (Standard Photo Mode):
```bash
./g640rip_cli.py proof input_photo.jpg \
  --profile targets/<profile>.icc \
  --no-paper-white \
  --out-proof proof_rel.png \
  --out-gamut gamut_mask.png
```

#### Absolute Colorimetric (Simulate Paper Base Tint):
```bash
./g640rip_cli.py proof input_photo.jpg \
  --profile targets/<profile>.icc \
  --out-proof proof_paper_white.png
```

- **Gamut Warning**: Inspect `gamut_mask.png`. Out-of-gamut pixels are highlighted in neon red/magenta. If $> 5\%$ of the image is out of gamut, consider Perceptual intent to smoothly roll off saturated hues.

---

### 3. Visual Print QA (Control Strip Inspection)

1. Generate the standard 600 DPI QA Control Strip:
   ```bash
   python3 .agents/skills/color-verification/scripts/generate_control_strip.py --size 4x6
   ```
2. Print the target with your active profile:
   ```bash
   ./g640rip_cli.py print targets/QA_Control_Strip_4x6.png \
     --profile targets/<profile>.icc \
     --media glossy \
     --size 4x6 \
     --fit-mode compensate
   ```
3. Allow the print to dry for 10 minutes.
4. Inspect under standard D50 (5000K) illumination:
   - **Neutral Step Wedge**: Look for unwanted greenish or reddish shifts across the 21 steps.
   - **Continuous Gradients**: Ensure no stair-stepping, posterization, or color solarization in smooth sky/skin transitions.
   - **Shadows**: Verify steps $1\%$ and $2\%$ are clearly discernible from $0\%$ solid black.
   - **Highlights**: Verify steps $97\%$ and $98\%$ have visible tone before hitting $100\%$ paper white.
   - **Skin Swatches**: Verify natural Caucasian and deep skin tones match calibrated reference.

---

## Detailed References

- [Photographic Standards & Tolerances](./references/verification_standards.md)

