#!/usr/bin/env bash
set -e

# ArgyllCMS Profile Builder for Canon G640 (10x15 / 4x6)
# Usage: ./build_profile_10x15.sh [80|160|240] [ProfileName]

TARGET_CHOICE="${1:-80}"
PROFILE_NAME="${2:-Canon_G640_10x15_Custom}"

echo "=== Canon G640 10x15 ICC Profiling Workflow ==="

if [ "$TARGET_CHOICE" == "80" ]; then
    BASE="G640_10x15_80p_i1"
elif [ "$TARGET_CHOICE" == "160" ]; then
    BASE="G640_10x15_160p_i1"
elif [ "$TARGET_CHOICE" == "240" ]; then
    BASE="G640_10x15_240p_i1"
else
    echo "Unknown target choice: $TARGET_CHOICE. Use 80, 160, or 240."
    exit 1
fi

echo "1. Step 1: Chartread spectrophotometer measurement"
echo "Place your printed 10x15 target under the strip ruler and run:"
echo "chartread -v -N $BASE"
echo ""
echo "2. Step 2: Generate ICC profile with colprof"
echo "colprof -v -D \"Canon G640 10x15 Custom\" -qm -as -cmt -dpp $BASE"
echo ""
echo "Target files are ready in directory: $(pwd)"

