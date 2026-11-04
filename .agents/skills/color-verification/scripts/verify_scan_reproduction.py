#!/usr/bin/env python3
"""
Closed-Loop Color Reproduction Verification Engine for Canon G640.
Processes a flatbed scan of a verification target printed WITH an ICC profile,
and compares measured physical color against nominal target values (CIEDE2000).

Outputs:
- Real-world printed ΔE00 statistics (Mean, 95th percentile, Max)
- Neutral gray tracking error & chromatic cast
- Dmax and black point verification
- Residual error vectors exported to JSON for iterative profile refinement
"""

import os
import sys
import json
import argparse
import numpy as np
from PIL import Image, ImageDraw
from typing import Dict, List, Any, Tuple

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    console = Console()
except ImportError:
    console = None


# Bradford chromatic adaptation matrix: CIE D65 -> CIE D50
BRADFORD_D65_TO_D50 = np.array([
    [ 1.0478112,  0.0228866, -0.0501270],
    [ 0.0295424,  0.9904844, -0.0170491],
    [-0.0092345,  0.0150436,  0.7521316]
])


def adapt_d65_to_d50(xyz: np.ndarray) -> np.ndarray:
    """Adapt CIE XYZ values under D65 illuminant to CIE D50 using Bradford transform."""
    return np.dot(BRADFORD_D65_TO_D50, xyz)


def srgb_to_xyz(rgb: np.ndarray) -> np.ndarray:
    """Convert sRGB [0..255] to CIE XYZ (D50 Bradford adapted) [0..100]."""
    rgb = np.array(rgb, dtype=float) / 255.0
    mask = rgb <= 0.04045
    lin = np.empty_like(rgb)
    lin[mask] = rgb[mask] / 12.92
    lin[~mask] = ((rgb[~mask] + 0.055) / 1.055) ** 2.4

    M = np.array([
        [0.4360747, 0.3850649, 0.1430804],
        [0.2225045, 0.7168786, 0.0606169],
        [0.0139322, 0.0971045, 0.7141733]
    ])
    return np.dot(M, lin) * 100.0


def xyz_to_lab(xyz: np.ndarray) -> np.ndarray:
    """Convert CIE XYZ (D50) to CIE L*a*b* (D50)."""
    Xn, Yn, Zn = 96.422, 100.000, 82.521
    x = xyz[0] / Xn
    y = xyz[1] / Yn
    z = xyz[2] / Zn

    delta = 6.0 / 29.0
    def f(t):
        return np.where(t > delta**3, t ** (1.0/3.0), t / (3 * delta**2) + 4.0/29.0)

    fx, fy, fz = f(x), f(y), f(z)
    L = 116.0 * fy - 16.0
    a = 500.0 * (fx - fy)
    b = 200.0 * (fy - fz)
    return np.array([L, a, b])


def flare_compensate_xyz(xyz: np.ndarray, flare_amount: float = 0.52) -> np.ndarray:
    """Compensate for flatbed scanner optical stray light reflections."""
    x, y, z = float(xyz[0]), float(xyz[1]), float(xyz[2])
    flare_factor = (1.0 - np.clip(y / 100.0, 0.0, 1.0))
    y_corr = max(0.35, y - flare_amount * flare_factor)
    scale = y_corr / max(y, 1e-5)
    return np.array([max(0.30, x * scale), y_corr, max(0.25, z * scale)])


