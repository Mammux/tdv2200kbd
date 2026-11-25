;
;	TDV 2200 / ND 320 keyboard - raw-only firmware
;
;	Replacement for ROM 965313-0 (2716, U8) for use with a USB adapter.
;	Sends key press/release scan codes only. The terminal character
;	tables, Shift/Ctrl translation, auto-repeat, LED blinking, ROM/RAM
;	tests, table dump and card reader (expansion) support are all gone.
;
;	The serial timing is based on the original ROM's timer interrupt.
;
;	Keyboard -> host, 8N1, 2400 baud after power-up or reset,
;	4800 baud after command 3Ah:
;	  00h-7Fh  key k pressed, k = row*16 + column
;	  80h-FFh  key k released (k OR 80h)
;	  00h, xx  special column changed, xx = bitmap:
;	           b0 ST1  b1 CAPS  b2 CTRL  b3 LOCK  b4 SHIFT  b5 AL1  b6 AL2  b7 SLUTT
;	  After power-up or reset the special column is always reported
;	  once, so the host sees "00 xx" when the keyboard is ready.
;
;	Host -> keyboard, 600 baud 8N1 (same codes as the original/patched ROM):
;	  01h-08h  LED 1-8 on          09h-10h  LED 1-8 off
;	  20h      reset               21h/22h  key click on/off
;	  24h      beep                25h      LEDs 1-8 off
;	  31h      report the special column again (raw mode is always on)
;	  32h/33h  Caps LED on/off     34h/35h  Lock LED on/off
;	  38h/39h  eager key presses on/off (off after reset)
;	  3Ah/3Bh  send at 4800/2400 baud (2400 after reset); the
;	           keyboard finishes the byte it is sending, switches,
;	           and then reports the special column ("00 xx")
;	  Anything else is ignored.
;
;	Debounce: a key change is reported once two scans in a row
;	(7.1 ms apart) read the same state for that key. With eager
;	presses on, a press is reported on the first scan that sees it;
;	releases still need two equal scans, which also hides contact
;	bounce after a press. A noise spike on a row line is then
;	reported as a short key press.
;
;	Hardware (schematic 391170):
;	  P1.0-3 column select (74LS154)   P1.4 special column select
;	  P1.5   TX data                   P1.6 TX active (key click)
;	  P1.7   click enable              BUS  rows in (INS) / LED latch out (OUTL)
;	  P2.5   beep trigger (low pulse)  P2.6 Lock LED   P2.7 Caps LED
;	  T0     RX data                   timer: 5.76 MHz / 480 / 5 = 2400 Hz
;	  F0     1 = send at 4800 baud
;
;	RAM:
;	  00h-07h  bank 0: r0 TX write ptr, r1 column state ptr, r2 column,
;	           r3 bytes in TX buffer, r5 eager mask (00h/FFh),
;	           r6/r7 scratch
;	  08h-0Bh  stack (2 levels: one call + the timer interrupt)
;	  0Ch      special column: last value reported
;	  0Dh      special column: last value read (debounce)
;	  0Fh      LED 1-8 mask
;	  10h-17h  TX ring buffer
;	  18h-1Fh  bank 1 (interrupt): r0 TX read ptr, r2 RX bit count,
;	           r3 RX sample divider, r4 RX byte, r5 TX bit count,
;	           r6 TX shift register, r7 saved A
;	  20h-3Fh  2 bytes per column: last read, last reported
;

	org	00000H
Reset:
	sel	rb0
	jmp	Init
	retr				; 003h: external interrupt (never enabled)
	nop
	nop
	nop

TimerInt:				; 007h: the routine is in page 2
	jmp	TimerIsr

;///////////////////////////////////////////////////////
;	Main loop: one column per timer tick, 16 columns + the
;	special column = one scan every 7.1 ms.
;
;	Each round starts right after a timer interrupt. The interrupt
;	changes P1.5 (TX), and the column select below reads P1, changes
;	it and writes it back: if an interrupt came in between, a TX bit
;	would be lost. Waiting for a fresh tick keeps them apart.

Main:
	clr	f1
	cpl	f1
