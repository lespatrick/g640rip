#!/usr/bin/env python3
"""
Iterative ICC Profile Refinement Engine for Canon G640.
Consumes closed-loop residual errors from verify_scan_reproduction.py and applies
negative feedback adjustments to the Argyll .ti3 dataset, then re-runs colprof.

Formula:
Lab_new = Lab_current - alpha * (Lab_measured - Lab_expected)
Where alpha (default 0.60) is the damping learning rate preventing overshoot.
"""

import os
import sys
import json
import shutil
import argparse
import subprocess
import numpy as np
from typing import Dict, List, Any

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    console = Console()
except ImportError:
    console = None


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


def lab_to_xyz(lab: np.ndarray) -> np.ndarray:
    """Convert CIE L*a*b* (D50) to CIE XYZ (D50) with strict physical bounds."""
    Xn, Yn, Zn = 96.422, 100.000, 82.521
    L, a, b = float(lab[0]), float(lab[1]), float(lab[2])
    # Strictly clamp L* to valid physical range
    L_clamped = np.clip(L, 0.5, 99.8)
    fy = (L_clamped + 16.0) / 116.0
    fx = a / 500.0 + fy
    fz = fy - b / 200.0

    delta = 6.0 / 29.0
    def f_inv(t):
        return np.where(t > delta, t ** 3, 3 * delta**2 * (t - 4.0/29.0))

    x = float(f_inv(fx) * Xn)
    y = float(f_inv(fy) * Yn)
    z = float(f_inv(fz) * Zn)
    return np.array([
        float(np.clip(x, 0.01, 99.0)),
        float(np.clip(y, 0.01, 100.0)),
        float(np.clip(z, 0.01, 110.0))
    ])


