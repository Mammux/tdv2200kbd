#!/usr/bin/env python3
"""Convert an Intel hex file to a 2 KB (2716) ROM image padded with FFh."""
import sys

src, dst = sys.argv[1], sys.argv[2]
rom = bytearray(b"\xff" * 0x800)
top = 0
for line in open(src):
    line = line.strip()
    if not line.startswith(":") or line[7:9] != "00":
        continue
    n, addr = int(line[1:3], 16), int(line[3:7], 16)
    data = bytes.fromhex(line[9:9 + 2 * n])
    if addr + n > len(rom):
        sys.exit(f"{src}: code at {addr:03X}h does not fit in 2 KB")
    rom[addr:addr + n] = data
    top = max(top, addr + n)
open(dst, "wb").write(rom)
print(f"{dst}: code ends at {top:03X}h")
