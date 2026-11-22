"""Generate the KiCad project for the TDV 2200 keyboard USB adapter.

Writes into ../ (the pcb folder):
  tdv2200-adapter.kicad_pro / .kicad_sch   project and schematic
  tdv2200.kicad_sym                       project symbols (Pico, MAX3490)
  tdv2200.pretty/                         project footprints (Pico, polyfuse)
  sym-lib-table, fp-lib-table

Symbols for C, polyfuse, DE-9, mounting hole and PWR_FLAG are copied from the
standard KiCad libraries (/usr/share/kicad/symbols) into the schematic.
"""
import copy
import json
import os
import uuid as uuidlib

from sexp import Sym, dump, find, find_all, parse

KILIB = "/usr/share/kicad/symbols/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PROJECT = "tdv2200-adapter"
NS = uuidlib.UUID("6b1d2c4e-2200-4c0d-9e11-0000000000aa")


def uid(*parts):
    """Deterministic UUIDs so re-running gives identical files."""
    return str(uuidlib.uuid5(NS, "/".join(map(str, parts))))


S = Sym
FONT = [S("effects"), [S("font"), [S("size"), 1.27, 1.27]]]
HIDE = [S("effects"), [S("font"), [S("size"), 1.27, 1.27]], S("hide")]


# ----------------------------------------------------------------- symbols
def load_lib(lib):
    return parse(open(KILIB + lib + ".kicad_sym").read())[0]


def lib_symbol(lib, name):
    root = load_lib(lib)
    syms = {s[1]: s for s in find_all(root, "symbol")}
    s = copy.deepcopy(syms[name])
    ext = find(s, "extends")
    if ext:                                   # flatten "extends"
        parent = copy.deepcopy(syms[ext[1]])
        props = {p[1]: p for p in find_all(s, "property")}
        flat = [S("symbol"), name]
        for x in parent[2:]:
            if isinstance(x, list) and x[0] == "property" and x[1] in props:
                flat.append(props.pop(x[1]))
            elif isinstance(x, list) and x[0] == "symbol":
                x[1] = name + x[1][len(ext[1]):]
                flat.append(x)
            else:
                flat.append(x)
        flat[2:2] = list(props.values())
        s = flat
    return s


def pin(num, name, ptype, x, y, angle, length=2.54):
    return [S("pin"), S(ptype), S("line"), [S("at"), x, y, angle], [S("length"), length],
            [S("name"), name, FONT], [S("number"), str(num), FONT]]


PICO_PINS = {
    1: "GP0", 2: "GP1", 3: "GND", 4: "GP2", 5: "GP3", 6: "GP4", 7: "GP5", 8: "GND",
    9: "GP6", 10: "GP7", 11: "GP8", 12: "GP9", 13: "GND", 14: "GP10", 15: "GP11",
    16: "GP12", 17: "GP13", 18: "GND", 19: "GP14", 20: "GP15", 21: "GP16", 22: "GP17",
    23: "GND", 24: "GP18", 25: "GP19", 26: "GP20", 27: "GP21", 28: "GND", 29: "GP22",
    30: "RUN", 31: "GP26_A0", 32: "GP27_A1", 33: "AGND", 34: "GP28_A2", 35: "ADC_VREF",
    36: "3V3_OUT", 37: "3V3_EN", 38: "GND", 39: "VSYS", 40: "VBUS",
}


def pico_type(name):
    if name in ("GND", "AGND"):
        return "power_in"
    if name in ("VBUS", "3V3_OUT"):
        return "power_out"
    if name in ("VSYS", "ADC_VREF"):
        return "power_in"
    if name in ("RUN", "3V3_EN"):
        return "input"
    return "bidirectional"


