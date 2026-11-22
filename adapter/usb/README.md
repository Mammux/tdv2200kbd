# USB keyboard firmware (CircuitPython)

Makes the adapter a normal USB keyboard. Works with either raw-mode keyboard
ROM: `tdv2200-raw.bin`, or `965313-0-rawmode.bin` (raw mode is switched on with
`31`, which this firmware sends at start-up).

## Install

1. Install CircuitPython on the Pico (UF2 from circuitpython.org).
2. Install the `adafruit_hid` library into `lib/` on the CIRCUITPY drive:
   either `pip install circup` and then `circup install adafruit_hid`, or copy
   the `adafruit_hid` folder from the Adafruit CircuitPython library bundle
   that matches your CircuitPython version.
3. Copy `code.py`, `tdv_translate.py` and `keymap.py` to the CIRCUITPY drive.
   Rename the sniffer's `code.py` first if you want to keep it.
4. Set the computer's keyboard layout to **Norwegian**.

The serial console (Thonny, `tio`, `screen`) shows each key event while
`DEBUG = True` in `code.py`, and you can still type hex bytes there to send
them to the keyboard (`24` beeps, `20` resets it).

## What each key sends

Keys are mapped by **position**: each key sends the USB key that sits in the
same place on a standard ISO keyboard. With a Norwegian layout selected, the
letters, digits and Æ Ø Å type what the keycaps show. The full list is in
`keymap.py`; to change it, edit `keymap.py` directly, or edit
`../tools/make_keymap.py` and run it again.

| TDV 2200 key | USB key |
|---|---|
| CAPS (top left) | Caps Lock; the keyboard's Caps LED follows the computer |
| CTRL | Left Control |
| LOCK | Right Alt (AltGr on Windows/Linux, Option on a Mac) |
| SHIFT (both) | Left Shift |
| EKSP INNS (far left) | Command / Windows key |
| Squiggle (far left) | Left Alt / Option |
| Del | Backspace |
| CartridgeReturn | Return |
| TAB+ TAB-, TABRight | Tab |
| Arrows, Home | Arrows, Home |
| FieldLeft / FieldRight | Home / End |
| RollUp / RollDown | Page Up / Page Down |
| STRYK | Delete (forward) |
| KOPI / FLYTT / ANGRE / HJELP | Copy / Cut / Undo / Help (used by Linux; most Mac apps ignore them) |
| SLUTT, SKRIV, FUNK | Pause, Print Screen, Menu |
| F1–F8 | F1–F8 |
| P1–P8 | F9–F16 |
| MERK, FELT, AVSN, SETN, ORD, LOKAL | F17–F22 |
| NewParagraph, LineFeed | F23, F24 |
| Numeric keypad | Numeric keypad (SP = Keypad +) |
| TABLeft, << >>, JUST, <> ><, (... ...), /aaa aaa, blank keys | Nothing yet: the console shows their codes |

A few keycaps don't match the Norwegian layout: the key labelled `@ \`` types
what the Norwegian layout puts there (`\ \``), and `@` is AltGr/Option+2 as
usual.

## Behaviour

* **Start-up and plugging in:** bytes are ignored until the keyboard sends a
  `00 xx` modifier report. The firmware asks for one with `31` at start-up, and
  every half second until it gets one, so the order in which the Pico and
  keyboard start doesn't matter.
* **Glitches:** a release of a key that isn't down, or a second press of one
  that is, is ignored, so noise can't leave a key stuck.
* **Key repeat** is done by the computer, as with any USB keyboard.
* **Rollover:** up to 6 keys plus the modifiers at once, the USB limit for a
  standard keyboard. A 7th key is ignored and noted on the console.

## Tests

`../tests/test_usb.py` runs the translation logic against the emulated
keyboard (both ROMs), and runs `code.py` itself on a PC with stand-ins for
the CircuitPython modules. It needs only Python 3:

```
python3 adapter/tests/test_usb.py
```

None of this has run on a real Pico yet.
