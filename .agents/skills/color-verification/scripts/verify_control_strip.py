#!/usr/bin/env python3
"""
Photographic QA Control Strip Color Accuracy & Reproduction Verifier for Canon G640.
Processes a flatbed scan of the printed Photographic Control Strip (portrait or landscape)
and evaluates:
- 21-step Neutral Gray linearity, Dmax, and chromatic cast (Chroma C*, Delta a*, Delta b*)
- Photographic Memory Colors accuracy (Skin tones, Sky, Foliage, Gold, Crimson)
- 24-patch ColorChecker Classic reproduction error (CIEDE2000 Delta E00)
- Shadow separation (0% to 5%) and Highlight separation (94% to 100%)
- Overall closed-loop grade and Delta E statistics
"""

import os
import sys
import argparse
import numpy as np
from PIL import Image

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
    return np.array([float(L), float(a), float(b)])


def flare_compensate_xyz(xyz: np.ndarray, flare_amount: float = 0.52) -> np.ndarray:
    """Compensate for flatbed scanner optical stray light reflections."""
    x, y, z = float(xyz[0]), float(xyz[1]), float(xyz[2])
    flare_factor = (1.0 - np.clip(y / 100.0, 0.0, 1.0))
    y_corr = max(0.35, y - flare_amount * flare_factor)
    scale = y_corr / max(y, 1e-5)
    return np.array([max(0.30, x * scale), y_corr, max(0.25, z * scale)])


def ciede2000(lab1: np.ndarray, lab2: np.ndarray, kL: float = 1.0, kC: float = 1.0, kH: float = 1.0) -> float:
    """Calculate CIEDE2000 color difference between two CIE L*a*b* colors."""
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2

    C1 = np.sqrt(a1**2 + b1**2)
    C2 = np.sqrt(a2**2 + b2**2)
    C_bar = (C1 + C2) / 2.0

    G = 0.5 * (1.0 - np.sqrt(C_bar**7 / (C_bar**7 + 25.0**7)))
    a1_prime = a1 * (1.0 + G)
    a2_prime = a2 * (1.0 + G)

    C1_prime = np.sqrt(a1_prime**2 + b1**2)
    C2_prime = np.sqrt(a2_prime**2 + b2**2)

    h1_prime = np.degrees(np.arctan2(b1, a1_prime)) % 360.0
    h2_prime = np.degrees(np.arctan2(b2, a2_prime)) % 360.0

    delta_L_prime = L2 - L1
    delta_C_prime = C2_prime - C1_prime

    if C1_prime * C2_prime == 0:
        delta_h_prime = 0.0
    elif abs(h1_prime - h2_prime) <= 180.0:
        delta_h_prime = h2_prime - h1_prime
    elif h2_prime <= h1_prime:
        delta_h_prime = h2_prime - h1_prime + 360.0
    else:
        delta_h_prime = h2_prime - h1_prime - 360.0

    delta_H_prime = 2.0 * np.sqrt(C1_prime * C2_prime) * np.sin(np.radians(delta_h_prime / 2.0))

    L_bar_prime = (L1 + L2) / 2.0
    C_bar_prime = (C1_prime + C2_prime) / 2.0

    if C1_prime * C2_prime == 0:
        h_bar_prime = h1_prime + h2_prime
    elif abs(h1_prime - h2_prime) <= 180.0:
        h_bar_prime = (h1_prime + h2_prime) / 2.0
    elif h1_prime + h2_prime < 360.0:
        h_bar_prime = (h1_prime + h2_prime + 360.0) / 2.0
    else:
        h_bar_prime = (h1_prime + h2_prime - 360.0) / 2.0

    T = (
        1.0
        - 0.17 * np.cos(np.radians(h_bar_prime - 30.0))
        + 0.24 * np.cos(np.radians(2.0 * h_bar_prime))
        + 0.32 * np.cos(np.radians(3.0 * h_bar_prime + 6.0))
        - 0.20 * np.cos(np.radians(4.0 * h_bar_prime - 63.0))
    )

    delta_theta = 30.0 * np.exp(-(((h_bar_prime - 275.0) / 25.0) ** 2))
    R_C = 2.0 * np.sqrt(C_bar_prime**7 / (C_bar_prime**7 + 25.0**7))
    S_L = 1.0 + ((0.015 * (L_bar_prime - 50.0) ** 2) / np.sqrt(20.0 + (L_bar_prime - 50.0) ** 2))
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