MainWait:
	jf1	MainWait		; the interrupt clears F1
	sel	rb0
	mov	a,r2
	jb4	Special
	in	a,p1
	anl	a,#0E0H
	orl	a,r2
	outl	p1,a			; select column r2
	nop				; let the row lines settle: 3 cycles,
	nop				; the same delay as the original ROM
	nop				; (mov a,r4 / jb7) before it reads them
	ins	a,bus			; rows of this column
	xch	a,@r1			; last read := now, a = previous read
	xrl	a,@r1			; keys that changed since the last scan
	cpl	a			; keys that read the same twice
	mov	r7,a
	mov	a,@r1
	anl	a,r5			; eager: keys down now may be reported too
	orl	a,r7
	mov	r7,a			; keys that may be reported
	mov	a,@r1			; now
	inc	r1			; r1 -> last reported
	xrl	a,@r1			; keys that differ from what was reported
	anl	a,r7
	jz	ColSkip1
	mov	r7,a
	mov	a,r3
	jb3	ColSkip1		; TX buffer full: retry next scan
	mov	a,r7			; isolate the lowest changed bit: x & -x
	cpl	a
	inc	a
	anl	a,r7
	mov	r7,a			; r7 = row mask
	mov	r6,#000H		; r6 = row * 16 (bit7 -> 00h ... bit0 -> 70h)
RowLoop:
	jb7	RowDone
	rl	a
	xch	a,r6
	add	a,#010H
	xch	a,r6
	jmp	RowLoop
RowDone:
	mov	a,@r1
	xrl	a,r7
	mov	@r1,a			; last reported ^= mask
	anl	a,r7			; nonzero if the key is now down
	add	a,#0FFH			; carry = down
	cpl	c			; carry = released
	clr	a
	rrc	a			; a = 80h if released, 00h if pressed
	orl	a,r6
	add	a,r2			; + column
	call	TxByte
ColSkip1:
	inc	r1
	inc	r2
	jmp	Service

Special:
	orl	p1,#010H		; select the special column
	nop
	ins	a,bus
	mov	r7,a
	mov	r1,#00DH
	xch	a,@r1			; 0Dh := now, a = previous read
	xrl	a,@r1
	jnz	SpecDone		; still changing: wait (debounce)
	dec	r1			; 0Ch: last reported
	mov	a,r7
	xrl	a,@r1
	jz	SpecDone
	mov	a,r3
	add	a,#0F9H			; carry if 7 or more bytes queued
	jc	SpecDone
	mov	a,r7
	mov	@r1,a
	clr	a
	call	TxByte
	mov	a,r7
	call	TxByte
SpecDone:
	mov	r2,#000H
	mov	r1,#020H

;	Start the next byte if the transmitter is idle
Service:
	sel	rb1
	mov	a,r5
	jnz	RxCheck
	sel	rb0
	mov	a,r3
	jz	RxCheck0
	dec	r3
	sel	rb1
	mov	a,@r0
	mov	r6,a
	mov	r5,#00AH		; start + 8 data + stop
	inc	r0
	mov	a,r0
	xrl	a,#018H
	jnz	RxCheck
	mov	r0,#010H
	jmp	RxCheck
RxCheck0:
	sel	rb1

;	Act on a received command (bank 1)
RxCheck:
	mov	a,r2
	jnz	Main			; byte still arriving
	mov	a,r4
	jz	Main			; nothing received
	mov	r4,#000H
	jb7	Main			; 80h-FFh: ignored
	jb6	Main			; 40h-7Fh: ignored
	jb5	ToCmd2x
	dec	a			; 01h-1Fh: LEDs (a = 00h-1Eh)
	jb4	Main			; 11h-1Fh: ignored (was LED blink)
	mov	r1,#00FH
	jb3	LedOff
	call	LedMask
	orl	a,@r1
	jmp	LedOut
LedOff:
	call	LedMask
	cpl	a
	anl	a,@r1
LedOut:
	mov	@r1,a
	cpl	a			; LEDs are active low
	outl	bus,a
	jmp	Main
ToCmd2x:
	jmp	Cmd2x

;	Commands 20h-3Bh. JMPP stays inside its page, so the dispatch
;	table and all handlers live together in page 1.

	org	00100H
Cmd2x:
	add	a,#0C4H			; carry if command >= 3Ch
	jc	CmdNone
	add	a,#CmdTbl+1CH		; a = CmdTbl + (command - 20h)
	jmpp	@a
CmdTbl:
	db	CmdNone, CmdClkOn, CmdClkOff, CmdNone	; 20h-23h
	db	CmdBeep, CmdLedsOff, CmdNone, CmdNone	; 24h-27h
	db	CmdNone, CmdNone, CmdNone, CmdNone	; 28h-2Bh
	db	CmdNone, CmdNone, CmdNone, CmdNone	; 2Ch-2Fh
	db	CmdNone, CmdReport, CmdCapsOn, CmdCapsOff	; 30h-33h
	db	CmdLockOn, CmdLockOff, CmdNone, CmdNone	; 34h-37h
	db	CmdEagerOn, CmdEagerOff, CmdFast, CmdSlow	; 38h-3Bh
