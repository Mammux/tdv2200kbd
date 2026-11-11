# TDV 2200 adapter - loopback test for the MAX3490 wiring (CircuitPython, RP2040)
#
# Checks the whole path  GP4 -> DI -> driver Y/Z -> DE-9 -> receiver A/B -> RO -> GP1
# without the keyboard.
#
# 1. Do NOT connect the keyboard.
# 2. On the adapter's DE-9, jumper pin 7 to pin 9 (Y -> A) and pin 2 to pin 4 (Z -> B).
# 3. Save this file as code.py on the CIRCUITPY drive (keep the sniffer's code.py
#    under another name meanwhile) and open the serial console.

import time

import board
import busio


def run(baud):
    rx = busio.UART(tx=None, rx=board.GP1, baudrate=baud, timeout=0.5,
                    receiver_buffer_size=512)
    tx = busio.UART(tx=board.GP4, rx=None, baudrate=baud)
    time.sleep(0.05)
    rx.reset_input_buffer()

    pattern = bytes(range(256))
    got = bytearray()
    for i in range(0, 256, 16):
        chunk = pattern[i:i + 16]
        tx.write(chunk)
        got += rx.read(len(chunk)) or b""

    rx.deinit()
    tx.deinit()

    errors = sum(1 for a, b in zip(pattern, got) if a != b) + abs(len(pattern) - len(got))
    print("{:5d} baud: sent 256, received {:3d}, errors {:3d}".format(baud, len(got), errors))
    if got and errors:
        print("        first bytes back:", " ".join("{:02x}".format(b) for b in got[:12]))
    return len(got), errors


print("\nTDV 2200 adapter loopback test")
results = [run(600), run(2400)]
received = sum(r[0] for r in results)
errors = sum(r[1] for r in results)

if errors == 0:
    print("PASS: Pico <-> MAX3490 <-> DE-9 wiring works in both directions.")
elif received == 0:
    print("FAIL: nothing came back. Check 3.3 V and GND on MAX3490 pins 1 and 4,")
    print("      GP4 -> DI (pin 3), RO (pin 2) -> GP1, and the two DE-9 jumpers.")
else:
    print("FAIL: data comes back but wrong. Most likely Y/Z (pins 5/6) or A/B (pins 8/7)")
    print("      are swapped somewhere between the MAX3490 and the DE-9.")
