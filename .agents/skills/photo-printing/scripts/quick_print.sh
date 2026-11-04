#!/usr/bin/env bash
set -e

# Convenience script for printing photos with optimal G640 Micro-RIP settings
# Usage: ./quick_print.sh <image_path> [4x6|A4] [ProfileName.icc]

IMAGE="$1"
SIZE="${2:-4x6}"
PROFILE="${3:-targets/Canon_G640_10x15_Glossy2_iter1.icc}"

if [ -z "$IMAGE" ] || [ ! -f "$IMAGE" ]; then
    echo "Usage: ./quick_print.sh <image_path> [4x6|A4] [ProfileName.icc]"
    exit 1
fi

echo "=== G640 Quick Photo Print ==="
echo "Image:   $IMAGE"
echo "Size:    $SIZE"
echo "Profile: $PROFILE"
echo "Layout:  Borderless (Compensate mode, 5% bottom margin, 0 repeated pixels)"
echo "Quality: High (Mode 4 16-bit LittleCMS2 pipeline)"

python3 g640rip_cli.py print "$IMAGE" \
    --size "$SIZE" \
    --media glossy \
    --profile "$PROFILE" \
    --borderless \
    --fit-mode compensate \
    --comp-y 5.0 \
    --contrast 0.10 \
    --quality high \
    --backend cups_raw