CmdNone:
	jmp	Main
CmdClkOn:
	orl	p1,#080H
	jmp	Main
CmdClkOff:
	anl	p1,#07FH
	jmp	Main
CmdBeep:
	anl	p2,#0DFH
	nop
	orl	p2,#020H
	jmp	Main
CmdLedsOff:
	mov	r1,#00FH
	clr	a
	jmp	LedOut
CmdReport:
	mov	r1,#00CH
	mov	@r1,#0FFH		; forces a new special column report
	jmp	Main
CmdCapsOn:
	orl	p2,#080H
	jmp	Main
CmdCapsOff:
	anl	p2,#07FH
	jmp	Main
CmdLockOn:
	orl	p2,#040H
	jmp	Main
CmdLockOff:
	anl	p2,#0BFH
	jmp	Main
CmdEagerOn:
	sel	rb0
	mov	r5,#0FFH
	jmp	Main
CmdEagerOff:
	sel	rb0
	mov	r5,#000H
	jmp	Main
CmdFast:
	mov	a,r5			; wait until the byte being sent is done
	jnz	CmdFast
	clr	f0
	cpl	f0
	jmp	CmdReport
CmdSlow:
	mov	a,r5
	jnz	CmdSlow
	clr	f0
	jmp	CmdReport

;///////////////////////////////////////////////////////
;	TxByte: put A in the TX ring buffer (bank 0). The caller
;	checks that there is room.

TxByte:
	mov	@r0,a
	inc	r3
	inc	r0
	mov	a,r0
	xrl	a,#018H
	jnz	TxByteEnd
	mov	r0,#010H
TxByteEnd:
	ret

;	LedMask: a = 1 << (a AND 7)
LedMask:
	anl	a,#007H
	add	a,#LedTbl
	movp	a,@a
	ret
LedTbl:
	db	001H, 002H, 004H, 008H, 010H, 020H, 040H, 080H

;///////////////////////////////////////////////////////

Init:
	dis	tcnti
	dis	i
	clr	f0			; 2400 baud
	mov	r0,#03FH
ClearRam:
	mov	@r0,#000H		; also: eager presses off (r5 = 00h)
	djnz	r0,ClearRam
	mov	a,#030H
	outl	p2,a			; LEDs off, beep idle
	mov	a,#020H
	outl	p1,a			; TX idle high, click off
	mov	a,#0FFH
	outl	bus,a			; LEDs 1-8 off
	mov	r0,#00CH
	mov	@r0,a			; force a special column report at start
	mov	r0,#010H		; TX write pointer
	mov	r1,#020H
	sel	rb1
	mov	r0,#010H		; TX read pointer
	mov	r3,#001H		; RX divider
	sel	rb0
	mov	t,a			; a = 0FFh: first tick soon
	strt	t
	en	tcnti
	jmp	Main

;///////////////////////////////////////////////////////
;	Timer interrupt, 2400 Hz.
;
;	TX: one bit per tick at 2400 baud; at 4800 baud a second bit
;	exactly 80 cycles after the first. Each TX slot takes the same
;	number of cycles whatever it sends, so the bit edges fall on
;	an exact grid. RX: sampled at 4 ticks per bit (600 baud).
;
;	Cycle counts are in the comments; the timing is checked in
;	the emulator (timing_check.py).

	org	00200H
TimerIsr:
	sel	rb1
	mov	r7,a
	clr	f1			; tell Main a tick has passed
	mov	a,#0FBH
	mov	t,a

;	TX slot 1. r5 = bits left: 10 -> start bit (9), data (8-1),
;	stop bit (0). The P1.5 write starts 16 cycles into the slot
;	on every path that sends a bit; all of those take 22 cycles.
TxSlot1:
	mov	a,r5			; 1
	jz	TxDone1			; 3: idle
	dec	a			; 4
	mov	r5,a			; 5
	jz	TxStop1			; 7
	xrl	a,#009H			; 9
	jz	TxStart1		; 11
	mov	a,r6			; 12
	rrc	a			; 13
	mov	r6,a			; 14
	jc	TxHigh1			; 16
	anl	p1,#0DFH		; 18: data 0
	nop				; 19
	nop				; 20
	jmp	TxDone1			; 22
TxHigh1:
	orl	p1,#020H		; 18: data 1
	nop				; 19
	nop				; 20
	jmp	TxDone1			; 22
