"""Command Line Interface for Canon G640 local micro-RIP."""

import argparse
import os
import sys
from typing import Optional
import numpy as np
from PIL import Image
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from ..transport.constants import CANON_MEDIA_TYPES, PAPER_SIZES, PRINT_QUALITY_DRAFT, PRINT_QUALITY_HIGH, PRINT_QUALITY_NORMAL
from ..transport.discovery import discover_canon_printers, probe_cups_for_canon, PrinterInfo
from ..transport.ipp_client import IPPClient
from ..raster.urf_encoder import encode_image_to_urf
from ..raster.pwg_encoder import encode_image_to_pwg
from ..color.engine import ColorEngine
from ..color.ink_limit import InkLimiter
from ..color.lcms2_capi import INTENT_RELATIVE_COLORIMETRIC, INTENT_PERCEPTUAL, INTENT_SATURATION, INTENT_ABSOLUTE_COLORIMETRIC
from ..color.linearization import LinearizationLUT
from ..color.soft_proof import SoftProofEngine, get_display_profile_path

console = Console()


def get_default_printer(printer_uri: Optional[str] = None) -> Optional[PrinterInfo]:
    """Resolve target printer from URI or discover automatically."""
    if printer_uri:
        return PrinterInfo(name="Specified Printer", host=printer_uri, formats=["image/urf", "image/pwg-raster"])
    
    with console.status("[bold green]Discovering Canon G640 via Bonjour / mDNS..."):
        printers = discover_canon_printers(timeout_sec=2.0)
    
    if printers:
        return printers[0]
    return None


def cmd_discover(args):
    """Discover Canon printers on the local network and CUPS."""
    console.print(Panel.fit("[bold cyan]Canon G640 Micro-RIP: Printer Discovery[/bold cyan]"))
    with console.status("[bold green]Probing mDNS and CUPS..."):
        printers = discover_canon_printers(timeout_sec=2.5)

    if not printers:
        console.print("[yellow]No Canon G600 / G640 series printers automatically detected.[/yellow]")
        console.print("[dim]Tip: Specify printer directly using --printer-uri ipp://<printer_ip>:631/ipp/print[/dim]")
        return

    table = Table(title="Discovered Printers", show_header=True, header_style="bold magenta")
    table.add_column("Name", style="bold")
    table.add_column("Host / IP")
    table.add_column("IPP URL", style="cyan")
    table.add_column("Formats")
    table.add_column("URF Specs")

    for p in printers:
        formats_str = ", ".join(p.formats) if p.formats else "image/urf, image/pwg-raster"
        urf_str = f"v{p.urf_features.get('version', '1.4')} (PQ: {p.urf_features.get('quality', '3-5')}, DPI: {p.urf_features.get('resolution', '600')})" if p.urf_features else "URF v1.4"
        table.add_row(p.name, p.ip_address or p.host, p.ipp_url, formats_str, urf_str)

    console.print(table)


def cmd_attributes(args):
    """Query Get-Printer-Attributes from target printer."""
    printer = get_default_printer(args.printer_uri)
    if not printer:
        console.print("[red]Printer not found. Please provide --printer-uri.[/red]")
        sys.exit(1)

    console.print(f"[bold cyan]Querying IPP attributes from {printer.ipp_url}...[/bold cyan]")
    client = IPPClient(printer.ipp_url, timeout_sec=10.0)
    try:
        attrs = client.get_printer_attributes()
    except Exception as e:
        console.print(f"[red]Failed to connect or retrieve attributes: {e}[/red]")
        sys.exit(1)

    table = Table(title="Printer IPP Attributes", show_header=True, header_style="bold blue")
    table.add_column("Attribute Name", style="bold yellow")
    table.add_column("Value", style="green")

    for k in sorted(attrs.keys()):
        val = str(attrs[k])
        if len(val) > 100:
            val = val[:97] + "..."
        table.add_row(k, val)

    console.print(table)


