# Rust adapter firmware

Work in progress; see [the plan](../../docs/rust-plan.md). The CircuitPython
firmware in [`../usb`](../usb) is still the one to use as a keyboard.

## Milestone 1: sniffer (`tdv-fw`)

Same job as the CircuitPython sniffer (`../code.py`), written with
[Embassy](https://embassy.dev):

* receives from the keyboard on GP1 (UART0, 2400 baud) and prints each byte on
  a USB serial port, with the time since the previous byte and a decoding
  (press / release / special column);
* sends hex bytes typed on the serial port to the keyboard on GP4 (UART1,
  600 baud), e.g. `20` (reset), `24` (beep), `32` / `33` (Caps LED);
* `boot` restarts the Pico into the UF2 bootloader, so you don't need to
  unplug it and hold BOOTSEL for the next version;
* the Pico's LED toggles for each burst received.

It shows up as *TDV 2200 keyboard adapter (sniffer)*, USB ID 1209:0001
(the pid.codes test ID, until the plan's later milestones).

### Trying it without building

1. Hold BOOTSEL while plugging in the Pico; it appears as the `RPI-RP2` drive.
2. Copy [`dist/tdv-fw-sniffer.uf2`](dist/tdv-fw-sniffer.uf2) onto it.
3. Open the serial port, e.g. on a Mac `screen /dev/tty.usbmodem*` (quit with
   Ctrl-A K), and press keys. Type `20` + Enter: you should get `00 60` back.

To go back to CircuitPython, type `boot` and copy the CircuitPython UF2 onto
the drive; the files on the CIRCUITPY drive are kept.

### Building

On a Mac (or Linux, Windows), with [rustup](https://rustup.rs):

```sh
rustup target add thumbv6m-none-eabi
cargo install elf2uf2-rs        # or use tools/elf2uf2.py below
cd adapter/rust/tdv-fw
cargo build --release
```

Flashing: put the Pico in the bootloader (BOOTSEL, or `boot` on the serial
port), then `cargo run --release`, which builds and copies the UF2 via
`elf2uf2-rs -d`. Without `elf2uf2-rs`:

```sh
python3 ../tools/elf2uf2.py target/thumbv6m-none-eabi/release/tdv-fw tdv-fw.uf2
```

and copy `tdv-fw.uf2` to the `RPI-RP2` drive.

Notes:

* Flash layout in `memory.x`: the last 64 KB are kept free for the saved
  configuration (milestone 5).
* A panic restarts the Pico rather than hanging.
