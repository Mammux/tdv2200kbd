"""Generate adapter/usb/keymap.py from firmware/keymap.csv.

Keys are mapped by their position on the keyboard (ISO 9995 grid names such
as C10 or E11, as used in the layout document) to the USB HID key at the same
place on a standard ISO keyboard. With the computer set to a Norwegian
layout, the main block then types what the keycaps show (Æ Ø Å, + ?, ' * ...).

The terminal-specific keys (P1-P8, NOTIS keys, cursor block) get the nearest
standard key, or F13-F24 so they can be bound to anything. Edit POS_HID below
and re-run this script, or edit keymap.py on the Pico directly.

    python3 adapter/tools/make_keymap.py
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")

# --- HID usage IDs (USB HID Usage Tables, keyboard page) -------------------
LETTER = {c: 0x04 + i for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")}
DIGIT = {str(d): 0x1E + (d - 1) % 10 for d in range(1, 11)}   # "1".."9" -> 1E-26, "10"(0) -> 27
F = {n: (0x3A + n - 1) if n <= 12 else (0x68 + n - 13) for n in range(1, 25)}

POS_HID = {
    # --- main block, ISO positions -------------------------------------
    **{f"E{i}": 0x1E + i - 1 for i in range(1, 11)},           # 1 ... 0
    "E11": 0x2D,  # + ?            (US: - _)
    "E12": 0x2E,  # @ `            (US: = +; Norwegian: \ `)
    "E13": F[23],  # NewParagraph
    "E14": 0x2A,  # Del            -> Backspace
    **{f"D{i}": LETTER[c] for i, c in enumerate("QWERTYUIOP", 1)},
    "D11": 0x2F,  # Å              (US: [ {)
    "D12": 0x30,  # ^ ~            (US: ] })
    "D13": F[24],  # LineFeed
    **{f"C{i}": LETTER[c] for i, c in enumerate("ASDFGHJKL", 1)},
    "C10": 0x33,  # Ø              (US: ; :)
    "C11": 0x34,  # Æ              (US: ' ")
    "C12": 0x32,  # ' *            (ISO key next to Return)
    "C13": 0x28,  # CartridgeReturn -> Return
    "B0": 0x64,   # < >            (ISO key next to left Shift)
    **{f"B{i}": LETTER[c] for i, c in enumerate("ZXCVBNM", 1)},
    "B8": 0x36,   # , ;
    "B9": 0x37,   # . :
    "B10": 0x38,  # - _
    "A5": 0x2C,   # Space
    "C99": 0xE2,  # Squiggle (far left)   -> Left Alt / Option
    "D99": 0xE3,  # EKSP INNS (far left)  -> Left GUI / Command / Windows
    # --- top row --------------------------------------------------------
    "G0": 0x29,   # ESC
    "G1": F[9], "G2": F[10], "G3": F[11], "G4": F[12],          # P1-P4 -> F9-F12
    "G5": F[13], "G6": F[14], "G7": F[15], "G8": F[16],         # P5-P8 -> F13-F16
    "G9": F[17], "G10": F[18], "G11": F[19], "G12": F[20],     # MERK FELT AVSN SETN
    "G13": F[21], "G14": F[22],                                  # ORD LOKAL
    # --- editing block (columns 47-49) ---------------------------------
    "G47": 0x4C,  # STRYK          -> Delete (forward)
    "G48": 0x7C,  # KOPI           -> Copy
    "G49": 0x7B,  # FLYTT          -> Cut
    "F47": 0x2B,  # TAB+ TAB-      -> Tab
    "D47": 0x4B,  # RollUp         -> Page Up
    "D48": 0x7A,  # ANGRE          -> Undo
    "D49": 0x4E,  # RollDown       -> Page Down
    "C47": 0x4A,  # FieldLeft      -> Home
    "C48": 0x52,  # Up
    "C49": 0x4D,  # FieldRight     -> End
    "B47": 0x50,  # Left
    "B48": 0x4A,  # Home
    "B49": 0x4F,  # Right
    "A48": 0x51,  # Down
    "A49": 0x2B,  # TABRight       -> Tab
    # --- right block: function keys and keypad --------------------------
    "F51": F[1], "F52": F[2], "F53": F[3], "F54": F[4],
    "E51": F[5], "E52": F[6], "E53": F[7], "E54": F[8],
    "D51": 0x5F, "D52": 0x60, "D53": 0x61, "D54": 0x57,         # 7 8 9, SP -> Keypad +
    "C51": 0x5C, "C52": 0x5D, "C53": 0x5E, "C54": 0x56,         # 4 5 6, -
    "B51": 0x59, "B52": 0x5A, "B53": 0x5B, "B54": 0x58,         # 1 2 3, ENTER
    "A51": 0x62, "A53": 0x63,                                    # 0 .
    "G51": 0x76,  # FUNK           -> Menu
    "G52": 0x46,  # SKRIV          -> Print Screen
    "G53": 0x75,  # HJELP          -> Help
    "G54": 0x48,  # SLUTT          -> Pause/Break
    # Not mapped (send nothing; shown in the console): A47 TABLeft, E47 << >>,
    # E48 JUST, E49 <> ><, F48 (... ...), F49 /aaa aaa and the blank keys in
    # column 50 (A50-G50).
}

# Special column bits -> HID usage. Bits 0 (ST1), 5 (AL1) and 6 (AL2) are not
# keys; bit 7 (SLUTT) duplicates matrix key G54, so it is left out here.
MODIFIERS = {
    1: (0x39, "CAPS  (E0)  -> Caps Lock"),
    2: (0xE0, "CTRL  (D0)  -> Left Control"),
    3: (0xE6, "LOCK  (C0)  -> Right Alt (AltGr; Option on a Mac)"),
    4: (0xE1, "SHIFT (B99, B11) -> Left Shift"),
}


def main():
    rows = list(csv.DictReader(open(os.path.join(ROOT, "firmware", "keymap.csv"), encoding="utf-8")))
    lines = []
    unmapped = []
    for r in sorted(rows, key=lambda r: int(r["press"], 16)):
        k = int(r["press"], 16)
        pos = r["position"]
        legend = {"C10": "Ø", "C11": "Æ", "D11": "Å"}.get(pos, r["legend"])
        code = POS_HID.get(pos, 0)
        if not code:
            unmapped.append(pos)
        lines.append(f"    0x{k:02X}: 0x{code:02X},  # {pos:4s} {legend}")
    out = [
        '"""TDV 2200 key -> USB HID usage. Generated by adapter/tools/make_keymap.py.',
        "",
        "KEYS: matrix index k (the raw press code) -> HID keyboard usage, 0 = none.",
        "MODIFIERS: bit in the special-column report -> HID usage.",
        "Edit here or in make_keymap.py. Usages E0-E7 are modifiers.",
        '"""',
        "",
        "KEYS = {",
        *lines,
        "}",
        "",
        "MODIFIERS = {",
        *[f"    {bit}: 0x{code:02X},  # {desc}" for bit, (code, desc) in MODIFIERS.items()],
        "}",
        "",
    ]
    path = os.path.join(ROOT, "adapter", "usb", "keymap.py")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write("\n".join(out))
    print(f"wrote {os.path.normpath(path)}: {len(rows)} keys, {len(unmapped)} unmapped: {' '.join(unmapped)}")


if __name__ == "__main__":
    main()
