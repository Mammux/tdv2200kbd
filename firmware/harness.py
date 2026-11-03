"""Test harness: TDV 2200 keyboard board around the MCS-48 emulator."""
from mcs48 import CPU

TICK_HZ = 2400          # timer interrupt rate = TX bit rate


class Keyboard:
    def __init__(self, rom):
        self.cpu = CPU(rom)
        self.keys = set()          # pressed matrix keys, index 0x00-0x7F
        self.special = 0x00        # special column bitmap (CAPS, CTRL, LOCK, SHIFT, ...)
        self.ticks = 0
        self.tx_samples = []
        self.rx_bits = []          # pending T0 levels, one per tick
        self.cpu.read_bus = self._bus
        self.cpu.on_tick = self._tick

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
        self.tx_samples.append((cpu.p1 >> 5) & 1)
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

    def received(self):
        """Decode keyboard -> host bytes from TX samples (1 sample per bit)."""
        s = self.tx_samples
        out, i = [], 0
        while i < len(s):
            if s[i] == 0 and i + 9 < len(s):
                byte = 0
                for b in range(8):
                    byte |= s[i + 1 + b] << b
                if s[i + 9] != 1:
                    out.append(("framing", byte))
                else:
                    out.append(byte)
                i += 10
            else:
                i += 1
        return out

    def take(self):
        """Return bytes received since the last call."""
        r = self.received()
        self.tx_samples = self.tx_samples[-0:] if False else []
        return r
