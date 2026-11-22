"""Tests for the CircuitPython USB keyboard firmware (adapter/usb).

1. The translator, fed with what the emulated keyboard (running the real
   tdv2200-raw.bin and 965313-0-rawmode.bin images) sends.
2. code.py itself, run on a PC with stand-ins for the CircuitPython modules
   (board, busio, supervisor, usb_hid, adafruit_hid) wired to the emulator.

    python3 adapter/tests/test_usb.py
"""
import os
import random
import runpy
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
FW = os.path.join(ROOT, "firmware")
USB = os.path.join(ROOT, "adapter", "usb")
sys.path[:0] = [FW, USB]

from harness import Keyboard  # noqa: E402  (8035 emulator + keyboard model)
import keymap  # noqa: E402
from tdv_translate import Translator  # noqa: E402

RAW = open(os.path.join(FW, "tdv2200-raw.bin"), "rb").read()
PATCHED = open(os.path.join(FW, "965313-0-rawmode.bin"), "rb").read()
ORIG = open(os.path.join(FW, "965313-0.bin"), "rb").read()
REAL_KEYS = [k for k in range(3, 128) if ORIG[0x600 + k] != 0]
SPECIAL_AL = 0x60            # AL1 + AL2, set on the prototype's keyboard
fails = 0


