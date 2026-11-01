#!/usr/bin/env python3
"""
Process flatbed scanned calibration chart (IMG_20261101_0001.tif)
and generate an ICC profile using ArgyllCMS colprof.

Supports configurable color correction strength (e.g. 70% color correction)
and optional ink limiting.
"""

import os
import sys
import argparse
import subprocess
import numpy as np
from PIL import Image, ImageDraw

from g640rip.color.ink_limit import InkLimiter


def srgb_to_xyz(rgb):
    """Convert sRGB [0..255] to CIE XYZ (D50 Bradford adapted) [0..100]."""
    rgb = np.array(rgb, dtype=float) / 255.0
    mask = rgb <= 0.04045
    lin = np.empty_like(rgb)
    lin[mask] = rgb[mask] / 12.92
    lin[~mask] = ((rgb[~mask] + 0.055) / 1.055) ** 2.4
    
    # sRGB to XYZ (D50 Bradford adapted) matrix
    M = np.array([
        [0.4360747, 0.3850649, 0.1430804],
        [0.2225045, 0.7168786, 0.0606169],
        [0.0139322, 0.0971045, 0.7141733]
    ])
    xyz = np.dot(M, lin) * 100.0
    return xyz


def xyz_to_lab(xyz):
    """Convert CIE XYZ (D50) to CIE L*a*b* (D50)."""
    Xn, Yn, Zn = 96.422, 100.000, 82.521
    x = xyz[0] / Xn
    y = xyz[1] / Yn
    z = xyz[2] / Zn
    
    delta = 6.0 / 29.0
    def f(t):
        return np.where(t > delta**3, t ** (1.0/3.0), t / (3 * delta**2) + 4.0/29.0)
    
    fx = f(x)
    fy = f(y)
    fz = f(z)
    
    L = 116.0 * fy - 16.0
    a = 500.0 * (fx - fy)
    b = 200.0 * (fy - fz)
    return np.array([L, a, b])


def lab_to_xyz(lab):
    """Convert CIE L*a*b* (D50) to CIE XYZ (D50)."""
    Xn, Yn, Zn = 96.422, 100.000, 82.521
    L, a, b = lab[0], lab[1], lab[2]
    fy = (L + 16.0) / 116.0
    fx = a / 500.0 + fy
    fz = fy - b / 200.0
    
    delta = 6.0 / 29.0
    def f_inv(t):
        return np.where(t > delta, t ** 3, 3 * delta**2 * (t - 4.0/29.0))
    
    x = f_inv(fx) * Xn
    y = f_inv(fy) * Yn
    z = f_inv(fz) * Zn
    return np.array([x, y, z])


