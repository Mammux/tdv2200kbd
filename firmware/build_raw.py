"""Assemble the raw-only firmware into a 2 KB image."""
from asm48 import assemble

code, labels = assemble(open("tdv2200-raw.asm").read(), 0)
assert labels["timerint"] == 0x007, "timer interrupt must be at 007h"
assert len(code) <= 0x800

# JMPP and MOVP only reach their own page: check tables and jump targets
page = lambda a: a >> 8
jmpp_at = labels["cmdtbl"] - 1
assert page(jmpp_at) == page(labels["cmdtbl"]) == page(labels["cmdtbl"] + 21)
for b in code[labels["cmdtbl"]:labels["cmdtbl"] + 22]:
    assert any(v == (page(jmpp_at) << 8 | b) for v in labels.values()), f"bad table entry {b:02X}"
movp_at = labels["ledtbl"] - 2
assert code[movp_at] == 0xA3 and page(movp_at + 1) == page(labels["ledtbl"]) == page(labels["ledtbl"] + 7)

image = code + b"\xFF" * (0x800 - len(code))
open("tdv2200-raw.bin", "wb").write(image)
print(f"tdv2200-raw.bin: code ends at {len(code):03X}h, rest of the 2 KB is FFh")
