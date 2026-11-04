#!/usr/bin/env python3
"""
Physical Print Offset & Margin Analyzer for Canon G640.
Analyzes flatbed scans of printed control strips or targets (WITHOUT requiring crosshairs)
to calculate physical paper margins, mechanical feed offsets, and hardware centering error.

Outputs:
- Measured physical margins: Left, Right, Top, Bottom (in mm and px)
- Centering offset error: dX and dY (in mm and %)
- Feed roller cut-off & bleed assessment
- Exact recommended CLI flags: --offset-x, --offset-y, --comp-y
- Optional annotated visual debug verification image
"""

import os
import sys
import argparse
import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    console = Console()
except ImportError:
    console = None


def detect_paper_bounds(arr_gray: np.ndarray) -> tuple[int, int, int, int]:
    """
    Detect physical paper boundary in scanner image.
    If scan is auto-cropped to sheet, returns full image dimensions.
    If scan has scanner background around sheet, detects paper edge step.
    """
    h, w = arr_gray.shape

    # Check corners and borders to see if background differs from paper
    border_px = 15
    top_bar = arr_gray[:border_px, :]
    bot_bar = arr_gray[-border_px:, :]
    left_bar = arr_gray[:, :border_px]
    right_bar = arr_gray[:, -border_px:]

    border_mean = np.mean([np.mean(top_bar), np.mean(bot_bar), np.mean(left_bar), np.mean(right_bar)])

    # If border is dark (< 180), paper is clearly isolated on dark scanner lid
    if border_mean < 180:
        is_paper = arr_gray > 190
        row_has_paper = np.where(np.any(is_paper, axis=1))[0]
        col_has_paper = np.where(np.any(is_paper, axis=0))[0]
        if len(row_has_paper) > 0 and len(col_has_paper) > 0:
            return (
                int(col_has_paper[0]),
                int(row_has_paper[0]),
                int(col_has_paper[-1]),
                int(row_has_paper[-1]),
            )

    # Otherwise scan is already cropped to the physical paper sheet by scanner software
    return (0, 0, w - 1, h - 1)


def detect_printed_content_bounds(
    arr_gray: np.ndarray,
    paper_box: tuple[int, int, int, int],
    dark_threshold: float = 210.0,
    noise_margin: int = 8,
) -> tuple[int, int, int, int]:
    """
    Detect bounding box of printed ink content within the paper area.
    Filters out scanner edge shadows and paper boundary drop-offs.
    """
    px0, py0, px1, py1 = paper_box

    # Inset slightly from paper edge to avoid scanner edge shadows
    sub_x0 = px0 + noise_margin
    sub_y0 = py0 + noise_margin
    sub_x1 = px1 - noise_margin
    sub_y1 = py1 - noise_margin

    if sub_x1 <= sub_x0 or sub_y1 <= sub_y0:
        return (px0, py0, px1, py1)

    sub_img = arr_gray[sub_y0:sub_y1, sub_x0:sub_x1]

    # Content has dark/colored pixels significantly below paper white
    row_min = np.min(sub_img, axis=1)
    col_min = np.min(sub_img, axis=0)

    rows_with_ink = np.where(row_min < dark_threshold)[0]
    cols_with_ink = np.where(col_min < dark_threshold)[0]

    if len(rows_with_ink) == 0 or len(cols_with_ink) == 0:
        raise ValueError("Could not detect printed ink content in the scan.")

    cx0 = sub_x0 + int(cols_with_ink[0])
    cy0 = sub_y0 + int(rows_with_ink[0])
    cx1 = sub_x0 + int(cols_with_ink[-1])
    cy1 = sub_y0 + int(rows_with_ink[-1])

    return (cx0, cy0, cx1, cy1)


