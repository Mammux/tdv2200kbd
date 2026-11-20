#!/bin/sh
# Build the C version of the raw-only firmware with the SDCC mcs48 port
# (branch mcs48-port of https://github.com/Mammux/sdcc, configured with
# --enable-mcs48-port). Set SDCC to its bin directory if sdcc is not on PATH,
# and SDCC_INC to its device/include/mcs48 directory if it is not installed.
set -e
cd "$(dirname "$0")"
[ -n "$SDCC" ] && PATH="$SDCC:$PATH"
INC=${SDCC_INC:+-I$SDCC_INC}
mkdir -p build
sdcc -mmcs48 --data-loc 0x0a $INC -o build/tdv2200-raw.ihx tdv2200-raw.c
python3 ihx2bin.py build/tdv2200-raw.ihx tdv2200-raw-c.bin
