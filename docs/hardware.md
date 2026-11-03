# Keyboard hardware

Tandberg TDV 2200 S keyboard as used on the Norsk Data ND 320 (item no. 4580).
Schematic: [`schematic-391170.pdf`](schematic-391170.pdf) (Tandberg part no.
391170, publication 5227, October 1980). The board described here is dated
1987 and differs in places (a 74HC240 replaces the two 14502 row buffers).

## Connector

The cable ends in a cast DE-9 with 6 of the 9 pins fitted. Directions are
as seen from the keyboard: TRANS goes to the terminal, REC comes from it.

| DE-9 | J2 (internal) | Signal | Wire | Chip pin |
|---|---|---|---|---|
| 3 | 1 | +5 V | red | AM26LS31 pin 16 |
| 6 | 6 | GND | black | AM26LS31 pin 8 |
| 9 | 4 | TRANS+ (keyboard → host) | brown | AM26LS31 pin 2 (Y, channel 1) |
| 4 | 5 | TRANS− | yellow | AM26LS31 pin 3 (Z, channel 1) |
| 7 | 2 | REC+ (host → keyboard) | blue | AM26LS32 pin 2 (A, channel 1) |
| 2 | 3 | REC− | white | AM26LS32 pin 1 (B, channel 1) |

The link is RS-422 at 5 V. **Do not connect it to an RS-232 port**: ±12 V can
damage the line chips.

Serial format: 8N1, **2400 baud** keyboard → host, **600 baud** host → keyboard.

## Main chips

| Ref | Part | Function |
|---|---|---|
| U1 | MAB 8035HL | MCS-48 CPU, no internal ROM, 64 bytes RAM, 5.76 MHz crystal |
| U8 | M2716 (socketed) | 2 KB EPROM with the firmware, label 965313 |
| U5, U7 | 74LS373 | U7: address latch for the EPROM. U5: LED latch (BUS output) |
| U4 | 74LS154 | 4-to-16 decoder, selects one of 16 matrix columns (P1.0-P1.3) |
| U2 | 74HC240 | Reads the 8 matrix rows onto the BUS |
| U10 | AM26LS31 | RS-422 driver (TX) |
| U9 | AM26LS32 | RS-422 receiver (RX) |
| U6 | MC3456 | Dual timer: key click and beep |

## CPU pins

| Pin | Use |
|---|---|
| P1.0-P1.3 | Matrix column select |
| P1.4 | Special column select (CAPS, CTRL, LOCK, SHIFT, AL1, AL2, SLUTT) |
| P1.5 | TX data |
| P1.6 | TX active ("trans flag"), also triggers the key click |
| P1.7 | Click enable |
| P2.0-P2.2 | EPROM A8-A10 during fetches |
| P2.3, P2.4, T1, INT | Card reader / expansion port (READY, CARD PRESENT, DATA, CLOCK) |
| P2.5 | Beep trigger |
| P2.6, P2.7 | Lock LED, Caps LED |
| T0 | RX data |
| BUS | Matrix rows in (INS), LED latch out (OUTL) |

The timer runs from 5.76 MHz / 15 / 32 = 12 kHz and is reloaded every 5
counts, giving a 2400 Hz interrupt: one TX bit per interrupt, RX sampled every
4 interrupts (600 baud). The main loop scans one column per interrupt, so a
full scan (16 columns + special) takes about 7.1 ms.

## Key matrix

16 columns × 8 rows = 128 positions; 123 are used. Key index
`k = row × 16 + column`, where row = 7 − (bit number on the BUS). Positions
0, 1, 2, 12 and 13 have no key. [`../firmware/keymap.csv`](../firmware/keymap.csv)
lists every key with its index, position name (as in the layout document) and
legend.

The special column has one row each for ST1 (bit 0), CAPS (1), CTRL (2),
LOCK (3), SHIFT (4), AL1 (5), AL2 (6) and SLUTT/BREAK (7).

## Replacing the EPROM

The 2716 needs 25 V to program, which most cheap programmers can't supply.
EEPROMs are easier, and can be reprogrammed electrically:

* **24-pin, plug-in:** AT28C16, X28C16, CAT28C16A. On this board socket pin 21
  (VPP on the 2716, /WE on these) is tied to +5 V, so the EEPROM can't be
  written in circuit. Measure it before fitting the chip.
* **28-pin AT28C64 / AT28C256** with an adapter. Mount the chip in a 28-pin
  socket on 24-pin header pins, overhanging at the notch end, so that chip
  pin 3 sits in socket pin 1 and chip pin 26 in socket pin 24. Then:

  | Chip pin | Function | Connect to |
  |---|---|---|
  | 28 | VCC | Socket pin 24 (+5 V) |
  | 27 | /WE | Chip pin 28 (never write) |
  | 26 | NC (28C64) / A13 (28C256) | Lands on socket pin 24 (+5 V) — fine |
  | 2 | A12 | GND or +5 V, not floating |
  | 1 | NC/RDY (28C64) / A14 (28C256) | Open (28C64) / GND or +5 V (28C256) |

  Chip A11 lands on socket pin 21 (+5 V). Program the `_x4_AT28C64.bin` or
  `_x16_AT28C256.bin` image, where the 2 KB firmware is repeated to fill the
  chip, so the keyboard runs the same code however the extra address lines
  end up.

Buy these chips from an authorised distributor: old Atmel EEPROMs are often
counterfeit on marketplaces. Keep the original EPROM.