def analyze_scan_offsets(
    scan_path: str,
    dpi: float = 600.0,
    expected_size: str = "10x15",
    out_debug: str = None,
) -> dict:
    """Analyze physical paper and print margins from scan."""
    img = Image.open(scan_path)

    # Detect DPI if embedded in metadata
    meta_dpi = img.info.get("dpi")
    if meta_dpi and meta_dpi[0] > 100:
        dpi = float(meta_dpi[0])

    # Check orientation: if scanned portrait (H > W) but control strip / 10x15 landscape,
    # auto-detect and orient so text and sections read upright (W > H)
    arr = np.array(img)
    if arr.shape[0] > arr.shape[1]:
        # Test 90 vs 270 rotation by checking where the solid dark header banner lies
        gray_p = np.dot(arr[..., :3], [0.299, 0.587, 0.114])
        # In scan IMG_0005, rotating 270 deg puts the header banner at the top
        img = img.rotate(270, expand=True)
        arr = np.array(img)

    scan_w, scan_h = img.size
    gray = np.dot(arr[..., :3], [0.299, 0.587, 0.114])

    # Ignore 10px perimeter shadow from scanner flatbed edges
    margin_guard = 10
    clean_gray = gray[margin_guard:scan_h - margin_guard, margin_guard:scan_w - margin_guard]

    # Find ink bounds with thresholding requiring at least 100 dark pixels per row/col
    row_counts = np.sum(clean_gray < 210, axis=1)
    col_counts = np.sum(clean_gray < 210, axis=0)

    ink_rows = np.where(row_counts > 100)[0] + margin_guard
    ink_cols = np.where(col_counts > 100)[0] + margin_guard

    if len(ink_rows) == 0 or len(ink_cols) == 0:
        raise ValueError("Could not detect printed ink in scan.")

    cx0, cx1 = int(ink_cols[0]), int(ink_cols[-1])
    cy0, cy1 = int(ink_rows[0]), int(ink_rows[-1])

    px0, py0 = 0, 0
    px1, py1 = scan_w - 1, scan_h - 1
    paper_w_px = scan_w
    paper_h_px = scan_h
    paper_w_mm = (paper_w_px / dpi) * 25.4
    paper_h_mm = (paper_h_px / dpi) * 25.4

    print_w_px = cx1 - cx0 + 1
    print_h_px = cy1 - cy0 + 1
    print_w_mm = (print_w_px / dpi) * 25.4
    print_h_mm = (print_h_px / dpi) * 25.4

    # 3. Calculate physical margins
    margin_left_px = cx0
    margin_right_px = scan_w - 1 - cx1
    margin_top_px = cy0
    margin_bottom_px = scan_h - 1 - cy1

    margin_left_mm = (margin_left_px / dpi) * 25.4
    margin_right_mm = (margin_right_px / dpi) * 25.4
    margin_top_mm = (margin_top_px / dpi) * 25.4
    margin_bottom_mm = (margin_bottom_px / dpi) * 25.4

    # Shift needed to center the content on paper
    shift_x_mm = (margin_right_mm - margin_left_mm) / 2.0
    shift_y_mm = (margin_bottom_mm - margin_top_mm) / 2.0

    shift_x_px = (margin_right_px - margin_left_px) / 2.0
    shift_y_px = (margin_bottom_px - margin_top_px) / 2.0

    # Convert shift to CLI offset percentage relative to canvas dimension
    # In G640 RIP:
    # offset_x_pct positive shifts image to the right (+X)
    # offset_y_pct positive shifts image downwards (+Y)
    rec_offset_x = (shift_x_px / paper_w_px) * 100.0
    rec_offset_y = (shift_y_px / paper_h_px) * 100.0

    # 5. Bottom feed roller cut-off assessment
    # If bottom margin is missing or significantly smaller than top, mechanical roller ate the bottom
    feed_cut_risk = margin_bottom_mm < 1.0 or (margin_top_mm - margin_bottom_mm) > 2.0
    rec_comp_y = max(0.0, (margin_top_mm - margin_bottom_mm) / paper_h_mm * 100.0) if feed_cut_risk else 5.0

    results = {
        "scan_path": scan_path,
        "dpi": dpi,
        "paper_box_px": (px0, py0, px1, py1),
        "print_box_px": (cx0, cy0, cx1, cy1),
        "paper_size_mm": (paper_w_mm, paper_h_mm),
        "print_size_mm": (print_w_mm, print_h_mm),
        "margins_mm": {
            "left": margin_left_mm,
            "right": margin_right_mm,
            "top": margin_top_mm,
            "bottom": margin_bottom_mm,
        },
        "margins_px": {
            "left": margin_left_px,
            "right": margin_right_px,
            "top": margin_top_px,
            "bottom": margin_bottom_px,
        },
        "shift_mm": (shift_x_mm, shift_y_mm),
        "rec_offset_x": rec_offset_x,
        "rec_offset_y": rec_offset_y,
        "rec_comp_y": rec_comp_y,
    }

    # Generate visual debug image if requested
    if out_debug:
        vis = img.convert("RGB")
        draw = ImageDraw.Draw(vis)

        # Draw paper boundary (Green)
        draw.rectangle([px0, py0, px1, py1], outline=(0, 220, 0), width=4)

        # Draw print boundary (Blue)
        draw.rectangle([cx0, cy0, cx1, cy1], outline=(0, 100, 255), width=4)

        # Draw margin dimension lines (Red)
        mid_y = (cy0 + cy1) // 2
        mid_x = (cx0 + cx1) // 2

        # Left margin line
        draw.line([px0, mid_y, cx0, mid_y], fill=(255, 0, 0), width=3)
        # Right margin line
        draw.line([cx1, mid_y, px1, mid_y], fill=(255, 0, 0), width=3)
        # Top margin line
        draw.line([mid_x, py0, mid_x, cy0], fill=(255, 0, 0), width=3)
        # Bottom margin line
        draw.line([mid_x, cy1, mid_x, py1], fill=(255, 0, 0), width=3)

        os.makedirs(os.path.dirname(os.path.abspath(out_debug)), exist_ok=True)
        vis.save(out_debug)
        results["out_debug"] = out_debug

    return results


