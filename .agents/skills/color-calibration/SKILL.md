---
name: color-calibration
description: >-
  Use this skill when the user asks to calibrate, profile, or linearize the Canon G640 printer, generate or print profiling targets, create or optimize ICC paper profiles with ArgyllCMS, process target scans, or configure ink limits and warm biases.
---

# Canon G640 Color Calibration & Profiling

This skill provides the complete end-to-end runbook for generating custom ICC paper profiles for the Canon PIXMA G640 using ArgyllCMS and optical flatbed scan or spectrophotometer measurements.

---

## Quick Reference Commands

| Task | Command |
| :--- | :--- |
| **Print 80p Target (10x15)** | `./g640rip_cli.py print-target targets/G640_10x15_80p_i1.tif --media glossy --size 10x15` |
| **Print 160p Target (10x15)** | `./g640rip_cli.py print-target targets/G640_10x15_160p_i1_01.tif --media glossy --size 10x15` |
| **Process Scan & Make ICC (100%)** | `python3 process_scan_and_make_icc.py --scan scan.tif --strength 1.0` |
| **Process Scan & Make ICC (70% Blend)** | `python3 process_scan_and_make_icc.py --scan scan.tif --strength 0.70` |
| **Adjust Neutral Warmth** | `python3 process_scan_and_make_icc.py --scan scan.tif --strength 1.0 --bias-factor 0.50 --warmth 0.5` |
| **Generate New Targets** | `.agents/skills/color-calibration/scripts/generate_targets.sh 80 10x15 MyTarget` |

---

## End-to-End Calibration Procedure

### Step 1: Select and Print the Calibration Target
Choose the target resolution based on paper size and required profiling accuracy:
- **80 Patches (Fast single-sheet 10x15)**: `targets/G640_10x15_80p_i1.tif`
- **160 Patches (2 sheets 10x15 / 1 sheet A4)**: `targets/G640_10x15_160p_i1_01.tif` + `_02.tif`
- **240 Patches (High-precision)**: `targets/G640_10x15_240p_i1_01.tif` through `_03.tif`

Print the target using **pure 1:1 hardware bypass (zero CMS)**:
```bash
./g640rip_cli.py print-target targets/G640_10x15_80p_i1.tif \
  --media glossy \
  --size 10x15 \
  --backend cups_raw
```
> [!IMPORTANT]
> Never print profiling targets through standard photo viewers or AirPrint dialogs, as macOS ColorSync will silently apply printer color matching.

---

### Step 2: Drying and Outgassing
Allow the printed target to dry and stabilize:
- **Dye Ink Glossy Papers (PP-201 / Luster)**: Minimum **15 to 30 minutes** before scanning or measuring.
- Colors shift significantly during the first 10 minutes as solvent carriers evaporate.

---

### Step 3: Capture Target Measurements

#### Option A: Flatbed Scanner Workflow (Automated)
1. Place the printed chart on the scanner platen glass aligned to the top-left corner.
2. Scan at **600 DPI, 24-bit RGB (or 48-bit TIFF)** with all auto-enhancements, unsharp masking, and auto-exposure disabled.
3. Save as uncompressed TIFF (e.g. `scan_target.tif`).
4. Run the automated processing engine:
   ```bash
   python3 process_scan_and_make_icc.py \
     --scan scan_target.tif \
     --ti2 targets/G640_10x15_80p_i1.ti2 \
     --strength 1.0 \
     --bias-factor 0.50
   ```
   *Features automatically applied*:
   - Optical flare compensation (restores $L^* \approx 3.0$ / $D_{\max} \ge 2.40$).
   - Bradford D65 to D50 chromatic adaptation.
   - Neutral-axis scanner chromatic neutralization (50% bias balance).
   - Generates Argyll `.ti3` and calls `colprof` to build the `.icc` profile.
   - Automatically installs to `~/Library/ColorSync/Profiles/`.

#### Option B: Spectrophotometer Workflow (i1Pro / ColorMunki)
```bash
cd targets
chartread -v -N G640_10x15_80p_i1
colprof -v -D "Canon G640 Custom" -qm -al -cmt -dpc -V 2.0 G640_10x15_80p_i1
```

---

### Step 4: Calibrating Balance & Warmth

If the resulting prints require fine-tuning:
1. **Skin Tone Warmth**:
   - If prints feel slightly too cool:
     ```bash
     python3 process_scan_and_make_icc.py --scan scan.tif --strength 1.0 --warmth 0.5
     ```
   - If prints feel too warm/red:
     ```bash
     python3 process_scan_and_make_icc.py --scan scan.tif --strength 1.0 --warmth -0.5
     ```
2. **Color Correction Blending**:
   - `1.0` (100%): Mathematically strict color matching.
   - `0.70` (70%): Blends 70% measured scan with 30% nominal target in Lab space; retains slightly richer saturation while maintaining hue accuracy.

---

### Step 5: Verify the Calibrated Profile
Immediately audit the new profile using the verification skill:
```bash
python3 .agents/skills/color-verification/scripts/verify_profile.py targets/Canon_G640_10x15_Glossy2.icc
```

Target benchmarks:
- **Mean $\Delta E_{00} \le 0.80$**
- **Max $\Delta E_{00} \le 2.50$**
- **$D_{\max} \ge 2.20$** ($L^*_{\min} \le 4.5$)

---

## Detailed References

- [Calibration Pipeline Architecture](./references/calibration_workflow.md)
