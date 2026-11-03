"""Minimal Intel MCS-48 (8035/8048) emulator and disassembler.

Written to test firmware patches for the Tandberg TDV 2200 keyboard
(8035 + external 2716). Models what that board uses: timer interrupt,
ports P1/P2, BUS input (key matrix) / output (LED latch), T0, T1, INT.
"""

# ---------------------------------------------------------------- opcode table
# name, length, cycles
OPS = {}
def op(code, name, length=1, cycles=1):
    OPS[code] = (name, length, cycles)

op(0x00, "nop")
op(0x02, "outl bus,a", 1, 2)
op(0x03, "add a,#{d}", 2, 2)
for p in range(8):
    op(0x04 | p << 5, "jmp {a11}", 2, 2)
    op(0x14 | p << 5, "call {a11}", 2, 2)
op(0x05, "en i")
op(0x07, "dec a")
op(0x08, "ins a,bus", 1, 2)
op(0x09, "in a,p1", 1, 2)
op(0x0A, "in a,p2", 1, 2)
op(0x10, "inc @r0"); op(0x11, "inc @r1")
op(0x13, "addc a,#{d}", 2, 2)
op(0x15, "dis i")
op(0x16, "jtf {a8}", 2, 2)
op(0x17, "inc a")
for r in range(8):
    op(0x18 + r, f"inc r{r}")
    op(0x28 + r, f"xch a,r{r}")
    op(0x48 + r, f"orl a,r{r}")
    op(0x58 + r, f"anl a,r{r}")
    op(0x68 + r, f"add a,r{r}")
    op(0x78 + r, f"addc a,r{r}")
    op(0xA8 + r, f"mov r{r},a")
    op(0xB8 + r, f"mov r{r},#{{d}}", 2, 2)
    op(0xC8 + r, f"dec r{r}")
    op(0xD8 + r, f"xrl a,r{r}")
    op(0xE8 + r, f"djnz r{r},{{a8}}", 2, 2)
    op(0xF8 + r, f"mov a,r{r}")
for i in range(2):
    op(0x20 + i, f"xch a,@r{i}")
    op(0x30 + i, f"xchd a,@r{i}")
    op(0x40 + i, f"orl a,@r{i}")
    op(0x50 + i, f"anl a,@r{i}")
    op(0x60 + i, f"add a,@r{i}")
    op(0x70 + i, f"addc a,@r{i}")
    op(0xA0 + i, f"mov @r{i},a")
    op(0xB0 + i, f"mov @r{i},#{{d}}", 2, 2)
    op(0xD0 + i, f"xrl a,@r{i}")
    op(0xF0 + i, f"mov a,@r{i}")
for b in range(8):
    op(0x12 | b << 5, f"jb{b} {{a8}}", 2, 2)
op(0x23, "mov a,#{d}", 2, 2)
op(0x25, "en tcnti")
op(0x26, "jnt0 {a8}", 2, 2)
op(0x27, "clr a")
op(0x35, "dis tcnti")
op(0x36, "jt0 {a8}", 2, 2)
op(0x37, "cpl a")
op(0x39, "outl p1,a", 1, 2)
op(0x3A, "outl p2,a", 1, 2)
op(0x42, "mov a,t")
op(0x43, "orl a,#{d}", 2, 2)
op(0x45, "strt cnt")
op(0x46, "jnt1 {a8}", 2, 2)
op(0x47, "swap a")
op(0x53, "anl a,#{d}", 2, 2)
op(0x55, "strt t")
op(0x56, "jt1 {a8}", 2, 2)
op(0x57, "da a")
op(0x62, "mov t,a")
op(0x65, "stop tcnt")
op(0x67, "rrc a")
op(0x76, "jf1 {a8}", 2, 2)
op(0x77, "rr a")
op(0x83, "ret", 1, 2)
op(0x85, "clr f0")
op(0x86, "jni {a8}", 2, 2)
op(0x88, "orl bus,#{d}", 2, 2)
op(0x89, "orl p1,#{d}", 2, 2)
op(0x8A, "orl p2,#{d}", 2, 2)
op(0x93, "retr", 1, 2)
op(0x95, "cpl f0")
op(0x96, "jnz {a8}", 2, 2)
op(0x97, "clr c")
op(0x98, "anl bus,#{d}", 2, 2)
op(0x99, "anl p1,#{d}", 2, 2)
op(0x9A, "anl p2,#{d}", 2, 2)
op(0xA3, "movp a,@a", 1, 2)
op(0xA5, "clr f1")
op(0xA7, "cpl c")
op(0xB3, "jmpp @a", 1, 2)
op(0xB5, "cpl f1")
op(0xB6, "jf0 {a8}", 2, 2)
op(0xC4 - 0xC4 + 0xC5, "sel rb0")
op(0xC6, "jz {a8}", 2, 2)
op(0xC7, "mov a,psw")
op(0xD3, "xrl a,#{d}", 2, 2)
op(0xD5, "sel rb1")
op(0xD7, "mov psw,a")
op(0xE3, "movp3 a,@a", 1, 2)
op(0xE5, "sel mb0")
op(0xE6, "jnc {a8}", 2, 2)
op(0xE7, "rl a")
op(0xF5, "sel mb1")
op(0xF6, "jc {a8}", 2, 2)
op(0xF7, "rlc a")


