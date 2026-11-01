#!/usr/bin/env python3
"""
Process flatbed scanned calibration chart (IMG_20261101_0001.tif)
and generate an ICC profile using ArgyllCMS colprof.
"""

import os
import sys
import subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont

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

def main():
    scan_file = "IMG_20261101_0001.tif"
    ti2_file = "targets/G640_10x15_80p_i1.ti2"
    base_name = "Canon_G640_10x15_Glossy2"
    ti3_file = f"targets/{base_name}.ti3"
    icc_file = f"targets/{base_name}.icc"
    
    if not os.path.exists(scan_file):
        print(f"Error: Scan file {scan_file} not found!")
        sys.exit(1)
    if not os.path.exists(ti2_file):
        print(f"Error: Target definition {ti2_file} not found!")
        sys.exit(1)

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
            
            # Trimmed mean: discard lowest 5% and highest 5% along each channel to filter scanner dust/scratches
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

            # Draw green bounding box on verification image
            draw.rectangle([cx-sample_r, cy-sample_r, cx+sample_r, cy+sample_r], outline=(0, 255, 0), width=3)
            draw.text((cx-sample_r+2, cy-sample_r+2), loc, fill=(0, 255, 0))

    # Save verification thumbnail
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
                ti2_records.append((sid, loc, r, g, b))

    print(f"   Matched {len(ti2_records)} target definitions with measured patches.")

    # Generate Argyll TI3 file
    print(f"5. Writing Argyll CGATS .ti3 file: {ti3_file}...")
    with open(ti3_file, "w") as f:
        f.write("CTI3\n\n")
        f.write(f'DESCRIPTOR "Canon G640 10x15 Photo Paper Plus Glossy II Profile Data"\n')
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
        
        for sid, loc, r, g, b in ti2_records:
            meas = patch_measurements.get(loc)
            if not meas:
                print(f"Error: Missing measurement for patch {loc}!")
                sys.exit(1)
            xyz = meas["xyz"]
            f.write(f"{sid:3d} {r:9.4f} {g:9.4f} {b:9.4f} {xyz[0]:9.4f} {xyz[1]:9.4f} {xyz[2]:9.4f}\n")
        
        f.write('END_DATA\n')

    # Run ArgyllCMS colprof
    print("6. Executing ArgyllCMS colprof to generate custom ICC profile...")
    colprof_cmd = [
        "colprof",
        "-v",
        "-D", "Canon G640 10x15 Photo Paper Plus Glossy II",
        "-qm",     # Medium quality cLUT
        "-al",     # Lab cLUT algorithm (standard for printer output profiles)
        "-cmt",    # Monitor in typical environment
        "-dpp",    # Practical reflection print
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
