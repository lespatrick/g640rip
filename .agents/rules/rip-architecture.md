# Canon G640 RIP Architecture Rules
- Target Printer: Canon PIXMA G640 (6-ink dye system: C, M, Y, K, Red, Grey).
- Host OS: macOS (Apple Silicon).
- Color Engine: Use LittleCMS2 (lcms2) C-API or Python bindings with 16-bit precision (`TYPE_RGB_16` / `TYPE_CMYK_16`).
- Printing Backend: Bypass macOS NSPrintInfo / Quartz color matching. Communicate directly via CUPS C-API (`cupsDoRequest` / raw IPP streams) or `libusb` using PWG/URF raster or Canon BJL commands.
- Performance: Critical pixel loops (LUT interpolation, stochastic error diffusion dithering) must be written in C/C++, Rust, or Numba JIT.