def pico_symbol():
    pins = []
    for n, name in PICO_PINS.items():
        if n <= 20:
            pins.append(pin(n, name, pico_type(name), -17.78, 24.13 - (n - 1) * 2.54, 0, 5.08))
        else:
            pins.append(pin(n, name, pico_type(name), 17.78, 24.13 - (40 - n) * 2.54, 180, 5.08))
    return [S("symbol"), "RaspberryPi_Pico", [S("in_bom"), S("yes")], [S("on_board"), S("yes")],
            [S("property"), "Reference", "U", [S("at"), 0, 29.21, 0], FONT],
            [S("property"), "Value", "RaspberryPi_Pico", [S("at"), 0, -29.21, 0], FONT],
            [S("property"), "Footprint", "tdv2200:RaspberryPi_Pico_TH", [S("at"), 0, -31.75, 0], HIDE],
            [S("property"), "Datasheet", "https://datasheets.raspberrypi.com/pico/pico-datasheet.pdf",
             [S("at"), 0, -34.29, 0], HIDE],
            [S("property"), "ki_description", "Raspberry Pi Pico (RP2040), through-hole or header sockets",
             [S("at"), 0, 0, 0], HIDE],
            [S("symbol"), "RaspberryPi_Pico_0_1",
             [S("rectangle"), [S("start"), -12.7, 26.67], [S("end"), 12.7, -26.67],
              [S("stroke"), [S("width"), 0.254], [S("type"), S("default")]],
              [S("fill"), [S("type"), S("background")]]],
             [S("text"), "USB", [S("at"), 0, 24.13, 0], FONT]],
            [S("symbol"), "RaspberryPi_Pico_1_1", *pins]]


def symbol_pins(sym):
    out = {}
    def walk(n):
        for x in n:
            if isinstance(x, list) and x:
                if x[0] == "pin":
                    at = find(x, "at")
                    out[find(x, "number")[1]] = (float(at[1]), float(at[2]), float(at[3]))
                else:
                    walk(x)
    walk(sym)
    return out


# ----------------------------------------------------------------- schematic
class Sheet:
    def __init__(self):
        self.root_uuid = uid("root")
        self.items = []
        self.libs = {}
        self.wired = set()

    def add_lib(self, lib_id, sym):
        s = copy.deepcopy(sym)
        s[1] = lib_id
        self.libs[lib_id] = s

    def place(self, lib_id, ref, value, x, y, footprint, unit_pins=True, fields=None):
        sym = self.libs[lib_id]
        pins = symbol_pins(sym)
        libprops = {p[1]: p for p in find_all(sym, "property")}

        def prop(name, val, default_effects):
            lp = libprops.get(name)
            if lp is None:
                return [S("property"), name, val, [S("at"), x, y, 0], default_effects]
            at = find(lp, "at")
            eff = copy.deepcopy(find(lp, "effects")) or default_effects
            return [S("property"), name, val,
                    [S("at"), round(x + float(at[1]), 3), round(y - float(at[2]), 3), float(at[3])], eff]

        ref_prop = prop("Reference", ref, FONT)
        if ref.startswith("#"):
            ref_prop[4] = HIDE
        props = [
            ref_prop,
            prop("Value", value, FONT),
            [S("property"), "Footprint", footprint, [S("at"), x, y, 0], HIDE],
            [S("property"), "Datasheet", "", [S("at"), x, y, 0], HIDE],
        ]
        for k, v in (fields or {}).items():
            props.append([S("property"), k, v, [S("at"), x, y, 0], HIDE])
        inst = [S("symbol"), [S("lib_id"), lib_id], [S("at"), x, y, 0], [S("unit"), 1],
                [S("in_bom"), S("yes")], [S("on_board"), S("yes")], [S("dnp"), S("no")],
                [S("uuid"), uid("sym", ref)], *props]
        inst += [[S("pin"), n, [S("uuid"), uid("pin", ref, n)]] for n in pins]
        inst.append([S("instances"), [S("project"), PROJECT,
                     [S("path"), "/" + self.root_uuid, [S("reference"), ref], [S("unit"), 1]]]])
        self.items.append(inst)
        self.placed = getattr(self, "placed", {})
        self.placed[ref] = (x, y, pins)

    def pin_xy(self, ref, num):
        x, y, pins = self.placed[ref]
        px, py, ang = pins[num]
        dx, dy = {0: (-1, 0), 180: (1, 0), 270: (0, -1), 90: (0, 1)}[int(ang)]
        return round(x + px, 2), round(y - py, 2), dx, dy

    def wire(self, a, b):
        self.items.append([S("wire"), [S("pts"), [S("xy"), *a], [S("xy"), *b]],
                           [S("stroke"), [S("width"), 0], [S("type"), S("default")]],
                           [S("uuid"), uid("wire", a, b)]])

    def label(self, ref, num, net, stub=2.54):
        x, y, dx, dy = self.pin_xy(ref, num)
        end = (round(x + dx * stub, 2), round(y + dy * stub, 2))
        self.wire((x, y), end)
        angle = {(-1, 0): 180, (1, 0): 0, (0, -1): 90, (0, 1): 270}[(dx, dy)]
        just = [S("justify"), S("right" if angle == 180 else "left"), S("bottom")]
        self.items.append([S("label"), net, [S("at"), *end, angle],
                           [S("effects"), [S("font"), [S("size"), 1.27, 1.27]], just],
                           [S("uuid"), uid("label", ref, num)]])
        self.wired.add((ref, num))

    def no_connect(self, ref, num):
        x, y, _, _ = self.pin_xy(ref, num)
        self.items.append([S("no_connect"), [S("at"), x, y], [S("uuid"), uid("nc", ref, num)]])
        self.wired.add((ref, num))

    def text(self, s, x, y, size=1.27):
        self.items.append([S("text"), s, [S("at"), x, y, 0],
                           [S("effects"), [S("font"), [S("size"), size, size]], [S("justify"), S("left"), S("top")]],
                           [S("uuid"), uid("text", s[:20], x, y)]])

    def check_all_pins_handled(self):
        for ref, (_, _, pins) in self.placed.items():
            for n in pins:
                assert (ref, n) in self.wired, f"{ref} pin {n} neither connected nor marked NC"

    def dump(self):
        doc = [S("kicad_sch"), [S("version"), S("20230121")], [S("generator"), S("eeschema")],
               [S("uuid"), self.root_uuid], [S("paper"), "A4"],
               [S("title_block"), [S("title"), "TDV 2200 keyboard USB adapter"],
                [S("date"), "2026-11-11"], [S("rev"), "1"],
                [S("company"), "github.com/Mammux/tdv2200kbd"],
                [S("comment"), 1, "Raspberry Pi Pico + MAX3490 RS-422 transceiver"],
                [S("comment"), 2, "Keyboard: TRANS 2400 baud -> GP1 (UART0 RX), REC 600 baud <- GP4 (UART1 TX)"]],
               [S("lib_symbols"), *self.libs.values()], *self.items,
               [S("sheet_instances"), [S("path"), "/", [S("page"), "1"]]]]
        return dump(doc) + "\n"


