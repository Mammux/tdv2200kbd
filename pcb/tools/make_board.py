"""Create a starting PCB: every footprint from the schematic, nets assigned,
parts roughly placed, board outline and mounting holes. No tracks: routing is
left to you. Needs KiCad's Python module (pcbnew) and the netlist exported
from the schematic:

    kicad-cli sch export netlist -o /tmp/adapter.net tdv2200-adapter.kicad_sch
    python3 tools/make_board.py /tmp/adapter.net
"""
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
from sexp import find, find_all, parse  # noqa: E402

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
KIFP = "/usr/share/kicad/footprints/"
mm = pcbnew.FromMM

# board outline (mm) and placement: Pico at the top edge so its USB socket
# is reachable, DE-9 on the right edge with its face over the edge
X0, Y0, X1, Y1 = 100.0, 100.0, 166.0, 160.0
PLACE = {             # ref: (x, y, rotation in degrees)
    "U1": (112.0, 101.37, 0),     # pin 1; Pico outline is flush with the top edge
    "U2": (140.0, 112.0, 0),      # MAX3490, pin 1
    "C1": (140.0, 106.5, 0),      # across U2 pins 1 (VCC) and 4 (GND) side
    "F1": (137.5, 150.0, 0),
    "J1": (153.26, 127.0, 90),    # pins 1-5 row, face pointing right
    "H1": (104.0, 104.0, 0), "H2": (162.0, 104.0, 0),
    "H3": (104.0, 156.0, 0), "H4": (162.0, 156.0, 0),
}


def load_fp(fpid):
    lib, name = fpid.split(":")
    path = os.path.join(HERE, "tdv2200.pretty") if lib == "tdv2200" else KIFP + lib + ".pretty"
    fp = pcbnew.FootprintLoad(path, name)
    assert fp is not None, f"footprint {fpid} not found"
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def main(netfile):
    net = parse(open(netfile).read())[0]
    board = pcbnew.BOARD()
    nets = {}
    pad_net = {}
    for n in find_all(find(net, "nets"), "net"):
        name = find(n, "name")[1]
        if name.startswith("unconnected"):
            continue
        name = name.lstrip("/")
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        nets[name] = ni
        for node in find_all(n, "node"):
            pad_net[(find(node, "ref")[1], find(node, "pin")[1])] = ni

    for c in find_all(find(net, "components"), "comp"):
        ref = find(c, "ref")[1]
        fpid = find(c, "footprint")
        if not fpid or not fpid[1]:
            continue
        fp = load_fp(fpid[1])
        fp.SetReference(ref)
        fp.SetValue(find(c, "value")[1])
        x, y, rot = PLACE[ref]
        fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        fp.SetOrientationDegrees(rot)
        board.Add(fp)
        for pad in fp.Pads():
            ni = pad_net.get((ref, pad.GetNumber()))
            if ni:
                pad.SetNet(ni)

    pts = [(X0, Y0), (X1, Y0), (X1, Y1), (X0, Y1)]
    for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(pcbnew.VECTOR2I(mm(ax), mm(ay)))
        seg.SetEnd(pcbnew.VECTOR2I(mm(bx), mm(by)))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(mm(0.1))
        board.Add(seg)

    txt = pcbnew.PCB_TEXT(board)
    txt.SetText("TDV 2200 USB adapter\ngithub.com/Mammux/tdv2200kbd")
    txt.SetPosition(pcbnew.VECTOR2I(mm(128), mm(156)))
    txt.SetLayer(pcbnew.F_SilkS)
    txt.SetTextSize(pcbnew.VECTOR2I(mm(1.0), mm(1.0)))
    board.Add(txt)

    out = os.path.join(HERE, "tdv2200-adapter.kicad_pcb")
    board.Save(out)
    print("written", os.path.normpath(out))
    # report anything that pokes outside the board (DE-9 face is meant to)
    for fp in board.GetFootprints():
        bb = fp.GetBoundingBox(False, False)
        l, t, r, b = (pcbnew.ToMM(v) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()))
        flag = "" if l >= X0 and t >= Y0 - 2 and r <= X1 and b <= Y1 else "  <- outside board"
        print(f"  {fp.GetReference():3s} {l:7.2f} {t:7.2f} {r:7.2f} {b:7.2f}{flag}")


if __name__ == "__main__":
    main(sys.argv[1])