TxStop1:
	nop				; 8
	nop
	nop
	nop
	nop
	nop
	nop
	nop
	nop				; 16
	orl	p1,#020H		; 18: stop bit
	anl	p1,#0BFH		; 20: TX active off
	jmp	TxDone1			; 22
TxStart1:
	nop				; 12
	nop
	nop
	nop
	nop				; 16
	anl	p1,#0DFH		; 18: start bit
	orl	p1,#040H		; 20: TX active on (key click)
	jmp	TxDone1			; 22
TxDone1:
	jf0	TxFast			; 24

;	RX, 600 baud: 4 ticks per bit. Copied from the original ROM.
RxSlow:
	djnz	r3,TimerIntEnd
	inc	r3
	mov	a,r2
	jnz	RxSlowBit
	jt0	TimerIntEnd		; line idle
	mov	r2,#008H		; start bit seen
	mov	r3,#006H		; first sample in the middle of bit 0
	jmp	TimerIntEnd
RxSlowBit:
	mov	r3,#004H
	mov	a,r4
	clr	c
	jnt0	RxSlowAny
	cpl	c
RxSlowAny:
	rrc	a
	mov	r4,a
	djnz	r2,TimerIntEnd
	mov	r3,#006H
	xrl	a,#020H			; command 20h: reset
	jz	RxReset
TimerIntEnd:
	mov	a,r7
	retr

RxReset:
	mov	r1,#008H		; return address on the stack := 000h
	mov	@r1,a			; (a = 0)
	inc	r1
	mov	@r1,a
	inc	a
	mov	psw,a			; stack pointer 1, F0 = 0 (2400 baud)
	retr

;	4800 baud: RX in a version that always takes 32 cycles, a
;	delay, then the second TX slot 80 cycles after the first.
TxFast:
	mov	a,r5			; 25
	jz	RxSlow			; 27: nothing more to send this tick
	djnz	r3,RxFastWait		; 29
	inc	r3			; 30
	mov	a,r2			; 31
	jnz	RxFastBit		; 33
	jt0	RxFastIdle		; 35: line idle
	mov	r2,#008H		; 37: start bit seen
	mov	r3,#006H		; 39
	nop				; 40
	nop
	nop
	nop
	nop
	nop
	nop				; 46
	jmp	RxFastDone		; 48
RxFastWait:				; 29
	nop				; 30
	nop
	nop
	nop
	nop
	nop				; 35
RxFastIdle:				; 35
	nop				; 36
	nop
	nop
	nop
	nop
	nop
	nop
	nop
	nop
	nop				; 45
	nop				; 46
	jmp	RxFastDone		; 48
RxFastBit:				; 33
	mov	r3,#004H		; 35
	mov	a,r4			; 36
	clr	c			; 37
	jnt0	RxFastZero		; 39
	cpl	c			; 40
	jmp	RxFastAny		; 42
RxFastZero:				; 39
	nop				; 40
	nop				; 41
	nop				; 42
RxFastAny:
	rrc	a			; 43
	mov	r4,a			; 44
	djnz	r2,RxFastMid		; 46
	mov	r3,#006H		; 48: byte complete
	xrl	a,#020H			; 50
	jz	RxReset			; 52
	jmp	RxFastDone2		; 54
RxFastMid:				; 46
	nop				; 47
	nop				; 48
RxFastDone:				; 48
	nop				; 49
	nop
	nop
	nop
	nop
	nop				; 54
RxFastDone2:				; 54
	mov	a,#008H			; 56
RxFastDelay:
	dec	a
	jnz	RxFastDelay		; 56 + 8 * 3 = 80

;	TX slot 2: same as slot 1, 80 cycles later.
TxSlot2:
	mov	a,r5
	jz	TimerIntEnd2
	dec	a
	mov	r5,a
	jz	TxStop2
	xrl	a,#009H
	jz	TxStart2
	mov	a,r6
	rrc	a
	mov	r6,a
	jc	TxHigh2
	anl	p1,#0DFH		; data 0
	nop
	nop
	jmp	TimerIntEnd2
TxHigh2:
	orl	p1,#020H		; data 1
	nop
	nop
	jmp	TimerIntEnd2
TxStop2:
	nop
	nop
	nop
	nop
	nop
	nop
	nop
	nop
	nop
	orl	p1,#020H		; stop bit
	anl	p1,#0BFH		; TX active off
	jmp	TimerIntEnd2
TxStart2:
	nop
	nop
	nop
	nop
	nop
	anl	p1,#0DFH		; start bit
	orl	p1,#040H		; TX active on
TimerIntEnd2:
	mov	a,r7
	retr