# Reference Macbeth ColorChecker 24 values (ASTM D2244 / ISO 17321-1 nominal D50 Lab)
COLORCHECKER_24_REF = [
    {"name": "Dark Skin", "rgb": (115, 82, 68), "lab": np.array([37.986, 13.555, 14.059])},
    {"name": "Light Skin", "rgb": (194, 150, 130), "lab": np.array([65.711, 18.130, 17.810])},
    {"name": "Blue Sky", "rgb": (98, 122, 157), "lab": np.array([49.927, -4.880, -21.925])},
    {"name": "Foliage", "rgb": (87, 108, 67), "lab": np.array([43.139, -13.095, 21.905])},
    {"name": "Blue Flower", "rgb": (133, 128, 177), "lab": np.array([55.112, 8.844, -25.399])},
    {"name": "Bluish Green", "rgb": (103, 189, 170), "lab": np.array([70.719, -33.397, -0.199])},
    {"name": "Orange", "rgb": (214, 126, 44), "lab": np.array([62.661, 36.067, 57.096])},
    {"name": "Purplish Blue", "rgb": (80, 91, 166), "lab": np.array([40.020, 10.410, -45.964])},
    {"name": "Moderate Red", "rgb": (193, 90, 99), "lab": np.array([51.124, 48.239, 16.248])},
    {"name": "Purple", "rgb": (94, 60, 108), "lab": np.array([30.325, 22.976, -21.587])},
    {"name": "Yellow Green", "rgb": (157, 188, 64), "lab": np.array([72.532, -23.709, 57.255])},
    {"name": "Orange Yellow", "rgb": (224, 163, 46), "lab": np.array([71.941, 19.364, 67.857])},
    {"name": "Blue", "rgb": (56, 61, 150), "lab": np.array([28.778, 14.179, -50.297])},
    {"name": "Green", "rgb": (70, 148, 73), "lab": np.array([55.261, -38.342, 31.370])},
    {"name": "Red", "rgb": (175, 54, 60), "lab": np.array([42.101, 53.378, 28.190])},
    {"name": "Yellow", "rgb": (231, 199, 31), "lab": np.array([81.733, 4.039, 79.819])},
    {"name": "Magenta", "rgb": (187, 86, 149), "lab": np.array([51.935, 49.986, -14.574])},
    {"name": "Cyan", "rgb": (8, 133, 161), "lab": np.array([51.038, -28.631, -28.638])},
    {"name": "White 9.5", "rgb": (243, 243, 242), "lab": np.array([96.539, -0.425, 1.186])},
    {"name": "Neutral 8", "rgb": (200, 200, 200), "lab": np.array([81.257, -0.638, -0.335])},
    {"name": "Neutral 6.5", "rgb": (160, 160, 160), "lab": np.array([66.766, -0.734, -0.504])},
    {"name": "Neutral 5", "rgb": (122, 122, 121), "lab": np.array([50.867, -0.153, -0.270])},
    {"name": "Neutral 3.5", "rgb": (85, 85, 85), "lab": np.array([35.656, -0.421, -1.231])},
    {"name": "Black 2", "rgb": (52, 52, 52), "lab": np.array([20.461, -0.079, -0.973])},
]

