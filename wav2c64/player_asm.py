"""ACME source code of the C64 player.

The template is filled in by :func:`make_player_source`. The resulting
file can be assembled with ACME (``acme name.asm``) or with the built-in
assembler in :mod:`wav2c64.asm6502`; both produce the identical PRG.
"""

from . import APP_NAME, VERSION, AUTHOR

MACHINE_AUTO, MACHINE_PAL, MACHINE_NTSC = 0, 1, 2
SID_AUTO, SID_6581, SID_8580 = 0, 1, 2

_TEMPLATE = r"""; =====================================================================
;  {app} {version} - C64 4-bit sample player for the ACME cross assembler
;  Author: {author}
;
;  Plays 4-bit samples (2 per byte, high nibble first) through the SID
;  volume register $D418. The sample clock is an NMI from CIA 2 timer A,
;  so the sample rate is exact.
;
;  Build:   acme {name}.asm          -> {name}.prg
;  Start:   LOAD"{name_upper}",8   and   RUN
;  Keys:    SPACE = play again / restart     Q = quit to BASIC
;
;  The sample data is included from "{name}.txt" (!byte lines).
; =====================================================================

!cpu 6510
!to "{name}.prg", cbm

; ---------------- settings -------------------------------------------
MACHINE   = {machine}      ; 0 = auto detect, 1 = PAL, 2 = NTSC
SID_MODEL = {sid}      ; 0 = auto detect, 1 = 6581, 2 = 8580 (digi boost)
LOOP      = {loop}      ; 0 = play once, 1 = loop until SPACE or Q

CLOCK_PAL  = 985248     ; CPU clock PAL  (Hz)
CLOCK_NTSC = 1022727    ; CPU clock NTSC (Hz)

; ---------------- zero page ------------------------------------------
ptr       = $fb         ; pointer to the current sample byte ($fb/$fc)
phase     = $fd         ; 0 = high nibble next, 1 = low nibble next
done      = $fe         ; 1 when the sample has ended
is8580    = $02         ; 0 = 6581, 1 = 8580
isntsc    = $f7         ; 0 = PAL, 1 = NTSC

; ---------------- hardware -------------------------------------------
VIC_RASTER = $d012
SID        = $d400
SID_VOL    = $d418
SID_OSC3   = $d41b
CIA1_PRA   = $dc00
CIA1_PRB   = $dc01
CIA2_TA    = $dd04
CIA2_ICR   = $dd0d
CIA2_CRA   = $dd0e
NMI_VEC    = $fffa
CHROUT     = $ffd2
STATUS     = $0400 + 12 * 40    ; status line on screen (row 12)
STATUS_COL = $d800 + 12 * 40

KEY_SPACE  = $10        ; keyboard row 7, bit 4
KEY_Q      = $40        ; keyboard row 7, bit 6

; ---------------- BASIC line: 10 SYS2061 -----------------------------
* = $0801
        !word basic_end, 10
        !byte $9e
        !pet "2061"
        !byte 0
basic_end:
        !word 0

; ---------------- main program ($080d) -------------------------------
start:
        sei
        lda #MACHINE            ; ---- PAL or NTSC? ----
        bne machine_fixed
        jsr detect_ntsc
        jmp machine_known
machine_fixed:
        cmp #MACHINE_NTSC_ID    ; C = 1 -> NTSC
        lda #0
        rol
        sta isntsc
machine_known:
        lda #SID_MODEL          ; ---- which SID? ----
        bne sid_fixed
        jsr detect_sid
        jmp sid_known
sid_fixed:
        cmp #SID_8580_ID        ; C = 1 -> 8580
        lda #0
        rol
        sta is8580
sid_known:
        lda #<msg_title         ; ---- screen text (KERNAL still on) ----
        ldy #>msg_title
        jsr print
        lda #<msg_6581
        ldy #>msg_6581
        ldx is8580
        beq print_sid
        lda #<msg_8580
        ldy #>msg_8580
print_sid:
        jsr print
        lda #<msg_pal
        ldy #>msg_pal
        ldx isntsc
        beq print_machine
        lda #<msg_ntsc
        ldy #>msg_ntsc
print_machine:
        jsr print
        lda #<msg_keys
        ldy #>msg_keys
        jsr print

        sei
        lda #$35                ; BASIC + KERNAL ROM off, I/O on
        sta $01                 ; -> NMI vector at $fffa is RAM

play:
        ldx #0                  ; status: playing
        jsr show_status
        jsr sid_init
        lda #<sample_start
        sta ptr
        lda #>sample_start
        sta ptr+1
        lda #0
        sta phase
        sta done
        lda #<nmi               ; install NMI handler
        sta NMI_VEC
        lda #>nmi
        sta NMI_VEC+1
        lda #$7f                ; all CIA 2 interrupts off
        sta CIA2_ICR
        lda CIA2_ICR            ; acknowledge pending ones
        lda isntsc
        bne timer_ntsc
        lda #<TIMER_PAL
        sta CIA2_TA
        lda #>TIMER_PAL
        sta CIA2_TA+1
        jmp timer_set
timer_ntsc:
        lda #<TIMER_NTSC
        sta CIA2_TA
        lda #>TIMER_NTSC
        sta CIA2_TA+1
timer_set:
        lda #$81                ; timer A -> NMI
        sta CIA2_ICR
        lda #$11                ; load + start timer A, continuous
        sta CIA2_CRA
        jsr wait_release

play_wait:                      ; ---- while playing ----
        lda done
        bne finished
        jsr read_keys
        and #KEY_Q
        bne quit
        jsr read_keys
        and #KEY_SPACE
        beq play_wait
        jsr stop_nmi            ; SPACE: restart
        jmp play

finished:                       ; ---- sample has ended ----
        jsr stop_nmi
        ldx #STATUS_DONE
        jsr show_status
        jsr wait_release
end_wait:
        jsr read_keys
        and #KEY_Q
        bne quit
        jsr read_keys
        and #KEY_SPACE
        beq end_wait
        jmp play                ; SPACE: play again

quit:
        jsr stop_nmi
        ldx #$18                ; silence the SID
        lda #0
quit_sid:
        sta SID,x
        dex
        bpl quit_sid
        lda #$0f                ; normal volume for BASIC
        sta SID_VOL
        ldx #STATUS_QUIT
        jsr show_status
        jsr wait_release
        lda #$37                ; ROMs back on
        sta $01
        cli
        rts                     ; back to BASIC (RUN plays again)

; ---------------- subroutines ----------------------------------------
print:                          ; print 0-terminated text at A/Y
        sta ptr
        sty ptr+1
        ldy #0
print_loop:
        lda (ptr),y
        beq print_end
        jsr CHROUT
        iny
        bne print_loop
print_end:
        rts

show_status:                    ; X = offset of a 40 char status text
        ldy #0
status_loop:
        lda status_texts,x
        sta STATUS,y
        lda #1                  ; white
        sta STATUS_COL,y
        inx
        iny
        cpy #40
        bne status_loop
        rts

read_keys:                      ; A = pressed keys of row 7 (SPACE, Q)
        lda #$7f
        sta CIA1_PRA
        lda CIA1_PRB
        eor #$ff
        and #KEY_SPACE + KEY_Q
        rts

wait_release:                   ; wait until SPACE and Q are released
        jsr read_keys
        bne wait_release
        ldx #0                  ; short debounce delay
        ldy #20
release_delay:
        dex
        bne release_delay
        dey
        bne release_delay
        rts

stop_nmi:
        lda #$7f                ; no more NMIs from CIA 2
        sta CIA2_ICR
        lda #0
        sta CIA2_CRA            ; stop timer A
        lda CIA2_ICR            ; acknowledge
        rts

sid_init:                       ; clear SID, 8580: switch on digi boost
        ldx #$18
        lda #0
sid_clear:
        sta SID,x
        dex
        bpl sid_clear
        lda is8580
        beq sid_init_done
        lda #$ff                ; sustain/release max for all 3 voices
        sta SID+$06
        sta SID+$0d
        sta SID+$14
        lda #$49                ; pulse + test bit + gate: a constant DC
        sta SID+$04             ; level on all 3 voices which $d418 then
        sta SID+$0b             ; modulates -> the 8580 gets the volume
        sta SID+$12             ; "click" the 6581 has by itself
        ldx #0                  ; wait until the envelopes are up
        ldy #8
sid_delay:
        dex
        bne sid_delay
        dey
        bne sid_delay
sid_init_done:
        rts

;----------------------------------------------------------------------
; PAL/NTSC detection: find the last raster line. PAL ends at line 311
; ($37 in $d012), NTSC at line 261/262 ($05/$06).
;----------------------------------------------------------------------
detect_ntsc:
dn_line:
        lda VIC_RASTER
dn_same:
        cmp VIC_RASTER
        beq dn_same
        bmi dn_line
        cmp #$20                ; C = 1 -> PAL
        lda #0
        rol
        eor #1                  ; A = 1 -> NTSC
        sta isntsc
        rts

;----------------------------------------------------------------------
; SID detection via oscillator 3: set the test bit, start a sawtooth and
; read $d41b at once. The 6581 delivers the value one cycle late (-> 3),
; the 8580 does not (-> 2). Measured 8 times on raster line 0 (border,
; no bad lines), majority vote.
;----------------------------------------------------------------------
detect_sid:
        lda #0
        sta is8580              ; counts 8580 results
        ldy #8
ds_try:
ds_wait1:
        lda VIC_RASTER
        beq ds_wait1
ds_wait2:
        lda VIC_RASTER
        bne ds_wait2
        lda #$ff
        sta SID+$12             ; test bit on (oscillator 3 stopped)
        sta SID+$0e             ; voice 3 frequency = $ffff
        sta SID+$0f
        lda #$20                ; sawtooth, test bit off -> runs
        sta SID+$12
        lda SID_OSC3            ; read oscillator 3
        lsr                     ; C = 1 -> 6581, C = 0 -> 8580
        bcs ds_next
        inc is8580
ds_next:
        dey
        bne ds_try
        lda #0
        sta SID+$12
        lda is8580              ; at least 5 of 8 -> 8580
        cmp #5
        lda #0
        rol
        sta is8580
        rts

; ---------------- NMI: output one sample -----------------------------
nmi:
        pha
        tya
        pha
        lda CIA2_ICR            ; acknowledge NMI
        ldy #0
        lda (ptr),y
        ldy phase
        bne nmi_low
        lsr                     ; high nibble
        lsr
        lsr
        lsr
        sta SID_VOL
        iny                     ; Y = 1
        sty phase
        pla
        tay
        pla
        rti
nmi_low:
        and #$0f                ; low nibble
        sta SID_VOL
        dey                     ; Y = 0
        sty phase
        inc ptr                 ; next byte
        bne nmi_check
        inc ptr+1
nmi_check:
        lda ptr
        cmp #<sample_end
        bne nmi_exit
        lda ptr+1
        cmp #>sample_end
        bne nmi_exit
        lda #LOOP               ; end reached
        beq nmi_stop
        lda #<sample_start      ; loop: start again
        sta ptr
        lda #>sample_start
        sta ptr+1
        jmp nmi_exit
nmi_stop:
        lda #$7f                ; no more NMIs
        sta CIA2_ICR
        inc done
nmi_exit:
        pla
        tay
        pla
        rti

; ---------------- texts ----------------------------------------------
msg_title:
        !byte 147, 5            ; clear screen, white
        !pet "{title}", 13
        !byte 154               ; light blue
        !pet "{subtitle}", 13, 13, 0
msg_6581:
        !pet "sid:     6581", 13, 0
msg_8580:
        !pet "sid:     8580 (digi boost on)", 13, 0
msg_pal:
        !pet "machine: pal", 13, 13, 0
msg_ntsc:
        !pet "machine: ntsc", 13, 13, 0
msg_keys:
        !pet "space = play again   q = quit", 13, 0

status_texts:
        !scr "playing...                              "
        !scr "finished. space = play again, q = quit  "
        !scr "bye!                                    "
STATUS_DONE = 40
STATUS_QUIT = 80

; ---------------- sample data ----------------------------------------
sample_start:
        !source "{name}.txt"
sample_end:

; ---------------- calculations / checks ------------------------------
MACHINE_NTSC_ID = 2
SID_8580_ID     = 2
TIMER_PAL  = CLOCK_PAL DIV SAMPLE_RATE - 1
TIMER_NTSC = CLOCK_NTSC DIV SAMPLE_RATE - 1

!if sample_end > $d000 {{
        !error "Sample too big: the data must end below $D000."
}}
!if TIMER_PAL < 75 {{
        !error "Sample rate too high for the NMI routine."
}}
"""


def _clip_pet(text, width=38):
    """Keep only characters that look right in the C64 upper case font."""
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789 .,:;-+()/!?'#=_"
    out = "".join(c for c in text.lower() if c in allowed)
    return out[:width]


def make_player_source(name, machine=MACHINE_AUTO, sid=SID_AUTO, loop=False,
                       title=None):
    """Return the ACME source of the player for project *name*."""
    t = _clip_pet(title if title else name, 38)
    return _TEMPLATE.format(
        app=APP_NAME, version=VERSION, author=AUTHOR,
        name=name, name_upper=name.upper(),
        machine=int(machine), sid=int(sid), loop=1 if loop else 0,
        title=t,
        subtitle=_clip_pet("%s %s sample player" % (APP_NAME, VERSION), 38),
    )
