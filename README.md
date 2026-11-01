# Canon PIXMA G640 Local Micro-RIP (macOS)

A high-fidelity local micro-RIP tailored specifically for the 6-ink **Canon PIXMA G640** (CMYK + Red + Grey) on macOS (Apple Silicon & Intel).

## Key Features & Architecture

1. **ColorSync & CUPS Filter Bypass**:
   - macOS default print pipelines intercept print jobs with Quartz/ColorSync filters and convert colors to generic sRGB, corrupting calibration targets and pre-profiled raster data.
   - `g640RIP` speaks directly to the printer's network socket via **pure-binary IPP 2.0 (`Print-Job`)** using Apple Raster (`image/urf` v1.4) and PWG-Raster (`image/pwg-raster`).
   - Bitmaps are transmitted directly to the printer's hardware ASIC without any operating system color alterations.

2. **LittleCMS2 16-Bit Engine**:
   - Direct 64-bit ctypes interface to `liblcms2` with full `TYPE_RGB_16` support.
   - **Calibration Target Mode (Zero Color Management)**:
     - 1:1 byte-for-byte passthrough for ArgyllCMS `targen` / `printtarg` calibration targets.
     - Preserves raw patch values across A4 / 4x6 / 5x7 canvas grids at 600 DPI without interpolation or resampling.
   - **Production Mode**:
     - 16-bit ICC transform (`INTENT_RELATIVE_COLORIMETRIC` + Black Point Compensation `cmsFLAGS_BLACKPOINTCOMPENSATION`).
     - Per-channel 1D Linearization Look-Up Tables (`LinearizationLUT`).
     - Total Ink Limit (`InkLimiter`) with smooth hyperbolic tangent roll-off to prevent ink puddling on fine-art and matte papers.

3. **Soft Proofing & Gamut Warning**:
   - Paper white simulation (`cmsFLAGS_SOFTPROOFING` with Absolute Colorimetric proofing intent).
   - Gamut warning detection and visual overlay mask.
   - Interactive local Web Dashboard with split-screen before/after comparison slider.

---

## Directory Structure

```
g640RIP/
├── g640rip_cli.py               # Main CLI executable
├── g640rip/
│   ├── transport/
│   │   ├── discovery.py         # Bonjour / mDNS and CUPS printer discovery
│   │   ├── ipp_client.py        # Pure-Python IPP 2.0 client
│   │   └── constants.py         # IPP tags, media types, Canon PPD parameters
│   ├── raster/
│   │   ├── urf_encoder.py       # Lossless Apple Raster (image/urf v1.4) encoder
│   │   └── pwg_encoder.py       # PWG-Raster (image/pwg-raster) encoder
│   ├── color/
│   │   ├── lcms2_capi.py        # 64-bit LittleCMS2 C-API ctypes wrapper
│   │   ├── engine.py            # Calibration & Production pipeline manager
│   │   ├── linearization.py     # 1D LUT per-channel density curves
│   │   ├── ink_limit.py         # Total Ink Limit (TIL) saturation limiter
│   │   └── soft_proof.py        # Soft proofing & Gamut warning mask generator
│   └── ui/
│       ├── server.py            # FastAPI REST & preview backend
│       └── static/
│           └── index.html       # Single-Page Application with split-slider proofing
└── tests/                       # Unit tests (Transport, Raster, Color, CLI)
```

---

## Quick Start & Usage

### 1. Environment Setup

```bash
# Setup virtual environment
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install uvicorn
```

### 2. Discovering the Printer

```bash
./g640rip_cli.py discover
```

### 3. ArgyllCMS Calibration Workflow

To create a custom `.icc` profile for your paper with ArgyllCMS and print the target without ColorSync interference:

```bash
# 1. Generate Argyll target definition & TIFF
targen -v -d2 -f462 G640_Luster_Target
printtarg -v -ii1 -h -T300 -pA4 G640_Luster_Target

# 2. Print target with G640RIP (Zero Color Management)
./g640rip_cli.py print-target G640_Luster_Target.tif --media luster --size A4
```

### 4. Production Printing with Custom ICC Profile

```bash
./g640rip_cli.py print photo.tif \
  --profile "/path/to/Canon_G640_Luster.icc" \
  --intent rel_col \
  --ink-limit 0.90 \
  --media luster \
  --size A4 \
  --quality high
```

### 5. Soft Proofing & Gamut Warning

```bash
./g640rip_cli.py proof photo.tif \
  --profile "/path/to/Canon_G640_Luster.icc" \
  --out-proof proof_preview.png \
  --out-gamut gamut_warning.png
```

### 5. Anulowanie zadania druku (Cancel Job)

Zarówno z poziomu GUI, jak i terminala możesz w dowolnym momencie natychmiast przerwać zadanie i wyczyścić bufor drukarki:

```bash
# Anulowanie wszystkich aktywnych zadań w kolejce
./g640rip_cli.py cancel

# Anulowanie konkretnego zadania
./g640rip_cli.py cancel --job-id 42
```

W interfejsie graficznym dostępny jest dedykowany czerwony przycisk: **"Cancel Print Job / Purge Queue"**.

### 6. Desktop GUI & Web Dashboard

#### Opcja A: Natywna aplikacja okienkowa macOS (Desktop Window)
Możesz uruchomić natywne okno aplikacji macOS Cocoa/WebKit na 2 sposoby:

1. **Dwuklik w Finderze**:
   Dwukliknij plik `Launch G640 RIP.command` w katalogu projektu.
2. **Z terminala**:
   ```bash
   ./g640rip_cli.py gui
   # lub po prostu:
   ./g640rip_cli.py
   ```

#### Opcja B: Uruchomienie w przeglądarce (Web Dashboard)
```bash
./g640rip_cli.py serve --port 8640
```
Następnie otwórz `http://localhost:8640` w Safari/Chrome.

---

## Running Unit Tests

```bash
.venv/bin/python3 -m unittest discover tests
```