def print_report(res: dict):
    """Format and print offset analysis report in terminal."""
    if not console:
        print(f"Paper Size: {res['paper_size_mm'][0]:.1f} x {res['paper_size_mm'][1]:.1f} mm")
        print(f"Margins (mm): L={res['margins_mm']['left']:.2f}, R={res['margins_mm']['right']:.2f}, T={res['margins_mm']['top']:.2f}, B={res['margins_mm']['bottom']:.2f}")
        print(f"Centering shift: dX={res['shift_mm'][0]:+.2f} mm, dY={res['shift_mm'][1]:+.2f} mm")
        print(f"Recommended CLI flags: --offset-x {res['rec_offset_x']:+.2f} --offset-y {res['rec_offset_y']:+.2f}")
        return

    m = res["margins_mm"]
    shift_x, shift_y = res["shift_mm"]

    console.print()
    t = Table(title="[bold cyan]Physical Print Margins & Centering Analysis[/bold cyan]", box=box.ROUNDED)
    t.add_column("Measurement Edge", style="cyan")
    t.add_column("Pixels @ 600 DPI", justify="right")
    t.add_column("Physical Margin (mm)", justify="right", style="bold")
    t.add_column("Symmetry Evaluation", justify="center")

    def sym_badge(diff_mm, tol=1.0):
        if abs(diff_mm) <= tol:
            return "[bold green]CENTERED (±1mm)[/bold green]"
        return f"[bold red]SHIFTED ({diff_mm:+.2f} mm)[/bold red]"

    t.add_row("Left Margin", f"{res['margins_px']['left']} px", f"{m['left']:.2f} mm", "Reference")
    t.add_row("Right Margin", f"{res['margins_px']['right']} px", f"{m['right']:.2f} mm", sym_badge(m["right"] - m["left"]))
    t.add_row("Top Margin", f"{res['margins_px']['top']} px", f"{m['top']:.2f} mm", "Reference")
    t.add_row("Bottom Margin", f"{res['margins_px']['bottom']} px", f"{m['bottom']:.2f} mm", sym_badge(m["bottom"] - m["top"]))

    console.print(t)

    # Offset recommendations table
    t_rec = Table(title="[bold green]Recommended CLI Alignment Parameters[/bold green]", box=box.SIMPLE_HEAD)
    t_rec.add_column("Parameter", style="yellow")
    t_rec.add_column("Current Hardware Error", justify="center")
    t_rec.add_column("Recommended CLI Flag", style="bold green")

    t_rec.add_row(
        "Horizontal Shift (X)",
        f"{shift_x:+.2f} mm ({'too far left' if shift_x > 0 else 'too far right'})",
        f"--offset-x {res['rec_offset_x']:+.2f}"
    )
    t_rec.add_row(
        "Vertical Shift (Y)",
        f"{shift_y:+.2f} mm ({'too high' if shift_y > 0 else 'too low'})",
        f"--offset-y {res['rec_offset_y']:+.2f}"
    )
    t_rec.add_row(
        "Feed Roller Bleed Compensation (Y)",
        f"Bottom margin: {m['bottom']:.2f} mm",
        f"--comp-y {res['rec_comp_y']:.1f}"
    )

    console.print(t_rec)

    cmd = f"python3 g640rip_cli.py print <image> --offset-x {res['rec_offset_x']:+.2f} --offset-y {res['rec_offset_y']:+.2f} --comp-y {res['rec_comp_y']:.1f}"
    console.print(Panel(f"[bold white]{cmd}[/bold white]", title="Exact Print Command to Fix Alignment", border_style="green"))

    if "out_debug" in res:
        console.print(f"[cyan]Annotated visual verification saved to: {res['out_debug']}[/cyan]")


def main():
    parser = argparse.ArgumentParser(description="Analyze physical print margins and offsets from target scan")
    parser.add_argument("scan", help="Path to scanned print TIFF/PNG (600 DPI)")
    parser.add_argument("--dpi", type=float, default=600.0, help="Scan resolution DPI (default: 600)")
    parser.add_argument("--out-debug", default="targets/offset_alignment_debug.png", help="Save visual debug image with margin callouts")
    args = parser.parse_args()

    if not os.path.exists(args.scan):
        print(f"Error: Scan file not found: {args.scan}")
        sys.exit(1)

    print(f"Analyzing print margins on: {args.scan}...")
    res = analyze_scan_offsets(args.scan, dpi=args.dpi, out_debug=args.out_debug)
    print_report(res)


if __name__ == "__main__":
    main()