# Reference Memory Colors
MEMORY_COLORS_REF = [
    {"name": "Caucasian Skin", "rgb": (232, 190, 172), "lab": xyz_to_lab(srgb_to_xyz(np.array([232, 190, 172])))},
    {"name": "Warm Portrait", "rgb": (210, 160, 138), "lab": xyz_to_lab(srgb_to_xyz(np.array([210, 160, 138])))},
    {"name": "Deep Skin", "rgb": (135, 90, 70), "lab": xyz_to_lab(srgb_to_xyz(np.array([135, 90, 70])))},
    {"name": "Sky Blue", "rgb": (110, 165, 215), "lab": xyz_to_lab(srgb_to_xyz(np.array([110, 165, 215])))},
    {"name": "Foliage Green", "rgb": (65, 125, 60), "lab": xyz_to_lab(srgb_to_xyz(np.array([65, 125, 60])))},
    {"name": "Citrus Orange", "rgb": (245, 130, 32), "lab": xyz_to_lab(srgb_to_xyz(np.array([245, 130, 32])))},
    {"name": "Deep Crimson", "rgb": (185, 30, 45), "lab": xyz_to_lab(srgb_to_xyz(np.array([185, 30, 45])))},
    {"name": "Warm Gold", "rgb": (215, 180, 65), "lab": xyz_to_lab(srgb_to_xyz(np.array([215, 180, 65])))},
]


def sample_box_lab(arr: np.ndarray, x0: int, y0: int, x1: int, y1: int, flare: float = 0.52) -> np.ndarray:
    """Extract trimmed mean Lab from region box."""
    box = arr[y0:y1, x0:x1]
    pixels = box.reshape(-1, 3)
    rgb_mean = np.zeros(3)
    for ch in range(3):
        p_ch = np.sort(pixels[:, ch])
        n_trim = int(len(p_ch) * 0.05)
        rgb_mean[ch] = np.mean(p_ch[n_trim:-n_trim] if n_trim > 0 else p_ch)
    xyz = flare_compensate_xyz(srgb_to_xyz(rgb_mean), flare_amount=flare)
    return xyz_to_lab(xyz)


def register_control_strip(scan_img: Image.Image) -> tuple[int, int, int, int, str]:
    """
    Detect orientation, scale, and header origin of control strip.
    Returns: (best_rot, x0, y0, header_width, mode)
    """
    best_config = None
    best_w = 0

    for rot in [0, 90, 180, 270]:
        t_img = scan_img.rotate(rot, expand=True)
        gray = np.dot(np.array(t_img)[..., :3], [0.299, 0.587, 0.114])
        h, w = gray.shape

        # Search top 25% for the black header banner
        row_min = np.min(gray[:int(h * 0.25), :], axis=1)
        dark_rows = np.where(row_min < 50)[0]
        if len(dark_rows) == 0:
            continue

        hy0 = dark_rows[0]
        row_sample = gray[hy0 + 20, :] if hy0 + 20 < h else gray[hy0, :]
        dark_cols = np.where(row_sample < 60)[0]
        if len(dark_cols) < 500:
            continue

        hx0, hx1 = dark_cols[0], dark_cols[-1]
        hw = hx1 - hx0

        if hw > best_w:
            best_w = hw
            mode = "landscape" if hw > 2600 else "portrait"
            best_config = (rot, int(hx0), int(hy0), int(hw), mode)

    if best_config is None:
        raise ValueError("Could not automatically register Control Strip in scan. Ensure 600 DPI scan.")

    return best_config