def build():
    sh = Sheet()
    pico = pico_symbol()
    max3490 = lib_symbol("Interface_UART", "MAX3490xPA")
    sh.add_lib("tdv2200:RaspberryPi_Pico", pico)
    sh.add_lib("tdv2200:MAX3490xPA", max3490)
    sh.add_lib("Device:C", lib_symbol("Device", "C"))
    sh.add_lib("Device:Polyfuse", lib_symbol("Device", "Polyfuse"))
    sh.add_lib("Connector:DE9_Receptacle_MountingHoles", lib_symbol("Connector", "DE9_Receptacle_MountingHoles"))
    sh.add_lib("Mechanical:MountingHole", lib_symbol("Mechanical", "MountingHole"))
    sh.add_lib("power:PWR_FLAG", lib_symbol("power", "PWR_FLAG"))

    sh.place("tdv2200:RaspberryPi_Pico", "U1", "RaspberryPi_Pico", 66.04, 99.06,
             "tdv2200:RaspberryPi_Pico_TH")
    sh.place("tdv2200:MAX3490xPA", "U2", "MAX3490xPA", 147.32, 93.98, "Package_DIP:DIP-8_W7.62mm",
             fields={"Note": "3.3 V full-duplex RS-422; MAX3490ECPA+ or similar"})
    sh.place("Device:C", "C1", "100nF", 175.26, 66.04,
             "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm",
             fields={"MPN": "Vishay K104K15X7RF5TL2", "Note": "Place next to U2 pins 1 and 4"})
    sh.place("Device:Polyfuse", "F1", "Wire link", 147.32, 139.7,
             "tdv2200:Fuse_Littelfuse_60R_P5.10mm",
             fields={"Note": "Fit a wire link. A 500 mA PTC (60R050XPR) dropped the keyboard supply "
                             "to 4.25 V and held it in reset. If a fuse is wanted, use 1.1 A hold or more."})
    sh.place("Connector:DE9_Receptacle_MountingHoles", "J1", "Keyboard", 228.6, 96.52,
             "Connector_Dsub:DSUB-9_Female_Horizontal_P2.77x2.84mm_EdgePinOffset9.90mm_Housed_MountingHolesOffset11.32mm",
             fields={"Note": "Female DE-9: mates with the keyboard's plug. Match footprint to the part bought."})
    sh.place("power:PWR_FLAG", "#FLG01", "PWR_FLAG", 175.26, 157.48, "")
    for i, (x, y) in enumerate([(40.64, 160.02), (55.88, 160.02), (71.12, 160.02), (86.36, 160.02)], 1):
        sh.place("Mechanical:MountingHole", f"H{i}", "MountingHole", x, y, "MountingHole:MountingHole_3.2mm_M3")

    # Pico
    for n, name in PICO_PINS.items():
        if name in ("GND", "AGND"):
            sh.label("U1", str(n), "GND")
    sh.label("U1", "2", "KBD_RX")          # GP1, UART0 RX, 2400 baud from keyboard
    sh.label("U1", "6", "KBD_TX")          # GP4, UART1 TX, 600 baud to keyboard
    sh.label("U1", "36", "+3V3")
    sh.label("U1", "40", "VBUS")
    for n in PICO_PINS:
        if ("U1", str(n)) not in sh.wired:
            sh.no_connect("U1", str(n))

    # MAX3490
    sh.label("U2", "1", "+3V3")
    sh.label("U2", "4", "GND")
    sh.label("U2", "2", "KBD_RX")
    sh.label("U2", "3", "KBD_TX")
    sh.label("U2", "8", "TRANS+")
    sh.label("U2", "7", "TRANS-")
    sh.label("U2", "5", "REC+")
    sh.label("U2", "6", "REC-")
    sh.label("C1", "1", "+3V3", 5.08)
    sh.label("C1", "2", "GND", 5.08)

    # power to the keyboard
    sh.label("F1", "1", "VBUS", 5.08)
    sh.label("F1", "2", "KBD_5V", 5.08)
    sh.label("#FLG01", "1", "GND")

    # keyboard connector
    sh.label("J1", "9", "TRANS+")
    sh.label("J1", "4", "TRANS-")
    sh.label("J1", "7", "REC+")
    sh.label("J1", "2", "REC-")
    sh.label("J1", "3", "KBD_5V")
    sh.label("J1", "6", "GND")
    sh.label("J1", "0", "GND")
    for n in ("1", "5", "8"):
        sh.no_connect("J1", n)
    sh.check_all_pins_handled()

    sh.text("Keyboard cable (as seen from the keyboard):\n"
            "  3 +5V red, 6 GND black\n"
            "  9 TRANS+ brown, 4 TRANS- yellow  (keyboard -> host, 2400 baud)\n"
            "  7 REC+ blue,   2 REC- white      (host -> keyboard, 600 baud)\n"
            "  1, 5, 8 not fitted in the keyboard plug",
            200.66, 124.46)
    sh.text("C1: as close as possible to U2 pins 1 and 4.\n"
            "F1: fit a wire link. A 500 mA polyfuse drops too much voltage\n"
            "(keyboard needs >= 4.75 V; it is held in reset below ~4.65 V).\n"
            "No termination resistor needed at 2400 baud.", 120.65, 152.4)
    return sh, pico, max3490