def main():
    parser = argparse.ArgumentParser(description="Process scanned target chart and create ICC profile.")
    parser.add_argument("--scan", default="IMG_20261101_0001.tif", help="Scanned chart TIFF image")
    parser.add_argument("--ti2", default="targets/G640_10x15_80p_i1.ti2", help="Target definition file")
    parser.add_argument("--strength", "--correction-strength", "-s", type=float, default=1.0, help="Color correction strength fraction [0.1..1.0] (default: 1.0 = 100%% correction, 0.70 = 70%% correction)")
    parser.add_argument("--ink-limit", type=float, default=1.0, help="Optional ink limit fraction [0.5..1.0] (default: 1.0 = no limit)")
    parser.add_argument("--name", default=None, help="Custom base name for output profile")
    args = parser.parse_args()

    scan_file = args.scan
    ti2_file = args.ti2
    strength = float(np.clip(args.strength, 0.05, 1.0))
    strength_pct = int(round(strength * 100))
    
    if args.name:
        base_name = args.name
    elif strength < 1.0:
        base_name = f"Canon_G640_10x15_Glossy2_70corr" if strength_pct == 70 else f"Canon_G640_10x15_Glossy2_{strength_pct}corr"
    else:
        base_name = "Canon_G640_10x15_Glossy2"

    ti3_file = f"targets/{base_name}.ti3"
    icc_file = f"targets/{base_name}.icc"
    desc_str = f"Canon G640 10x15 Photo Paper Plus Glossy II" + (f" ({strength_pct}% Color Correction)" if strength < 1.0 else "")

    if not os.path.exists(scan_file):
        print(f"Error: Scan file {scan_file} not found!")
        sys.exit(1)
    if not os.path.exists(ti2_file):
        print(f"Error: Target definition {ti2_file} not found!")
        sys.exit(1)

    print(f"=== Canon G640 Target Scanner & ICC Builder (Color Correction: {strength_pct}%) ===")
    print(f"1. Loading scanned chart: {scan_file}...")
    scan_img = Image.open(scan_file)
    print(f"   Raw dimensions: {scan_img.size}, mode: {scan_img.mode}")

    # Rotate 180 degrees to match target layout
    print("2. Orienting scan (180° rotation)...")
    scan_180 = scan_img.rotate(180, expand=True)
    arr_s = np.array(scan_180)

    # Grid parameters
    strip_names = ["A", "B", "C", "D", "E", "F", "G", "H"]
    col_centers = [641, 830, 1019, 1208, 1397, 1586, 1775, 1964]
    row_centers = [586, 846, 1106, 1366, 1627, 1888, 2136, 2395, 2668, 2928, 3188]
    sample_r = 25  # 50x50 pixel sampling region (patch is ~188x236 px)

    # Prepare verification image
    vis_img = scan_180.copy()
    draw = ImageDraw.Draw(vis_img)

    # Sample all 88 patches
    print("3. Sampling patches from calibrated 600 DPI scan...")
    patch_measurements = {}
    for r_idx, cy in enumerate(row_centers):
        for c_idx, cx in enumerate(col_centers):
            loc = f"{strip_names[c_idx]}{r_idx+1}"
            box = arr_s[cy-sample_r:cy+sample_r, cx-sample_r:cx+sample_r]
            
            # Trimmed mean: discard lowest 5% and highest 5% along each channel
            pixels = box.reshape(-1, 3)
            rgb_mean = np.zeros(3)
            for ch in range(3):
                p_ch = np.sort(pixels[:, ch])
                n_trim = int(len(p_ch) * 0.05)
                rgb_mean[ch] = np.mean(p_ch[n_trim:-n_trim] if n_trim > 0 else p_ch)

            xyz = srgb_to_xyz(rgb_mean)
            lab = xyz_to_lab(xyz)
            patch_measurements[loc] = {
                "rgb_raw": rgb_mean,
                "xyz": xyz,
                "lab": lab,
                "cx": cx,
                "cy": cy,
            }

            draw.rectangle([cx-sample_r, cy-sample_r, cx+sample_r, cy+sample_r], outline=(0, 255, 0), width=3)
            draw.text((cx-sample_r+2, cy-sample_r+2), loc, fill=(0, 255, 0))

    vis_out = "targets/scan_patches_verification.jpg"
    vis_img.thumbnail((1200, 1800))
    vis_img.save(vis_out, quality=85)
    print(f"   Saved patch verification overlay to {vis_out}")

    # Read original TI2 file
    print(f"4. Reading Argyll target definitions from {ti2_file}...")
    ti2_records = []
    with open(ti2_file, "r") as f:
        in_data = False
        for line in f:
            line_str = line.strip()
            if line_str == "BEGIN_DATA":
                in_data = True
                continue
            if line_str == "END_DATA":
                break
            if in_data and line_str:
                parts = line_str.split()
                sid = int(parts[0])
                loc = parts[1].strip("\"")
                r, g, b = float(parts[2]), float(parts[3]), float(parts[4])
                exp_x, exp_y, exp_z = float(parts[5]), float(parts[6]), float(parts[7])
                ti2_records.append((sid, loc, r, g, b, exp_x, exp_y, exp_z))

    print(f"   Matched {len(ti2_records)} target definitions with measured patches.")

    # Apply Ink Limiting if specified
    limiter = None
    if args.ink_limit < 1.0:
        knee = max(0.40, args.ink_limit - 0.10)
        limiter = InkLimiter(max_total_ink=args.ink_limit, soft_knee=knee)
        print(f"   Applied Ink Limiter to target RGB: Max={int(args.ink_limit*100)}%")

    # Generate Argyll TI3 file with blended color correction
    print(f"5. Writing Argyll CGATS .ti3 file: {ti3_file}...")
    if strength < 1.0:
        print(f"   Blending color correction at {strength_pct}% strength (30% nominal target + 70% measured scan in L*a*b* space)...")
    with open(ti3_file, "w") as f:
        f.write("CTI3\n\n")
        f.write(f'DESCRIPTOR "{desc_str}"\n')
        f.write('ORIGINATOR "g640RIP Target Scanner Engine"\n')
        f.write('CREATED "Sun Nov  1 2026"\n')
        f.write('KEYWORD "DEVICE_CLASS"\n')
        f.write('DEVICE_CLASS "OUTPUT"\n')
        f.write('KEYWORD "COLOR_REP"\n')
        f.write('COLOR_REP "RGB_XYZ"\n\n')
        f.write('NUMBER_OF_FIELDS 7\n')
        f.write('BEGIN_DATA_FORMAT\n')
        f.write('SAMPLE_ID RGB_R RGB_G RGB_B XYZ_X XYZ_Y XYZ_Z\n')
        f.write('END_DATA_FORMAT\n\n')
        f.write(f'NUMBER_OF_SETS {len(ti2_records)}\n')
        f.write('BEGIN_DATA\n')
        
        for sid, loc, r, g, b, exp_x, exp_y, exp_z in ti2_records:
            meas = patch_measurements.get(loc)
            if not meas:
                print(f"Error: Missing measurement for patch {loc}!")
                sys.exit(1)
            
            xyz_meas = meas["xyz"]
            lab_meas = meas["lab"]

            # Blend color correction in Lab space
            if strength < 1.0:
                xyz_exp = np.array([exp_x, exp_y, exp_z])
                lab_exp = xyz_to_lab(xyz_exp)
                # Linear blend between expected target Lab and scanned measured Lab
                lab_blended = (1.0 - strength) * lab_exp + strength * lab_meas
                xyz_final = lab_to_xyz(lab_blended)
            else:
                xyz_final = xyz_meas

            # If ink limited, transform RGB sent to device
            r_dev, g_dev, b_dev = r, g, b
            if limiter is not None:
                rgb_arr = np.array([[[int(round(r * 2.55)), int(round(g * 2.55)), int(round(b * 2.55))]]], dtype=np.uint8)
                rgb_lim = limiter.apply_rgb(rgb_arr)
                r_dev = float(rgb_lim[0, 0, 0]) / 2.55
                g_dev = float(rgb_lim[0, 0, 1]) / 2.55
                b_dev = float(rgb_lim[0, 0, 2]) / 2.55

            f.write(f"{sid:3d} {r_dev:9.4f} {g_dev:9.4f} {b_dev:9.4f} {xyz_final[0]:9.4f} {xyz_final[1]:9.4f} {xyz_final[2]:9.4f}\n")
        
        f.write('END_DATA\n')

    # Run ArgyllCMS colprof
    print("6. Executing ArgyllCMS colprof to generate custom ICC profile...")
    colprof_cmd = [
        "colprof",
        "-v",
        "-D", desc_str,
        "-qm",     # Medium quality cLUT
        "-al",     # Lab cLUT algorithm
        "-cmt",    # Monitor in typical environment
        "-dpp",    # Practical reflection print
        "-O", icc_file,
        f"targets/{base_name}"
    ]
    print(f"   Command: {' '.join(colprof_cmd)}")
    subprocess.run(colprof_cmd, check=True)

    if os.path.exists(icc_file):
        print(f"\n[SUCCESS] Generated ICC Profile: {icc_file}")
        
        # Install to macOS system ColorSync directory
        colorsync_dir = os.path.expanduser("~/Library/ColorSync/Profiles")
        os.makedirs(colorsync_dir, exist_ok=True)
        dest_icc = os.path.join(colorsync_dir, f"{base_name}.icc")
        import shutil
        shutil.copy2(icc_file, dest_icc)
        print(f"[INSTALLED] Installed profile to: {dest_icc}")
        print("Profile is now active and selectable in the G640 RIP Web UI & CLI!")
    else:
        print(f"Error: Expected output ICC file {icc_file} was not created!")
        sys.exit(1)


if __name__ == "__main__":
    main()