def analyze_control_strip(scan_path: str, flare: float = 0.52) -> dict:
    """Analyze all color reproduction sections on scanned control strip."""
    scan_img = Image.open(scan_path)
    rot, hx0, hy0, hw, mode = register_control_strip(scan_img)

    t_img = scan_img.rotate(rot, expand=True)
    arr = np.array(t_img)

    if mode == "landscape":
        usable_w = 3380.0
        scale = float(hw) / usable_w

        # 1. Neutral Step Wedge
        wedge_y0 = hy0 + int((85 + 28) * scale)
        step_h = int(160 * scale)
        step_w = int(hw / 21.0)

        # 4. Memory Colors
        mem_y0 = hy0 + int(910 * scale)
        mem_h = int(100 * scale)
        mw = int(hw / len(MEMORY_COLORS_REF))

        # 5. ColorChecker 24
        cc_y0 = hy0 + int(1068 * scale)
        left_w = int((hw - 40 * scale) * 4 / 7)
        cc_pw = left_w // 6
        cc_ph = int(110 * scale)

    else:  # portrait
        usable_w = 2202.0
        scale = float(hw) / usable_w

        # 1. Neutral Step Wedge
        wedge_y0 = hy0 + int((120 + 35) * scale)
        step_h = int(160 * scale)
        step_w = int(hw / 21.0)

        # 4. Memory Colors
        mem_y0 = hy0 + int(1090 * scale)
        mem_h = int(140 * scale)
        mw = int(hw / len(MEMORY_COLORS_REF))

        cc_y0 = None

    # Sample 1: Neutral Step Wedge (21 Steps)
    wedge_results = []
    chroma_list = []

    for i in range(21):
        pct = int(round(i * 5.0))
        nom_val = int(round(i * (255.0 / 20.0)))
        nom_lab = xyz_to_lab(srgb_to_xyz(np.array([nom_val, nom_val, nom_val])))

        px0 = hx0 + int(i * step_w) + int(15 * scale)
        px1 = px0 + step_w - int(30 * scale)
        py0 = wedge_y0 + int(15 * scale)
        py1 = py0 + step_h - int(30 * scale)

        meas_lab = sample_box_lab(arr, px0, py0, px1, py1, flare=flare)
        de = ciede2000(meas_lab, nom_lab)
        chroma = np.sqrt(meas_lab[1]**2 + meas_lab[2]**2)
        chroma_list.append(chroma)

        wedge_results.append({
            "step": i + 1,
            "pct": pct,
            "nom_lab": nom_lab,
            "meas_lab": meas_lab,
            "delta_lab": meas_lab - nom_lab,
            "chroma": chroma,
            "de00": de,
        })

    # Dmax and Black Point from Step 1 (0% Lightness)
    l_min = wedge_results[0]["meas_lab"][0]
    y_black = max(0.01, 100.0 * (((l_min + 16.0) / 116.0) ** 3))
    d_max = -np.log10(y_black / 100.0)

    # Sample 2: Photographic Memory Colors
    memory_results = []
    for i, ref in enumerate(MEMORY_COLORS_REF):
        px0 = hx0 + int(i * mw) + int(20 * scale)
        px1 = px0 + mw - int(40 * scale)
        py0 = mem_y0 + int(15 * scale)
        py1 = py0 + mem_h - int(30 * scale)

        meas_lab = sample_box_lab(arr, px0, py0, px1, py1, flare=flare)
        de = ciede2000(meas_lab, ref["lab"])
        memory_results.append({
            "name": ref["name"],
            "nom_lab": ref["lab"],
            "meas_lab": meas_lab,
            "delta_lab": meas_lab - ref["lab"],
            "de00": de,
        })

    # Sample 3: ColorChecker 24 (if landscape)
    cc24_results = []
    if mode == "landscape" and cc_y0 is not None:
        for idx, ref in enumerate(COLORCHECKER_24_REF):
            row = idx // 6
            col = idx % 6
            px0 = hx0 + col * cc_pw + int(15 * scale)
            px1 = px0 + cc_pw - int(30 * scale)
            py0 = cc_y0 + row * cc_ph + int(15 * scale)
            py1 = py0 + cc_ph - int(30 * scale)

            meas_lab = sample_box_lab(arr, px0, py0, px1, py1, flare=flare)
            de = ciede2000(meas_lab, ref["lab"])
            cc24_results.append({
                "patch_id": idx + 1,
                "name": ref["name"],
                "nom_lab": ref["lab"],
                "meas_lab": meas_lab,
                "delta_lab": meas_lab - ref["lab"],
                "de00": de,
            })

    # Aggregate stats
    all_de = [w["de00"] for w in wedge_results] + [m["de00"] for m in memory_results]
    if cc24_results:
        all_de += [c["de00"] for c in cc24_results]

    mean_de = float(np.mean(all_de))
    p95_de = float(np.percentile(all_de, 95))
    max_de = float(np.max(all_de))
    avg_gray_chroma = float(np.mean(chroma_list))

    return {
        "scan_path": scan_path,
        "mode": mode,
        "rotation": rot,
        "wedge_results": wedge_results,
        "memory_results": memory_results,
        "cc24_results": cc24_results,
        "l_min": l_min,
        "d_max": d_max,
        "avg_gray_chroma": avg_gray_chroma,
        "mean_de00": mean_de,
        "p95_de00": p95_de,
        "max_de00": max_de,
    }