# ----------------------------------------------------------------- footprints
def fp_pico():
    """Raspberry Pi Pico on two 1x20 rows, 17.78 mm apart (pins or header sockets)."""
    pads = []
    for n in range(1, 41):
        x, y = (0, (n - 1) * 2.54) if n <= 20 else (17.78, (40 - n) * 2.54)
        shape = "rect" if n == 1 else "oval"
        pads.append(f'  (pad "{n}" thru_hole {shape} (at {x:.2f} {y:.2f}) (size 1.7 1.7) (drill 1.02) '
                    f'(layers "*.Cu" "*.Mask") (tstamp {uid("pico-pad", n)}))')
    x0, y0, x1, y1 = -1.61, -1.37, 19.39, 49.63      # 21 x 51 mm board, pin 1 at origin
    def rect(layer, w, a, b, c, d, tag):
        return (f'  (fp_rect (start {a:.2f} {b:.2f}) (end {c:.2f} {d:.2f}) (stroke (width {w}) (type solid)) '
                f'(fill none) (layer "{layer}") (tstamp {uid("pico-rect", tag)}))')
    return f"""(footprint "RaspberryPi_Pico_TH" (version 20221018) (generator pcbnew)
  (layer "F.Cu")
  (descr "Raspberry Pi Pico, 2x20 pins 17.78 mm apart, pin 1 at origin, USB at the top. Solder directly or use 1x20 header sockets.")
  (tags "RP2040 Pico")
  (attr through_hole)
  (fp_text reference "REF**" (at 8.89 -3.2) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))) (tstamp {uid("pico-ref")}))
  (fp_text value "RaspberryPi_Pico_TH" (at 8.89 51.5) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))) (tstamp {uid("pico-val")}))
  (fp_text user "USB" (at 8.89 1.5) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))) (tstamp {uid("pico-usb")}))
{rect("F.SilkS", 0.12, x0 - 0.11, y0 - 0.11, x1 + 0.11, y1 + 0.11, "silk")}
{rect("F.Fab", 0.1, x0, y0, x1, y1, "fab")}
{rect("F.Fab", 0.1, 5.39, y0 - 1.3, 13.39, y0 + 4.0, "usb")}
{rect("F.CrtYd", 0.05, x0 - 0.5, y0 - 1.8, x1 + 0.5, y1 + 0.5, "crt")}
""" + "\n".join(pads) + "\n)\n"


