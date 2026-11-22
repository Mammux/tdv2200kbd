#!/bin/sh
# Rebuild every image from source and run all emulator tests.
set -e
cd "$(dirname "$0")"
python3 build_patch.py
python3 make_patched_asm.py
python3 build_raw.py
python3 make_large_images.py
python3 test_orig.py
python3 test_patch.py
python3 test_raw.py
python3 test_raw.py c/tdv2200-raw-c.bin
python3 ../adapter/tests/test_usb.py