def ciede2000(lab1: np.ndarray, lab2: np.ndarray, kL: float = 1.0, kC: float = 1.0, kH: float = 1.0) -> float:
    """
    Calculate CIEDE2000 color difference between two CIE L*a*b* colors.
    Complies with ISO/CIE 11664-6:2014.
    """
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2

    C1 = np.sqrt(a1**2 + b1**2)
    C2 = np.sqrt(a2**2 + b2**2)
    C_bar = (C1 + C2) / 2.0

    G = 0.5 * (1.0 - np.sqrt(C_bar**7 / (C_bar**7 + 25.0**7)))
    a1_prime = (1.0 + G) * a1
    a2_prime = (1.0 + G) * a2

    C1_prime = np.sqrt(a1_prime**2 + b1**2)
    C2_prime = np.sqrt(a2_prime**2 + b2**2)

    h1_prime = np.degrees(np.arctan2(b1, a1_prime)) % 360.0
    h2_prime = np.degrees(np.arctan2(b2, a2_prime)) % 360.0

    delta_L_prime = L2 - L1
    delta_C_prime = C2_prime - C1_prime

    if C1_prime * C2_prime == 0.0:
        delta_h_prime = 0.0
    else:
        diff_h = h2_prime - h1_prime
        if abs(diff_h) <= 180.0:
            delta_h_prime = diff_h
        elif diff_h > 180.0:
            delta_h_prime = diff_h - 360.0
        else:
            delta_h_prime = diff_h + 360.0

    delta_H_prime = 2.0 * np.sqrt(C1_prime * C2_prime) * np.sin(np.radians(delta_h_prime / 2.0))

    L_bar_prime = (L1 + L2) / 2.0
    C_bar_prime = (C1_prime + C2_prime) / 2.0

    if C1_prime * C2_prime == 0.0:
        h_bar_prime = h1_prime + h2_prime
    else:
        sum_h = h1_prime + h2_prime
        if abs(h1_prime - h2_prime) <= 180.0:
            h_bar_prime = sum_h / 2.0
        elif sum_h < 360.0:
            h_bar_prime = (sum_h + 360.0) / 2.0
        else:
            h_bar_prime = (sum_h - 360.0) / 2.0

    T = (1.0 - 0.17 * np.cos(np.radians(h_bar_prime - 30.0))
         + 0.24 * np.cos(np.radians(2.0 * h_bar_prime))
         + 0.32 * np.cos(np.radians(3.0 * h_bar_prime + 6.0))
         - 0.20 * np.cos(np.radians(4.0 * h_bar_prime - 63.0)))

    delta_theta = 30.0 * np.exp(-(((h_bar_prime - 275.0) / 25.0) ** 2))
    R_C = 2.0 * np.sqrt(C_bar_prime**7 / (C_bar_prime**7 + 25.0**7))
    S_L = 1.0 + ((0.015 * ((L_bar_prime - 50.0) ** 2)) / np.sqrt(20.0 + ((L_bar_prime - 50.0) ** 2)))
    S_C = 1.0 + 0.045 * C_bar_prime
    S_H = 1.0 + 0.015 * C_bar_prime * T
    R_T = -np.sin(np.radians(2.0 * delta_theta)) * R_C

    dE = np.sqrt(
        (delta_L_prime / (kL * S_L)) ** 2
        + (delta_C_prime / (kC * S_C)) ** 2
        + (delta_H_prime / (kH * S_H)) ** 2
        + R_T * (delta_C_prime / (kC * S_C)) * (delta_H_prime / (kH * S_H))
    )
    return float(dE)


def sample_scan_patches(scan_path: str, flare: float = 0.52) -> Dict[str, Dict[str, Any]]:
    """Sample patches from 600 DPI chart scan with flare compensation."""
    scan_img = Image.open(scan_path)
    # Detect orientation: if width > height rotate 90
    if scan_img.width > scan_img.height:
        scan_img = scan_img.rotate(90, expand=True)

    # Standard G640 10x15 chart orientation check
    # Argyll target has black patch cluster in row 1
    scan_180 = scan_img.rotate(180, expand=True)
    arr_s = np.array(scan_180)

    strip_names = ["A", "B", "C", "D", "E", "F", "G", "H"]
    col_centers = [641, 830, 1019, 1208, 1397, 1586, 1775, 1964]
    row_centers = [586, 846, 1106, 1366, 1627, 1888, 2136, 2395, 2668, 2928, 3188]
    sample_r = 25

    patch_measurements = {}
    for r_idx, cy in enumerate(row_centers):
        for c_idx, cx in enumerate(col_centers):
            loc = f"{strip_names[c_idx]}{r_idx+1}"
            box = arr_s[cy-sample_r:cy+sample_r, cx-sample_r:cx+sample_r]

            pixels = box.reshape(-1, 3)
            rgb_mean = np.zeros(3)
            for ch in range(3):
                p_ch = np.sort(pixels[:, ch])
                n_trim = int(len(p_ch) * 0.05)
                rgb_mean[ch] = np.mean(p_ch[n_trim:-n_trim] if n_trim > 0 else p_ch)

            xyz_raw = srgb_to_xyz(rgb_mean)
            xyz = flare_compensate_xyz(xyz_raw, flare_amount=flare)
            lab = xyz_to_lab(xyz)
            patch_measurements[loc] = {
                "rgb_raw": rgb_mean,
                "xyz": xyz,
                "lab": lab,
                "cx": cx,
                "cy": cy,
            }

    return patch_measurements