def fp_fuse():
    """Littelfuse 60R radial PTC: lead spacing 5.1 mm, body up to 7.4 x 3.0 mm."""
    return f"""(footprint "Fuse_Littelfuse_60R_P5.10mm" (version 20221018) (generator pcbnew)
  (layer "F.Cu")
  (descr "Littelfuse 60R series radial PTC (e.g. 60R050XPR), lead spacing 5.1 mm. Check against the datasheet of the part used.")
  (tags "PTC polyfuse radial")
  (attr through_hole)
  (fp_text reference "REF**" (at 2.55 -2.6) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))) (tstamp {uid("f-ref")}))
  (fp_text value "Fuse_Littelfuse_60R_P5.10mm" (at 2.55 2.6) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))) (tstamp {uid("f-val")}))
  (fp_rect (start -1.15 -1.5) (end 6.25 1.5) (stroke (width 0.1) (type solid)) (fill none) (layer "F.Fab") (tstamp {uid("f-fab")}))
  (fp_rect (start -1.27 -1.62) (end 6.37 1.62) (stroke (width 0.12) (type solid)) (fill none) (layer "F.SilkS") (tstamp {uid("f-silk")}))
  (fp_rect (start -1.65 -2.0) (end 6.75 2.0) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd") (tstamp {uid("f-crt")}))
  (pad "1" thru_hole circle (at 0 0) (size 1.6 1.6) (drill 0.8) (layers "*.Cu" "*.Mask") (tstamp {uid("f-p1")}))
  (pad "2" thru_hole circle (at 5.1 0) (size 1.6 1.6) (drill 0.8) (layers "*.Cu" "*.Mask") (tstamp {uid("f-p2")}))
)
"""


def write(path, text):
    with open(os.path.join(OUT, path), "w") as f:
        f.write(text)


def main():
    sh, pico, max3490 = build()
    write(PROJECT + ".kicad_sch", sh.dump())

    lib = [S("kicad_symbol_lib"), [S("version"), S("20220914")], [S("generator"), S("kicad_symbol_editor")]]
    for s in (pico, max3490):
        lib.append(copy.deepcopy(s))
    write("tdv2200.kicad_sym", dump(lib) + "\n")

    os.makedirs(os.path.join(OUT, "tdv2200.pretty"), exist_ok=True)
    write("tdv2200.pretty/RaspberryPi_Pico_TH.kicad_mod", fp_pico())
    write("tdv2200.pretty/Fuse_Littelfuse_60R_P5.10mm.kicad_mod", fp_fuse())

    write("sym-lib-table", '(sym_lib_table\n  (lib (name "tdv2200")(type "KiCad")(uri "${KIPRJMOD}/tdv2200.kicad_sym")(options "")(descr "TDV 2200 adapter symbols"))\n)\n')
    write("fp-lib-table", '(fp_lib_table\n  (lib (name "tdv2200")(type "KiCad")(uri "${KIPRJMOD}/tdv2200.pretty")(options "")(descr "TDV 2200 adapter footprints"))\n)\n')
    write(PROJECT + ".kicad_pro", json.dumps({
        "meta": {"filename": PROJECT + ".kicad_pro", "version": 1},
        "sheets": [[sh.root_uuid, ""]],
        "boards": [],
        "text_variables": {},
    }, indent=2) + "\n")
    print("written to", os.path.normpath(OUT))


if __name__ == "__main__":
    main()
