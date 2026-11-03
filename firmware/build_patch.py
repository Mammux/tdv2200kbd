"""Build the raw-mode patched ROM from the original 965313-0 dump."""
import sys, hashlib
from asm48 import assemble

ORIG = "965313-0.bin"
OUT = "965313-0-rawmode.bin"
FREE_START, FREE_END = 0x56A, 0x5FF      # inclusive, all 00h in the original
FIX = 0x5FF                              # checksum adjustment byte

rom = bytearray(open(ORIG, "rb").read())
assert len(rom) == 2048
assert hashlib.sha1(rom).hexdigest(), "read ok"
assert all(b == 0 for b in rom[FREE_START:FREE_END + 1]), "free area not empty"


def expect(addr, data):
    assert rom[addr:addr + len(data)] == bytes(data), f"unexpected bytes at {addr:03X}"


# sanity: the hook sites contain what we think they do
expect(0x05C, [0xFC, 0xF2, 0xCB])        # mov a,r4 / jb7 0CBh
expect(0x0F4, [0x24, 0x5B])              # jmp 15Bh (CheckSpecialKeys)
expect(0x3A1, [0xD3, 0x30])              # xrl a,#30h
expect(0x3DE, [0xA0, 0x1B, 0x18])        # TxByte

code, labels = assemble(open("rawmode_patch.asm").read(), FREE_START)
end = FREE_START + len(code)
assert end <= FIX, f"patch too big: ends at {end:03X}"
rom[FREE_START:end] = code


def jmp(target):
    return bytes([0x04 | ((target >> 8) << 5), target & 0xFF])


rom[0x05C:0x05F] = jmp(labels["rawcol"]) + b"\x00"   # jmp RawCol / nop
rom[0x0F4:0x0F6] = jmp(labels["rawspecial"])
rom[0x3A1:0x3A3] = jmp(labels["rawcmd"])


def checksum(r):
    """Same algorithm as the ROM's own check (command 2Dh)."""
    acc = c = 0
    for b in r:
        s = b + acc + c
        c, acc = s >> 8, s & 0xFF
    return (acc + c) & 0xFF


target = checksum(open(ORIG, "rb").read())
for x in range(256):
    rom[FIX] = x
    if checksum(rom) == target:
        break
else:
    sys.exit("no checksum fix found")

open(OUT, "wb").write(rom)
print(f"patch {FREE_START:03X}-{end - 1:03X} ({len(code)} bytes, {FIX - end} spare), "
      f"fix byte {FIX:03X}={rom[FIX]:02X}, checksum {checksum(rom):02X} (original {target:02X})")
for k in ("rawcol", "rawspecial", "rawcmd"):
    print(f"  {k:10s} {labels[k]:03X}")
