"""FastAPI-based Local Web Dashboard for Canon G640 micro-RIP."""

import base64
import io
import os
from typing import List, Optional
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
import uvicorn

from ..transport.constants import CANON_MEDIA_TYPES, PAPER_SIZES, PRINT_QUALITY_DRAFT, PRINT_QUALITY_HIGH, PRINT_QUALITY_NORMAL
from ..transport.discovery import discover_canon_printers, PrinterInfo
from ..transport.ipp_client import IPPClient
from ..raster.urf_encoder import encode_image_to_urf
from ..color.engine import ColorEngine
from ..color.ink_limit import InkLimiter
from ..color.lcms2_capi import INTENT_RELATIVE_COLORIMETRIC, INTENT_PERCEPTUAL
from ..color.soft_proof import SoftProofEngine, get_display_profile_path

app = FastAPI(title="Canon G640 Micro-RIP Dashboard", version="1.0.0")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def list_system_icc_profiles() -> List[dict]:
    """Scan macOS system and user ColorSync profile directories."""
    paths = [
        "/Library/ColorSync/Profiles",
        "/System/Library/ColorSync/Profiles",
        os.path.expanduser("~/Library/ColorSync/Profiles"),
        os.path.abspath("./profiles"),
    ]
    profiles = []
    seen = set()
    for base in paths:
        if not os.path.exists(base):
            continue
        for root, _, files in os.walk(base):
            for f in files:
                if f.lower().endswith((".icc", ".icm")):
                    full_p = os.path.join(root, f)
                    if f not in seen:
                        seen.add(f)
                        profiles.append({
                            "name": os.path.splitext(f)[0],
                            "filename": f,
                            "path": full_p,
                        })
    profiles.sort(key=lambda x: x["name"])
    return profiles


@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Canon G640 Micro-RIP UI</h1><p>Static index.html missing.</p>"


@app.get("/api/printers")
async def get_printers():
    printers = discover_canon_printers(timeout_sec=2.0)
    data = []
    for p in printers:
        data.append({
            "name": p.name,
            "host": p.host,
            "ip": p.ip_address,
            "ipp_url": p.ipp_url,
            "formats": p.formats,
            "urf": p.urf_features,
        })
    return {"printers": data}


@app.get("/api/profiles")
async def get_profiles():
    return {"profiles": list_system_icc_profiles()}


@app.get("/api/media-options")
async def get_media_options():
    return {
        "media_types": CANON_MEDIA_TYPES,
        "paper_sizes": list(PAPER_SIZES.keys()),
        "qualities": ["high", "normal", "draft"],
    }


@app.post("/api/proof")
async def post_proof(
    file: UploadFile = File(...),
    paper_profile_path: str = Form(...),
    simulate_paper_white: bool = Form(False),
):
    """Generate soft proof and gamut warning preview."""
    if not os.path.exists(paper_profile_path):
        raise HTTPException(status_code=400, detail="Specified paper profile does not exist.")

    contents = await file.read()
    try:
        orig_img = Image.open(io.BytesIO(contents)).convert("RGB")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image file: {e}")

    # Generate soft proof
    engine = SoftProofEngine(
        paper_profile_path=paper_profile_path,
        simulate_paper_white=simulate_paper_white,
    )
    proof_img = engine.render_soft_proof(orig_img)
    gamut_img, mask = engine.render_gamut_warning(orig_img)
    gamut_pct = round(float((mask.sum() / mask.size) * 100.0), 2)

    # Encode to Base64 JPEG/PNG for instant Web display
    def to_b64(img: Image.Image) -> str:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

    return {
        "original_preview": to_b64(orig_img),
        "proof_preview": to_b64(proof_img),
        "gamut_preview": to_b64(gamut_img),
        "out_of_gamut_percent": gamut_pct,
    }


