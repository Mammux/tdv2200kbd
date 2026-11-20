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


def measure(rom, label, enable_raw=False, seed=1, events=600, commands=True):
    kb = Keyboard(rom)
    cpu = kb.cpu
    st = dict(irq_entries=[], irq_len=[], work=[], missed=0, ticks_since_cpl=0,
              tx_edges=[], last_tx=1, cpl_cycle=None, irq_start=None, max_work_at=None)
    step = cpu.step

    def tracked():
        pc, in_irq = cpu.pc, cpu.in_irq
        op = cpu.rom[pc & 0x7FF]
        step()
        if not in_irq and cpu.in_irq:                 # interrupt entered
            st["irq_entries"].append(cpu.cycles)
            st["irq_start"] = cpu.cycles
            st["ticks_since_cpl"] += 1
        if in_irq and not cpu.in_irq:                 # RETR
            st["irq_len"].append(cpu.cycles - st["irq_start"])
        if op == 0xB5 and not in_irq:                 # CPL F1: main starts a tick's work
            if st["ticks_since_cpl"] > 1:
                st["missed"] += st["ticks_since_cpl"] - 1
            st["ticks_since_cpl"] = 0
            st["cpl_cycle"] = cpu.cycles
        if op == 0x76 and not in_irq and st["cpl_cycle"] is not None and pc == st.get("main_pc", pc):
            st["main_pc"] = pc                        # back at JF1: work for this tick done
            w = cpu.cycles - st["cpl_cycle"]
            st["work"].append(w)
            st["cpl_cycle"] = None
        tx = (cpu.p1 >> 5) & 1
        if tx != st["last_tx"]:
            st["tx_edges"].append(cpu.cycles)
            st["last_tx"] = tx

    cpu.step = tracked
    rng = random.Random(seed)
    kb.run_ms(100)
    if enable_raw:
        kb.send(0x31); kb.run_ms(60)
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
    off_grid = max(abs(((b - edges[0]) + TICK // 2) % TICK - TICK // 2) for b in edges)
    framing = sum(1 for x in kb.received() if not isinstance(x, int))
    w = st["work"]
    print(f"{label}")
    print(f"  ticks {len(e)}, bytes sent {len(kb.received())}, framing errors {framing}")
    print(f"  main-loop work per tick: typical {sorted(w)[len(w)//2]} cycles, "
          f"max {max(w)} cycles (budget {TICK}); missed ticks {st['missed']}")
    print(f"  interrupt routine: max {max(st['irq_len'])} cycles; entry jitter max {jitter} cycles")
    print(f"  TX edges off the 160-cycle grid by at most {off_grid} cycles "
          f"({off_grid / TICK * 100:.1f}% of a bit)")
    return st


if __name__ == "__main__":
    measure(ORIG, "Original 965313-0")
    measure(open("965313-0-rawmode.bin", "rb").read(), "Patched, normal mode")
    measure(open("965313-0-rawmode.bin", "rb").read(), "Patched, raw mode", enable_raw=True)
    measure(open("tdv2200-raw.bin", "rb").read(), "Raw-only firmware")
