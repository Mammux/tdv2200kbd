#!/usr/bin/env python3
"""Convert an RP2040 firmware ELF to a UF2 file (no dependencies).

    python3 elf2uf2.py target/thumbv6m-none-eabi/release/tdv-fw tdv-fw.uf2

Copies the loadable segments that sit in flash (0x10000000...) into 256-byte
UF2 blocks for the RP2040 bootloader. Use this if `elf2uf2-rs` or `picotool`
isn't available.
"""
import struct
import sys

FLASH_START, FLASH_END = 0x10000000, 0x10000000 + 16 * 1024 * 1024
FAMILY_RP2040 = 0xE48BFF56
PAGE = 256


def flash_image(elf: bytes) -> dict[int, bytearray]:
    if elf[:4] != b"\x7fELF" or elf[4] != 1 or elf[5] != 1:
        sys.exit("not a 32-bit little-endian ELF file")
    phoff, = struct.unpack_from("<I", elf, 0x1C)
    phentsize, phnum = struct.unpack_from("<HH", elf, 0x2A)
    pages: dict[int, bytearray] = {}
    for i in range(phnum):
        p_type, p_offset, _vaddr, p_paddr, p_filesz, _memsz, _flags, _align = \
            struct.unpack_from("<8I", elf, phoff + i * phentsize)
        if p_type != 1 or p_filesz == 0:  # PT_LOAD with file contents
            continue
        if not (FLASH_START <= p_paddr and p_paddr + p_filesz <= FLASH_END):
            continue  # e.g. RAM-only segments
        data = elf[p_offset:p_offset + p_filesz]
        for j, b in enumerate(data):
            addr = p_paddr + j
            page = pages.setdefault(addr & ~(PAGE - 1), bytearray(PAGE))
            page[addr % PAGE] = b
    if not pages:
        sys.exit("no flash contents found")
    return pages


def uf2(pages: dict[int, bytearray]) -> bytes:
    out = bytearray()
    addrs = sorted(pages)
    for n, addr in enumerate(addrs):
        header = struct.pack("<8I", 0x0A324655, 0x9E5D5157, 0x00002000,  # family ID present
                             addr, PAGE, n, len(addrs), FAMILY_RP2040)
        out += header + pages[addr] + bytes(476 - PAGE) + struct.pack("<I", 0x0AB16F30)
    return bytes(out)


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    with open(sys.argv[1], "rb") as f:
        pages = flash_image(f.read())
    with open(sys.argv[2], "wb") as f:
        f.write(uf2(pages))
    print(f"{sys.argv[2]}: {len(pages)} blocks, {len(pages) * PAGE // 1024} KB of flash")


if __name__ == "__main__":
    main()