@app.post("/api/export-raster")
async def post_export_raster(
    file: UploadFile = File(...),
    mode: str = Form("production"),
    paper_profile_path: Optional[str] = Form(None),
    media_type: str = Form("luster"),
    paper_size: str = Form("A4"),
    quality: str = Form("high"),
    ink_limit: float = Form(0.90),
    borderless: bool = Form(False),
    fit_mode: str = Form("fill"),
    bleed_pct: float = Form(1.5),
):
    """Generate raw URF stream and return as downloadable file."""
    contents = await file.read()
    try:
        img = Image.open(io.BytesIO(contents)).convert("RGB")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image file: {e}")

    qual_val = PRINT_QUALITY_HIGH if quality == "high" else (PRINT_QUALITY_DRAFT if quality == "draft" else PRINT_QUALITY_NORMAL)

    if mode == "target":
        engine = ColorEngine()
        processed_img = engine.process_calibration_target(img, page_size_name=paper_size, dpi=600)
    else:
        limiter = InkLimiter(max_total_ink=ink_limit)
        engine = ColorEngine(
            paper_profile_path=paper_profile_path,
            ink_limiter=limiter,
            intent=INTENT_RELATIVE_COLORIMETRIC,
            use_bpc=True,
        )
        processed_img = engine.process_production_image(
            img,
            page_size_name=paper_size,
            borderless=borderless,
            fit_mode=fit_mode,
            bleed_pct=bleed_pct,
        )

    urf_bytes = encode_image_to_urf(processed_img, dpi=600, quality=qual_val)
    from fastapi.responses import Response
    return Response(
        content=urf_bytes,
        media_type="image/urf",
        headers={"Content-Disposition": f"attachment; filename=raw_raster_{file.filename}.urf"},
    )


@app.post("/api/print")
async def post_print(
    file: UploadFile = File(...),
    printer_uri: str = Form(...),
    mode: str = Form("production"),  # "production" or "target"
    paper_profile_path: Optional[str] = Form(None),
    media_type: str = Form("luster"),
    paper_size: str = Form("A4"),
    quality: str = Form("high"),
    ink_limit: float = Form(0.90),
    backend: str = Form("cups_raw"),
    borderless: bool = Form(False),
    fit_mode: str = Form("fill"),
    bleed_pct: float = Form(1.5),
):
    """Execute raw IPP Print-Job directly to printer."""
    contents = await file.read()
    try:
        img = Image.open(io.BytesIO(contents)).convert("RGB")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image file: {e}")

    # Quality enum
    qual_val = PRINT_QUALITY_HIGH if quality == "high" else (PRINT_QUALITY_DRAFT if quality == "draft" else PRINT_QUALITY_NORMAL)
    canon_media = CANON_MEDIA_TYPES.get(media_type.lower(), media_type)
    page_spec = PAPER_SIZES.get(paper_size, PAPER_SIZES["A4"])

    if mode == "target":
        # Calibration Target Mode (1:1 zero color management)
        engine = ColorEngine()
        processed_img = engine.process_calibration_target(img, page_size_name=paper_size, dpi=600)
        job_title = f"ArgyllTarget-{file.filename}"
    else:
        # Production Mode
        limiter = InkLimiter(max_total_ink=ink_limit)
        engine = ColorEngine(
            paper_profile_path=paper_profile_path,
            ink_limiter=limiter,
            intent=INTENT_RELATIVE_COLORIMETRIC,
            use_bpc=True,
        )
        processed_img = engine.process_production_image(
            img,
            page_size_name=paper_size,
            borderless=borderless,
            fit_mode=fit_mode,
            bleed_pct=bleed_pct,
        )
        job_title = f"G640RIP-{file.filename}"

    # Encode URF
    urf_bytes = encode_image_to_urf(processed_img, dpi=600, quality=qual_val)

    # Dispatch directly via IPP / CUPS raw spooler
    client = IPPClient(printer_uri=printer_uri, timeout_sec=600.0)
    try:
        resp = client.print_job(
            raster_data=urf_bytes,
            document_format="image/urf",
            job_name=job_title,
            media=page_spec["media_name"],
            media_type=canon_media,
            print_quality=qual_val,
            backend=backend,
            borderless=borderless,
        )
        return {"status": "success", "message": "Job dispatched successfully", "resp": resp}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Print failed: {e}")


@app.post("/api/cancel")
async def post_cancel(
    printer_uri: Optional[str] = Form(None),
    job_id: Optional[int] = Form(None),
):
    """Cancel active print job or purge all queue jobs."""
    target_uri = printer_uri or "ipp://192.168.0.41:631/ipp/print"
    client = IPPClient(printer_uri=target_uri, timeout_sec=10.0)
    res = client.cancel_job(job_id=job_id)
    return res


@app.get("/api/jobs")
async def get_jobs():
    """List current active jobs from CUPS / lpstat."""
    import subprocess
    try:
        out = subprocess.check_output(["lpstat", "-o"], text=True)
        lines = [line.strip() for line in out.splitlines() if line.strip()]
        return {"jobs": lines}
    except Exception:
        return {"jobs": []}


def start_server(host: str = "127.0.0.1", port: int = 8640):
    """Entrypoint to run uvicorn server."""
    uvicorn.run(app, host=host, port=port, log_level="info")

