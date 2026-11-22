# TDV 2200 (ND 320) keyboard -> USB keyboard. CircuitPython, RP2040.
#
# Needs a keyboard ROM with raw mode: tdv2200-raw.bin (always raw) or
# 965313-0-rawmode.bin (raw mode switched on by command 31h, sent below).
#
# Files on the CIRCUITPY drive:
#   code.py           this file
#   tdv_translate.py  byte stream -> key presses
#   keymap.py         which USB key each TDV key sends (edit to taste)
#   lib/adafruit_hid/ from the Adafruit CircuitPython library bundle
#
# Wiring as in adapter/build-sheet.html:
#   GP1 (UART0 RX) <- MAX3490 RO   keyboard -> host, 2400 baud
#   GP4 (UART1 TX) -> MAX3490 DI   host -> keyboard, 600 baud
#
# The serial console shows what happens when DEBUG is True. Typing hex bytes
# and Enter there sends them to the keyboard, as in the sniffer (e.g. 24 = beep).

import sys
import time

import board
import busio
import supervisor
import usb_hid
from adafruit_hid.keyboard import Keyboard

import keymap
from tdv_translate import Translator

DEBUG = True             # print events on the serial console
CMD_RAW_MODE = 0x31      # raw mode on (patched ROM) / re-report modifiers (raw-only ROM)
CMD_CAPS_LED_ON = 0x32
CMD_CAPS_LED_OFF = 0x33
RESYNC_EVERY = 0.5       # seconds between 31h requests while out of sync

kbd_in = busio.UART(tx=None, rx=board.GP1, baudrate=2400, timeout=0,
                    receiver_buffer_size=256)
kbd_out = busio.UART(tx=board.GP4, rx=None, baudrate=600)

time.sleep(1)            # let the computer finish setting up USB
usb = Keyboard(usb_hid.devices)
tr = Translator(keymap.KEYS, keymap.MODIFIERS)


def say(*args):
    if DEBUG:
        print(*args)


def send_to_keyboard(*data):
    kbd_out.write(bytes(data))


def apply(events):
    for kind, usage in events:
        try:
            if kind == "press":
                usb.press(usage)
            else:
                usb.release(usage)
        except ValueError:
            say("more than 6 keys held: %02x not sent" % usage)
        say(kind, "%02x" % usage)


def console_command(line):
    try:
        data = bytes(int(t, 16) for t in line.replace(",", " ").split())
    except ValueError:
        print("use hex bytes, e.g.: 24")
        return
    if data:
        kbd_out.write(data)
        print(">> sent", " ".join("%02x" % b for b in data))


print("TDV 2200 USB keyboard. Type hex + Enter to send bytes to the keyboard.")
time.sleep(0.2)          # keyboard start-up
send_to_keyboard(CMD_RAW_MODE)
last_resync = time.monotonic()
caps_led = None
cmd = ""

while True:
    # keyboard -> USB
    n = kbd_in.in_waiting
    if n:
        was_synced = tr.synced
        data = kbd_in.read(n) or b""
        for b in data:
            tr.feed(b)
        apply(tr.take_events())
        for line in tr.take_log():
            say(line)
        if tr.synced and not was_synced:
            # The report we synced on may have been noise: ask for a fresh
            # one, which puts the modifiers right if it was.
            send_to_keyboard(CMD_RAW_MODE)

    # still waiting for a "00 xx" report: ask for one now and then
    if not tr.synced and time.monotonic() - last_resync > RESYNC_EVERY:
        send_to_keyboard(CMD_RAW_MODE)
        last_resync = time.monotonic()

    # computer's Caps Lock state -> the keyboard's Caps LED
    on = usb.led_on(Keyboard.LED_CAPS_LOCK)
    if on != caps_led:
        caps_led = on
        send_to_keyboard(CMD_CAPS_LED_ON if on else CMD_CAPS_LED_OFF)

    # serial console -> keyboard
    while supervisor.runtime.serial_bytes_available:
        ch = sys.stdin.read(1)
        if ch in "\r\n":
            if cmd.strip():
                console_command(cmd)
            cmd = ""
        else:
            cmd += ch