def parse_ti2(ti2_path: str) -> List[Dict[str, Any]]:
    """Parse Argyll .ti2 target reference definitions."""
    records = []
    with open(ti2_path, "r") as f:
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
                
                xyz_exp_d65 = np.array([exp_x, exp_y, exp_z])
                xyz_exp_d50 = adapt_d65_to_d50(xyz_exp_d65)
                lab_exp = xyz_to_lab(xyz_exp_d50)

                records.append({
                    "sid": sid,
                    "loc": loc,
                    "rgb": (r, g, b),
                    "xyz_exp_d50": xyz_exp_d50,
                    "lab_exp": lab_exp,
                })
    return records


def analyze_verification_scan(scan_path: str, ti2_path: str, flare: float = 0.52) -> Dict[str, Any]:
    """Execute end-to-end verification and residual calculation."""
    patches = sample_scan_patches(scan_path, flare=flare)
    ti2_records = parse_ti2(ti2_path)

    results = []
    de_list = []
    neutrals = []

    for rec in ti2_records:
        loc = rec["loc"]
        meas = patches.get(loc)
        if not meas:
            continue

        lab_exp = rec["lab_exp"]
        lab_meas = meas["lab"]

        de00 = ciede2000(lab_exp, lab_meas)
        de76 = float(np.linalg.norm(lab_exp - lab_meas))
        delta_lab = lab_meas - lab_exp

        r, g, b = rec["rgb"]
        is_neutral = (abs(r - g) < 1e-4 and abs(g - b) < 1e-4)

        entry = {
            "sid": rec["sid"],
            "loc": loc,
            "rgb": [r, g, b],
            "lab_expected": [float(x) for x in lab_exp],
            "lab_measured": [float(x) for x in lab_meas],
            "delta_lab": [float(x) for x in delta_lab],  # measured - expected
            "de00": de00,
            "de76": de76,
            "is_neutral": is_neutral
        }
        results.append(entry)
        de_list.append(de00)

        if is_neutral:
            neutrals.append(entry)

    # Statistics
    de_arr = np.array(de_list)
    stats = {
        "mean_de00": float(np.mean(de_arr)),
        "p95_de00": float(np.percentile(de_arr, 95)),
        "max_de00": float(np.max(de_arr)),
        "median_de00": float(np.median(de_arr)),
        "patches_count": len(de_arr),
        "results": results,
    }

    # Neutral statistics
    if neutrals:
        neutrals.sort(key=lambda item: item["lab_measured"][0])
        chroma_list = [np.sqrt(n["lab_measured"][1]**2 + n["lab_measured"][2]**2) for n in neutrals]
        stats["avg_gray_chroma"] = float(np.mean(chroma_list))
        stats["max_gray_chroma"] = float(np.max(chroma_list))
        stats["l_min"] = float(neutrals[0]["lab_measured"][0])
        stats["d_max"] = float(-np.log10(max(0.001, (10.0 ** ((neutrals[0]['lab_measured'][0] + 16.0)/116.0 * 3) / 100.0) if neutrals[0]['lab_measured'][0] > 7.9996 else (neutrals[0]['lab_measured'][0] / 903.3))))
        stats["neutrals"] = neutrals

    # Top worst patches
    worst_patches = sorted(results, key=lambda x: x["de00"], reverse=True)[:5]
    stats["worst_patches"] = worst_patches

    return stats