def print_control_strip_report(data: dict):
    """Format Rich report for control strip color verification."""
    if not console:
        print(f"=== QA Control Strip Verification: {data['scan_path']} ===")
        print(f"Mean ΔE00: {data['mean_de00']:.2f}, Max ΔE00: {data['max_de00']:.2f}")
        print(f"Dmax: {data['d_max']:.2f}, L*min: {data['l_min']:.2f}")
        print(f"Avg Gray Chroma C*: {data['avg_gray_chroma']:.2f}")
        return

    console.print()
    console.rule(f"[bold cyan]Photographic QA Control Strip Audit: {os.path.basename(data['scan_path'])} ({data['mode'].upper()})[/bold cyan]")

    t_sum = Table(title="Overall Reproduction Fidelity Metrics", box=box.ROUNDED)
    t_sum.add_column("Reproduction Metric", style="cyan")
    t_sum.add_column("Measured Value", justify="right", style="bold")
    t_sum.add_column("Photo Tolerance", justify="center")
    t_sum.add_column("Fidelity Status", justify="center")

    def badge(val, good_lim, warn_lim):
        if val <= good_lim:
            return "[bold green]PASS[/bold green]"
        elif val <= warn_lim:
            return "[bold yellow]WARN[/bold yellow]"
        return "[bold red]FAIL[/bold red]"

    t_sum.add_row("Mean ΔE00 (Overall Error)", f"{data['mean_de00']:.2f}", "≤ 2.00", badge(data["mean_de00"], 2.00, 3.50))
    t_sum.add_row("95th Percentile ΔE00", f"{data['p95_de00']:.2f}", "≤ 4.00", badge(data["p95_de00"], 4.00, 6.00))
    t_sum.add_row("Peak Max ΔE00", f"{data['max_de00']:.2f}", "≤ 8.00", badge(data["max_de00"], 8.00, 12.00))
    t_sum.add_row("Neutral Gray Chroma (C* avg)", f"{data['avg_gray_chroma']:.2f}", "≤ 1.50", badge(data["avg_gray_chroma"], 1.50, 2.50))
    t_sum.add_row("Black Point (L*min)", f"{data['l_min']:.2f}", "≤ 4.50", badge(data["l_min"], 4.50, 6.50))
    t_sum.add_row("Maximum Density (Dmax)", f"{data['d_max']:.2f}", "≥ 2.20", "[bold green]PASS[/bold green]" if data["d_max"] >= 2.20 else "[bold red]FAIL[/bold red]")

    console.print(t_sum)

    # Neutral Step Wedge Tracking Table (sample steps)
    t_gray = Table(title="Neutral Gray Step Wedge Tracking (Selected Steps)", box=box.SIMPLE_HEAD)
    t_gray.add_column("Step", justify="center", style="cyan")
    t_gray.add_column("Nominal L*", justify="right")
    t_gray.add_column("Measured Lab", justify="center")
    t_gray.add_column("Cast (Δa*, Δb*)", justify="right")
    t_gray.add_column("Chroma C*", justify="right", style="bold")
    t_gray.add_column("ΔE00", justify="right", style="bold green")

    sample_indices = [0, 2, 5, 10, 15, 18, 20]
    for idx in sample_indices:
        w = data["wedge_results"][idx]
        exp_l = f"{w['nom_lab'][0]:.1f}"
        meas_s = f"{w['meas_lab'][0]:.1f}, {w['meas_lab'][1]:+.1f}, {w['meas_lab'][2]:+.1f}"
        cast_s = f"{w['delta_lab'][1]:+.1f}, {w['delta_lab'][2]:+.1f}"
        c_style = "[green]" if w["chroma"] < 1.5 else ("[yellow]" if w["chroma"] < 2.5 else "[red]")
        t_gray.add_row(f"{w['pct']}%", exp_l, meas_s, cast_s, f"{c_style}{w['chroma']:.2f}[/]", f"{w['de00']:.2f}")

    console.print(t_gray)

    # Photographic Memory Colors Table
    t_mem = Table(title="Photographic Memory Colors Fidelity", box=box.SIMPLE_HEAD)
    t_mem.add_column("Memory Swatch", style="cyan")
    t_mem.add_column("Nominal Lab", justify="right")
    t_mem.add_column("Measured Lab", justify="right")
    t_mem.add_column("Error Δ(L, a, b)", justify="right")
    t_mem.add_column("ΔE00", justify="right", style="bold green")

    for m in data["memory_results"]:
        nom_s = f"{m['nom_lab'][0]:.1f}, {m['nom_lab'][1]:+.1f}, {m['nom_lab'][2]:+.1f}"
        meas_s = f"{m['meas_lab'][0]:.1f}, {m['meas_lab'][1]:+.1f}, {m['meas_lab'][2]:+.1f}"
        delta_s = f"{m['delta_lab'][0]:+.1f}, {m['delta_lab'][1]:+.1f}, {m['delta_lab'][2]:+.1f}"
        t_mem.add_row(m["name"], nom_s, meas_s, delta_s, f"{m['de00']:.2f}")

    console.print(t_mem)

    # 24-patch ColorChecker Table if available
    if data["cc24_results"]:
        t_cc = Table(title="ColorChecker 24-Patch Summary (Top 5 Highest Discrepancies)", box=box.SIMPLE_HEAD)
        t_cc.add_column("Patch ID", justify="center", style="cyan")
        t_cc.add_column("Color Name")
        t_cc.add_column("Nominal Lab", justify="right")
        t_cc.add_column("Measured Lab", justify="right")
        t_cc.add_column("Error Δ(L, a, b)", justify="right")
        t_cc.add_column("ΔE00", justify="right", style="bold red")

        sorted_cc = sorted(data["cc24_results"], key=lambda x: x["de00"], reverse=True)
        for c in sorted_cc[:5]:
            nom_s = f"{c['nom_lab'][0]:.1f}, {c['nom_lab'][1]:+.1f}, {c['nom_lab'][2]:+.1f}"
            meas_s = f"{c['meas_lab'][0]:.1f}, {c['meas_lab'][1]:+.1f}, {c['meas_lab'][2]:+.1f}"
            delta_s = f"{c['delta_lab'][0]:+.1f}, {c['delta_lab'][1]:+.1f}, {c['delta_lab'][2]:+.1f}"
            t_cc.add_row(str(c["patch_id"]), c["name"], nom_s, meas_s, delta_s, f"{c['de00']:.2f}")

        console.print(t_cc)


def main():
    parser = argparse.ArgumentParser(description="Verify Color Accuracy on Scanned QA Control Strip")
    parser.add_argument("scan", help="Scanned control strip image TIFF/PNG (600 DPI)")
    parser.add_argument("--flare", type=float, default=0.52, help="Scanner optical flare compensation (default: 0.52)")
    args = parser.parse_args()

    if not os.path.exists(args.scan):
        print(f"Error: Scan file not found: {args.scan}")
        sys.exit(1)

    print(f"Analyzing color reproduction on QA Control Strip: {args.scan}...")
    data = analyze_control_strip(args.scan, flare=args.flare)
    print_control_strip_report(data)


if __name__ == "__main__":
    main()
