#!/usr/bin/env bash
set -e

# ArgyllCMS Target Generator for Canon G640
# Usage: ./generate_targets.sh [80|160|240] [10x15|A4] [BaseName]

PATCH_COUNT="${1:-80}"
PAGE_SIZE="${2:-10x15}"
BASE_NAME="${3:-G640_${PAGE_SIZE}_${PATCH_COUNT}p}"

echo "=== Generating ArgyllCMS Profiling Targets ==="
echo "Patches:   $PATCH_COUNT"
echo "Paper Size:$PAGE_SIZE"
echo "Base Name: $BASE_NAME"

cd targets

if [ "$PAGE_SIZE" == "10x15" ]; then
    # 100 x 149 mm (Postcard/4x6)
    PAGE_ARGS="-p 100x149"
else
    # ISO A4: 210 x 297 mm
    PAGE_ARGS="-p A4"
fi

# 1. Generate target description (.ti1) with optimal distribution
# -d2 (RGB printer)
# -s (single channel steps)
# -f (total patches)
echo "1. Running targen to generate color distribution (.ti1)..."
targen -v -d2 -s16 -f"$PATCH_COUNT" "$BASE_NAME"

# 2. Layout printable patches into TIFF image (.tif) and reading definition (.ti2)
# -i i1 (X-Rite i1-style layout with boundary marks)
# -b (suppress boundary border for full printable area)
# -t 600 (600 DPI)
echo "2. Running printtarg to layout patches (.tif + .ti2)..."
printtarg -v -i i1 -t 600 $PAGE_ARGS "$BASE_NAME"

echo ""
echo "[SUCCESS] Generated target files in targets/:"
ls -lh "${BASE_NAME}"*