def cmd_print_target(args):
    """Print ArgyllCMS calibration target with zero color management (1:1 passthrough)."""
    console.print(Panel.fit("[bold red]Calibration Target Mode: Zero Color Management[/bold red]"))
    if not os.path.exists(args.file):
        console.print(f"[red]Target file not found: {args.file}[/red]")
        sys.exit(1)

    img = Image.open(args.file)
    console.print(f"[green]Loaded target image: {args.file} ({img.size[0]}x{img.size[1]} px, mode: {img.mode})[/green]")

    engine = ColorEngine()
    console.print(f"[cyan]Formatting target 1:1 on {args.size} canvas (600 DPI, no color transform)...[/cyan]")
    canvas_img = engine.process_calibration_target(img, page_size_name=args.size, dpi=600)
    console.print(f"[dim]Canvas size: {canvas_img.size[0]}x{canvas_img.size[1]} px[/dim]")

    console.print("[cyan]Encoding lossless Apple Raster (image/urf v1.4)...[/cyan]")
    urf_data = encode_image_to_urf(canvas_img, dpi=600, quality=PRINT_QUALITY_HIGH)
    console.print(f"[green]Encoded URF stream: {len(urf_data) / 1024:.1f} KB[/green]")

    if args.dry_run:
        console.print("[yellow]Dry-run requested. Skipping IPP socket transmission.[/yellow]")
        if args.out_raster:
            with open(args.out_raster, "wb") as f:
                f.write(urf_data)
            console.print(f"[green]Saved raw URF raster to {args.out_raster}[/green]")
        return

    printer = get_default_printer(args.printer_uri)
    if not printer:
        console.print("[red]Printer not found. Please provide --printer-uri.[/red]")
        sys.exit(1)

    media_type = CANON_MEDIA_TYPES.get(args.media.lower(), args.media)
    page_spec = PAPER_SIZES.get(args.size, PAPER_SIZES["A4"])

    console.print(f"[bold green]Sending raw Print-Job to {printer.ipp_url} (backend: {args.backend})...[/bold green]")
    client = IPPClient(printer.ipp_url, timeout_sec=600.0)
    try:
        resp = client.print_job(
            raster_data=urf_data,
            document_format="image/urf",
            job_name=f"ArgyllTarget-{os.path.basename(args.file)}",
            media=page_spec["media_name"],
            media_type=media_type,
            print_quality=PRINT_QUALITY_HIGH,
            backend=args.backend,
            borderless=args.borderless,
        )
        console.print(f"[bold green]Print job submitted successfully! Status: {resp.get('status')}[/bold green]")
    except Exception as e:
        console.print(f"[red]Error transmitting print job: {e}[/red]")
        sys.exit(1)


