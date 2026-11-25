"""Test harness: TDV 2200 keyboard board around the MCS-48 emulator."""
from bisect import bisect_right

from mcs48 import CPU

TICK_HZ = 2400          # timer interrupt rate (and TX bit rate at 2400 baud)
CYCLES_PER_S = 384000   # 5.76 MHz / 15


class Keyboard:
    def __init__(self, rom, baud=2400):
        self.cpu = CPU(rom)
        self.keys = set()          # pressed matrix keys, index 0x00-0x7F
        self.special = 0x00        # special column bitmap (CAPS, CTRL, LOCK, SHIFT, ...)
        self.ticks = 0
        self.baud = baud           # what the host's receiver is set to
        self.edge_t = []           # TX line (P1.5) changes: cycle ...
        self.edge_v = []           # ... and the new level
        self._tx = 1
        self._pos = 0              # cycle where the next take() starts looking
        self.rx_bits = []          # pending T0 levels, one per tick
        self.cpu.read_bus = self._bus
        self.cpu.on_tick = self._tick
        step = self.cpu.step

        def step_and_watch_tx():
            step()
            v = (self.cpu.p1 >> 5) & 1
            if v != self._tx:
                self._tx = v
                self.edge_t.append(self.cpu.cycles)
                self.edge_v.append(v)
        self.cpu.step = step_and_watch_tx

    # BUS read: P1.0-3 selects a column via the 74LS154, P1.4 selects the special column
    def _bus(self, cpu):
        if cpu.p1 & 0x10:
            return self.special
        col = cpu.p1 & 0x0F
        v = 0
        for k in self.keys:
            if k & 0x0F == col:
                v |= 1 << (7 - (k >> 4))
        return v

    def _tick(self, cpu):
        self.ticks += 1
        cpu.t0 = self.rx_bits.pop(0) if self.rx_bits else 1

    def run_ticks(self, n):
        end = self.ticks + n
        while self.ticks < end:
            self.cpu.step()

    def run_ms(self, ms):
        self.run_ticks(int(ms * TICK_HZ / 1000))

    def send(self, byte):
        """Host -> keyboard at 600 baud (4 ticks per bit), 8N1."""
        bits = [0] + [(byte >> i) & 1 for i in range(8)] + [1, 1]
        for b in bits:
            self.rx_bits += [b] * 4

    def level(self, t):
        """TX line level at cycle t."""
        i = bisect_right(self.edge_t, t)
        return self.edge_v[i - 1] if i else 1

    def _decode(self):
        """Decode keyboard -> host bytes like a UART set to self.baud.

        From self._pos: wait for a falling edge, sample each bit in its
        middle, check the stop bit, then look for the next start bit after
        the middle of the stop bit. Returns (bytes, position). A byte whose
        stop bit hasn't arrived yet is left for the next call. Framing errors
        come back as ("framing", byte).
        """
        bit = CYCLES_PER_S / self.baud
        now = self.cpu.cycles
        out, pos = [], self._pos
        i = bisect_right(self.edge_t, pos)
        while i < len(self.edge_t):
            t, v = self.edge_t[i], self.edge_v[i]
            if v != 0:
                i += 1
                continue
            if t + 9.5 * bit > now:
                break                          # byte still arriving
            samples = [self.level(t + (k + 0.5) * bit) for k in range(10)]
            pos = t + 9.5 * bit
            i = bisect_right(self.edge_t, pos)
            if samples[0] != 0:
                continue                       # glitch, not a start bit
            byte = sum(b << k for k, b in enumerate(samples[1:9]))
            out.append(byte if samples[9] == 1 else ("framing", byte))
        return out, pos

    def received(self):
        """Complete bytes since the last take(), without consuming them."""
        return self._decode()[0]

    def take(self):
        """Return bytes received since the last call; keep a byte still arriving."""
        out, self._pos = self._decode()
        return out
