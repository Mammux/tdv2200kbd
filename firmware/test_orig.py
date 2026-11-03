"""Check the emulator against known behaviour of the original ROM 965313-0."""
from harness import Keyboard

rom = open("965313-0.bin", "rb").read()
fails = 0


def k_for(ch):
    """Matrix index of the key whose unshifted code is ch (0-2 are not keys)."""
    return [k for k in range(3, 128) if rom[0x680 + k] == ch and rom[0x600 + k] & 1][0]


def check(name, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  got {got}, want {want}"))


kb = Keyboard(rom)
kb.run_ms(200)
check("silent after power-up", kb.take(), [])
a, one = k_for(0x61), k_for(0x31)
kb.keys = {a}; kb.run_ms(60); check("a -> 61", kb.take(), [0x61])
kb.keys = set(); kb.run_ms(60); check("release sends nothing", kb.take(), [])
kb.special = 0x10; kb.run_ms(30); kb.keys = {a}; kb.run_ms(60)
check("Shift+a -> 41", kb.take(), [0x41])
kb.keys = set(); kb.special = 0; kb.run_ms(60)
kb.special = 0x04; kb.run_ms(30); kb.keys = {one}; kb.run_ms(60)
check("Ctrl+1 -> FF 86 (as in the layout document)", kb.take(), [0xFF, 0x86])
kb.keys = set(); kb.special = 0; kb.run_ms(60)
kb.keys = {a}; kb.run_ms(1500)
check("holding a for 1.5 s repeats (15 x 61)", kb.take(), [0x61] * 15)
kb.keys = set(); kb.run_ms(60); kb.take()
kb.special = 0x02; kb.run_ms(30); kb.special = 0; kb.run_ms(30)
check("Caps -> FF C1 and Caps LED (P2.7) on", (kb.take(), kb.cpu.p2 & 0x80), ([0xFF, 0xC1], 0x80))
kb.send(0x2D); kb.run_ms(400)
check("ROM checksum command 2D -> AA", kb.take(), [0xAA])

print("\nALL PASS" if not fails else f"\n{fails} FAILED")
