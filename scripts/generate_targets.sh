#!/usr/bin/env bash
set -e

# ==============================================================================
# ArgyllCMS Target & QA Strip Generator for Canon PIXMA G640 Micro-RIP
# Generates 600 DPI profiling targets and QA verification strips in targets/
# ==============================================================================

# Ensure ArgyllCMS tools are available
command -v targen >/dev/null 2>&1 || {
    echo >&2 "[ERROR] ArgyllCMS 'targen' tool is not installed or not in PATH."
    echo >&2 "Install ArgyllCMS via Homebrew: brew install argyll-cms"
    exit 1
}
command -v printtarg >/dev/null 2>&1 || {
    echo >&2 "[ERROR] ArgyllCMS 'printtarg' tool is not installed or not in PATH."
    echo >&2 "Install ArgyllCMS via Homebrew: brew install argyll-cms"
    exit 1
}

# Resolve repository root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGETS_DIR="$REPO_ROOT/targets"
mkdir -p "$TARGETS_DIR"

TARGET_TYPE="${1:-all}"
PAGE_SIZE="${2:-10x15}"

print_usage() {
    echo "Usage: $0 [all|80|160|240|qa] [10x15|A4]"
    echo ""
    echo "Options:"
    echo "  all      Generate standard 80p single-sheet, 160p, 240p targets & QA strip (Default)"
    echo "  80       Generate 80-patch single-sheet 4x6\" target (G640_10x15_80p_i1.tif)"
    echo "  160      Generate 160-patch 2-sheet target (G640_10x15_160p_i1_*.tif)"
    echo "  240      Generate 240-patch 3-sheet target (G640_10x15_240p_i1_*.tif)"
    echo "  qa       Generate 600 DPI QA visual evaluation strip (QA_Control_Strip_10x15.png)"
    echo ""
    echo "Paper Size: 10x15 (4x6\" / 101.6x152.4 mm, default) or A4 (210x297 mm)"
}

generate_argyll_target() {
    local patches="$1"
    local size="$2"
    local single_steps="$3"
    local grey_steps="$4"
    local base_name="G640_${size}_${patches}p_i1"

    local page_arg
    if [ "$size" == "10x15" ]; then
        page_arg="-p 101.6x152.4"
    else
        page_arg="-p A4"
    fi

    echo ""
    echo "------------------------------------------------------------------"
    echo "Generating ${patches}-patch target: ${base_name} (${size})"
    echo "------------------------------------------------------------------"

    cd "$TARGETS_DIR"

    # Step 1: targen
    # -d2: RGB output device
    # -s: single channel step count (R, G, B)
    # -g: composite grey step count (balanced neutrals)
    # -f: total patch count
    echo "1. Running targen to generate color distribution (.ti1)..."
    targen -v -d2 -s"${single_steps}" -g"${grey_steps}" -f"${patches}" "${base_name}"

    # Step 2: printtarg
    # -i i1: X-Rite i1Pro strip layout
    # -t 600: 600 DPI lossless raster output
    echo "2. Running printtarg to layout patches (.ti2 + .tif)..."
    printtarg -v -i i1 -t 600 $page_arg "${base_name}"

    echo "[OK] Generated ${base_name} in $TARGETS_DIR"
}

generate_qa_strip() {
    local size="$1"
    local strip_script="$REPO_ROOT/.agents/skills/color-verification/scripts/generate_control_strip.py"

    echo ""
    echo "------------------------------------------------------------------"
    echo "Generating QA Visual Evaluation Strip (${size})"
    echo "------------------------------------------------------------------"

    if [ -f "$strip_script" ]; then
        local out_name="QA_Control_Strip_${size}.png"
        python3 "$strip_script" --out "$TARGETS_DIR/$out_name" --size "$size" --orientation landscape
        echo "[OK] Generated $out_name in $TARGETS_DIR"
    else
        echo "[WARNING] QA strip script not found at $strip_script; skipping."
    fi
}

echo "=== Canon G640 Target & Strip Generator ==="
echo "Target Selection: $TARGET_TYPE"
echo "Paper Size:       $PAGE_SIZE"
echo "Output Directory: $TARGETS_DIR"

case "$TARGET_TYPE" in
    80)
        generate_argyll_target 80 "$PAGE_SIZE" 8 8
        ;;
    160)
        generate_argyll_target 160 "$PAGE_SIZE" 10 10
        ;;
    240)
        generate_argyll_target 240 "$PAGE_SIZE" 12 12
        ;;
    qa)
        generate_qa_strip "$PAGE_SIZE"
        ;;
    all)
        generate_argyll_target 80 "$PAGE_SIZE" 8 8
        generate_argyll_target 160 "$PAGE_SIZE" 10 10
        generate_argyll_target 240 "$PAGE_SIZE" 12 12
        generate_qa_strip "$PAGE_SIZE"
        ;;
    -h|--help|help)
        print_usage
        exit 0
        ;;
    *)
        echo "[ERROR] Unknown target selection: $TARGET_TYPE"
        print_usage
        exit 1
        ;;
esac

echo ""
echo "=== Summary of targets in $TARGETS_DIR ==="
ls -lh "$TARGETS_DIR"
echo ""
echo "Ready to print via: ./g640rip_cli.py print-target targets/G640_10x15_80p_i1.tif"

