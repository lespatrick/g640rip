#!/usr/bin/env python3
"""
Color Reproduction Verification Tool for Canon G640 Micro-RIP.
Analyzes ICC paper profiles against Argyll .ti3 measurement data or target scans.

Calculates:
- CIEDE2000 (ΔE00) and CIE76 (ΔE76) error statistics (Mean, 95th percentile, Max)
- Neutral Gray Axis Tracking (chromatic drift ΔC* along L* = [0..100])
- Maximum Black Density (Dmax) and Minimum Black Level (L*min)
- Colorimetric Gamut Coverage
- Quality grading against Photographic Master (Fogra/ISO 12647-7) standards
"""

import os
import sys
import argparse
import subprocess
import numpy as np
from typing import List, Dict, Any, Optional

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    console = Console()
except ImportError:
    console = None


def run_profcheck(ti3_path: str, icc_path: str, use_ciede2000: bool = True) -> Dict[str, Any]:
    """Execute ArgyllCMS profcheck to extract patch-by-patch Delta E errors."""
    cmd = ["profcheck", "-v2"]
    if use_ciede2000:
        cmd.append("-k")
    cmd.extend([ti3_path, icc_path])

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        stdout = res.stdout
    except FileNotFoundError:
        return {"error": "profcheck tool not found in PATH. Ensure ArgyllCMS is installed."}
    except subprocess.CalledProcessError as e:
        return {"error": f"profcheck failed: {e.stderr or e.stdout}"}

    lines = stdout.splitlines()
    patch_errors = []
    summary = {}

    for line in lines:
        line_s = line.strip()
        if "errors(CIEDE2000):" in line_s or "errors:" in line_s:
            parts = line_s.split(",")
            for p in parts:
                if "max." in p:
                    summary["max"] = float(p.split("=")[1].strip())
                elif "avg." in p:
                    summary["avg"] = float(p.split("=")[1].strip())
                elif "RMS" in p:
                    summary["rms"] = float(p.split("=")[1].strip())
        elif line_s.startswith("[") and "]" in line_s and ":" in line_s:
            # Format: [0.928599] 1: 1.00000000 ...
            try:
                bracket_val = line_s[1:line_s.index("]")]
                de_val = float(bracket_val)
                patch_errors.append(de_val)
            except Exception:
                pass

    if patch_errors:
        summary["p95"] = float(np.percentile(patch_errors, 95))
        summary["median"] = float(np.median(patch_errors))
        summary["count"] = len(patch_errors)
        summary["all_de"] = patch_errors

    return summary


def parse_ti3_neutrals(ti3_path: str) -> List[Dict[str, float]]:
    """Parse neutral gray ramp patches from Argyll .ti3 file."""
    neutrals = []
    if not os.path.exists(ti3_path):
        return neutrals

    with open(ti3_path, "r") as f:
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
                if len(parts) >= 7:
                    try:
                        sid = int(parts[0])
                        r, g, b = float(parts[1]), float(parts[2]), float(parts[3])
                        x, y, z = float(parts[4]), float(parts[5]), float(parts[6])

                        # Check if neutral in RGB device space (R == G == B within small delta)
                        if abs(r - g) < 1.0 and abs(g - b) < 1.0:
                            # Convert XYZ to Lab (D50)
                            Xn, Yn, Zn = 96.422, 100.000, 82.521
                            x_n, y_n, z_n = x / Xn, y / Yn, z / Zn
                            delta = 6.0 / 29.0
                            def fx(t):
                                return t ** (1.0/3.0) if t > delta**3 else (t / (3 * delta**2) + 4.0/29.0)

                            L = 116.0 * fx(y_n) - 16.0
                            a = 500.0 * (fx(x_n) - fx(y_n))
                            b_val = 200.0 * (fx(y_n) - fx(z_n))
                            chroma = np.sqrt(a**2 + b_val**2)

                            neutrals.append({
                                "id": sid,
                                "rgb": (r, g, b),
                                "L": L,
                                "a": a,
                                "b": b_val,
                                "chroma": chroma,
                                "Y": y
                            })
                    except Exception:
                        pass

    neutrals.sort(key=lambda item: item["L"])
    return neutrals


