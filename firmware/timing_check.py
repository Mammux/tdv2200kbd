"""Cycle timing check: does the main loop or the interrupt ever overrun a tick?

The timer interrupt fires every 5 timer counts = 160 instruction cycles
(2400 Hz). It sends one TX bit per tick and samples RX. The main loop waits
for each tick (F1 handshake) and then does one column of work.

For each ROM this measures, over a busy random session:
  * main-loop work per tick, and how often it takes longer than one tick
    (a "missed tick": two interrupts between consecutive CPL F1)
  * interrupt routine length and entry jitter
  * TX bit timing: every change of the TX line must fall on the 160-cycle grid
  * whether the byte stream decodes without framing errors
"""
import random
import sys

from harness import Keyboard

TICK = 160
ORIG = open("965313-0.bin", "rb").read()
REAL_KEYS = [k for k in range(3, 128) if ORIG[0x600 + k] != 0]


def measure(rom, label, enable_raw=False, seed=1, events=600, commands=True, setup=(), baud=2400):
    """setup: command bytes sent first (e.g. 3Ah for 4800 baud); baud: the
    host's receive speed afterwards."""
    kb = Keyboard(rom)
    cpu = kb.cpu
    bit = 384000 // baud
    st = dict(irq_entries=[], irq_len=[], work=[], ticks_per_round=[], tx_edges=[],
              irq_start=None, work_start=None, last_round=None, last_tx=1)
    step = cpu.step

    def tracked():
        pc, in_irq = cpu.pc, cpu.in_irq
        op = cpu.rom[pc & 0x7FF]
        step()
        if not in_irq and cpu.in_irq:                 # interrupt entered
            st["irq_entries"].append(cpu.cycles)
            st["irq_start"] = cpu.cycles
        if in_irq and not cpu.in_irq:                 # RETR
            st["irq_len"].append(cpu.cycles - st["irq_start"])
        if op == 0x76 and not in_irq:                 # JF1 in the main loop
            if cpu.pc == ((pc + 2) & 0x7FF):          # fell through: a tick's work starts
                n = len(st["irq_entries"])
                if st["last_round"] is not None:
                    st["ticks_per_round"].append(n - st["last_round"])
                st["last_round"] = n
                st["work_start"] = cpu.cycles
            elif st["work_start"] is not None:        # waiting again: work done
                st["work"].append(cpu.cycles - st["work_start"])
                st["work_start"] = None
        tx = (cpu.p1 >> 5) & 1
        if tx != st["last_tx"]:
            st["tx_edges"].append(cpu.cycles)
            st["last_tx"] = tx

    cpu.step = tracked
    rng = random.Random(seed)
    kb.run_ms(100)
    if enable_raw:
        kb.send(0x31); kb.run_ms(60)
    for c in setup:
        kb.send(c); kb.run_ms(40)
    kb.take()
    kb.baud = baud
    kb.run_ms(20); kb.take()
    st["tx_edges"] = []
    for _ in range(events):
        r = rng.random()
        if r < 0.6:
            kb.keys ^= {rng.choice(REAL_KEYS)}
        elif r < 0.75:
            kb.special ^= 1 << rng.choice([1, 2, 3, 4, 7])
        elif r < 0.8 and commands:
            kb.send(rng.choice([0x01, 0x09, 0x21, 0x22, 0x24, 0x25]))
        elif r < 0.85:
            kb.keys = set(rng.sample(REAL_KEYS, 12))    # bursts: many keys at once
        kb.run_ms(rng.choice([2, 5, 10, 20, 40]))
    kb.keys = set(); kb.special = 0; kb.run_ms(500)

    e = st["irq_entries"]
    jitter = max(abs((b - a) - TICK) for a, b in zip(e, e[1:]))
    edges = st["tx_edges"]
    off_grid = max(abs(((b - edges[0]) + bit // 2) % bit - bit // 2) for b in edges)
    got = kb.received()
    framing = sum(1 for x in got if not isinstance(x, int))
    w, tp = st["work"], st["ticks_per_round"]
    slow = sum(1 for x in tp if x > 1)
    print(f"{label}")
    print(f"  ticks {len(e)}, bytes sent {len(got)}, framing errors {framing}")
    print(f"  main-loop work per tick: typical {sorted(w)[len(w)//2]} cycles, max {max(w)}; "
          f"rounds that took more than one tick: {slow} of {len(tp)} ({slow / len(tp) * 100:.1f}%)")
    print(f"  interrupt routine: max {max(st['irq_len'])} cycles (tick = {TICK}); "
          f"entry jitter max {jitter} cycles")
    print(f"  TX edges off the {bit}-cycle bit grid by at most {off_grid} cycles "
          f"({off_grid / bit * 100:.1f}% of a bit)")
    return st


if __name__ == "__main__":
    measure(ORIG, "Original 965313-0")
    measure(open("965313-0-rawmode.bin", "rb").read(), "Patched, normal mode")
    measure(open("965313-0-rawmode.bin", "rb").read(), "Patched, raw mode", enable_raw=True)
    raw = open("tdv2200-raw.bin", "rb").read()
    measure(raw, "Raw-only firmware, 2400 baud")
    measure(raw, "Raw-only firmware, 2400 baud, eager presses", setup=[0x38])
    measure(raw, "Raw-only firmware, 4800 baud", setup=[0x3A], baud=4800)
    measure(raw, "Raw-only firmware, 4800 baud, eager presses", setup=[0x3A, 0x38], baud=4800)
