#!/usr/bin/env python3
"""Automatically bump semantic version and synchronize version files."""

import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_FILE = os.path.join(BASE_DIR, "VERSION")
INIT_FILE = os.path.join(BASE_DIR, "g640rip", "__init__.py")


def read_version() -> str:
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            v = f.read().strip()
            if v:
                return v
    # Fallback to __init__.py
    if os.path.exists(INIT_FILE):
        with open(INIT_FILE, "r", encoding="utf-8") as f:
            m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', f.read())
            if m:
                return m.group(1)
    return "1.0.0"


def bump(version: str, bump_type: str = "patch") -> str:
    clean = version.lstrip("v").strip()
    parts = clean.split(".")
    major = int(parts[0]) if len(parts) > 0 else 1
    minor = int(parts[1]) if len(parts) > 1 else 0
    patch = int(parts[2]) if len(parts) > 2 else 0

    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1

    return f"{major}.{minor}.{patch}"


def write_version(new_version: str):
    # 1. Update VERSION file
    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        f.write(f"{new_version}\n")

    # 2. Update g640rip/__init__.py
    if os.path.exists(INIT_FILE):
        with open(INIT_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        new_content = re.sub(
            r'__version__\s*=\s*["\']([^"\']+)["\']',
            f'__version__ = "{new_version}"',
            content,
        )
        with open(INIT_FILE, "w", encoding="utf-8") as f:
            f.write(new_content)


def main():
    bump_type = "patch"
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if "major" in arg:
            bump_type = "major"
        elif "minor" in arg:
            bump_type = "minor"

    current = read_version()
    new_version = bump(current, bump_type)
    write_version(new_version)
    # Output only new version to stdout
    print(new_version)


if __name__ == "__main__":
    main()