def cmd_print(args):
    """Print image in Production Mode (16-bit ICC + RelCol + BPC + LUT + TIL)."""
    console.print(Panel.fit("[bold green]Production Mode: 16-bit LittleCMS2 Color Pipeline[/bold green]"))
    if not os.path.exists(args.file):
        console.print(f"[red]Image file not found: {args.file}[/red]")
        sys.exit(1)

    img = Image.open(args.file)
    console.print(f"[green]Loaded image: {args.file} ({img.size[0]}x{img.size[1]} px, mode: {img.mode})[/green]")

    # Linearization LUT
    lut = LinearizationLUT.create_identity()
    if args.linearization and os.path.exists(args.linearization):
        console.print(f"[cyan]Loading linearization curves from {args.linearization}...[/cyan]")
        lut = LinearizationLUT.from_json(args.linearization)

    # Ink Limiter
    limiter = InkLimiter(max_total_ink=args.ink_limit)
    console.print(f"[cyan]Configured Ink Limiter: max={args.ink_limit * 100:.0f}%[/cyan]")

    # Intent
    intents = {
        "rel_col": INTENT_RELATIVE_COLORIMETRIC,
        "perceptual": INTENT_PERCEPTUAL,
        "sat": INTENT_SATURATION,
        "abs_col": INTENT_ABSOLUTE_COLORIMETRIC,
    }
    selected_intent = intents.get(args.intent.lower(), INTENT_RELATIVE_COLORIMETRIC)

    engine = ColorEngine(
        paper_profile_path=args.profile,
        input_profile_path=args.input_profile,
        linearization=lut,
        ink_limiter=limiter,
        intent=selected_intent,
        use_bpc=not args.no_bpc,
    )

    console.print(f"[cyan]Executing 16-bit color transform & layout (size={args.size}, borderless={args.borderless}, fit={args.fit_mode}, comp=X:{args.comp_x}%/Y:{args.comp_y}%, contrast={args.contrast:+.2f})...[/cyan]")
    processed_img = engine.process_production_image(
        img,
        page_size_name=args.size,
        borderless=args.borderless,
        fit_mode=args.fit_mode,
        bleed_pct=args.bleed,
        comp_x_pct=args.comp_x,
        comp_y_pct=args.comp_y,
        offset_x_pct=args.offset_x,
        offset_y_pct=args.offset_y,
        contrast=args.contrast,
    )

    console.print("[cyan]Encoding Apple Raster (image/urf v1.4, 600 DPI)...[/cyan]")
    quality_val = PRINT_QUALITY_HIGH if args.quality == "high" else (PRINT_QUALITY_DRAFT if args.quality == "draft" else PRINT_QUALITY_NORMAL)
    urf_data = encode_image_to_urf(processed_img, dpi=600, quality=quality_val)
    console.print(f"[green]Encoded URF stream: {len(urf_data) / 1024:.1f} KB[/green]")

    if args.dry_run:
        console.print("[yellow]Dry-run requested. Skipping IPP socket transmission.[/yellow]")
        if args.out_raster:
            with open(args.out_raster, "wb") as f:
                f.write(urf_data)
            console.print(f"[green]Saved raw URF raster to {args.out_raster}[/green]")
        return

    printer = get_default_printer(args.printer_uri)
    if not printer:
        console.print("[red]Printer not found. Please provide --printer-uri.[/red]")
        sys.exit(1)

    media_type = CANON_MEDIA_TYPES.get(args.media.lower(), args.media)
    page_spec = PAPER_SIZES.get(args.size, PAPER_SIZES["A4"])

    console.print(f"[bold green]Sending Print-Job to {printer.ipp_url} (backend: {args.backend})...[/bold green]")
    client = IPPClient(printer.ipp_url, timeout_sec=600.0)
    try:
        resp = client.print_job(
            raster_data=urf_data,
            document_format="image/urf",
            job_name=f"Production-{os.path.basename(args.file)}",
            media=page_spec["media_name"],
            media_type=media_type,
            print_quality=quality_val,
            backend=args.backend,
            borderless=args.borderless,
        )
        console.print(f"[bold green]Print job submitted successfully! Status: {resp.get('status')}[/bold green]")
    except Exception as e:
        console.print(f"[red]Error transmitting print job: {e}[/red]")
        sys.exit(1)


def cmd_proof(args):
    """Generate soft proof simulation and gamut warning overlay."""
    console.print(Panel.fit("[bold blue]Soft Proofing & Gamut Warning Simulation[/bold blue]"))
    if not os.path.exists(args.file):
        console.print(f"[red]Image file not found: {args.file}[/red]")
        sys.exit(1)
    if not os.path.exists(args.profile):
        console.print(f"[red]Paper profile not found: {args.profile}[/red]")
        sys.exit(1)

    img = Image.open(args.file)
    proof_engine = SoftProofEngine(
        paper_profile_path=args.profile,
        display_profile_path=args.display_profile,
        simulate_paper_white=not args.no_paper_white,
    )

    console.print(f"[cyan]Rendering soft proof simulation for {args.profile}...[/cyan]")
    proof_img = proof_engine.render_soft_proof(img)
    out_proof = args.out_proof or "proof_simulation.png"
    proof_img.save(out_proof)
    console.print(f"[green]Saved soft proof simulation to: {out_proof}[/green]")

    if args.out_gamut:
        console.print("[cyan]Computing gamut warning mask...[/cyan]")
        gamut_img, mask = proof_engine.render_gamut_warning(img)
        gamut_img.save(args.out_gamut)
        out_of_gamut_pct = (np.sum(mask) / mask.size) * 100.0
        console.print(f"[green]Saved gamut warning image to: {args.out_gamut} ({out_of_gamut_pct:.2f}% pixels out of gamut)[/green]")


