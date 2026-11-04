---
name: photo-printing
description: >-
  Use this skill when the user asks to print photos, images, or documents on the Canon G640, configure print layout, paper sizes, media types, borderless framing, contrast boost, or cancel and monitor print jobs.
---

# Canon G640 Photo Printing & Production Runbook

This skill provides the complete operational guide for dispatching high-precision photographic print jobs to the Canon PIXMA G640 via the local Micro-RIP engine, bypassing macOS ColorSync and applying custom LittleCMS2 16-bit color transforms.

---

## Quick Reference Commands

| Task | Command |
| :--- | :--- |
| **Quick Photo Print (4x6)** | `.agents/skills/photo-printing/scripts/quick_print.sh <photo.jpg> 4x6 targets/<profile>.icc` |
| **Production Print (Custom)** | `./g640rip_cli.py print <photo.jpg> --size 4x6 --media glossy --profile targets/<profile>.icc --borderless --fit-mode compensate` |
| **Launch Desktop GUI** | `./g640rip_cli.py gui` |
| **Launch Web Dashboard** | `./g640rip_cli.py serve --port 8640` |
| **Check Spooler Queue** | `lpstat -o` |
| **Cancel All Active Jobs** | `.agents/skills/photo-printing/scripts/cancel_jobs.sh` |

---

## Production Printing Procedures

### 1. Borderless Photo Printing (Recommended Mode)

To achieve borderless edge-to-edge printing **without cropping feet or details from the bottom** and **without repeated pixels on the sides**:

```bash
./g640rip_cli.py print input_photo.jpg \
  --size 4x6 \
  --media glossy \
  --profile targets/<profile>.icc \
  --borderless \
  --fit-mode compensate \
  --comp-y 5.0 \
  --quality high \
  --backend cups_raw
```

#### Key Parameters:
* `--borderless` (`-b`): Enables Canon hardware Fullbleed mode (`Postcard.Fullbleed` / `4x6.Fullbleed`).
* `--fit-mode compensate`: Guarantees real image pixels cover 100% of the paper width (**zero repeated pixels on left and right**), while aligning the bottom to protect against mechanical feed cut-off.
* `--comp-y 3.5`: Sets 3.5% bottom feed roller safety margin.
* `--scale-x -3.5`: Hardware width scaling correction percent (calibrated from A5 scan: fixes overspray and cut-off).
* `--scale-y -5.0`: Hardware feed length scaling correction percent (calibrated from A5 scan: preserves top and bottom edges).
* `--offset-x +0.82`: Horizontal centering shift percent (+X = right).
* `--offset-y +1.41`: Vertical feed centering shift percent (+Y = down).
* `--backend cups_raw`: Uses macOS background spooler (`-o raw`), preventing IPP socket timeouts during slow high-density photo passes.

---

### 2. A4 High-Quality Borderless Art Printing

For large A4 photo prints on Luster or Glossy II paper:

```bash
./g640rip_cli.py print portfolio_piece.tif \
  --size A4 \
  --media luster \
  --profile targets/<profile>.icc \
  --borderless \
  --fit-mode fill \
  --bleed 1.5 \
  --quality high
```

---

### 3. Printing with White Borders (Gallery / Matting Style)

When photos need clean white margins for matting or framing without cropping:

```bash
./g640rip_cli.py print art_print.png \
  --size 4x6 \
  --media glossy \
  --profile targets/<profile>.icc \
  --fit-mode fit \
  --quality high
```

---

### 4. Interactive Desktop GUI & Web Dashboard

Users who prefer visual drag-and-drop framing and split-screen soft proofing can use:
* **Native Desktop App**:
  ```bash
  ./g640rip_cli.py gui
  ```
* **Web Dashboard**:
  ```bash
  ./g640rip_cli.py serve --port 8640
  ```
  Open browser at `http://localhost:8640`.

---

### 5. Managing & Cancelling Print Jobs

If paper jams, incorrect media was loaded, or a job needs immediate halting:
```bash
# Cancel active job via Micro-RIP and CUPS
.agents/skills/photo-printing/scripts/cancel_jobs.sh

# Or check status
lpstat -o
```

---

## Detailed References

- [Framing Modes & S-Curve Pipeline](./references/framing_modes.md)
- [Supported Media Types & Paper Sizes](./references/media_and_sizes.md)

