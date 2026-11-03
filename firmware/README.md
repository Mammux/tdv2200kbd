# Firmware

Two images for ROM socket U8 (2716). Use either one with the USB adapter:

| Image | What it is |
|---|---|
| `965313-0-rawmode.bin` | Original firmware plus a raw mode the adapter turns on with `31`. Still works in a terminal. |
| `tdv2200-raw.bin` | New raw-only firmware (about 390 bytes). Raw mode is always on; everything else is removed. |

Both send the same codes and accept the same LED commands, so the same adapter firmware works with either.

## Patched original ROM

Patch for keyboard firmware **965313-0** (2716 EPROM, U8) that adds a
press/release mode for use with a USB adapter. Without the enable command
the keyboard behaves exactly like the original, so the patched chip still
works in a real terminal.

## Files

| File | What it is |
|---|---|
| `965313-0-rawmode.bin` | Patched 2 KB ROM image, ready to program |
| `965313-0.bin` | Original dump (unchanged) |
| `965313-0.asm` | Disassembly of the original by Frode (DASMx), reassembles to the dump exactly |
| `965313-0-layout.txt` | Key layout and flag documentation for 965313-0 |
| `rawmode_patch.asm` | Patch source (MCS-48) |
| `build_patch.py` | Assembles the patch into the original and fixes the checksum |
| `test_patch.py` | Emulator test suite (normal-mode regression + raw mode) |
| `mcs48.py`, `asm48.py`, `harness.py` | 8035 emulator/disassembler, mini assembler, keyboard model |
| `keymap.csv` | Raw code for every key, with position and legend |
| `965313-0-rawmode.asm` | Disassembly of the patched image, reassembles to the .bin exactly |
| `tdv2200-raw.asm`, `tdv2200-raw.bin` | Raw-only firmware source and image |
| `build_raw.py`, `test_raw.py` | Build and emulator tests for the raw-only firmware |
| `*_x4_AT28C64.bin`, `*_x16_AT28C256.bin` | Images repeated to fill an 8 KB / 32 KB EEPROM (`make_large_images.py`) |
| `build_all.sh` | Rebuilds everything and runs all tests |

Rebuild everything and run all tests: `./build_all.sh` (Python 3, no extra packages).

## Protocol additions

Host to keyboard (600 baud 8N1). These commands are ignored by the original ROM:

| Byte | Action |
|---|---|
| `31` | Enable raw mode |
| `32` / `33` | Caps LED on / off |
| `34` / `35` | Lock LED on / off |
| `36` | Disable raw mode (`20`, the existing reset command, also does this) |

Keyboard to host in raw mode (2400 baud 8N1):

| Bytes | Meaning |
|---|---|
| `00`-`7F` | Key *k* pressed. *k* = row × 16 + column |
| `80`-`FF` | Key *k* released (*k* + 80h) |
| `00 xx` | Modifier column changed. `xx` is the new state: bit0 ST1, bit1 CAPS, bit2 CTRL, bit3 LOCK, bit4 SHIFT, bit5 AL1, bit6 AL2, bit7 SLUTT/BREAK |

Matrix position 0 has no key, so `00` is always the start of a modifier report.
A modifier report is sent right after `31`, so the host starts in sync.

In raw mode the keyboard's own auto-repeat, Shift/Ctrl/Caps translation and
Caps/Lock LED handling are off; the host does those. The 8 LED commands
`01`-`18` work as before.

## How it works

* Hook at `05C` (per-column scan): in raw mode, a column's rows must read the
  same on two scans in a row (about 7 ms apart) before a change is reported.
  One changed key per column is sent per scan; the rest follow on later scans.
* Hook at `0F4` (modifier column): reports the whole bitmap when it changes.
  RAM `0Ch` (the repeat buffer in normal mode) holds the last value sent.
* Hook at `3A1` (commands `30`-`3F`): adds `31`-`36` through a jump table.
* The raw-mode flag is the P2.1 port latch. The original ROM keeps a flag in
  P2.2 in the same way.
* New code: `56A`-`5F3` (previously zero-filled). Byte `5FF` is set so the
  ROM checksum (command `2D`) still returns `AA`.

## Emulator results

All tests in `test_patch.py` pass:

* Six random sessions of key presses, modifiers and commands produce output
  byte-for-byte identical to the original ROM when raw mode is off.
* Raw mode: all 123 keys report press and release; several keys in one column;
  40 keys at once (TX buffer full) with nothing lost or repeated; modifiers;
  LED commands; leaving raw mode with `36` and with reset `20`; a 400-event
  random session decodes to exactly the real key state; the stack never goes
  deeper than 2 levels (the RAM above that holds data).

The emulator was checked against the original ROM first. `a` gives `61`,
Shift+`a` gives `41`, Ctrl+`1` gives `FF 86` (matching the layout document),
auto-repeat starts after about 0.8 s, and the ROM checksum is `AA`.

## Programming

The 2716 needs 25 V to program, which most cheap programmers can't supply.
An **AT28C16** EEPROM is a pin-compatible replacement. On this board, pin 21
(VPP on the 2716, /WE on the 28C16) goes to +5 V, so the EEPROM can't be
written while it's in the keyboard. Check that before fitting it, and keep
the original EPROM.

## Raw-only firmware (`tdv2200-raw.bin`)

Written from scratch except the timer interrupt (serial TX/RX), which is
copied from the original ROM. Removed: character tables, Shift/Ctrl/Caps
translation, auto-repeat, LED blinking, keyboard lock, ROM/RAM tests, table
dump and the card reader (expansion) port.

Differences from the patched ROM in raw mode:

* Raw mode is on from power-up. At power-up and after reset (`20`) the
  keyboard sends the modifier report `00 xx`, so the host can tell it's ready.
* The modifier column is debounced like the keys (two equal reads ~7 ms apart).
* `31` re-sends the modifier report. `36` and other old commands are ignored.

Commands: `01`-`08` LED on, `09`-`10` LED off, `20` reset, `21`/`22` click
on/off, `24` beep, `25` LEDs 1-8 off, `31` re-send modifiers, `32`/`33` Caps
LED on/off, `34`/`35` Lock LED on/off.

Emulator tests (`test_raw.py`), all passing: start-up report; press and
release for all 123 keys; no auto-repeat; modifiers; 3 ms glitches filtered;
8 keys in one column; 40 keys at once; every command; old commands silent;
reset; stack within 2 levels; a 500-event random session decodes to the real
key state and matches the patched ROM's raw mode.