def parse_ti3_file(ti3_path: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Parse header lines and data records from Argyll .ti3 file."""
    headers = []
    records = []
    with open(ti3_path, "r") as f:
        in_data = False
        for line in f:
            line_str = line.strip()
            if line_str == "BEGIN_DATA":
                in_data = True
                continue
            if line_str == "END_DATA":
                break
            if not in_data:
                headers.append(line)
            else:
                if line_str:
                    parts = line_str.split()
                    sid = int(parts[0])
                    r, g, b = float(parts[1]), float(parts[2]), float(parts[3])
                    x, y, z = float(parts[4]), float(parts[5]), float(parts[6])
                    records.append({
                        "sid": sid,
                        "rgb": (r, g, b),
                        "xyz": np.array([x, y, z])
                    })
    return headers, records


def write_refined_ti3(output_path: str, headers: List[str], records: List[Dict[str, Any]], desc: str):
    """Write refined Argyll .ti3 dataset."""
    with open(output_path, "w") as f:
        for h in headers:
            if h.startswith("DESCRIPTOR"):
                f.write(f'DESCRIPTOR "{desc}"\n')
            elif h.startswith("NUMBER_OF_SETS"):
                f.write(f'NUMBER_OF_SETS {len(records)}\n')
            else:
                f.write(h)
        f.write("BEGIN_DATA\n")
        for r in records:
            sid = r["sid"]
            rgb_r, rgb_g, rgb_b = r["rgb"]
            x, y, z = r["xyz"]
            f.write(f"{sid:3d} {rgb_r:9.4f} {rgb_g:9.4f} {rgb_b:9.4f} {x:9.4f} {y:9.4f} {z:9.4f}\n")
        f.write("END_DATA\n")


def build_icc_with_colprof(base_name: str, desc: str, output_icc: str) -> bool:
    """Execute Argyll colprof with critical photographic settings."""
    cmd = [
        "colprof",
        "-v",
        "-D", desc,
        "-qm",     # Medium quality 33x33x33 cLUT
        "-al",     # Lab cLUT algorithm
        "-cmt",    # Typical D50 proofing
        "-dpc",    # Critical print evaluation environment P1 (shadow contrast preservation)
        "-V", "2.0",  # Dark region cLUT density emphasis
        "-O", output_icc,
        f"targets/{base_name}"
    ]
    print(f"Running Argyll colprof: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Error running colprof: {res.stderr or res.stdout}")
        return False
    return os.path.exists(output_icc)


def install_profile(icc_path: str, base_name: str):
    """Install refined profile to macOS ColorSync."""
    colorsync_dir = os.path.expanduser("~/Library/ColorSync/Profiles")
    os.makedirs(colorsync_dir, exist_ok=True)
    dest_path = os.path.join(colorsync_dir, f"{base_name}.icc")
    shutil.copy2(icc_path, dest_path)
    print(f"[INSTALLED] Copied to macOS ColorSync: {dest_path}")


def main():
    parser = argparse.ArgumentParser(description="Iterative Closed-Loop ICC Profile Refinement")
    parser.add_argument("--base-ti3", default="targets/Canon_G640_10x15_Glossy2.ti3", help="Base .ti3 profile measurement file")
    parser.add_argument("--residuals", default="targets/verification_residuals.json", help="Residual errors JSON from verify_scan_reproduction.py")
    parser.add_argument("--rate", "--alpha", type=float, default=0.60, help="Negative feedback learning/damping factor (default: 0.60)")
    parser.add_argument("--name", default=None, help="Output profile base name (default: auto-incremented iter)")
    args = parser.parse_args()

    if not os.path.exists(args.base_ti3):
        print(f"Error: Base ti3 file {args.base_ti3} not found.")
        sys.exit(1)
    if not os.path.exists(args.residuals):
        print(f"Error: Residual errors file {args.residuals} not found. Run verify_scan_reproduction.py first.")
        sys.exit(1)

    with open(args.residuals, "r") as f:
        res_data = json.load(f)

    # Determine iteration name
    if args.name:
        out_base = args.name
    else:
        # Detect current iteration
        stem = os.path.splitext(os.path.basename(args.base_ti3))[0]
        if "_iter" in stem:
            parts = stem.split("_iter")
            current_iter = int(parts[1])
            out_base = f"{parts[0]}_iter{current_iter + 1}"
        else:
            out_base = f"{stem}_iter1"

    out_ti3 = f"targets/{out_base}.ti3"
    out_icc = f"targets/{out_base}.icc"
    desc_str = f"Canon G640 10x15 Glossy II (Refined {out_base})"

    print(f"=== Iterative Profile Refinement ===")
    print(f"Base ti3:       {args.base_ti3}")
    print(f"Residuals:      {args.residuals} (Mean ΔE00: {res_data.get('mean_de00', 0):.2f})")
    print(f"Learning Rate:  α = {args.rate:.2f}")
    print(f"Output Profile: {out_icc}")

    headers, base_records = parse_ti3_file(args.base_ti3)
    residuals_by_sid = {entry["sid"]: entry for entry in res_data.get("results", [])}

    alpha = float(np.clip(args.rate, 0.1, 1.0))
    refined_records = []
    corrections_summary = []

    for r in base_records:
        sid = r["sid"]
        xyz_old = r["xyz"]
        lab_old = xyz_to_lab(xyz_old)

        res_entry = residuals_by_sid.get(sid)
        if res_entry:
            # delta_lab = lab_measured - lab_expected
            delta_lab = np.array(res_entry["delta_lab"], dtype=float)
            
            # Bound per-iteration step to +/- 5.0 dE to prevent runaway or noise amplification
            delta_bounded = np.clip(delta_lab, -5.0, 5.0)

            # In Argyll's .ti3 file, each row characterizes the printer's forward response:
            #   Device RGB -> Physical Lab produced on paper.
            # If the physical print measured warmer/redder than expected (delta_lab > 0),
            # we tell colprof that this RGB physically outputs higher Lab (+).
            # When colprof constructs the inverse B2A LUT (PCS Lab -> Device RGB),
            # it reduces warm ink channels to hit the neutral PCS target.
            lab_new = lab_old + alpha * delta_bounded
            lab_new[0] = float(np.clip(lab_new[0], 0.5, 99.5))
            lab_new[1] = float(np.clip(lab_new[1], -110.0, 110.0))
            lab_new[2] = float(np.clip(lab_new[2], -110.0, 110.0))

            xyz_new = lab_to_xyz(lab_new)

            corrections_summary.append({
                "sid": sid,
                "rgb": r["rgb"],
                "lab_old": lab_old,
                "lab_new": lab_new,
                "delta": delta_bounded,
                "de00_orig": res_entry.get("de00", 0.0)
            })
        else:
            xyz_new = xyz_old

        refined_records.append({
            "sid": sid,
            "rgb": r["rgb"],
            "xyz": xyz_new
        })

    # Write new .ti3
    write_refined_ti3(out_ti3, headers, refined_records, desc_str)
    print(f"[CREATED] Saved refined measurement dataset: {out_ti3}")

    # Build ICC via colprof
    success = build_icc_with_colprof(out_base, desc_str, out_icc)
    if not success:
        print("[ERROR] colprof failed to build ICC profile.")
        sys.exit(1)

    print(f"[SUCCESS] Built refined ICC Profile: {out_icc}")
    install_profile(out_icc, out_base)

    # Show Rich table of corrections
    if console and corrections_summary:
        t = Table(title=f"Sample Iterative Adjustments (α = {alpha:.2f})", box=box.ROUNDED)
        t.add_column("Patch ID", style="cyan")
        t.add_column("Original Lab", justify="right")
        t.add_column("Measured Discrepancy Δ", justify="right", style="yellow")
        t.add_column("Refined Target Lab", justify="right", style="green")
        t.add_column("Original ΔE00", justify="right", style="bold red")

        # Top 5 by original error
        corrections_summary.sort(key=lambda x: x["de00_orig"], reverse=True)
        for c in corrections_summary[:5]:
            old_s = f"{c['lab_old'][0]:.1f}, {c['lab_old'][1]:+.1f}, {c['lab_old'][2]:+.1f}"
            diff_s = f"{c['delta'][0]:+.1f}, {c['delta'][1]:+.1f}, {c['delta'][2]:+.1f}"
            new_s = f"{c['lab_new'][0]:.1f}, {c['lab_new'][1]:+.1f}, {c['lab_new'][2]:+.1f}"
            t.add_row(str(c["sid"]), old_s, diff_s, new_s, f"{c['de00_orig']:.2f}")

        console.print(t)
        console.print(Panel(f"Refined profile '{out_base}.icc' is now installed and ready for verification!", border_style="green"))


if __name__ == "__main__":
    main()
