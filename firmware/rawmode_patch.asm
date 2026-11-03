; =====================================================================
;  TDV 2200 / ND 320 keyboard (ROM 965313-0) - "raw mode" patch
;
;  Adds a press/release scan-code mode that the host switches on with a
;  command. Without that command the keyboard behaves exactly as before,
;  so the patched EPROM still works in a real terminal.
;
;  Host -> keyboard commands added (600 baud, unused by the original ROM):
;     31h  enable raw mode
;     32h  Caps LED on        33h  Caps LED off
;     34h  Lock LED on        35h  Lock LED off
;     36h  disable raw mode   (sending 20h = reset also returns to normal)
;
;  Keyboard -> host in raw mode (2400 baud):
;     00h-7Fh   key k pressed      k = row*16 + column, row 0..7, col 0..15
;     80h-FFh   key k released     (k OR 80h)
;     00h, xx   special column changed; xx = new bitmap:
;                 bit0 ST1   bit1 CAPS   bit2 CTRL   bit3 LOCK
;                 bit4 SHIFT bit5 AL1    bit6 AL2    bit7 SLUTT/BREAK
;     (position 0 has no key, so 00h never means "key 0 pressed")
;
;  Raw mode turns off the keyboard's own auto-repeat, Shift/Ctrl/Caps
;  handling and its Caps/Lock LED logic: the host does all of that.
;  The raw-mode flag is the P2.1 port latch (A9 of the EPROM during
;  fetches), the same trick the original ROM uses for P2.2.
;
;  Free space used: 056Ah-05FFh. Hooks: 05Ch, 0F4h, 3A1h.
; =====================================================================

; ---- hook 1: per-column key scan (from 05Ch, bank 0, r1 -> raw[col])
RawCol:     in   a,p2
            jb1  RawColDo
            mov  a,r4               ; original code that was overwritten
            jb7  ToKDNC
            jmp  05Fh               ; back to "ins a,bus" in the main loop
RawColDo:   ins  a,bus              ; rows of this column
            xch  a,@r1              ; raw[col] = now, a = last scan
            xrl  a,@r1
            jnz  ToKDNC             ; still changing: wait (debounce)
            mov  a,@r1              ; stable state
            inc  r1                 ; r1 -> reported[col]
            xrl  a,@r1              ; bits that differ from what we reported
            jz   ToKD
            mov  r7,a
            mov  a,r3
            jb3  ToKD               ; TX buffer full: retry next scan
            mov  a,r7               ; isolate lowest changed bit: x & -x
            cpl  a
            inc  a
            anl  a,r7
            mov  r7,a               ; r7 = row mask
            mov  r6,#00h            ; r6 = row * 16 (bit7 -> 00h ... bit0 -> 70h)
RowLoop:    jb7  RowDone
            rl   a
            xch  a,r6
            add  a,#10h
            xch  a,r6
            jmp  RowLoop
RowDone:    mov  a,@r1
            xrl  a,r7
            mov  @r1,a              ; reported[col] ^= mask
            anl  a,r7               ; nonzero if the key is now down
            add  a,#0FFh            ; carry = down
            cpl  c                  ; carry = released
            clr  a
            rrc  a                  ; a = 80h if released, 00h if pressed
            orl  a,r6
            add  a,r2               ; + column
            call 3DEh               ; TxByte: put A in the TX ring buffer
ToKD:       jmp  0CCh               ; KeyDone
ToKDNC:     jmp  0CBh               ; KeyDoneNoChangeInKeyHold

; ---- hook 2: special column (from 0F4h, bank 0)
RawSpecial: in   a,p2
            jb1  RawSpecDo
            jmp  15Bh               ; original CheckSpecialKeys
RawSpecDo:  orl  p1,#10h            ; select the special column
            nop
            ins  a,bus
            mov  r7,a
            mov  r1,#0Ch            ; RAM 0Ch: last reported bitmap (repeat
            xrl  a,@r1              ; buffer in normal mode, unused in raw)
            jz   ToEOS
            mov  a,r3
            anl  a,#0Fh
            add  a,#0F9h            ; carry if 7 or more bytes queued
            jc   ToEOS
            mov  a,r7
            mov  @r1,a
            clr  a
            call 3DEh
            mov  a,r7
            call 3DEh
ToEOS:      jmp  1FAh               ; end of scan (r1/r2 reset there)

; ---- hook 3: commands 30h-3Fh (from 3A1h, bank 1, A = command)
RawCmd:     add  a,#0C9h            ; carry if command >= 37h
            jc   CEnd
            add  a,#CmdTbl+7        ; a = CmdTbl + (command - 30h)
            jmpp @a
CmdTbl:     db   C30, C31, C32, C33, C34, C35, C36
C30:        orl  p2,#04h            ; original 30h behaviour
            jmp  050h
C31:        mov  r1,#0Ch
            mov  @r1,#0FFh          ; force a report of the special column
            sel  rb0
            mov  a,r4
            anl  a,#7Fh             ; clear "keyboard locked"
            mov  r4,a
            orl  p2,#02h            ; raw mode on
            jmp  050h
C32:        orl  p2,#80h            ; Caps LED on
            jmp  050h
C33:        anl  p2,#7Fh            ; Caps LED off
            jmp  050h
C34:        orl  p2,#40h            ; Lock LED on
            jmp  050h
C35:        anl  p2,#0BFh           ; Lock LED off
            jmp  050h
C36:        anl  p2,#0FDh           ; raw mode off
CEnd:       jmp  050h               ; Main
