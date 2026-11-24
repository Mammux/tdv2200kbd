#!/bin/sh
# Flash the Pico through a Raspberry Pi wired as an SWD probe (see pi-swd.cfg).
#
#   tools/flash-via-pi.sh tdv-fw/target/thumbv6m-none-eabi/release/tdv-fw [user@host]
#
# The Pi defaults to $TDV_PI, else pi@raspberrypi.local. Needs ssh access to
# the Pi and `sudo apt install openocd` there.
set -e
ELF=${1:?usage: flash-via-pi.sh firmware.elf [user@host]}
PI=${2:-${TDV_PI:-pi@raspberrypi.local}}
HERE=$(dirname "$0")

scp -q "$ELF" "$PI:/tmp/tdv-fw.elf"
scp -q "$HERE/pi-swd.cfg" "$PI:/tmp/pi-swd.cfg"
ssh "$PI" "openocd -f /tmp/pi-swd.cfg -f target/rp2040.cfg -c 'program /tmp/tdv-fw.elf verify reset exit'"
