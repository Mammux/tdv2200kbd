"""Emulator tests for the raw-only firmware's optional modes:
4800 baud (3Ah/3Bh) and eager key presses (38h/39h).

Also measures key-press latency in each mode, with bouncing contacts.

Usage: python3 test_raw_modes.py
"""
import random
from harness import Keyboard, CYCLES_PER_S

RAW = open("tdv2200-raw.bin", "rb").read()
ORIG = open("965313-0.bin", "rb").read()
REAL_KEYS = [k for k in range(3, 128) if ORIG[0x600 + k] != 0]
TICK_MS = 1000 / 2400
fails = 0


def check(name, cond, detail=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails += 1


def hexs(seq):
    return " ".join(f"{x:02X}" if isinstance(x, int) else str(x) for x in seq)


def keyboard(*commands, baud=2400):
    """A keyboard after power-up, with commands sent and the host set to baud."""
    kb = Keyboard(RAW)
    kb.run_ms(40); kb.take()
    for c in commands:
        kb.send(c); kb.run_ms(40)
    kb.take()                          # anything sent before the host switches
    kb.baud = baud
    kb.run_ms(40)
    return kb


def press_release_all(kb):
    bad = []
    for k in REAL_KEYS:
        kb.keys = {k}; kb.run_ms(40); p = kb.take()
        kb.keys = set(); kb.run_ms(40); r = kb.take()
        if p != [k] or r != [k | 0x80]:
            bad.append((hex(k), p, r))
    return bad


def bounce(kb, key, down, rng, ms):
    """Change key to down, with the contact chattering for up to ms first."""
    end = kb.cpu.cycles + ms * CYCLES_PER_S / 1000
    while kb.cpu.cycles < end:
        kb.keys ^= {key}
        kb.run_ticks(rng.choice([1, 1, 2, 3]))
    (kb.keys.add if down else kb.keys.discard)(key)


# --- switching speed -------------------------------------------------------

kb = Keyboard(RAW)
kb.run_ms(40); kb.take()
kb.special = 0x60; kb.run_ms(40); kb.take()
kb.send(0x3A); kb.run_ms(20)           # 16.7 ms to receive the command at 600 baud
kb.take(); kb.baud = 4800; kb.run_ms(40)
check("3Ah: keyboard reports 00 xx at 4800 baud", kb.take() == [0x00, 0x60], hexs(kb.received()))
bad = press_release_all(kb)
check(f"4800 baud: every key ({len(REAL_KEYS)}) press and release", not bad, bad[:5])
many = REAL_KEYS[:40]
kb.keys = set(many); kb.run_ms(800); p = kb.take()
kb.keys = set(); kb.run_ms(800); r = kb.take()
check("4800 baud: 40 keys at once, each press and release exactly once, no framing errors",
      sorted(p) == sorted(many) and sorted(r) == sorted(k | 0x80 for k in many),
      f"{len(p)} presses, {len(r)} releases")
kb.send(0x24); kb.send(0x32); kb.run_ms(60)
check("4800 baud: commands still work (32h Caps LED)", kb.cpu.p2 & 0x80)

# switch in the middle of a burst: the byte being sent is finished at 4800,
# the rest of the queue goes out at 2400, then 00 xx
kb.keys = set(); kb.run_ms(100); kb.take()
kb.keys = set(many)
kb.send(0x3B)
while kb.cpu.f0:                        # run until the keyboard switches
    kb.cpu.step()
t_switch = kb.cpu.cycles                # it switches as the last stop bit starts:
while kb.cpu.cycles < t_switch + 80:    # let the host see that stop bit
    kb.cpu.step()
before = kb.take()                      # decoded at 4800
kb.baud = 2400
kb.run_ms(1500)
after = kb.take()
sent = before + after
check("3Bh during a burst: bytes before the switch at 4800, after it at 2400, none lost",
      all(isinstance(x, int) for x in sent) and len(before) > 0 and after[-2:] == [0x00, 0x60]
      and sorted(sent[:-2]) == sorted(many),
      f"{len(before)} before, {len(after)} after: {hexs(sent[-6:])}")
kb.keys = set(); kb.run_ms(1500); kb.take()
check("2400 baud again: keys work", press_release_all(kb) == [])

kb.send(0x3A); kb.run_ms(20); kb.take(); kb.baud = 4800; kb.run_ms(40); kb.take()
kb.send(0x20); kb.run_ms(20); kb.take(); kb.baud = 2400; kb.run_ms(60)
check("20h reset goes back to 2400 baud", kb.take() == [0x00, 0x60], hexs(kb.received()))

# --- eager presses ---------------------------------------------------------

kb = keyboard(0x38)
kb.keys = {0x40}; kb.run_ms(3); kb.keys = set(); kb.run_ms(40)
check("eager: a 3 ms spike is reported as a short press (the known cost)",
      kb.take() == [0x40, 0xC0], hexs(kb.received()))
kb.send(0x39); kb.run_ms(40); kb.take()
kb.keys = {0x40}; kb.run_ms(3); kb.keys = set(); kb.run_ms(40)
check("39h: eager off, 3 ms spike ignored again", kb.take() == [], hexs(kb.received()))
kb.send(0x38); kb.run_ms(40)
kb.special = 0x04; kb.run_ms(3); kb.special = 0; kb.run_ms(40)
check("eager: modifier column is still debounced (3 ms spike ignored)", kb.take() == [],
      hexs(kb.received()))
kb.send(0x20); kb.run_ms(60); kb.take()
kb.keys = {0x40}; kb.run_ms(3); kb.keys = set(); kb.run_ms(40)
check("20h reset turns eager presses off", kb.take() == [], hexs(kb.received()))

kb = keyboard(0x38)
bad = press_release_all(kb)
check("eager: every key press and release", not bad, bad[:5])
col = [k for k in REAL_KEYS if k & 0x0F == 5]
kb.keys = set(col); kb.run_ms(100); p = kb.take()
kb.keys = set(); kb.run_ms(100); r = kb.take()
check("eager: all keys of one column together", sorted(p) == sorted(col)
      and sorted(r) == sorted(k | 0x80 for k in col))

# per-key debounce: a key in the same column as a chattering key is not held up
for label, cmds in (("defer", ()), ("eager", (0x38,))):
    kb = keyboard(*cmds)
    rng = random.Random(3)
    a, b = 0x15, 0x25                    # same column (5)
    kb.keys = {a}
    for _ in range(int(40 / TICK_MS)):   # a chatters for 40 ms ...
        kb.keys ^= {a}
        kb.run_ticks(rng.choice([1, 2, 3]))
    kb.keys = set(); kb.run_ms(40); kb.take()
    kb.keys = {b}
    for _ in range(int(20 / TICK_MS)):   # ... and while it chatters again, b is pressed
        kb.keys ^= {a}
        kb.run_ticks(rng.choice([1, 2, 3]))
    kb.keys.discard(a); kb.run_ms(40)
    got = kb.take()
    check(f"{label}: a key is reported while another key in its column chatters",
          0x25 in got, hexs(got))

# bouncing contacts: exactly one press and one release
for label, cmds, baud in (("2400 defer", (), 2400), ("2400 eager", (0x38,), 2400),
                          ("4800 eager", (0x3A, 0x38), 4800)):
    kb = keyboard(*cmds, baud=baud)
    rng = random.Random(11)
    bad = 0
    for i in range(150):
        k = rng.choice(REAL_KEYS)
        kb.run_ms(rng.uniform(0, 10))
        bounce(kb, k, True, rng, rng.uniform(0, 5)); kb.run_ms(rng.uniform(30, 80))
        bounce(kb, k, False, rng, rng.uniform(0, 5)); kb.run_ms(40)
        got = kb.take()
        if got != [k, k | 0x80]:
            bad += 1
    check(f"{label}: 150 presses with up to 5 ms of contact bounce -> one press, one release each",
          bad == 0, f"{bad} wrong")

# fuzz at 4800 baud with eager presses: decoded state matches the real state
kb = keyboard(0x3A, 0x38, baud=4800)
kb.take()
rng = random.Random(7)
for _ in range(500):
    if rng.random() < 0.8:
        kb.keys ^= {rng.choice(REAL_KEYS)}
    else:
        kb.special ^= 1 << rng.choice([1, 2, 3, 4, 7])
    kb.run_ms(rng.choice([10, 20, 40, 80]))
kb.run_ms(500)
state, spec, s, i = set(), None, kb.received(), 0
ok = all(isinstance(x, int) for x in s)
while ok and i < len(s):
    if s[i] == 0:
        spec = s[i + 1]; i += 2; continue
    (state.add if s[i] < 0x80 else state.discard)(s[i] & 0x7F); i += 1
check("fuzz at 4800 baud, eager: decoded state matches real state, no framing errors",
      ok and state == kb.keys and (spec == kb.special or spec is None))

# --- latency ---------------------------------------------------------------

print("\nKey press latency (key down -> end of the byte at the host), 300 presses:")
results = {}
for label, cmds, baud in (("2400 baud, defer (power-up default)", (), 2400),
                          ("4800 baud, defer", (0x3A,), 4800),
                          ("2400 baud, eager", (0x38,), 2400),
                          ("4800 baud, eager", (0x3A, 0x38), 4800)):
    kb = keyboard(*cmds, baud=baud)
    rng = random.Random(5)
    lat = []
    for _ in range(300):
        k = rng.choice(REAL_KEYS)
        kb.run_ms(rng.uniform(0, 10))
        kb.take()
        t0 = kb.cpu.cycles
        kb.keys = {k}
        got = []
        while not got:
            kb.run_ticks(1)
            got = kb.take()
        lat.append((kb._pos - t0) / CYCLES_PER_S * 1000)
        kb.run_ms(40); kb.keys = set(); kb.run_ms(40); kb.take()
    lat.sort()
    results[label] = lat
    print(f"  {label:38s} min {lat[0]:5.1f}  mean {sum(lat) / len(lat):5.1f}  "
          f"max {lat[-1]:5.1f} ms")
m = {k: sum(v) / len(v) for k, v in results.items()}
check("4800 baud + eager is the fastest, by at least 8 ms on average",
      m["2400 baud, defer (power-up default)"] - m["4800 baud, eager"] >= 8, m)

print("\nALL PASS" if not fails else f"\n{fails} FAILED")
