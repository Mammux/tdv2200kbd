/* Raspberry Pi Pico (RP2040, 2 MB flash).
 *
 * The last 64 KB of flash are kept out of the program area: milestone 5
 * stores the configuration there (see docs/rust-plan.md).
 */
MEMORY {
    BOOT2 : ORIGIN = 0x10000000, LENGTH = 0x100
    FLASH : ORIGIN = 0x10000100, LENGTH = 2048K - 0x100 - 64K
    RAM   : ORIGIN = 0x20000000, LENGTH = 264K
}

__config_start = ORIGIN(FLASH) - 0x100 + 2048K - 64K;
__config_end   = ORIGIN(FLASH) - 0x100 + 2048K;
