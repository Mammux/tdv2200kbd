"""Turn the TDV 2200 raw-mode byte stream into USB key presses and releases.

No hardware access here, so it runs both on the Pico (CircuitPython) and on
a PC for testing.

Raw protocol (keyboard -> host):
    01h-7Fh  key k pressed
    80h-FFh  key k released (k + 80h)
    00h, xx  special column now reads xx (CAPS, CTRL, LOCK, SHIFT ...)

Until the first "00 xx" report the stream is treated as noise (plugging the
cable in produces junk bytes). Releases of keys that are not down and
repeated presses of keys that are already down are ignored, so a glitch
can't leave a key stuck down or press one twice.
"""


class Translator:
    def __init__(self, keys, modifiers):
        self.keys = keys              # k -> HID usage (0 = none)
        self.modifiers = modifiers    # special-column bit -> HID usage
        self.synced = False
        self.want_special = False     # next byte is a special-column bitmap
        self.special = 0
        self.down = set()             # matrix keys currently down
        self.hid_count = {}           # HID usage -> how many physical keys hold it
        self.events = []              # ("press" | "release", usage) for the caller
        self.log = []                 # human-readable notes for the console

    # ---- HID usage bookkeeping (two keys may share one usage, e.g. Home)
    def _hid_down(self, usage):
        if not usage:
            return
        n = self.hid_count.get(usage, 0)
        self.hid_count[usage] = n + 1
        if n == 0:
            self.events.append(("press", usage))

    def _hid_up(self, usage):
        n = self.hid_count.get(usage, 0)
        if not usage or n == 0:
            return
        if n == 1:
            del self.hid_count[usage]
            self.events.append(("release", usage))
        else:
            self.hid_count[usage] = n - 1

    def _special(self, value):
        changed = value ^ self.special
        for bit, usage in self.modifiers.items():
            if changed >> bit & 1:
                if value >> bit & 1:
                    self._hid_down(usage)
                else:
                    self._hid_up(usage)
        self.special = value

    # ---- public
    def feed(self, byte):
        """Process one byte from the keyboard; results go to self.events."""
        if self.want_special:
            self.want_special = False
            if not self.synced:
                self.synced = True
                self.log.append("in sync, special column %02x" % byte)
            self._special(byte)
            return
        if byte == 0x00:
            self.want_special = True
            return
        if not self.synced:
            self.log.append("ignored %02x (not in sync yet)" % byte)
            return
        k = byte & 0x7F
        if byte & 0x80:
            if k in self.down:
                self.down.discard(k)
                self._hid_up(self.keys.get(k, 0))
        elif k not in self.down:
            self.down.add(k)
            usage = self.keys.get(k, 0)
            if not usage:
                self.log.append("key %02x has no USB key assigned" % k)
            self._hid_down(usage)

    def release_all(self):
        """Forget every key (e.g. after a lost connection) and release them."""
        for usage in list(self.hid_count):
            self.events.append(("release", usage))
        self.hid_count.clear()
        self.down.clear()
        self.special = 0

    def take_events(self):
        ev, self.events = self.events, []
        return ev

    def take_log(self):
        log, self.log = self.log, []
        return log
