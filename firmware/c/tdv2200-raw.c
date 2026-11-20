/*
 * TDV 2200 / ND 320 keyboard - raw-only firmware, C version
 *
 * C rewrite of tdv2200-raw.asm (github.com/Mammux/tdv2200kbd) for the
 * SDCC mcs48 port:
 *
 *     sdcc -mmcs48 --data-loc 0x0a tdv2200-raw.c
 *     python3 ihx2bin.py tdv2200-raw.ihx tdv2200-raw.bin
 *
 * Same protocol, structure and RAM layout as the assembler version (one
 * column per 2400 Hz timer tick, serial I/O in the timer interrupt); see
 * tdv2200-raw.asm for the description of the hardware and the protocol.
 * The compiled code is larger and slower (about 650 instead of 390 bytes,
 * 57 instead of 39 cycles in the interrupt) but behaves the same in the
 * emulator test suite of that repository (test_raw.py).
 *
 * Keyboard -> host, 2400 baud 8N1:
 *   00h-7Fh  key k pressed, k = row*16 + column
 *   80h-FFh  key k released
 *   00h, xx  special column changed, xx = bitmap
 *
 * Host -> keyboard, 600 baud 8N1:
 *   01h-08h  LED 1-8 on          09h-10h  LED 1-8 off
 *   20h      reset               21h/22h  key click on/off
 *   24h      beep                25h      LEDs 1-8 off
 *   31h      report the special column again
 *   32h/33h  Caps LED on/off     34h/35h  Lock LED on/off
 *
 * Internal RAM (64 bytes):
 *   00h-07h  bank 0: code generator registers, R7 = current column
 *   08h-09h  stack: one level, for the timer interrupt (main() calls nothing)
 *   0Ah-17h  main loop variables and the TX ring buffer (--data-loc 0x0a)
 *   18h-1Fh  bank 1 (interrupt): R2-R6 hold the serial state
 *   20h-3Fh  2 bytes per column: last read, last reported
 */

#include <mcs48.h>

#define TXBUF_SIZE 8

/* 2 bytes per column: [2*c] last read, [2*c+1] last reported */
__data __at (0x20) unsigned char col_state[32];

/* Timer interrupt state in register bank 1, as in the original ROM */
__data __at (0x1a) unsigned char rx_count;      /* R2: RX bits still to come */
__data __at (0x1b) unsigned char rx_div;        /* R3: RX sample divider */
__data __at (0x1c) unsigned char rx_byte;       /* R4: received byte */
__data __at (0x1d) unsigned char tx_bits;       /* R5: TX bits still to send */
__data __at (0x1e) unsigned char tx_shift;      /* R6: TX shift register */

/* Bank 0 R7: column being scanned, 0-15, 16 = special column */
__data __at (0x07) unsigned char col;

unsigned char txbuf[TXBUF_SIZE];
unsigned char tx_count;                         /* bytes in txbuf */
unsigned char tx_wr, tx_rd;                     /* ring buffer indices */
unsigned char spec_reported;                    /* special column: last value sent */
unsigned char spec_read;                        /* special column: last value read */
unsigned char leds;                             /* LED 1-8 mask */

/* The interrupt changes these behind main()'s back */
#define RX_COUNT (*(volatile unsigned char *) &rx_count)
#define RX_BYTE  (*(volatile unsigned char *) &rx_byte)
#define TX_BITS  (*(volatile unsigned char *) &tx_bits)

/* Put a byte in the TX ring buffer. The caller checks that there is room.
   A macro, not a function: main() must not use a stack level. */
#define TX_BYTE(b) do { \
    txbuf[tx_wr] = (b); \
    tx_count++; \
    tx_wr = (tx_wr + 1) & (TXBUF_SIZE - 1); \
  } while (0)

/*
 * Timer interrupt, 2400 Hz: one TX bit per tick, RX sampled at 4 ticks
 * per bit (600 baud).
 */
