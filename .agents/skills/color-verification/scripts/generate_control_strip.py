#!/usr/bin/env python3
"""
Generate Photographic Quality Control Strip for Canon G640.
Creates a high-resolution 600 DPI test target for visual print QA:
- 21-step neutral step wedge (tests gray balance and linearity)
- Smooth continuous gradients (tests cLUT banding and quantization)
- Standard photographic memory colors (skin tones, foliage, sky)
- Low-end shadow separation (0% to 6% in 1% steps)
- High-end highlight separation (94% to 100% in 1% steps)
- Fine line resolution patterns
"""

import os
import sys
import argparse
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def create_control_chart(width: int = 2362, height: int = 3520) -> Image.Image:
    """Create 600 DPI photographic verification chart (10x15 cm: 2362x3520)."""
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    margin = 80
    usable_w = width - 2 * margin

    # Header
    y = margin
    draw.rectangle([margin, y, width - margin, y + 80], fill=(30, 30, 35))
    draw.text((margin + 30, y + 25), "Canon PIXMA G640 - Photographic Color & Linearity QA Target", fill=(255, 255, 255))
    y += 120

    # Section 1: 21-Step Neutral Gray Step Wedge
    draw.text((margin, y), "1. Neutral Step Wedge (21 Steps, 0% to 100% Lightness)", fill=(50, 50, 50))
    y += 35
    num_steps = 21
    step_w = usable_w // num_steps
    step_h = 160
    for i in range(num_steps):
        val = int(round(i * (255.0 / (num_steps - 1))))
        x0 = margin + i * step_w
        x1 = x0 + step_w if i < num_steps - 1 else width - margin
        draw.rectangle([x0, y, x1, y + step_h], fill=(val, val, val), outline=(180, 180, 180))
        # Label
        text_color = (255, 255, 255) if val < 128 else (0, 0, 0)
        pct = int(round(i * 5.0))
        draw.text((x0 + 8, y + step_h - 30), f"{pct}%", fill=text_color)
    y += step_h + 60

    # Section 2: Continuous Gradients (RGB + CMY + Gray)
    draw.text((margin, y), "2. Continuous Tonal Gradients (Band / Quantization Check)", fill=(50, 50, 50))
    y += 35
    grad_channels = [
        ("Neutral Gray", lambda t: (t, t, t)),
        ("Red", lambda t: (t, 0, 0)),
        ("Green", lambda t: (0, t, 0)),
        ("Blue", lambda t: (0, 0, t)),
        ("Cyan", lambda t: (0, t, t)),
        ("Magenta", lambda t: (t, 0, t)),
        ("Yellow", lambda t: (t, t, 0)),
    ]
    grad_h = 45
    t_arr = np.linspace(0, 255, usable_w, dtype=np.uint8)

    for name, color_fn in grad_channels:
        # Build gradient strip
        strip = np.zeros((grad_h, usable_w, 3), dtype=np.uint8)
        for i in range(usable_w):
            r, g, b = color_fn(t_arr[i])
            strip[:, i, 0] = r
            strip[:, i, 1] = g
            strip[:, i, 2] = b
        strip_img = Image.fromarray(strip, mode="RGB")
        img.paste(strip_img, (margin, y))
        draw.rectangle([margin, y, margin + usable_w, y + grad_h], outline=(150, 150, 150))
        draw.text((margin + 10, y + 12), name, fill=(255, 255, 255) if name in ("Neutral Gray", "Red", "Blue") else (0, 0, 0))
        y += grad_h + 10
    y += 40

    # Section 3: Shadow & Highlight Separation Tests
    draw.text((margin, y), "3. Shadow & Highlight Separation (Detail Resolution)", fill=(50, 50, 50))
    y += 35
    half_w = (usable_w - 40) // 2
    box_h = 130

    # Shadows: 0%, 1%, 2%, 3%, 4%, 5%
    draw.text((margin, y), "Deep Shadows: 0% to 5% Step Separation", fill=(80, 80, 80))
    y_sub = y + 30
    shadow_steps = [0, 1, 2, 3, 4, 5, 8]
    sw = half_w // len(shadow_steps)
    for i, s_pct in enumerate(shadow_steps):
        s_val = int(round(s_pct * 2.55))
        bx0 = margin + i * sw
        bx1 = bx0 + sw
        draw.rectangle([bx0, y_sub, bx1, y_sub + box_h], fill=(s_val, s_val, s_val), outline=(60, 60, 60))
        draw.text((bx0 + 6, y_sub + box_h - 26), f"{s_pct}%", fill=(200, 200, 200))

    # Highlights: 94%, 96%, 97%, 98%, 99%, 100%
    hx_start = margin + half_w + 40
    draw.text((hx_start, y), "Subtle Highlights: 94% to 100% Step Separation", fill=(80, 80, 80))
    hl_steps = [94, 96, 97, 98, 99, 100]
    hw = half_w // len(hl_steps)
    for i, h_pct in enumerate(hl_steps):
        h_val = int(round(h_pct * 2.55))
        bx0 = hx_start + i * hw
        bx1 = bx0 + hw
        draw.rectangle([bx0, y_sub, bx1, y_sub + box_h], fill=(h_val, h_val, h_val), outline=(200, 200, 200))
        draw.text((bx0 + 6, y_sub + box_h - 26), f"{h_pct}%", fill=(80, 80, 80))
    y = y_sub + box_h + 60

    # Section 4: Memory Color Swatches
    draw.text((margin, y), "4. Photographic Memory Colors (Skin Tones, Sky, Foliage)", fill=(50, 50, 50))
    y += 35
    memory_colors = [
        ("Caucasian Skin", (232, 190, 172)),
        ("Warm Portrait", (210, 160, 138)),
        ("Deep Skin", (135, 90, 70)),
        ("Sky Blue", (110, 165, 215)),
        ("Foliage Green", (65, 125, 60)),
        ("Citrus Orange", (245, 130, 32)),
        ("Deep Crimson", (185, 30, 45)),
        ("Warm Gold", (215, 180, 65)),
    ]
    mw = usable_w // len(memory_colors)
    mh = 140
    for i, (m_name, m_rgb) in enumerate(memory_colors):
        mx0 = margin + i * mw
        mx1 = mx0 + mw
        draw.rectangle([mx0, y, mx1, y + mh], fill=m_rgb, outline=(180, 180, 180))
        # Label wrapped
        words = m_name.split()
        draw.text((mx0 + 6, y + mh - 44), words[0], fill=(255, 255, 255) if m_rgb[0] < 150 else (0, 0, 0))
        if len(words) > 1:
            draw.text((mx0 + 6, y + mh - 24), words[1], fill=(255, 255, 255) if m_rgb[0] < 150 else (0, 0, 0))
    y += mh + 60

    # Section 5: Fine Line Sharpness & Alignment Patterns
    draw.text((margin, y), "5. Micro-Line Resolution & Head Alignment Check (600 DPI)", fill=(50, 50, 50))
    y += 35
    pattern_h = 100
    pat_w = usable_w // 3
    # 1px alternating lines
    p1 = np.ones((pattern_h, pat_w, 3), dtype=np.uint8) * 255
    p1[:, ::2] = 0
    img.paste(Image.fromarray(p1), (margin, y))
    draw.rectangle([margin, y, margin + pat_w, y + pattern_h], outline=(150, 150, 150))
    draw.text((margin + 10, y + pattern_h - 25), "1 px / 600 DPI grid", fill=(255, 0, 0))

    # 2px alternating lines
    p2 = np.ones((pattern_h, pat_w, 3), dtype=np.uint8) * 255
    for c in range(pat_w):
        if (c // 2) % 2 == 0:
            p2[:, c] = 0
    img.paste(Image.fromarray(p2), (margin + pat_w + 10, y))
    draw.rectangle([margin + pat_w + 10, y, margin + 2*pat_w + 10, y + pattern_h], outline=(150, 150, 150))
    draw.text((margin + pat_w + 20, y + pattern_h - 25), "2 px / 300 DPI grid", fill=(255, 0, 0))

    # Radial / crosshair
    p3_x = margin + 2*pat_w + 20
    p3_w = width - margin - p3_x
    draw.rectangle([p3_x, y, p3_x + p3_w, y + pattern_h], fill=(245, 245, 245), outline=(150, 150, 150))
    cx = p3_x + p3_w // 2
    cy = y + pattern_h // 2
    draw.line([cx - 40, cy, cx + 40, cy], fill=(0, 0, 0), width=1)
    draw.line([cx, cy - 40, cx, cy + 40], fill=(0, 0, 0), width=1)
    draw.ellipse([cx - 25, cy - 25, cx + 25, cy + 25], outline=(0, 0, 0), width=1)
    draw.text((p3_x + 10, y + pattern_h - 25), "Registration cross", fill=(80, 80, 80))

    return img


def main():
    parser = argparse.ArgumentParser(description="Generate Photographic QA Control Strip")
    parser.add_argument("--out", "-o", default="targets/QA_Control_Strip_10x15.png", help="Output path (PNG or TIFF)")
    parser.add_argument("--size", default="10x15", choices=["10x15", "A4"], help="Paper size")
    args = parser.parse_args()

    if args.size == "10x15":
        w, h = 2362, 3520
    else:
        w, h = 4960, 7016

    print(f"Generating 600 DPI QA Control Target ({args.size}: {w}x{h} px)...")
    img = create_control_chart(w, h)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    img.save(args.out, dpi=(600, 600))
    print(f"[SUCCESS] Saved QA Control Strip to: {args.out}")


if __name__ == "__main__":
    main()

