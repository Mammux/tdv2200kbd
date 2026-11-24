# Plan: Rust firmware for the adapter

Replaces the CircuitPython firmware in `adapter/usb/` with Rust, and adds a
way to change the configuration from the computer while it runs.

## Decisions

| Question | Decision |
|---|---|
| Board | Raspberry Pi Pico (RP2040), as now. Everything here also works on the RP2350 (Pico 2) |
| Framework | [Embassy](https://embassy.dev) (`embassy-rp`, `embassy-usb`): async tasks, composite USB |
| Configuration channel | Typed RPC over a USB vendor interface (`postcard-rpc`), with a Rust command-line tool on the computer |
| Debugging | No second Pico available: see [Debugging](#debugging) |

## Hardware use (unchanged)

| Pin | Use |
|---|---|
| GP1 (UART0 RX) | Keyboard → adapter, 2400 baud 8N1, from MAX3490 RO |
| GP4 (UART1 TX) | Adapter → keyboard, 600 baud 8N1, to MAX3490 DI |
| VBUS | +5 V to the keyboard (DE-9 pin 3), no fuse |

## USB device

| Interface | Purpose |
|---|---|
| HID keyboard, boot protocol | Normal typing; boot protocol also works in BIOS/UEFI setup and early boot |
| HID consumer control | Media keys (volume, play/pause) that terminal keys can be assigned to |
| Vendor interface (bulk) | Configuration and monitoring, `postcard-rpc`. Microsoft OS 2.0 descriptors make Windows load WinUSB by itself; macOS and Linux need nothing |

USB polling interval 1 ms. Each byte from the keyboard is translated and sent
as soon as it arrives.

## What can be configured

* **Key map:** what each TDV key sends (keyboard usage, modifier or media key), on several layers. A key can switch layer while held or toggle it.
* **Modifier column:** what CAPS, CTRL, LOCK and SHIFT send.
* **Macros:** a key that sends a sequence of keys or types a string.
* **LEDs:** which computer lock state (Caps, Num, Scroll) or layer lights which of the keyboard's LEDs (1-8, Caps, Lock).
* **Keyboard behaviour:** key click on or off, beep on events.
* **Diagnostics:** live monitor of raw bytes from the keyboard; send raw command bytes to the keyboard.
* **Maintenance:** save to flash, reset to defaults, export/import, reboot into the UF2 bootloader.

## Storage

* Defaults are compiled in. A build script generates the default key map from `firmware/keymap.csv`, the same source as `adapter/usb/keymap.py`.
* Saved settings live in the last flash sectors, managed by `sequential-storage` (wear levelling, safe against power loss). Each record carries a format version: newer firmware upgrades old records or falls back to defaults.
* **Factory reset:** hold ESC while plugging in. A bad configuration can never lock you out.

## Repository layout

A Cargo workspace in `adapter/rust/`:

| Crate | Contents | Target |
|---|---|---|
| `tdv-core` | Byte-stream translator (port of `tdv_translate.py`), key map, layers, macros, configuration types, RPC endpoint definitions | `no_std`; Pico and computer |
| `tdv-fw` | Embassy tasks: keyboard UARTs, USB HID, LEDs, storage, configuration server | `thumbv6m-none-eabi` (RP2040) |
| `tdv-cli` | Command-line tool | macOS, Windows, Linux |

Example commands for `tdv-cli`:

```
tdv info                      # firmware version, saved/unsaved changes
tdv monitor                   # live key events: position, legend, raw code, USB key
tdv get G51                   # what FUNK sends
tdv set G51 F13               # keys by layout position or by legend
tdv set --layer 1 C8 Up
tdv led caps -> 1             # computer's Caps Lock state lights LED 1
tdv save | tdv reset | tdv bootloader
tdv export > tdv.toml         # whole configuration as TOML
tdv import tdv.toml
```

Configuration files use the position names from the layout document
(`G51 = "F13"`), not raw numbers.

## Testing

* `tdv-core` runs on the computer, so the translator, layers and macros get ordinary `cargo test` unit tests.
* The Python emulator records byte streams from the real keyboard ROMs (`firmware/harness.py`), with the USB events expected for each, as test fixture files. The Rust tests replay them, so the Rust and CircuitPython versions are checked against the same reference.
* Configuration protocol: round-trip tests between `tdv-cli` and `tdv-core` on the computer, no hardware needed.
* On the Pico: a short manual checklist per milestone.

## Debugging

There's no second Pico to use as a debug probe. Options, cheapest first:

1. **No probe.** Flash UF2 files (BOOTSEL, later `tdv bootloader`). Log messages go over the vendor interface to `tdv monitor --log`. Enough for most of the work.
2. **A Raspberry Pi as the probe.** OpenOCD can drive the Pico's SWD debug pins from a Raspberry Pi's GPIO header (three wires: SWCLK, SWDIO, GND). That gives flashing, breakpoints with `gdb`, and RTT logging. Works with a Pi that has the 40-pin header; check OpenOCD's GPIO driver for the Pi model used.
3. **A Raspberry Pi Debug Probe, or any second Pico** with the `debugprobe` firmware. Works directly with `probe-rs` and `defmt`, the smoothest setup.

## Milestones

1. **Skeleton:** Embassy project that receives from the keyboard and logs the bytes. Proves the UART setup. *Written and builds (`adapter/rust/tdv-fw`, USB serial sniffer); not yet tried on the adapter.*
2. **Same as the CircuitPython version:** translator, HID keyboard with the compiled-in map, Caps LED, resync after plug-in. Then the CircuitPython version can be retired.
3. **USB polish:** boot protocol, 1 ms polling, media keys.
4. **Configuration in RAM:** `postcard-rpc` endpoints and `tdv-cli` with `info`, `monitor`, `get`/`set` and LED mapping.
5. **Saving:** flash storage, factory reset, reboot into the bootloader.
6. **Extras:** layers, macros, TOML import/export.
7. **Optional:** GUI or web configurator (WebUSB over the same vendor interface).
