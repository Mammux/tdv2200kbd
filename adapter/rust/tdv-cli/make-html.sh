#!/bin/sh
# Render tdv.1 as a standalone HTML page (tdv.1.html). Needs mandoc
# (macOS: built in as /usr/bin/mandoc; Debian/Ubuntu: apt install mandoc).
set -e
cd "$(dirname "$0")"
{
cat <<'HEAD'
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>tdv(1) — configure the TDV 2200 keyboard USB adapter</title>
<style>
:root { color-scheme: light dark; --fg:#1d1d1f; --bg:#fbfaf7; --muted:#6b6b6b;
        --rule:#dedbd2; --accent:#9a3412; --code-bg:#f1eee6; }
@media (prefers-color-scheme: dark) {
  :root { --fg:#e8e6e1; --bg:#1a1918; --muted:#9b978f; --rule:#3a3835;
          --accent:#f0a46b; --code-bg:#262422; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg);
       font: 16px/1.55 ui-sans-serif, -apple-system, "Segoe UI", sans-serif; }
.page { max-width: 52rem; margin: 0 auto; padding: 2rem 1.25rem 4rem; }
code, pre, var { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: .93em; }
table.head, table.foot { width:100%; border-collapse:collapse; color:var(--muted);
       font: 13px ui-monospace, Menlo, monospace; }
table.head { border-bottom:1px solid var(--rule); margin-bottom:1rem; }
table.foot { border-top:1px solid var(--rule); margin-top:3rem; }
table.head td, table.foot td { padding:.4rem 0; }
.head-vol { text-align:center; } .head-rtitle, .foot-os { text-align:right; }
h1.Sh { font-size: .95rem; letter-spacing:.08em; text-transform:uppercase;
        color:var(--accent); margin:2.4rem 0 .6rem; padding-bottom:.25rem;
        border-bottom:1px solid var(--rule); }
h2.Ss { font-size: 1.05rem; margin:1.6rem 0 .4rem; }
a.permalink { color:inherit; text-decoration:none; }
section.Sh > p, section.Sh > div, section.Sh > dl, section.Ss > p,
section.Ss > dl, section.Ss > div { margin-left: 1.5rem; }
p.Pp, div.Pp { margin: .8rem 0; }
.Nm, .Cm, .Fl { font-weight: 600; }
code.Nm, code.Cm, code.Fl, code.Li, code.Ev { color: inherit; }
var.Ar { font-style: italic; }
table.Nm { border-collapse: collapse; margin: .1rem 0 .1rem 1.5rem; }
table.Nm td { padding: .1rem 0; vertical-align: top; }
table.Nm td:first-child { padding-right: .6em; white-space: nowrap; }
section.Sh > table.Nm + br { display: none; }
section.Sh > p.Pp:empty { margin: .4rem 0; }
code.Li { background: var(--code-bg); padding: .05em .3em; border-radius: 3px; }
pre code.Li { background: none; padding: 0; }
.Pa { font-style: italic; }
pre { background: var(--code-bg); padding: .75rem 1rem; border-radius: 6px;
      overflow-x:auto; line-height:1.45; margin:.8rem 0; }
div.Bd-indent { margin-left: 1.5rem; }
dl.Bl-tag { display:grid; grid-template-columns: max-content 1fr; gap:.35rem 1.25rem; margin:.8rem 0; }
dl.Bl-tag > dt { grid-column:1; }
dl.Bl-tag > dd { grid-column:2; margin:0; }
dl.Bl-tag > dd > p:first-child, dl.Bl-tag > dd > dl:first-child { margin-top:0; }
@media (max-width: 40rem) {
  dl.Bl-tag { display:block; }
  dl.Bl-tag > dd { margin: .15rem 0 .8rem 1.25rem; }
  section.Sh > p, section.Sh > div, section.Sh > dl, section.Ss > p,
  section.Ss > dl, section.Ss > div { margin-left: 0; }
}
a { color: var(--accent); }
</style>
</head>
<body>
<div class="page">
HEAD
mandoc -T html -O fragment tdv.1 | sed -e 's/&#x2018;<code class="Li">/<code class="Li">/g' -e 's|</code>&#x2019;|</code>|g'
printf '</div>\n</body>\n</html>\n'
} > tdv.1.html
echo "wrote $(pwd)/tdv.1.html"
