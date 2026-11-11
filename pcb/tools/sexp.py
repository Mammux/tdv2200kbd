"""Minimal S-expression reader/writer for KiCad files."""
import re

_TOKEN = re.compile(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()"]+')


class Sym(str):
    """Bare (unquoted) atom."""


def parse(text):
    stack, cur = [], []
    for m in _TOKEN.finditer(text):
        t = m.group(0)
        if t == "(":
            stack.append(cur); cur = []
        elif t == ")":
            done = cur; cur = stack.pop(); cur.append(done)
        elif t.startswith('"'):
            cur.append(t[1:-1].replace('\\"', '"').replace("\\\\", "\\"))
        else:
            cur.append(Sym(t))
    assert not stack
    return cur


def dump(node, indent=0):
    if not isinstance(node, list):
        if isinstance(node, Sym):
            return str(node)
        if isinstance(node, (int, float)):
            return _num(node)
        return '"' + str(node).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    simple = all(not isinstance(x, list) for x in node)
    if simple or len(node) <= 2 and not any(isinstance(x, list) and len(x) > 4 for x in node):
        return "(" + " ".join(dump(x, indent) for x in node) + ")"
    out = "("
    for i, x in enumerate(node):          # keep the original order of children
        if isinstance(x, list):
            out += "\n" + "  " * (indent + 1) + dump(x, indent + 1)
        else:
            out += ("" if i == 0 else " ") + dump(x, indent)
    return out + "\n" + "  " * indent + ")"


def _num(v):
    if isinstance(v, int):
        return str(v)
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def find(node, key):
    """First child list whose head is key."""
    for x in node:
        if isinstance(x, list) and x and x[0] == key:
            return x
    return None


def find_all(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]
