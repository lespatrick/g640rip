# Canon G640 Framing Modes & Image Pipeline Reference

This document details how the Canon G640 Micro-RIP frames images, handles borderless overspray, and manages photographic contrast.

---

## 1. Framing & Layout Modes (`--fit-mode`)

| Mode | Behavior | Best Used For |
| :--- | :--- | :--- |
| **`compensate`** *(Default / Recommended for Borderless)* | Scales uniformly so authentic photo covers 100% of the canvas width (`inner_w >= canvas_w`). Protects the bottom edge from printer mechanical feed roller cut-off (`comp_y = 5.0%`). Completely eliminates horizontal edge clamping (**0 repeated pixels on left and right**). | Borderless photo prints where you want 100% of the photo preserved without cutting off feet/details at the bottom. |
| **`fill`** | Scales uniformly to completely cover the canvas, center-cropping any excess aspect ratio difference. Supports optional `--bleed` overspray expansion (0.0% to 2.5%). | Standard photo lab borderless framing when cropping composition edges is acceptable. |
| **`fit`** | Scales image uniformly to fit completely inside the printable area without cropping. Creates clean margins (letterbox / pillarbox). | Art prints or proofs where the full original uncropped aspect ratio must remain visible with white borders. |
| **`none`** | Centers the image 1:1 at specified DPI without any scaling. | Exact millimeter engineering prints and calibration targets. |

---

## 2. Hardware Feed Roller Compensation (`--comp-y`)

Canon G640 mechanical feed rollers advance paper through the print zone. When the trailing edge of a 10x15 or A4 sheet exits the main feed roller pinch:
- The printer firmware accelerates paper exit, mechanically cropping approximately **$5\%$ of the image from the bottom edge**.
- **Solution in `compensate` mode**:
  - The image bottom is aligned to $safe\_h = canvas\_h \times (1 - comp\_y / 100)$ (e.g. row 3344 on 10x15).
  - The overspray buffer below row 3344 absorbs the mechanical feed cut-off.
  - The real photo content remains 100% intact right down to the physical cut edge of the paper.

---

## 3. Photographic Contrast S-Curve (`--contrast`)

Standard ICC relative colorimetric transforms can sometimes feel flat under gallery lighting. The Micro-RIP provides a 16-bit precision symmetric sigmoid S-curve:

$$y = \frac{x^\gamma}{x^\gamma + (1 - x)^\gamma}$$

Where $\gamma = 1.0 + \text{contrast}$:
- `0.0`: Linear identity (100% untouched ICC output).
- `0.10`: Subtle punch (+10% midtone contrast).
- `0.15`: Medium contrast (+15% depth in portraits).
- `0.25`: High contrast / deep blacks (+25% dynamic range for architecture/night photos).
- **Zero Clipping Guarantee**: Pure black ($0$) and pure white ($1.0$) remain mathematically unclipped.
