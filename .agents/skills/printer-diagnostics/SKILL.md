---
name: printer-diagnostics
description: >-
  Use this skill when the user asks to probe, discover, diagnose, or troubleshoot the Canon G640 printer, query IPP attributes and supported capabilities, monitor CUPS queues, cancel print jobs, or resolve connectivity and transport issues.
---

# Canon G640 Printer Diagnostics & Device Management

This skill covers device discovery, IPP protocol attribute queries, hardware capability probing, print queue monitoring, and job cancellation for the Canon PIXMA G640.

---

## Quick Reference Commands

| Task | Command |
| :--- | :--- |
| **Discover Printer (mDNS & CUPS)** | `./g640rip_cli.py discover` |
| **Query Full IPP Attributes** | `./g640rip_cli.py attributes` |
| **Query Specific Printer IPP** | `./g640rip_cli.py attributes --printer-uri ipp://192.168.0.49:631/ipp/print` |
| **Check Spooler & Queue Status** | `lpstat -p Canon_G600_series -o` |
| **Cancel Active / Stuck Jobs** | `./g640rip_cli.py cancel` |
| **Cancel Specific Job by ID** | `./g640rip_cli.py cancel --job-id 58` |
| **Purge CUPS Spooler Directly** | `cancel -a Canon_G600_series` |

---

## Diagnostic Procedures

### 1. Network Discovery & Bonjour / mDNS Resolution
To locate the Canon G640 on the local subnet:
```bash
./g640rip_cli.py discover
```
* **Discovery Mechanism**:
  1. Broadcasts mDNS queries for `_ipp._tcp.local` and `_printer._tcp.local`.
  2. Inspects local CUPS system queues for existing Canon G600/G640 definitions.
  3. Extracts IP address, IPP endpoint URL, supported document formats (`image/urf`, `image/pwg-raster`), and URF feature tags.

---

### 2. Querying Device Attributes & URF Capabilities
To inspect hardware capabilities, media trays, supported resolutions, and ink status:
```bash
./g640rip_cli.py attributes
```
Key attributes returned:
* `urf-supported`: Lists supported raster features (e.g. `V1.4`, `PQ3-5`, `RS600`, `CP1`).
* `pwg-raster-document-type-supported`: Confirms `srgb_8` and color depths.
* `media-supported`: Enumerates physical media definitions (e.g. `na_index-4x6_4x6in`, `iso_a4_210x297mm`).
* `printer-state`: Shows idle (3), processing (4), or stopped (5).
* `printer-state-reasons`: Indicates warnings (e.g. `marker-supply-low-warning`, `media-empty`).

---

### 3. Queue Monitoring & Stuck Job Recovery
If the printer stalls or a large raster transmission needs to be halted:
```bash
# 1. Cancel via RIP CLI (sends binary IPP_OP_CANCEL_JOB and purges CUPS)
./g640rip_cli.py cancel

# 2. Verify queue is clear
lpstat -o
```

---

### 4. Transport Backends (`cups_raw` vs `direct_ipp`)
* **`cups_raw` (Recommended)**:
  - Spools raster jobs to macOS CUPS background daemon (`lp -d Canon_G600_series -o raw`).
  - Immune to IPP socket timeouts during slow high-density passes.
* **`direct_ipp`**:
  - Connects directly to printer port 631 via pure-binary IPP 2.0.
  - Useful for standalone Linux/Docker deployments without local CUPS daemons.

