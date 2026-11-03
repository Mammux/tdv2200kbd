"""Repeat the 2 KB images to fill an AT28C64 (8 KB) or AT28C256 (32 KB).

With every 2 KB block identical, the keyboard reads the right code however
the extra address lines of the larger chip are tied (see docs/hardware.md).
"""
for name in ("965313-0-rawmode", "tdv2200-raw"):
    data = open(f"{name}.bin", "rb").read()
    assert len(data) == 0x800
    open(f"{name}_x4_AT28C64.bin", "wb").write(data * 4)
    open(f"{name}_x16_AT28C256.bin", "wb").write(data * 16)
    print(f"{name}: _x4_AT28C64.bin, _x16_AT28C256.bin")
