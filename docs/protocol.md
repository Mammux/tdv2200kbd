# Serial protocol

8N1. Keyboard → host at **2400 baud**, host → keyboard at **600 baud**.

## Original firmware (965313-0)

The keyboard sends a character code when a key is pressed, with Shift, Ctrl,
Caps and Lock applied inside the keyboard. Releases send nothing. Holding a
key repeats it after about 0.8 s, every 50 ms. Some Ctrl combinations are sent
as `FF` followed by a code. The full table is in
[`../firmware/965313-0-layout.txt`](../firmware/965313-0-layout.txt).

Other keyboard → host codes:

| Code | Meaning |
|---|---|
| `FF C1` / `FF C0` | Caps Lock turned on / off |
| `F9` / `FE` | Keyboard locked (Shift+SLUTT) / unlocked |
| `DC`-`DF` | AL1/AL2 state |
| `EF`, `F3`, `F5`, `F6` … `F7` | Card reader / expansion port |

Host → keyboard commands:

| Code | Action |
|---|---|
| `01`-`08` | LED 1-8 on |
| `09`-`10` | LED 1-8 off |
| `11`-`18` | LED 1-8 blink |
| `20` | Reset |
| `21` / `22` | Key click on / off |
| `23` | Caps Lock on |
| `24` | Beep |
| `25` / `26` | All LEDs off / LEDs 5-8 off |
| `27` | Check expansion data line |
| `28` / `29` | Auto-repeat on / off |
| `2A` | Report AL1/AL2 |
| `2B` / `2C` | Expansion ready off / on |
| `2D` | ROM checksum (answers `AA`) |
| `2E` | RAM test (answers `AA` if OK, `EE` if not) |
| `2F` | Dump the character tables |
| `30` | Expansion mode flag |

## Raw mode

Available in both new images:

* `965313-0-rawmode.bin`: the original firmware plus raw mode, which the host
  turns on with `31`. Without that command it behaves exactly like the original.
* `tdv2200-raw.bin`: raw mode only, always on.

Keyboard → host:

| Bytes | Meaning |
|---|---|
| `00`-`7F` | Key `k` pressed |
| `80`-`FF` | Key `k` released (`k + 80`) |
| `00 xx` | Special column changed; `xx` = bit0 ST1, bit1 CAPS, bit2 CTRL, bit3 LOCK, bit4 SHIFT, bit5 AL1, bit6 AL2, bit7 SLUTT |

Position 0 has no key, so `00` always starts a special-column report.
AL1 and AL2 (bits 5 and 6) are configuration lines, not keys: on the
prototype's keyboard both are always set, so it reports `00 60` at rest.
A host should take modifiers from bits 1–4 and 7 only.
After power-up, or after plugging the cable in, treat incoming bytes as noise
until the first `00 xx` report, and ignore releases of keys that aren't down.
Keys are debounced (two equal reads about 7 ms apart; per key in the
raw-only ROM). There is no auto-repeat in raw mode; the host does that.

Host → keyboard:

| Code | Patched ROM | Raw-only ROM |
|---|---|---|
| `01`-`10` | LEDs 1-8 on/off | LEDs 1-8 on/off |
| `20` | Reset (leaves raw mode) | Reset |
| `21` / `22`, `24`, `25` | As original | Click on/off, beep, LEDs off |
| `31` | Raw mode on, then reports the special column | Reports the special column again |
| `32` / `33` | Caps LED on / off | Caps LED on / off |
| `34` / `35` | Lock LED on / off | Lock LED on / off |
| `36` | Raw mode off | Ignored |
| `38` / `39` | Ignored | Eager key presses on / off |
| `3A` / `3B` | Ignored | Send at 4800 / 2400 baud, then report the special column |
| other | As original | Ignored |

The raw-only ROM also sends the special-column report by itself at power-up
and after reset. An adapter that sends `31` at start-up works with both images.

### Speed and debounce options (raw-only ROM, November 2026 and later)

Both are off after power-up and after `20`, so an adapter that doesn't know
about them works as before.

* **`3A` / `3B`: 4800 / 2400 baud** from keyboard to host. The keyboard
  finishes the byte it is sending, switches, and reports the special column
  (`00 xx`) at the new speed. Bytes still queued go out at the new speed too,
  so the host should switch its receiver and ignore what it gets until that
  `00 xx`. Host → keyboard stays at 600 baud.
  The timer still runs at 2400 Hz; at 4800 baud the interrupt sends a second
  bit exactly 80 cycles after the first. Bit edges are within one CPU cycle
  (0.3 µs) of the ideal at both speeds.
* **`38` / `39`: eager key presses on / off.** On: a press is reported on the
  first scan that sees it instead of the second. Releases still need two
  equal scans, which also hides contact bounce after a press (bounce shorter
  than one scan, 7.1 ms). The cost: a noise spike on a row line becomes a
  short key press. The modifier column is always debounced.
* **Detecting the options:** only ROMs that have them answer `3B` (at
  2400 baud) with `00 xx`; older ROMs send nothing. The CircuitPython
  adapter firmware uses this to decide.

Measured in the emulator, from key down to the end of the byte at the host
(300 presses at random times; key travel not included):

| Mode | Mean | Range |
|---|---|---|
| 2400 baud, defer (default) | 15.2 ms | 11.5–18.6 ms |
| 4800 baud, defer | 12.9 ms | 9.5–16.6 ms |
| 2400 baud, eager | 8.1 ms | 4.4–11.5 ms |
| 4800 baud, eager | 5.8 ms | 2.5–9.5 ms |

The key click (P1.6 high while a byte is sent) is half as long at 4800 baud.