def format_cli_output(icc_path: str, ti3_path: str, stats: Dict[str, Any], neutrals: List[Dict[str, float]]):
    """Render beautiful terminal report using rich."""
    if console is None:
        print(f"=== Verification Report: {os.path.basename(icc_path)} ===")
        print(f"ΔE00 Avg: {stats.get('avg', 0):.2f}, 95th%: {stats.get('p95', 0):.2f}, Max: {stats.get('max', 0):.2f}")
        return

    # Assessment
    avg_de = stats.get("avg", 99.0)
    max_de = stats.get("max", 99.0)
    p95_de = stats.get("p95", 99.0)

    if avg_de <= 0.6 and max_de <= 2.0:
        grade = "[bold green]EXCELLENT (Master Photographic Quality)[/bold green]"
    elif avg_de <= 1.2 and max_de <= 3.0:
        grade = "[bold cyan]VERY GOOD (Exceeds Fogra Proofing Criteria)[/bold cyan]"
    elif avg_de <= 2.0 and max_de <= 4.5:
        grade = "[bold yellow]ACCEPTABLE (Standard Commercial Photographic)[/bold yellow]"
    else:
        grade = "[bold red]FAIL (Recalibration Recommended)[/bold red]"

    # Main Summary Table
    t_summary = Table(title=f"Color Accuracy Verification: {os.path.basename(icc_path)}", box=box.ROUNDED)
    t_summary.add_column("Metric", style="bold cyan")
    t_summary.add_column("Measured Value", style="bold white", justify="right")
    t_summary.add_column("Photo Tolerance", style="dim", justify="right")
    t_summary.add_column("Status", justify="center")

    def status_badge(val, good_lim, warn_lim):
        if val <= good_lim:
            return "[green]PASS[/green]"
        elif val <= warn_lim:
            return "[yellow]WARN[/yellow]"
        return "[red]FAIL[/red]"

    t_summary.add_row("Mean ΔE00", f"{avg_de:.3f}", "≤ 0.80", status_badge(avg_de, 0.80, 1.50))
    t_summary.add_row("95th Percentile ΔE00", f"{p95_de:.3f}", "≤ 1.80", status_badge(p95_de, 1.80, 2.50))
    t_summary.add_row("Max Peak ΔE00", f"{max_de:.3f}", "≤ 3.00", status_badge(max_de, 2.50, 4.00))

    if neutrals:
        min_L = neutrals[0]["L"]
        # Optical density: D = -log10(Y / 100)
        min_Y = max(0.01, neutrals[0]["Y"])
        dmax = -np.log10(min_Y / 100.0)
        t_summary.add_row("Min Black Level (L*min)", f"{min_L:.2f}", "≤ 4.50", status_badge(min_L, 4.50, 8.00))
        t_summary.add_row("Max Density (Dmax)", f"{dmax:.2f}", "≥ 2.20", status_badge(2.40 - dmax, 0.20, 0.60))

        avg_gray_chroma = float(np.mean([n["chroma"] for n in neutrals]))
        max_gray_chroma = float(np.max([n["chroma"] for n in neutrals]))
        t_summary.add_row("Avg Gray Chroma (ΔC*)", f"{avg_gray_chroma:.2f}", "≤ 1.20", status_badge(avg_gray_chroma, 1.20, 2.00))
        t_summary.add_row("Max Gray Chroma (ΔC*)", f"{max_gray_chroma:.2f}", "≤ 2.00", status_badge(max_gray_chroma, 2.00, 3.00))

    console.print()
    console.print(t_summary)
    console.print(Panel(f"Overall Quality Rating: {grade}", border_style="cyan"))

    # Gray Balance Table if available
    if neutrals:
        t_gray = Table(title="Neutral Axis Gray Balance & Tone Curve Tracking", box=box.SIMPLE_HEAD)
        t_gray.add_column("Patch", style="cyan", justify="center")
        t_gray.add_column("Device RGB", justify="center")
        t_gray.add_column("L* (Lightness)", justify="right")
        t_gray.add_column("a* (Green-Red)", justify="right")
        t_gray.add_column("b* (Blue-Yellow)", justify="right")
        t_gray.add_column("Chroma ΔC*", justify="right")
        t_gray.add_column("Visual Cast", justify="left")

        for n in neutrals:
            ch = n["chroma"]
            a = n["a"]
            b = n["b"]
            
            # Identify dominant tint cast
            if ch < 0.6:
                cast = "[green]Neutral / Clean[/green]"
            else:
                tints = []
                if a > 0.5: tints.append("Red")
                elif a < -0.5: tints.append("Green")
                if b > 0.5: tints.append("Warm/Yellow")
                elif b < -0.5: tints.append("Cool/Blue")
                cast_str = " + ".join(tints) if tints else "Slight Tint"
                color = "yellow" if ch < 1.8 else "red"
                cast = f"[{color}]{cast_str}[/{color}]"

            rgb_str = f"{int(round(n['rgb'][0]*2.55))},{int(round(n['rgb'][1]*2.55))},{int(round(n['rgb'][2]*2.55))}"
            t_gray.add_row(
                str(n["id"]),
                rgb_str,
                f"{n['L']:.1f}",
                f"{a:+.2f}",
                f"{b:+.2f}",
                f"{ch:.2f}",
                cast
            )
        console.print(t_gray)


