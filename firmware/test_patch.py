"""Emulator tests for the raw-mode patch."""
import random
from harness import Keyboard

ORIG = open("965313-0.bin", "rb").read()
PATCH = open("965313-0-rawmode.bin", "rb").read()
REAL_KEYS = [k for k in range(128) if ORIG[0x600 + k] in
             (0x05, 0x06, 0x07, 0x0D, 0x0F, 0x1F, 0x27) and k >= 3]
fails = 0


def check(name, cond, detail=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails += 1


def hexs(seq):
    return " ".join(f"{x:02X}" if isinstance(x, int) else str(x) for x in seq)


class Tracked(Keyboard):
    """Keyboard that also records the deepest stack use."""
    def __init__(self, rom):
        super().__init__(rom)
        self.max_sp = 0
        step = self.cpu.step
        def tracked_step():
            step()
            self.max_sp = max(self.max_sp, self.cpu.sp)
        self.cpu.step = tracked_step


# ------------------------------------------------ 1. normal mode is unchanged
def script(kb, rng, steps=250):
    kb.run_ms(100)
    for _ in range(steps):
        r = rng.random()
        if r < 0.45:
            k = rng.choice(REAL_KEYS)
            kb.keys ^= {k}
        elif r < 0.6:
            kb.special ^= 1 << rng.choice([1, 2, 3, 4, 7])
        elif r < 0.65:
            kb.send(rng.choice([0x01, 0x05, 0x0A, 0x12, 0x21, 0x22, 0x24, 0x25,
                                0x28, 0x29, 0x2A, 0x30]))
        elif r < 0.7:
            kb.keys.clear()
        kb.run_ms(rng.choice([5, 10, 20, 40, 120]))
    kb.keys.clear(); kb.special = 0
    kb.run_ms(300)
    return kb.received(), kb.cpu.p2, kb.cpu.bus_out


for seed in range(6):
    a = script(Tracked(ORIG), random.Random(seed))
    b = script(Tracked(PATCH), random.Random(seed))
    check(f"normal mode identical to original (random session {seed}, {len(a[0])} bytes)",
          a == b, f"\n orig  {hexs(a[0][:40])}\n patch {hexs(b[0][:40])}")

for cmd in (0x2D, 0x2E):
    kb = Keyboard(PATCH); kb.run_ms(100); kb.send(cmd); kb.run_ms(400)
    check(f"command {cmd:02X}h answers AA", kb.received() == [0xAA], hexs(kb.received()))


# ------------------------------------------------ 2. raw mode
def raw_kb():
    kb = Tracked(PATCH)
    kb.run_ms(100)
    kb.send(0x31)
    kb.run_ms(60)
    return kb


kb = raw_kb()
check("enabling raw mode reports special column 00 00", kb.take() == [0x00, 0x00], hexs(kb.received()))
check("raw flag P2.1 set", kb.cpu.p2 & 0x02 == 0x02)

bad = []
for k in REAL_KEYS:
    kb.keys = {k}; kb.run_ms(40); p = kb.take()
    kb.keys = set(); kb.run_ms(40); r = kb.take()
    if p != [k] or r != [k | 0x80]:
        bad.append((k, p, r))
check(f"every key ({len(REAL_KEYS)}) sends k on press and k|80h on release", not bad, bad[:5])

kb.keys = {0x40}; kb.run_ms(2000)
check("no auto-repeat in raw mode (2 s hold)", kb.take() == [0x40], hexs(kb.received()))
kb.keys = set(); kb.run_ms(40); kb.take()

kb.special = 0x10; kb.run_ms(40)
check("SHIFT down -> 00 10", kb.take() == [0x00, 0x10], hexs(kb.received()))
kb.special = 0x14; kb.run_ms(40)
check("CTRL down too -> 00 14", kb.take() == [0x00, 0x14], hexs(kb.received()))
kb.keys = {0x40}; kb.run_ms(40)
check("key while Shift+Ctrl held is still raw (40)", kb.take() == [0x40], hexs(kb.received()))
kb.keys = set(); kb.special = 0; kb.run_ms(40)
check("release all -> C0 00 00", sorted(kb.take()) == [0x00, 0x00, 0xC0], hexs(kb.received()))
kb.special = 0x02; kb.run_ms(40); kb.special = 0; kb.run_ms(40)
check("CAPS press/release -> 00 02 00 00, LED untouched",
      kb.take() == [0x00, 0x02, 0x00, 0x00] and kb.cpu.p2 & 0x80 == 0, hexs(kb.received()))

# same column, several rows at once
col = [k for k in REAL_KEYS if k & 0x0F == 5]
kb.keys = set(col); kb.run_ms(100); p = kb.take()
kb.keys = set(); kb.run_ms(100); r = kb.take()
check(f"{len(col)} keys in one column pressed together all reported",
      sorted(p) == sorted(col) and sorted(r) == sorted(k | 0x80 for k in col), f"{hexs(p)} / {hexs(r)}")

# many keys at once: TX buffer overflow handling
many = REAL_KEYS[:40]
kb.keys = set(many); kb.run_ms(800); p = kb.take()
kb.keys = set(); kb.run_ms(800); r = kb.take()
check("40 keys at once: each press and release reported exactly once",
      sorted(p) == sorted(many) and sorted(r) == sorted(k | 0x80 for k in many),
      f"{len(p)} presses, {len(r)} releases")

# LED commands
for cmd, bit, val in [(0x32, 0x80, 0x80), (0x33, 0x80, 0), (0x34, 0x40, 0x40), (0x35, 0x40, 0)]:
    kb.send(cmd); kb.run_ms(40)
    check(f"command {cmd:02X}h sets P2 bit {bit:02X} to {val:02X}", kb.cpu.p2 & bit == val)
kb.send(0x05); kb.run_ms(40)
check("original LED command 05h still works in raw mode", kb.cpu.bus_out == 0xEF, f"{kb.cpu.bus_out:02X}")
check("stack never deeper than 2 levels in raw mode", kb.max_sp <= 2, kb.max_sp)

# leave raw mode
kb.take()
kb.send(0x36); kb.run_ms(40)
kb.keys = {0x40}; kb.run_ms(40); kb.keys = set(); kb.run_ms(40)
check("command 36h returns to normal mode ('a' -> 61)", kb.take() == [0x61], hexs(kb.received()))
kb.send(0x31); kb.run_ms(40); kb.take()
kb.send(0x20); kb.run_ms(100)
kb.keys = {0x40}; kb.run_ms(40); kb.keys = set(); kb.run_ms(40)
check("reset command 20h returns to normal mode", kb.take() == [0x61], hexs(kb.received()))

# fuzz raw mode: event stream must track the true key state exactly
rng = random.Random(42)
kb = raw_kb(); kb.take()
state, spec = set(), 0
for _ in range(400):
    if rng.random() < 0.8:
        kb.keys ^= {rng.choice(REAL_KEYS)}
    else:
        kb.special ^= 1 << rng.choice([1, 2, 3, 4, 7])
    kb.run_ms(rng.choice([10, 20, 40, 80]))
kb.run_ms(500)
stream = kb.received()
i = 0
while i < len(stream):
    b = stream[i]
    if b == 0x00:
        spec = stream[i + 1]; i += 2; continue
    (state.add if b < 0x80 else state.discard)(b & 0x7F)
    i += 1
check("raw fuzz: decoded state matches real key state", state == kb.keys and spec == kb.special,
      f"{sorted(state)} vs {sorted(kb.keys)}, {spec:02X} vs {kb.special:02X}")

print("\nALL PASS" if not fails else f"\n{fails} FAILED")
