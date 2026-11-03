# TDV 2200 S (ND 320) keyboard sniffer - CircuitPython, RP2040
#
# Phase 1: find out what the keyboard sends. No USB keyboard yet.
#
# Wiring (see the build sheet):
#   GP1 (UART0 RX) <- MAX3490 RO   keyboard -> host, 2400 baud
#   GP4 (UART1 TX) -> MAX3490 DI   host -> keyboard, 600 baud
#
# Open the board's serial console (Thonny, Mu, `tio /dev/ttyACM0`,
# `screen /dev/ttyACM0 115200`, or PuTTY on COMx) and press keys.
# Every received chunk is printed as:
#   +gap_ms  hex bytes  |printable|
# A gap of more than BURST_MS starts a new line, so one keypress
# (and its release, if the keyboard sends one) is easy to tell apart.
#
# To experiment with commands to the keyboard (LEDs, beeper, ...),
# type hex bytes in the console and press Enter, e.g.:  1b 41
# They are sent to the keyboard at 600 baud.

import sys
import time

import board
import busio
import supervisor

KBD_BAUD_IN = 2400   # keyboard -> host
KBD_BAUD_OUT = 600   # host -> keyboard
BURST_MS = 30        # gap that separates one burst from the next

kbd_in = busio.UART(
    tx=None, rx=board.GP1, baudrate=KBD_BAUD_IN,
    bits=8, parity=None, stop=1, timeout=0, receiver_buffer_size=512,
)
kbd_out = busio.UART(
    tx=board.GP4, rx=None, baudrate=KBD_BAUD_OUT,
    bits=8, parity=None, stop=1,
)


def fmt(data):
    hexs = " ".join("{:02x}".format(b) for b in data)
    text = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    return hexs, text


def send_hex(line):
    try:
        data = bytes(int(tok, 16) for tok in line.replace(",", " ").split())
    except ValueError:
        print("!! could not parse:", repr(line), "- use hex bytes like: 1b 41")
        return
    if data:
        kbd_out.write(data)
        print(">> sent", fmt(data)[0])


print()
print("TDV 2200 sniffer: listening at", KBD_BAUD_IN, "baud on GP1,",
      "sending at", KBD_BAUD_OUT, "baud on GP4")
print("Press keys on the TDV keyboard. Type hex + Enter to send bytes.")

last_ns = time.monotonic_ns()
cmd = ""

while True:
    # Keyboard -> host
    n = kbd_in.in_waiting
    if n:
        data = kbd_in.read(n)
        if data:
            now = time.monotonic_ns()
            gap_ms = (now - last_ns) // 1_000_000
            last_ns = now
            hexs, text = fmt(data)
            if gap_ms > BURST_MS:
                print()
            print("+{:6d} ms  {:<24}  |{}|".format(gap_ms, hexs, text))

    # Console -> keyboard
    while supervisor.runtime.serial_bytes_available:
        ch = sys.stdin.read(1)
        if ch in "\r\n":
            if cmd.strip():
                send_hex(cmd)
            cmd = ""
        else:
            cmd += ch