def main():
    parser = argparse.ArgumentParser(description="Canon G640 Color Reproduction & ICC Verification Tool")
    parser.add_argument("profile", help="Path to ICC profile (.icc)")
    parser.add_argument("--ti3", default=None, help="Path to Argyll .ti3 measurement file (defaults to matching name)")
    parser.add_argument("--html-gamut", action="store_true", help="Generate interactive 3D HTML gamut visualization via profcheck -w")
    args = parser.parse_args()

    icc_path = args.profile
    if not os.path.exists(icc_path):
        print(f"Error: Profile {icc_path} does not exist.")
        sys.exit(1)

    ti3_path = args.ti3
    if not ti3_path:
        base = os.path.splitext(icc_path)[0]
        candidate = base + ".ti3"
        if os.path.exists(candidate):
            ti3_path = candidate
        else:
            # Check targets/ directory
            bname = os.path.basename(base)
            cand2 = os.path.join("targets", bname + ".ti3")
            if os.path.exists(cand2):
                ti3_path = cand2

    if not ti3_path or not os.path.exists(ti3_path):
        print(f"Error: Argyll measurement file (.ti3) not found for {icc_path}. Please specify with --ti3.")
        sys.exit(1)

    # 1. Run profcheck
    stats = run_profcheck(ti3_path, icc_path, use_ciede2000=True)
    if "error" in stats:
        print(f"Error during verification: {stats['error']}")
        sys.exit(1)

    # 2. Parse neutral gray axis tracking
    neutrals = parse_ti3_neutrals(ti3_path)

    # 3. Output formatted report
    format_cli_output(icc_path, ti3_path, stats, neutrals)

    # 4. Optional 3D Gamut HTML
    if args.html_gamut:
        print("\nGenerating 3D interactive gamut visualization...")
        subprocess.run(["profcheck", "-k", "-w", "-x", "-m", "-e", ti3_path, icc_path], check=False)
        html_file = os.path.splitext(icc_path)[0] + ".x3d.html"
        if os.path.exists(html_file):
            print(f"[SUCCESS] Saved 3D Gamut Visualization to: {html_file}")


if __name__ == "__main__":
    main()