void
timer_int (void) __interrupt (TIMER_VECTOR)
{
  F1 = 0;                       /* tell main() a tick has passed */
  T = 0xfb;

  if (--rx_div == 0)
    {
      rx_div = 1;
      if (!rx_count)
        {
          if (!T0)              /* start bit seen */
            {
              rx_count = 8;
              rx_div = 6;       /* first sample in the middle of bit 0 */
            }
        }
      else
        {
          rx_div = 4;
          rx_byte >>= 1;
          if (T0)
            rx_byte |= 0x80;
          if (--rx_count == 0)
            {
              rx_div = 6;
              if (rx_byte == 0x20)
                {
                  /* command 20h: reset. Make the interrupt return to 000h. */
                  __asm
                    clr   a
                    mov   r1, #0x08
                    mov   @r1, a
                    inc   r1
                    mov   @r1, a
                    inc   a
                    mov   psw, a
                    retr
                  __endasm;
                }
            }
        }
    }

  if (tx_bits)
    {
      if (--tx_bits == 0)
        {
          P1 &= 0xbf;           /* stop bit / idle */
          P1 |= 0x20;
        }
      else if (tx_bits == 9 || !(tx_shift & 1))
        {
          if (tx_bits != 9)
            tx_shift >>= 1;
          P1 &= 0xdf;           /* start bit or 0 */
          P1 |= 0x40;
        }
      else
        {
          tx_shift >>= 1;
          P1 |= 0x20;
        }
    }
}

void
main (void)
{
  unsigned char now, prev, mask, row16, bit;
  __data unsigned char *p;

  P2 = 0x30;                    /* LEDs off, beep idle */
  P1 = 0x20;                    /* TX idle high, click off */
  BUS = 0xff;                   /* LEDs 1-8 off */
  spec_reported = 0xff;         /* force a special column report at start */
  rx_div = 1;
  col = 0;
  T = 0xff;                     /* first tick soon */
  STRT_T ();
  EN_TCNTI ();

  for (;;)
    {
      /* one column per timer tick */
      while (F1)
        ;
      F1 = 1;

      if (!(col & 0x10))
        {
          P1 = (P1 & 0xe0) | col;       /* select the column */
          now = BUS;
          p = &col_state[col << 1];
          prev = *p;
          *p = now;
          if (prev == now)              /* stable for two scans */
            {
              p++;
              mask = now ^ *p;          /* changed since last report */
              if (mask && !(tx_count & TXBUF_SIZE))
                {
                  mask &= -mask;        /* lowest changed bit */
                  row16 = 0;            /* bit7 -> 00h ... bit0 -> 70h */
                  for (bit = mask; !(unsigned char) (bit & 0x80); bit <<= 1)
                    row16 += 0x10;
                  *p ^= mask;
                  TX_BYTE (((*p & mask) ? 0x00 : 0x80) | row16 | col);
                }
            }
          col++;
        }
      else
        {
          P1 |= 0x10;                   /* select the special column */
          NOP ();
          now = BUS;
          prev = spec_read;
          spec_read = now;
          if (prev == now && now != spec_reported && tx_count < TXBUF_SIZE - 1)
            {
              spec_reported = now;
              TX_BYTE (0x00);
              TX_BYTE (now);
            }
          col = 0;
        }

      /* start the next byte if the transmitter is idle */
      if (!TX_BITS && tx_count)
        {
          tx_count--;
          tx_shift = txbuf[tx_rd];
          tx_rd = (tx_rd + 1) & (TXBUF_SIZE - 1);
          TX_BITS = 10;                 /* start + 8 data + stop */
        }

      /* act on a received command */
      if (RX_COUNT || !RX_BYTE)
        continue;
      now = RX_BYTE;
      RX_BYTE = 0;

      if (now & 0xc0)                   /* 40h-FFh: ignored */
        continue;
      if (!(now & 0x20))
        {
          /* 01h-1Fh: LEDs */
          now--;
          if (now & 0x10)               /* 11h-1Fh: ignored */
            continue;
          mask = 1 << (now & 7);
          if (now & 0x08)
            leds &= ~mask;
          else
            leds |= mask;
          BUS = ~leds;                  /* LEDs are active low */
          continue;
        }

      switch (now)
        {
        case 0x21:
          P1 |= 0x80;                   /* click on */
          break;
        case 0x22:
          P1 &= 0x7f;                   /* click off */
          break;
        case 0x24:
          P2 &= 0xdf;                   /* beep */
          NOP ();
          P2 |= 0x20;
          break;
        case 0x25:
          leds = 0;
          BUS = 0xff;
          break;
        case 0x31:
          spec_reported = 0xff;         /* forces a new special column report */
          break;
        case 0x32:
          P2 |= 0x80;                   /* Caps LED */
          break;
        case 0x33:
          P2 &= 0x7f;
          break;
        case 0x34:
          P2 |= 0x40;                   /* Lock LED */
          break;
        case 0x35:
          P2 &= 0xbf;
          break;
        }
    }
}
