"""Produce 965313-0-rawmode.asm: the original disassembly with the raw-mode
patch applied in source form, then check it assembles to the patched image."""
import re
from asm48 import assemble

src = open("965313-0.asm").read()
lines = src.split("\n")


def replace_once(text, old, new):
    assert text.count(old) == 1, f"expected exactly one match for {old!r}"
    return text.replace(old, new)


HEADER = """;
;	PATCHED IMAGE: 965313-0 + raw-mode patch (press/release scan codes)
;
;	Based on the DASMx disassembly above. Every change is marked
;	"PATCH". The rest is byte-for-byte the original ROM.
;
;	Changes:
;	  - Main (05Ch):           mov a,r4 / jb7  ->  jmp RawCol / nop
;	  - DoLastKBColumn (0F4h): jmp CheckSpecialKeys  ->  jmp RawSpecial
;	  - L03A1 (3A1h):          xrl a,#030H  ->  jmp RawCmd
;	  - 056Ah-05F3h:           new code (was zero-filled)
;	  - 05FFh:                 checksum adjustment, so command 2Dh still returns AAh
;
;	Host -> keyboard (600 baud), new commands:
;	  31h raw mode on    36h raw mode off (reset 20h also turns it off)
;	  32h/33h Caps LED on/off    34h/35h Lock LED on/off
;
;	Keyboard -> host in raw mode (2400 baud):
;	  00h-7Fh  key k pressed, k = row*16 + column
;	  80h-FFh  key k released (k OR 80h)
;	  00h, xx  special column changed, xx = bitmap:
;	           b0 ST1  b1 CAPS  b2 CTRL  b3 LOCK  b4 SHIFT  b5 AL1  b6 AL2  b7 SLUTT
;
"""

# header goes after the DASMx banner (before the first org)
src = replace_once(src, "\torg\t00000H", HEADER + "\n\torg\t00000H")

# hook 1: per-column scan
src = replace_once(src,
    "\toutl\tp1,a\n\tmov\ta,r4\n\tjb7\tKeyDoneNoChangeInKeyHold\n\tins\ta,bus\n",
    "\toutl\tp1,a\n"
    "\tjmp\tRawCol\t\t\t; PATCH: was  mov a,r4 / jb7 KeyDoneNoChangeInKeyHold\n"
    "\tnop\t\t\t\t; PATCH\n"
    "MainReadRows:\t\t\t\t; PATCH: label added (return point from RawCol)\n"
    "\tins\ta,bus\n")

# hook 2: special column
src = replace_once(src,
    "DoLastKBColumn:\n\tjmp\tCheckSpecialKeys",
    "DoLastKBColumn:\n\tjmp\tRawSpecial\t\t; PATCH: was  jmp CheckSpecialKeys")

# hook 3: commands 30h-3Fh
src = replace_once(src,
    "L03A1:\n\txrl\ta,#030H\n\tjnz\tBackToMain\n\torl\tp2,#004H\n\tjmp\tMain\n",
    "L03A1:\n"
    "\tjmp\tRawCmd\t\t\t; PATCH: was  xrl a,#030H\n"
    "\tjnz\tBackToMain\t\t; PATCH: the next 3 instructions are no longer\n"
    "\torl\tp2,#004H\t\t;        reached (command 30h is handled in RawCmd)\n"
    "\tjmp\tMain\n")

# new code in the zero-filled area after ReadFromPage5
patch = open("rawmode_patch.asm").read()
body = patch[patch.index("; ---- hook 1"):]
for num, lab in [("05Fh", "MainReadRows"), ("0CBh", "KeyDoneNoChangeInKeyHold"),
                 ("0CCh", "KeyDone"), ("3DEh", "TxByte"), ("15Bh", "CheckSpecialKeys"),
                 ("1FAh", "L01FA"), ("050h", "Main")]:
    body = re.sub(r"(\b(?:jmp|call)\s+)" + num + r"\b", r"\g<1>" + lab, body)
body = "\n".join(";" + l[1:] if l.startswith("; ") else l for l in body.split("\n"))

zero_block_start = src.index("ReadFromPage5:\n\tmovp\ta,@a\n\tret\n\n")
zero_block_start += len("ReadFromPage5:\n\tmovp\ta,@a\n\tret\n\n")
zero_block_end = src.index("\n\n;////////////////////////////////////////////////////////////\nReadFromPage6:")
zeros = src[zero_block_start:zero_block_end]
assert set(re.findall(r"[0-9A-F]+H", zeros)) == {"00H"} and zeros.count("00H") == 150

new_block = (
    ";////////////////////////////////////////////////////////////\n"
    ";\tPATCH: raw-mode code, 056Ah-05F3h (this area was all 00H)\n"
    ";////////////////////////////////////////////////////////////\n\n"
    + body.strip("\n") + "\n\n"
    ";\tPATCH: unused (00H) up to the checksum adjustment byte\n"
    "\tdb\t00H, 00H, 00H, 00H, 00H, 00H, 00H, 00H, 00H, 00H, 00H\n"
    "\tdb\t0F1H\t\t\t; PATCH: checksum adjustment (ROM sum stays AAh)"
)
src = src[:zero_block_start] + new_block + src[zero_block_end:]

# reformat the patch block to the DASMx tab style:  label: / <tab>op<tab>args
out = []
in_patch = False
for l in src.split("\n"):
    if "PATCH: raw-mode code" in l:
        in_patch = True
    if l.startswith(";\tPATCH: unused"):
        in_patch = False
    if in_patch and l and not l.startswith(";"):
        code, _, comment = l.partition(";")
        m = re.match(r"^(\w+):\s*(.*)$", code.strip()) if re.match(r"^\w+:", code) else None
        label, ins = (m.group(1), m.group(2)) if m else (None, code.strip())
        if label:
            out.append(label + ":")
        if ins:
            op, _, args = ins.partition(" ")
            args = args.strip()
            # DASMx number style: #0FFh -> #0FFH, #10h -> #010H
            args = re.sub(r"#0?([0-9A-Fa-f]{2})h\b", lambda m: "#0" + m.group(1).upper() + "H", args)
            # drop comments that only repeat the jump target's name
            target = args.split(",")[-1]
            if comment.strip().split(":")[0].strip() in (target, "original " + target):
                comment = ""
            text = f"\t{op}\t{args}" if args else f"\t{op}"
            if comment.strip():
                width = len(text.expandtabs(8))
                text += "\t" * max(1, (40 - width + 7) // 8) + "; " + comment.strip()
            out.append(text)
        continue
    out.append(l)
src = "\n".join(out)

open("965313-0-rawmode.asm", "w").write(src)

code, labels = assemble(src, 0)
patched = open("965313-0-rawmode.bin", "rb").read()
assert code == patched, "assembled source does not match the patched image"
print("965313-0-rawmode.asm assembles to 965313-0-rawmode.bin exactly",
      f"({len(src.splitlines())} lines)")
