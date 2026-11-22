# Adapter PCB (KiCad)

KiCad project for the adapter board: Raspberry Pi Pico, MAX3490, decoupling
capacitor, a wire link where a fuse could go (F1), and the DE-9 for the keyboard.

Open `tdv2200-adapter.kicad_pro` in KiCad 7 or newer. KiCad 8/9 will offer to
upgrade the files; that's fine.

| File | What it is |
|---|---|
| `tdv2200-adapter.kicad_sch` | Schematic, same circuit as `../adapter/build-sheet.html` |
| `tdv2200-adapter.kicad_pcb` | Starting board: parts placed, nets assigned, **not routed** |
| `tdv2200.kicad_sym`, `tdv2200.pretty/` | Project symbols and footprints (Pico, MAX3490, 60R polyfuse) |
| `sym-lib-table`, `fp-lib-table` | Point KiCad at the project libraries |
| `tools/` | Scripts that generated all of the above |

## Parts and footprints

| Ref | Part | Footprint |
|---|---|---|
| U1 | Raspberry Pi Pico | `tdv2200:RaspberryPi_Pico_TH` (2 × 20 holes, 17.78 mm apart: solder the Pico on, or use 1×20 header sockets) |
| U2 | MAX3490 (DIP-8) | `Package_DIP:DIP-8_W7.62mm` |
| C1 | 100 nF ceramic, 5 mm pitch (Vishay K104K15X7RF5TL2) | `Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm` |
| F1 | **Wire link** (see below) | `tdv2200:Fuse_Littelfuse_60R_P5.10mm` (5.1 mm pitch; a wire link fits) |
| J1 | DE-9 female, right-angle | `Connector_Dsub:DSUB-9_Female_Horizontal_P2.77x2.84mm_EdgePinOffset9.90mm_Housed_MountingHolesOffset11.32mm` |
| H1-H4 | M3 mounting holes | `MountingHole:MountingHole_3.2mm_M3` |

Before ordering, check:

* **J1 gender and footprint.** The board needs the opposite gender to the
  keyboard's plug (female if the plug has pins). Right-angle DE-9s differ in
  how far the pins sit from the board edge, so pick the footprint that
  matches the connector you buy. With the one chosen here, the connector's
  flange lines up with the board's right edge.
* **F1 is a wire link.** On the real keyboard a 500 mA polyfuse (60R050XPR)
  dropped the keyboard's supply to 4.25 V, below the 4.65 V at which its
  reset chip holds the CPU, so it only beeped. With a wire link it gets
  4.93 V. If you want a fuse anyway, use one with a hold current of 1.1 A or
  more (lower resistance), and check that the keyboard still gets at least
  4.75 V. Check its lead spacing against the footprint (5.1 mm).

## Nets

| Net | Connects |
|---|---|
| KBD_RX | Pico GP1 (UART0 RX) — U2 RO |
| KBD_TX | Pico GP4 (UART1 TX) — U2 DI |
| +3V3 | Pico 3V3_OUT — U2 VCC — C1 |
| VBUS | Pico VBUS — F1 |
| KBD_5V | F1 — J1 pin 3 |
| TRANS+ / TRANS− | U2 A / B — J1 pins 9 / 4 (keyboard → host) |
| REC+ / REC− | U2 Y / Z — J1 pins 7 / 2 (host → keyboard) |
| GND | Pico GND pins — U2 GND — C1 — J1 pin 6 and shell |

## Routing tips

* Put a ground pour on the bottom layer (and optionally the top) connected to GND.
* Keep C1's tracks to U2 pins 1 and 4 as short as possible.
* 0.3–0.5 mm is plenty for the signal tracks. Use about 0.8 mm for VBUS and KBD_5V.
* Route TRANS+/TRANS− side by side, and REC+/REC− side by side.
* Run the DRC before ordering. On the unrouted board the only warnings are the
  22 unconnected pads, and silkscreen over the board edge from the DE-9 and
  the Pico's USB end (both meant to overhang).

## Regenerating

`tools/make_kicad.py` writes the schematic, libraries and project files.
`tools/make_board.py` builds the starting board from the schematic's netlist.
They need KiCad's standard libraries in `/usr/share/kicad` and, for the board,
KiCad's Python module (`pcbnew`):

```
python3 tools/make_kicad.py
kicad-cli sch export netlist -o /tmp/adapter.net tdv2200-adapter.kicad_sch
python3 tools/make_board.py /tmp/adapter.net
```

Once you start editing in KiCad, edit there and don't regenerate: the scripts
overwrite the files.