def print_report(stats: Dict[str, Any], scan_path: str):
    """Render terminal report with Rich."""
    mean_de = stats["mean_de00"]
    p95_de = stats["p95_de00"]
    max_de = stats["max_de00"]

    if mean_de <= 0.80 and max_de <= 2.50:
        grade = "[bold green]EXCELLENT (Master Photographic Match)[/bold green]"
    elif mean_de <= 1.50 and max_de <= 3.50:
        grade = "[bold cyan]GOOD (Commercial Photo Proof)[/bold cyan]"
    elif mean_de <= 2.50:
        grade = "[bold yellow]ACCEPTABLE (Minor Drift, Refinement Recommended)[/bold yellow]"
    else:
        grade = "[bold red]POOR (Iterative Refinement Necessary)[/bold red]"

    if console is None:
        print(f"=== Verification Scan: {scan_path} ===")
        print(f"Mean ΔE00: {mean_de:.2f}, P95: {p95_de:.2f}, Max: {max_de:.2f}")
        return

    t = Table(title=f"Closed-Loop Color Verification: {os.path.basename(scan_path)}", box=box.ROUNDED)
    t.add_column("Reproduction Metric", style="bold cyan")
    t.add_column("Measured Value", style="bold white", justify="right")
    t.add_column("Target Tolerance", style="dim", justify="right")
    t.add_column("Status", justify="center")

    def status_badge(val, good_lim, warn_lim):
        if val <= good_lim:
            return "[green]PASS[/green]"
        elif val <= warn_lim:
            return "[yellow]WARN[/yellow]"
        return "[red]FAIL[/red]"

    t.add_row("Mean ΔE00 (Perceptual Error)", f"{mean_de:.3f}", "≤ 0.80", status_badge(mean_de, 0.80, 1.80))
    t.add_row("95th Percentile ΔE00", f"{p95_de:.3f}", "≤ 1.80", status_badge(p95_de, 1.80, 2.80))
    t.add_row("Peak Max ΔE00", f"{max_de:.3f}", "≤ 3.00", status_badge(max_de, 3.00, 4.50))

    if "l_min" in stats:
        t.add_row("Black Point (L*min)", f"{stats['l_min']:.2f}", "≤ 4.50", status_badge(stats["l_min"], 4.50, 7.00))
        t.add_row("Max Density (Dmax)", f"{stats['d_max']:.2f}", "≥ 2.20", status_badge(2.40 - stats["d_max"], 0.20, 0.50))
        t.add_row("Avg Gray Drift (Chroma ΔC*)", f"{stats['avg_gray_chroma']:.2f}", "≤ 1.20", status_badge(stats["avg_gray_chroma"], 1.20, 2.00))

    console.print()
    console.print(t)
    console.print(Panel(f"Closed-Loop Rating: {grade}", border_style="cyan"))

    # Top 5 worst patches table
    t_worst = Table(title="Top 5 Largest Color Discrepancies (Candidates for Refinement)", box=box.SIMPLE_HEAD)
    t_worst.add_column("Patch", style="cyan")
    t_worst.add_column("Device RGB", justify="center")
    t_worst.add_column("Expected Lab", justify="right")
    t_worst.add_column("Measured Lab", justify="right")
    t_worst.add_column("Error Δ(L, a, b)", justify="right")
    t_worst.add_column("ΔE00", style="bold red", justify="right")

    for w in stats["worst_patches"]:
        rgb_s = f"{int(round(w['rgb'][0]*2.55))},{int(round(w['rgb'][1]*2.55))},{int(round(w['rgb'][2]*2.55))}"
        exp_s = f"{w['lab_expected'][0]:.1f}, {w['lab_expected'][1]:+.1f}, {w['lab_expected'][2]:+.1f}"
        meas_s = f"{w['lab_measured'][0]:.1f}, {w['lab_measured'][1]:+.1f}, {w['lab_measured'][2]:+.1f}"
        delta_s = f"{w['delta_lab'][0]:+.1f}, {w['delta_lab'][1]:+.1f}, {w['delta_lab'][2]:+.1f}"
        t_worst.add_row(w["loc"], rgb_s, exp_s, meas_s, delta_s, f"{w['de00']:.2f}")

    console.print(t_worst)


def main():
    parser = argparse.ArgumentParser(description="Verify Closed-Loop Color Reproduction from Target Scan")
    parser.add_argument("--scan", required=True, help="Scanned verification chart TIFF (600 DPI)")
    parser.add_argument("--ti2", default="targets/G640_10x15_80p_i1.ti2", help="Target reference definitions (.ti2)")
    parser.add_argument("--out-json", default="targets/verification_residuals.json", help="Export path for residual errors (JSON)")
    parser.add_argument("--flare", type=float, default=0.52, help="Scanner optical flare compensation (default: 0.52)")
    args = parser.parse_args()

    if not os.path.exists(args.scan):
        print(f"Error: Scan file {args.scan} not found.")
        sys.exit(1)
    if not os.path.exists(args.ti2):
        print(f"Error: TI2 reference {args.ti2} not found.")
        sys.exit(1)

    print(f"Analyzing verification scan {args.scan} against reference {args.ti2}...")
    stats = analyze_verification_scan(args.scan, args.ti2, flare=args.flare)
    print_report(stats, args.scan)

    # Save residuals for refine_icc_profile.py
    os.makedirs(os.path.dirname(os.path.abspath(args.out_json)), exist_ok=True)
    with open(args.out_json, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\n[SAVED] Exported residual error vectors for profile refinement to: {args.out_json}")


if __name__ == "__main__":
    main()
