# Raw-only firmware in C

`tdv2200-raw.c` is a C version of [`../tdv2200-raw.asm`](../tdv2200-raw.asm)
for the experimental MCS-48 port of SDCC. It sends the same codes and
accepts the same commands, and passes the same emulator tests:

```sh
cd ..
python3 test_raw.py c/tdv2200-raw-c.bin
```

`tdv2200-raw-c.bin` is the prebuilt 2 KB image, so the tests run without
SDCC. Use the assembler image for the real keyboard: the C one is untested
on hardware.

## Building

You need SDCC from the `mcs48-port` branch of
<https://github.com/Mammux/sdcc>, configured with `--enable-mcs48-port`.
Then:

```sh
SDCC=/path/to/sdcc/bin SDCC_INC=/path/to/sdcc/device/include/mcs48 ./build.sh
```

This runs `sdcc -mmcs48 --data-loc 0x0a tdv2200-raw.c` and converts the
Intel hex output to a 2 KB image padded with `FF` (`ihx2bin.py`).

## Compared with the assembler version

The structure is the same: one column per 2400 Hz timer tick, serial I/O
in the timer interrupt, and the same RAM layout. The interrupt's state is
in register bank 1 R2-R6, the current column is in bank 0 R7, and the TX
buffer and variables are in `0Ah`-`17h`. `main()` makes no calls, so the
stack only ever holds the interrupt's return address.

| | Assembler | C |
|---|---|---|
| Code size | 390 bytes | about 650 bytes |
| Timer interrupt | 39 cycles | 57 cycles |
| Slowest main loop pass (tick = 160 cycles) | 173 cycles | 269 cycles |

The main loop sometimes needs two ticks for one column. The tests still
pass, but the main loop's read-modify-write of P1 (column select) can more
often coincide with the interrupt changing the TX bit, which would garble
a transmitted bit. The assembler version has the same window, only
smaller.