def cmd_serve(args):
    """Launch the local interactive Web UI dashboard."""
    console.print(Panel.fit(f"[bold magenta]Starting Canon G640 RIP Web Dashboard on http://localhost:{args.port}[/bold magenta]"))
    from ..ui.server import start_server
    start_server(host=args.host, port=args.port)


def cmd_gui(args):
    """Launch the native macOS Desktop application window."""
    console.print(Panel.fit(f"[bold magenta]Launching Canon G640 Native Desktop GUI...[/bold magenta]"))
    from ..ui.desktop import launch_desktop_gui
    launch_desktop_gui(host=args.host, port=args.port)


def cmd_cancel(args):
    """Cancel print job or purge queue."""
    console.print(Panel.fit("[bold red]Cancelling Print Jobs...[/bold red]"))
    target = args.printer_uri or "ipp://192.168.0.41:631/ipp/print"
    client = IPPClient(target)
    res = client.cancel_job(job_id=args.job_id)
    console.print(f"[green]Status:[/green] {res.get('status')}")
    for d in res.get("details", []):
        console.print(f" - {d}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Canon G640 Local Micro-RIP for macOS")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # gui
    p_gui = subparsers.add_parser("gui", help="Launch native macOS Desktop GUI app")
    p_gui.add_argument("--host", default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    p_gui.add_argument("--port", type=int, default=8640, help="HTTP Port (default: 8640)")
    p_gui.set_defaults(func=cmd_gui)

    # cancel
    p_cncl = subparsers.add_parser("cancel", help="Cancel active print job(s) and purge queue")
    p_cncl.add_argument("--job-id", type=int, help="Optional specific job ID to cancel")
    p_cncl.add_argument("--printer-uri", help="Target printer IPP URL")
    p_cncl.set_defaults(func=cmd_cancel)

    # discover
    p_disc = subparsers.add_parser("discover", help="Discover Canon G600 / G640 on network & CUPS")
    p_disc.set_defaults(func=cmd_discover)

    # attributes
    p_attr = subparsers.add_parser("attributes", help="Query printer IPP attributes")
    p_attr.add_argument("--printer-uri", help="Target printer IPP URL (e.g. ipp://192.168.0.41:631/ipp/print)")
    p_attr.set_defaults(func=cmd_attributes)

    # print-target
    p_targ = subparsers.add_parser("print-target", help="Print ArgyllCMS calibration target without color management")
    p_targ.add_argument("file", help="Path to ArgyllCMS TIFF or PNG target")
    p_targ.add_argument("--printer-uri", help="Target printer IPP URL")
    p_targ.add_argument("--media", default="luster", choices=list(CANON_MEDIA_TYPES.keys()), help="Media type")
    p_targ.add_argument("--size", default="A4", choices=list(PAPER_SIZES.keys()), help="Paper size")
    p_targ.add_argument("--backend", default="cups_raw", choices=["cups_raw", "direct_ipp"], help="Transport backend (default: cups_raw)")
    p_targ.add_argument("--dry-run", action="store_true", help="Generate raster without sending to printer")
    p_targ.add_argument("--borderless", "-b", action="store_true", help="Print target borderless (fullbleed)")
    p_targ.add_argument("--out-raster", help="Save raw URF raster to file")
    p_targ.set_defaults(func=cmd_print_target)

    # print
    p_prnt = subparsers.add_parser("print", help="Print image in Production Mode (ICC + Linearization + Ink Limit)")
    p_prnt.add_argument("file", help="Path to image file (TIFF, PNG, JPEG)")
    p_prnt.add_argument("--profile", required=True, help="Custom paper ICC profile path")
    p_prnt.add_argument("--input-profile", help="Input color profile path (default: sRGB)")
    p_prnt.add_argument("--linearization", help="1D LUT linearization JSON curve file")
    p_prnt.add_argument("--ink-limit", type=float, default=1.0, help="Maximum total ink limit [0.5 - 1.0] (default: 1.0 = no limit / full dynamic range)")
    p_prnt.add_argument("--contrast", type=float, default=0.0, help="Contrast boost factor [0.0 - 0.5] (e.g. 0.15 = +15%% medium contrast)")
    p_prnt.add_argument("--intent", default="rel_col", choices=["rel_col", "perceptual", "sat", "abs_col"], help="Rendering intent")
    p_prnt.add_argument("--no-bpc", action="store_true", help="Disable Black Point Compensation")
    p_prnt.add_argument("--media", default="luster", choices=list(CANON_MEDIA_TYPES.keys()), help="Media type")
    p_prnt.add_argument("--size", default="A4", choices=list(PAPER_SIZES.keys()), help="Paper size")
    p_prnt.add_argument("--borderless", "-b", action="store_true", help="Print borderless (fullbleed) with zero white margins")
    p_prnt.add_argument("--fit-mode", default="compensate", choices=["compensate", "fill", "fit", "none"], help="Framing mode: compensate (100%% safe area + edge buffer), fill (crop), fit (contain), none (original)")
    p_prnt.add_argument("--bleed", type=float, default=0.0, help="Bleed expansion overspray percentage for fill mode (default: 0.0%%)")
    p_prnt.add_argument("--comp-x", type=float, default=2.7, help="Horizontal hardware bleed compensation percent (default: 2.7%%)")
    p_prnt.add_argument("--comp-y", type=float, default=5.0, help="Vertical hardware bleed compensation percent (default: 5.0%%)")
    p_prnt.add_argument("--offset-x", type=float, default=0.0, help="Horizontal shift percent [-5.0 to +5.0] (default: 0.0)")
    p_prnt.add_argument("--offset-y", type=float, default=0.0, help="Vertical shift percent [-5.0 to +5.0] (default: 0.0)")
    p_prnt.add_argument("--quality", default="high", choices=["draft", "normal", "high"], help="Print quality")
    p_prnt.add_argument("--printer-uri", help="Target printer IPP URL")
    p_prnt.add_argument("--backend", default="cups_raw", choices=["cups_raw", "direct_ipp"], help="Transport backend (default: cups_raw)")
    p_prnt.add_argument("--dry-run", action="store_true", help="Generate raster without sending to printer")
    p_prnt.add_argument("--out-raster", help="Save raw URF raster to file")
    p_prnt.set_defaults(func=cmd_print)

    # proof
    p_prf = subparsers.add_parser("proof", help="Soft proof simulation of paper white and gamut warning")
    p_prf.add_argument("file", help="Path to input image file")
    p_prf.add_argument("--profile", required=True, help="Paper ICC profile path")
    p_prf.add_argument("--display-profile", help="Display ICC profile path (default: macOS Display P3 / sRGB)")
    p_prf.add_argument("--no-paper-white", action="store_true", help="Do not simulate paper white tint")
    p_prf.add_argument("--out-proof", help="Output path for soft-proofed image (PNG)")
    p_prf.add_argument("--out-gamut", help="Output path for gamut warning overlay (PNG)")
    p_prf.set_defaults(func=cmd_proof)

    # serve
    p_srv = subparsers.add_parser("serve", help="Launch interactive Web UI dashboard")
    p_srv.add_argument("--host", default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    p_srv.add_argument("--port", type=int, default=8640, help="HTTP Port (default: 8640)")
    p_srv.set_defaults(func=cmd_serve)

    return parser


def main():
    parser = build_parser()
    if len(sys.argv) == 1:
        # Default to launching native desktop GUI
        console.print("[dim]Tip: Use --help to view CLI options. Launching Desktop GUI...[/dim]")
        args = parser.parse_args(["gui"])
    else:
        args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
