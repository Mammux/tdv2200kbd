# tdv2200kbd

Using the keyboard from a Tandberg **TDV 2200 S** terminal (sold by Norsk Data
as the **ND 320**, item no. 4580) as a USB keyboard on a modern computer.

<p align="center">
  <a href="https://deskthority.net/wiki/File:ND246-Notis-TDV2200-9S-1984.jpg">
    <img src="https://deskthority.net/wiki/images/f/f6/ND246-Notis-TDV2200-9S-1984.jpg"
         alt="Tandberg TDV 2200/9S terminal branded ND 246, with its NOTIS keyboard (1984)" width="640">
  </a>
  <br>
  <sub>A TDV 2200/9S terminal sold as the ND 246 (1984), with the same family of
  NOTIS keyboard. Photo: Torfinn Ingolfsen,
  <a href="https://creativecommons.org/licenses/by-sa/3.0/">CC BY-SA 3.0</a>,
  via <a href="https://deskthority.net/wiki/File:ND246-Notis-TDV2200-9S-1984.jpg">Deskthority</a>.</sub>
</p>

The keyboard has its own 8035 microcontroller and talks to the terminal over
an RS-422 serial link. This project has two parts:

1. **An adapter**: a Raspberry Pi Pico (RP2040) and a MAX3490 RS-422
   transceiver between the keyboard's DE-9 plug and USB.
2. **New keyboard firmware**: the original firmware only sends a character
   when a key is pressed, with Shift and Ctrl applied inside the keyboard.
   A USB keyboard needs separate press and release events for every key,
   including the modifiers, so the 2716 EPROM is replaced with firmware
   that sends raw scan codes.

## Status

| Part | State |
|---|---|
| Keyboard pinout | Traced on the real keyboard, matches a 2013 cable table |
| Adapter schematic | Designed, not built yet |
| Adapter PCB (KiCad) | Schematic done, parts placed, not routed |
| Sniffer firmware (CircuitPython) | Written, not run on hardware yet |
| Patched original ROM (raw mode on command) | Passes all emulator tests, not tried on hardware |
| Raw-only ROM | Passes all emulator tests, not tried on hardware |
| USB HID firmware for the adapter | Not started |

## Layout

| Path | Contents |
|---|---|
| [`docs/hardware.md`](docs/hardware.md) | Keyboard connector pinout, chips, memory and EEPROM replacements |
| [`docs/protocol.md`](docs/protocol.md) | Serial protocol: original and raw mode |
| [`docs/schematic-391170.pdf`](docs/schematic-391170.pdf) | Tandberg keyboard schematic, part no. 391170 (scan by Torfinn Ingolfsen) |
| [`adapter/build-sheet.html`](adapter/build-sheet.html) | Adapter schematic, wiring, parts list and bring-up steps (open in a browser) |
| [`adapter/code.py`](adapter/code.py) | CircuitPython sniffer: prints what the keyboard sends, sends hex bytes to it |
| [`adapter/loopback_test.py`](adapter/loopback_test.py) | Tests the Pico–MAX3490–DE-9 wiring without the keyboard |
| [`pcb/`](pcb/) | KiCad project for the adapter board ([README](pcb/README.md)) |
| [`firmware/`](firmware/) | Keyboard ROM images, sources, 8035 emulator and tests ([README](firmware/README.md)) |

## Quick start

1. Build the adapter from `adapter/build-sheet.html`.
2. Program `firmware/965313-0-rawmode.bin` into an AT28C16 (or see
   `docs/hardware.md` for AT28C64/AT28C256), put it in socket U8 in place of the
   original 2716, and keep the original.
3. Install CircuitPython on the Pico, copy `adapter/code.py` to it and open
   the serial console. Type `31` and Enter to turn on raw mode, then press keys:
   each press shows `k`, each release `k + 80`. `firmware/keymap.csv` lists `k`
   for every key.

## Rebuilding the firmware

```
cd firmware
./build_all.sh
```

This needs only Python 3. It rebuilds both ROM images from source, regenerates
the patched disassembly, and runs the emulator tests.

## Credits

* `firmware/965313-0.asm` (the disassembly of the original ROM) and the ROM dump
  are by Frode; the dump is also in the Supermagnum/Tandberg repository on GitHub.
* `docs/schematic-391170.pdf` was scanned by Torfinn Ingolfsen (2013).
* The photo at the top is by Torfinn Ingolfsen, licensed
  [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/), and is shown
  from [Deskthority](https://deskthority.net/wiki/File:ND246-Notis-TDV2200-9S-1984.jpg)
  (it isn't stored in this repository).
* Protocol details from the Deskthority TDV 2200 S thread and NDWiki.
