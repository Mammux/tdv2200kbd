"""Tiny two-pass MCS-48 assembler for small patches.

Syntax matches the disassembler in mcs48.py, e.g.
    Label:  mov a,#0Fh
            jb7 Label
            jmp 0CBh
Numbers: 0Fh, 0x0F, 15. Comments start with ';'.
"""
import re
from mcs48 import OPS

_PATTERNS = []
for code, (name, length, _) in OPS.items():
    rx = re.escape(name)
    rx = rx.replace(re.escape("{d}"), r"(?P<d>[^\s,]+)")
    rx = rx.replace(re.escape("{a8}"), r"(?P<a8>[^\s,]+)")
    rx = rx.replace(re.escape("{a11}"), r"(?P<a11>[^\s,]+)")
    _PATTERNS.append((re.compile("^" + rx + "$"), code, length))


def _num(tok, labels):
    t = tok.strip()
    if "+" in t:
        return sum(_num(p, labels) for p in t.split("+"))
    if t in labels:
        return labels[t]
    if t.lower().startswith("0x"):
        return int(t, 16)
    if t.lower().endswith("h"):
        return int(t[:-1], 16)
    return int(t)


def assemble(src, org, rom_size=0x800):
    """Return (bytes, labels). Two passes."""
    lines = []
    for raw in src.splitlines():
        line = raw.split(";")[0].strip()
        if not line:
            continue
        while ":" in line.split()[0]:
            lab, line = line.split(":", 1)
            lines.append(("label", lab.strip()))
            line = line.strip()
            if not line:
                break
        if line:
            lines.append(("ins", re.sub(r"\s*,\s*", ",", re.sub(r"\s+", " ", line.lower()))))
    labels = {}
    for pass_ in (1, 2):
        pc = org
        out = bytearray()
        for kind, text in lines:
            if kind == "label":
                if pass_ == 1:
                    labels[text.lower()] = pc
                continue
            if text.startswith("org "):
                target = _num(text[4:], labels)
                assert target >= pc, f"org {target:03X} is behind current address {pc:03X}"
                out += b"\xFF" * (target - pc)
                pc = target
                continue
            if text.startswith("db "):
                for tok in text[3:].split(","):
                    tok = tok.strip()
                    if tok.startswith("'") and tok.endswith("'"):
                        out += tok[1:-1].encode("ascii"); pc += len(tok) - 2
                        continue
                    out.append(_num(tok, labels) & 0xFF if pass_ == 2 else 0)
                    pc += 1
                continue
            for rx, code, length in _PATTERNS:
                m = rx.match(text)
                if not m:
                    continue
                gd = m.groupdict()
                if "a11" in gd:
                    tgt = _num(gd["a11"], labels) if pass_ == 2 else 0
                    if (code >> 5) != (tgt >> 8):
                        continue           # wrong JMP/CALL page variant
                    out += bytes([code, tgt & 0xFF])
                elif "a8" in gd:
                    tgt = _num(gd["a8"], labels) if pass_ == 2 else (pc + 1) & 0xF00
                    if (tgt & 0xF00) != ((pc + 1) & 0xF00):
                        raise ValueError(f"{text}: target {tgt:03X} not in page of {pc:03X}")
                    out += bytes([code, tgt & 0xFF])
                elif "d" in gd:
                    v = _num(gd["d"], labels) if pass_ == 2 else 0
                    out += bytes([code, v & 0xFF])
                else:
                    out.append(code)
                pc += length
                break
            else:
                if pass_ == 2 or not any(text.startswith(p) for p in ("jmp", "call")):
                    raise ValueError(f"cannot assemble: {text!r}")
                out += b"\0\0"; pc += 2   # pass 1 placeholder for jmp/call to unknown label
    return bytes(out), labels