def disasm(rom, addr):
    code = rom[addr]
    if code not in OPS:
        return f"db {code:02X}h", 1
    name, length, _ = OPS[code]
    d = rom[(addr + 1) & 0x7FF] if length == 2 else 0
    a11 = ((code >> 5) << 8) | d
    a8 = ((addr + 1) & 0xF00) | d
    return name.format(d=f"{d:02X}h", a11=f"{a11:03X}h", a8=f"{a8:03X}h"), length


# ---------------------------------------------------------------- CPU
class CPU:
    def __init__(self, rom):
        self.rom = bytearray(rom)
        self.ram = bytearray(64)
        self.reset()
        # external world
        self.read_bus = lambda cpu: 0x00      # value on BUS during INS
        self.t0 = 1
        self.t1 = 1
        self.int_pin = 1
        self.on_tick = None                   # called after each timer ISR entry

    def reset(self):
        self.pc = 0
        self.a = 0
        self.cy = self.ac = self.f0 = self.f1 = 0
        self.bs = 0
        self.sp = 0
        self.p1 = 0xFF
        self.p2 = 0xFF
        self.bus_out = 0xFF
        self.t = 0
        self.timer_run = False
        self.prescale = 0
        self.tf = 0
        self.tcnti = False
        self.ien = False
        self.in_irq = False
        self.timer_pending = False
        self.cycles = 0

    # registers
    def r(self, n):
        return self.ram[(self.bs * 0x18) + n]

    def setr(self, n, v):
        self.ram[(self.bs * 0x18) + n] = v & 0xFF

    def psw(self):
        return (self.cy << 7) | (self.ac << 6) | (self.f0 << 5) | (self.bs << 4) | 0x08 | self.sp

    def setpsw(self, v):
        self.cy = v >> 7 & 1
        self.ac = v >> 6 & 1
        self.f0 = v >> 5 & 1
        self.bs = v >> 4 & 1
        self.sp = v & 7

    def push(self):
        base = 8 + 2 * self.sp
        self.ram[base] = self.pc & 0xFF
        self.ram[base + 1] = ((self.psw() & 0xF0) | (self.pc >> 8 & 0x0F))
        self.sp = (self.sp + 1) & 7

    def pop(self, restore_psw):
        self.sp = (self.sp - 1) & 7
        base = 8 + 2 * self.sp
        lo, hi = self.ram[base], self.ram[base + 1]
        self.pc = ((hi & 0x0F) << 8) | lo
        if restore_psw:
            self.cy = hi >> 7 & 1
            self.ac = hi >> 6 & 1
            self.f0 = hi >> 5 & 1
            self.bs = hi >> 4 & 1

    def fetch(self):
        b = self.rom[self.pc & 0x7FF]
        self.pc = (self.pc & 0x800) | ((self.pc + 1) & 0x7FF)
        return b

    def add(self, v, carry=0):
        s = self.a + v + carry
        self.ac = 1 if ((self.a & 0xF) + (v & 0xF) + carry) > 0xF else 0
        self.cy = 1 if s > 0xFF else 0
        self.a = s & 0xFF

    def clock(self, n):
        for _ in range(n):
            self.cycles += 1
            if self.timer_run:
                self.prescale += 1
                if self.prescale == 32:
                    self.prescale = 0
                    self.t = (self.t + 1) & 0xFF
                    if self.t == 0:
                        self.tf = 1
                        if self.tcnti:
                            self.timer_pending = True

    def step(self):
        # interrupts
        if not self.in_irq:
            if self.ien and self.int_pin == 0:
                self.push(); self.pc = 3; self.in_irq = True; self.clock(2)
                return
            if self.timer_pending and self.tcnti:
                self.timer_pending = False
                self.push(); self.pc = 7; self.in_irq = True; self.clock(2)
                if self.on_tick:
                    self.on_tick(self)
                return
        addr = self.pc
        code = self.fetch()
        if code not in OPS:
            raise RuntimeError(f"illegal opcode {code:02X} at {addr:03X}")
        name, length, cyc = OPS[code]
        d = self.fetch() if length == 2 else 0
        self.clock(cyc)
        page = (addr + 1) & 0xF00          # page of the operand byte

        def jcond(c):
            if c:
                self.pc = page | d

        hi3, lo5 = code >> 5, code & 0x1F
        if lo5 == 0x04:                    # JMP
            self.pc = (hi3 << 8) | d
        elif lo5 == 0x14:                  # CALL
            self.push(); self.pc = (hi3 << 8) | d
        elif lo5 == 0x12:                  # JBb
            jcond(self.a >> hi3 & 1)
        elif 0x18 <= code <= 0x1F: self.setr(code - 0x18, self.r(code - 0x18) + 1)
        elif 0x28 <= code <= 0x2F:
            n = code - 0x28; t = self.r(n); self.setr(n, self.a); self.a = t
        elif 0x48 <= code <= 0x4F: self.a |= self.r(code - 0x48)
        elif 0x58 <= code <= 0x5F: self.a &= self.r(code - 0x58)
        elif 0x68 <= code <= 0x6F: self.add(self.r(code - 0x68))
        elif 0x78 <= code <= 0x7F: self.add(self.r(code - 0x78), self.cy)
        elif 0xA8 <= code <= 0xAF: self.setr(code - 0xA8, self.a)
        elif 0xB8 <= code <= 0xBF: self.setr(code - 0xB8, d)
        elif 0xC8 <= code <= 0xCF: self.setr(code - 0xC8, self.r(code - 0xC8) - 1)
        elif 0xD8 <= code <= 0xDF: self.a ^= self.r(code - 0xD8)
        elif 0xE8 <= code <= 0xEF:
            n = code - 0xE8; self.setr(n, self.r(n) - 1); jcond(self.r(n) != 0)
        elif 0xF8 <= code <= 0xFF: self.a = self.r(code - 0xF8)
        elif code in (0x10, 0x11):
            p = self.r(code & 1) & 0x3F; self.ram[p] = (self.ram[p] + 1) & 0xFF
        elif code in (0x20, 0x21):
            p = self.r(code & 1) & 0x3F; self.a, self.ram[p] = self.ram[p], self.a
        elif code in (0x30, 0x31):
            p = self.r(code & 1) & 0x3F
            a, m = self.a, self.ram[p]
            self.a = (a & 0xF0) | (m & 0x0F); self.ram[p] = (m & 0xF0) | (a & 0x0F)
        elif code in (0x40, 0x41): self.a |= self.ram[self.r(code & 1) & 0x3F]
        elif code in (0x50, 0x51): self.a &= self.ram[self.r(code & 1) & 0x3F]
        elif code in (0x60, 0x61): self.add(self.ram[self.r(code & 1) & 0x3F])
        elif code in (0x70, 0x71): self.add(self.ram[self.r(code & 1) & 0x3F], self.cy)
        elif code in (0xA0, 0xA1): self.ram[self.r(code & 1) & 0x3F] = self.a
        elif code in (0xB0, 0xB1): self.ram[self.r(code & 1) & 0x3F] = d
        elif code in (0xD0, 0xD1): self.a ^= self.ram[self.r(code & 1) & 0x3F]
        elif code in (0xF0, 0xF1): self.a = self.ram[self.r(code & 1) & 0x3F]
        elif code == 0x00: pass
        elif code == 0x02: self.bus_out = self.a
        elif code == 0x03: self.add(d)
        elif code == 0x05: self.ien = True
        elif code == 0x07: self.a = (self.a - 1) & 0xFF
        elif code == 0x08: self.a = self.read_bus(self) & 0xFF
        elif code == 0x09: self.a = self.p1
        elif code == 0x0A: self.a = self.p2
        elif code == 0x13: self.add(d, self.cy)
        elif code == 0x15: self.ien = False
        elif code == 0x16:
            t = self.tf; self.tf = 0; jcond(t)
        elif code == 0x17: self.a = (self.a + 1) & 0xFF
        elif code == 0x23: self.a = d
        elif code == 0x25: self.tcnti = True
        elif code == 0x26: jcond(self.t0 == 0)
        elif code == 0x27: self.a = 0
        elif code == 0x35: self.tcnti = False; self.timer_pending = False
        elif code == 0x36: jcond(self.t0 == 1)
        elif code == 0x37: self.a ^= 0xFF
        elif code == 0x39: self.p1 = self.a
        elif code == 0x3A: self.p2 = self.a
        elif code == 0x42: self.a = self.t
        elif code == 0x43: self.a |= d
        elif code == 0x46: jcond(self.t1 == 0)
        elif code == 0x47: self.a = ((self.a << 4) | (self.a >> 4)) & 0xFF
        elif code == 0x53: self.a &= d
        elif code == 0x55: self.timer_run = True; self.prescale = 0
        elif code == 0x56: jcond(self.t1 == 1)
        elif code == 0x62: self.t = self.a
        elif code == 0x65: self.timer_run = False
        elif code == 0x67:
            c = self.a & 1; self.a = (self.a >> 1) | (self.cy << 7); self.cy = c
        elif code == 0x76: jcond(self.f1)
        elif code == 0x77: self.a = ((self.a >> 1) | (self.a << 7)) & 0xFF
        elif code == 0x83: self.pop(False)
        elif code == 0x85: self.f0 = 0
        elif code == 0x86: jcond(self.int_pin == 0)
        elif code == 0x88: self.bus_out |= d
        elif code == 0x89: self.p1 |= d
        elif code == 0x8A: self.p2 |= d
        elif code == 0x93: self.pop(True); self.in_irq = False
        elif code == 0x95: self.f0 ^= 1
        elif code == 0x96: jcond(self.a != 0)
        elif code == 0x97: self.cy = 0
        elif code == 0x98: self.bus_out &= d
        elif code == 0x99: self.p1 &= d
        elif code == 0x9A: self.p2 &= d
        elif code == 0xA3: self.a = self.rom[(self.pc & 0x700) | self.a]
        elif code == 0xA5: self.f1 = 0
        elif code == 0xA7: self.cy ^= 1
        elif code == 0xB3: self.pc = (addr & 0x700) | self.rom[(addr & 0x700) | self.a]
        elif code == 0xB5: self.f1 ^= 1
        elif code == 0xB6: jcond(self.f0)
        elif code == 0xC5: self.bs = 0
        elif code == 0xC6: jcond(self.a == 0)
        elif code == 0xC7: self.a = self.psw()
        elif code == 0xD3: self.a ^= d
        elif code == 0xD5: self.bs = 1
        elif code == 0xD7: self.setpsw(self.a)
        elif code == 0xE3: self.a = self.rom[0x300 | self.a]
        elif code in (0xE5, 0xF5): pass
        elif code == 0xE6: jcond(not self.cy)
        elif code == 0xE7: self.a = ((self.a << 1) | (self.a >> 7)) & 0xFF
        elif code == 0xF6: jcond(self.cy)
        elif code == 0xF7:
            c = self.a >> 7; self.a = ((self.a << 1) | self.cy) & 0xFF; self.cy = c
        else:
            raise RuntimeError(f"unimplemented {code:02X} {name} at {addr:03X}")
