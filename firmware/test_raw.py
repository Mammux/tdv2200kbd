"""Emulator tests for the raw-only firmware (tdv2200-raw.bin).

Usage: python3 test_raw.py [image]   (default tdv2200-raw.bin; the C version
is tested with c/tdv2200-raw-c.bin)
"""
import random
import sys
from harness import Keyboard

ORIG = open("965313-0.bin", "rb").read()
RAW = open(sys.argv[1] if len(sys.argv) > 1 else "tdv2200-raw.bin", "rb").read()
PATCH = open("965313-0-rawmode.bin", "rb").read()
REAL_KEYS = [k for k in range(3, 128) if ORIG[0x600 + k] != 0]
fails = 0


def check(name, cond, detail=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails += 1


def hexs(seq):
    return " ".join(f"{x:02X}" if isinstance(x, int) else str(x) for x in seq)


class Tracked(Keyboard):
    def __init__(self, rom):
        super().__init__(rom)
        self.max_sp = 0
        self.p2_low_seen = 0
        step = self.cpu.step
        def tracked():
            step()
            self.max_sp = max(self.max_sp, self.cpu.sp)
            self.p2_low_seen |= ~self.cpu.p2 & 0xFF
        self.cpu.step = tracked


kb = Tracked(RAW)
kb.run_ms(40)
check("power-up: reports special column 00 00 within 40 ms", kb.take() == [0x00, 0x00], hexs(kb.received()))

bad = []
for k in REAL_KEYS:
    kb.keys = {k}; kb.run_ms(40); p = kb.take()
    kb.keys = set(); kb.run_ms(40); r = kb.take()
    if p != [k] or r != [k | 0x80]:
        bad.append((hex(k), p, r))
check(f"every key ({len(REAL_KEYS)}) sends k on press and k|80h on release", not bad, bad[:5])

kb.keys = {0x40}; kb.run_ms(2000)
check("no auto-repeat (2 s hold)", kb.take() == [0x40], hexs(kb.received()))
kb.keys = set(); kb.run_ms(40); kb.take()

kb.special = 0x10; kb.run_ms(40)
check("SHIFT down -> 00 10", kb.take() == [0x00, 0x10], hexs(kb.received()))
kb.special = 0x14; kb.run_ms(40)
check("CTRL down too -> 00 14", kb.take() == [0x00, 0x14], hexs(kb.received()))
kb.special = 0; kb.run_ms(40); kb.take()

# a 3 ms glitch on a modifier line is filtered out (debounce)
kb.special = 0x04; kb.run_ms(3); kb.special = 0; kb.run_ms(40)
check("3 ms modifier glitch ignored", kb.take() == [], hexs(kb.received()))
kb.keys = {0x40}; kb.run_ms(3); kb.keys = set(); kb.run_ms(40)
check("3 ms key glitch ignored", kb.take() == [], hexs(kb.received()))

col = [k for k in REAL_KEYS if k & 0x0F == 5]
kb.keys = set(col); kb.run_ms(100); p = kb.take()
kb.keys = set(); kb.run_ms(100); r = kb.take()
check(f"{len(col)} keys in one column together all reported",
      sorted(p) == sorted(col) and sorted(r) == sorted(k | 0x80 for k in col))

many = REAL_KEYS[:40]
kb.keys = set(many); kb.run_ms(800); p = kb.take()
kb.keys = set(); kb.run_ms(800); r = kb.take()
check("40 keys at once: each press and release exactly once",
      sorted(p) == sorted(many) and sorted(r) == sorted(k | 0x80 for k in many),
      f"{len(p)} presses, {len(r)} releases")
check("no framing errors in any output so far", all(isinstance(x, int) for x in p + r))

# commands
for n in range(1, 9):
    kb.send(n); kb.run_ms(30)
check("01h-08h turn LEDs 1-8 on (bus latch all low)", kb.cpu.bus_out == 0x00, f"{kb.cpu.bus_out:02X}")
kb.send(0x09); kb.send(0x10); kb.run_ms(60)
check("09h/10h turn LEDs 1 and 8 off", kb.cpu.bus_out == 0x81, f"{kb.cpu.bus_out:02X}")
kb.send(0x25); kb.run_ms(30)
check("25h turns LEDs 1-8 off", kb.cpu.bus_out == 0xFF, f"{kb.cpu.bus_out:02X}")
kb.send(0x21); kb.run_ms(30); on = kb.cpu.p1 & 0x80
kb.send(0x22); kb.run_ms(30); off = kb.cpu.p1 & 0x80
check("21h/22h click on/off (P1.7)", on == 0x80 and off == 0)
kb.p2_low_seen = 0; kb.send(0x24); kb.run_ms(30)
check("24h pulses the beep line P2.5", kb.p2_low_seen & 0x20 and kb.cpu.p2 & 0x20)
for cmd, bit, val in [(0x32, 0x80, 0x80), (0x33, 0x80, 0), (0x34, 0x40, 0x40), (0x35, 0x40, 0)]:
    kb.send(cmd); kb.run_ms(30)
    check(f"{cmd:02X}h sets P2 bit {bit:02X} to {val:02X}", kb.cpu.p2 & bit == val)
kb.take()
kb.special = 0x30; kb.run_ms(40); kb.take()
kb.send(0x31); kb.run_ms(40)
check("31h re-reports the special column", kb.take() == [0x00, 0x30], hexs(kb.received()))
kb.special = 0
kb.run_ms(40); kb.take()
for cmd in (0x2D, 0x2E, 0x2F, 0x30, 0x36, 0x11, 0x55, 0xC1):
    kb.send(cmd)
kb.run_ms(200)
check("old/unknown commands produce no output", kb.take() == [], hexs(kb.received()))
kb.send(0x02); kb.run_ms(30); kb.send(0x32); kb.run_ms(30); kb.take()
kb.send(0x20); kb.run_ms(60)
check("20h resets: LEDs off and special column reported again",
      kb.take() == [0x00, 0x00] and kb.cpu.bus_out == 0xFF and kb.cpu.p2 & 0xC0 == 0,
      hexs(kb.received()))
check("stack never deeper than 2 levels", kb.max_sp <= 2, kb.max_sp)

# fuzz: decoded stream equals real state; same final state as the patched ROM in raw mode
def fuzz(rom, enable):
    rng = random.Random(7)
    k = Tracked(rom); k.run_ms(100)
    if enable:
        k.send(0x31); k.run_ms(60)
    k.take()
    for _ in range(500):
        if rng.random() < 0.8:
            k.keys ^= {rng.choice(REAL_KEYS)}
        else:
            k.special ^= 1 << rng.choice([1, 2, 3, 4, 7])
        k.run_ms(rng.choice([10, 20, 40, 80]))
    k.run_ms(500)
    state, spec, s, i = set(), None, k.received(), 0
    while i < len(s):
        if s[i] == 0:
            spec = s[i + 1]; i += 2; continue
        (state.add if s[i] < 0x80 else state.discard)(s[i] & 0x7F); i += 1
    return state, spec, k


st, sp, k = fuzz(RAW, False)
check("fuzz (500 events): decoded state matches real state", st == k.keys and sp == k.special)
st2, sp2, _ = fuzz(PATCH, True)
check("fuzz: same result as the patched ROM in raw mode", (st, sp) == (st2, sp2))

print("\nALL PASS" if not fails else f"\n{fails} FAILED")