def check(name, cond, detail=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {detail}"))
    fails += not cond


class Rig:
    """Emulated keyboard -> translator, tracking which USB keys are down."""

    def __init__(self, rom, enable=None):
        self.kb = Keyboard(rom)
        self.kb.special = SPECIAL_AL
        self.tr = Translator(keymap.KEYS, keymap.MODIFIERS)
        self.usb_down = set()
        self.events = []
        self.kb.run_ms(100)
        if enable:
            self.kb.send(enable)
        self.step(60)

    def step(self, ms):
        self.kb.run_ms(ms)
        for b in self.kb.take():
            assert isinstance(b, int), "framing error from keyboard"
            self.tr.feed(b)
        for kind, usage in self.tr.take_events():
            self.events.append((kind, usage))
            (self.usb_down.add if kind == "press" else self.usb_down.discard)(usage)

    def expected_down(self):
        want = {keymap.KEYS.get(k, 0) for k in self.kb.keys} - {0}
        want |= {u for bit, u in keymap.MODIFIERS.items() if self.kb.special >> bit & 1}
        return want


# ---------------------------------------------------------------- translator
for label, rom, enable in (("raw-only ROM", RAW, None), ("patched ROM, raw mode", PATCHED, 0x31)):
    r = Rig(rom, enable)
    check(f"{label}: in sync after start-up report, nothing pressed", r.tr.synced and not r.usb_down)
    bad = []
    for k in REAL_KEYS:
        r.events.clear()
        r.kb.keys = {k}; r.step(40)
        pressed = list(r.events)
        r.kb.keys = set(); r.step(40)
        usage = keymap.KEYS.get(k, 0)
        want = [("press", usage), ("release", usage)] if usage else []
        if r.events != want:
            bad.append((hex(k), r.events))
    check(f"{label}: all {len(REAL_KEYS)} keys press and release their USB key", not bad, bad[:4])

    r.events.clear()
    for bit, usage in keymap.MODIFIERS.items():
        r.kb.special = SPECIAL_AL | 1 << bit; r.step(40)
        r.kb.special = SPECIAL_AL; r.step(40)
    want = [e for bit, u in keymap.MODIFIERS.items() for e in (("press", u), ("release", u))]
    check(f"{label}: CAPS, CTRL, LOCK and SHIFT press/release their USB keys", r.events == want, r.events)

    r.events.clear()
    r.kb.special = SPECIAL_AL | 0x10; r.step(40)          # Shift down
    r.kb.keys = {0x40}; r.step(40)                         # A
    r.kb.keys = set(); r.step(40)
    r.kb.special = SPECIAL_AL; r.step(40)
    check(f"{label}: Shift+A gives Shift down, A down, A up, Shift up",
          r.events == [("press", 0xE1), ("press", 0x04), ("release", 0x04), ("release", 0xE1)], r.events)

    # Random typing. Every 20 events, let the keyboard catch up (it sends one
    # byte per 4 ms and reports one change per column per 7 ms scan) and
    # check that exactly the right USB keys are down.
    rng = random.Random(3)
    bad = []
    for i in range(1, 301):
        if rng.random() < 0.8:
            r.kb.keys ^= {rng.choice(REAL_KEYS)}
        else:
            r.kb.special ^= 1 << rng.choice([1, 2, 3, 4])
        r.step(rng.choice([10, 20, 40]))
        if i % 20 == 0:
            r.step(1000)
            if r.usb_down != r.expected_down():
                bad.append((i, sorted(r.usb_down ^ r.expected_down())))
    r.kb.keys = set(); r.kb.special = SPECIAL_AL; r.step(1000)
    check(f"{label}: 300 random events: USB keys down match the real keys at every check",
          not bad and not r.usb_down, (bad[:3], sorted(r.usb_down)))

# noise and glitches, fed directly
t = Translator(keymap.KEYS, keymap.MODIFIERS)
for b in (0xFF, 0x35, 0xFE, 0x40):
    t.feed(b)
check("bytes before the first 00 xx report are ignored", not t.synced and not t.take_events())
t.feed(0x00); t.feed(0x60)
check("00 60 puts it in sync, AL1/AL2 press nothing", t.synced and not t.take_events())
t.feed(0xC0)
check("release of a key that isn't down is ignored", not t.take_events())
t.feed(0x40); t.feed(0x40)
check("a repeated press is sent once", t.take_events() == [("press", 0x04)])
t.feed(0xC0)
t.take_events()
home, field_left = 0x3D, 0x4D                  # B48 Home and C47 FieldLeft both send Home
t.feed(home); t.feed(field_left); t.feed(home | 0x80)
mid = t.take_events()
t.feed(field_left | 0x80)
check("two keys sharing a USB key: released only when both are up",
      mid == [("press", 0x4A)] and t.take_events() == [("release", 0x4A)])
t.feed(0x0B)                                   # G50, a blank key with nothing assigned
check("unassigned key sends nothing and is logged",
      not t.take_events() and any("no USB key" in s for s in t.take_log()))


# ---------------------------------------------------------------- code.py on stand-ins
class StopTest(Exception):
    pass


class FakeHID:
    LED_CAPS_LOCK = 2

    def __init__(self, devices):
        self.down, self.log, self.leds = set(), [], 0

    def press(self, *codes):
        for c in codes:
            if c not in self.down and len([d for d in self.down if d < 0xE0]) >= 6 and c < 0xE0:
                raise ValueError("Trying to press more than six keys at once.")
            self.down.add(c); self.log.append(("press", c))

    def release(self, *codes):
        for c in codes:
            self.down.discard(c); self.log.append(("release", c))

    def led_on(self, led):
        return bool(self.leds & led)


def run_code_py(rom, script):
    """Run adapter/usb/code.py with the emulator behind fake UARTs.

    script: list of (ms, action) run in the fake time line; action(kb, hid) or None.
    """
    kb = Keyboard(rom)
    kb.special = SPECIAL_AL
    state = {"hid": None, "t": 0.0, "script": list(script), "sent": []}

    class UART:
        def __init__(self, tx=None, rx=None, baudrate=9600, **kw):
            self.rx = rx is not None

        @property
        def in_waiting(self):
            # each poll of the main loop advances the emulated world by 2 ms
            if not state["script"]:
                raise StopTest
            ms, action = state["script"][0]
            if ms <= 0:
                state["script"].pop(0)
                if action:
                    action(kb, state["hid"])
            else:
                state["script"][0] = (ms - 2, action)
            kb.run_ms(2)
            state["t"] += 0.002
            state["pending"] = kb.take()
            return len(state["pending"])

        def read(self, n):
            return bytes(state.pop("pending", []))

        def write(self, data):
            state["sent"] += list(data)
            for b in data:
                kb.send(b)

    def hid_factory(devices):
        state["hid"] = FakeHID(devices)
        return state["hid"]

    mods = {
        "board": types.SimpleNamespace(GP1="GP1", GP4="GP4"),
        "busio": types.SimpleNamespace(UART=UART),
        "supervisor": types.SimpleNamespace(runtime=types.SimpleNamespace(serial_bytes_available=False)),
        "usb_hid": types.SimpleNamespace(devices=[]),
        "adafruit_hid": types.ModuleType("adafruit_hid"),
        "adafruit_hid.keyboard": types.SimpleNamespace(Keyboard=None),
    }
    FakeHID.__init__  # keep class attribute LED_CAPS_LOCK reachable as Keyboard.LED_CAPS_LOCK
    kbd_cls = type("Keyboard", (), {"LED_CAPS_LOCK": FakeHID.LED_CAPS_LOCK,
                                    "__new__": lambda cls, devices: hid_factory(devices)})
    mods["adafruit_hid.keyboard"].Keyboard = kbd_cls
    real_sleep = __import__("time").sleep
    saved = {m: sys.modules.get(m) for m in mods}
    sys.modules.update(mods)
    import time as _time
    _time.sleep = lambda s: None
    real_mono = _time.monotonic
    _time.monotonic = lambda: state["t"]
    out = []
    real_print = __builtins__.print if hasattr(__builtins__, "print") else print
    try:
        import builtins
        builtins.print = lambda *a, **k: out.append(" ".join(str(x) for x in a))
        runpy.run_path(os.path.join(USB, "code.py"), run_name="__main__")
    except StopTest:
        pass
    finally:
        import builtins
        builtins.print = real_print
        _time.sleep, _time.monotonic = real_sleep, real_mono
        for m, v in saved.items():
            if v is None:
                sys.modules.pop(m, None)
            else:
                sys.modules[m] = v
    return state, out


def press(*keys):
    return lambda kb, hid: kb.keys.update(keys)


def release_all(kb, hid):
    kb.keys.clear()


def caps_led(on):
    def act(kb, hid):
        hid.leds = FakeHID.LED_CAPS_LOCK if on else 0
    return act


LETTER_KEYS = [k for k in REAL_KEYS if 0x04 <= keymap.KEYS.get(k, 0) <= 0x1D]   # A-Z
state, out = run_code_py(RAW, [
    (300, None),
    (0, press(0x40)), (60, None), (0, release_all), (60, None),          # A
    (0, lambda kb, hid: setattr(kb, "special", SPECIAL_AL | 0x04)), (60, None),   # Ctrl down
    (0, press(0x33)), (60, None), (0, release_all), (60, None),          # C
    (0, lambda kb, hid: setattr(kb, "special", SPECIAL_AL)), (60, None),
    (0, caps_led(True)), (100, None), (0, caps_led(False)), (100, None),
    (0, press(*LETTER_KEYS[:10])), (200, None), (0, release_all), (200, None),
])
hid = state["hid"]
check("code.py: A, then Ctrl+C reach USB in order",
      hid.log[:6] == [("press", 0x04), ("release", 0x04), ("press", 0xE0), ("press", 0x06),
                      ("release", 0x06), ("release", 0xE0)], hid.log[:6])
check("code.py: Caps LED follows the computer (32 then 33 sent)",
      state["sent"][-2:] == [0x32, 0x33] or (0x32 in state["sent"] and state["sent"][-1] == 0x33),
      state["sent"])
check("code.py: 10 keys at once: the 7th and later are refused by USB, nothing stays down",
      not hid.down and any("more than 6 keys" in s for s in out), (sorted(hid.down), out[-5:]))
check("code.py: sends 31 at start-up", state["sent"][:1] == [0x31], state["sent"])

state, out = run_code_py(PATCHED, [(300, None), (0, press(0x40)), (60, None), (0, release_all), (60, None)])
check("code.py with the patched ROM: 31 turns raw mode on and A works",
      state["hid"].log == [("press", 0x04), ("release", 0x04)], state["hid"].log)

print("\nALL PASS" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
