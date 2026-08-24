"""Fabrication audit: a call edge whose source line shows a RECEIVER call.

The receiver must be a real expression char before the dot — `x.f(`,
`)` .f(`, `].f(`. The spread operator `...f(` is NOT a receiver call, and
a substring check for ".f(" matches its final dot, which is how the first
version of this audit reported 231 phantom fabrications on a real repo.
"""
import re, sqlite3, pathlib, sys, collections

db, root = sys.argv[1], pathlib.Path(sys.argv[2])
c = sqlite3.connect(db); c.row_factory = sqlite3.Row
rows = c.execute("""SELECT b.qualname dst, e.line, fa.path spath FROM edges e
  JOIN symbols a ON a.id=e.src JOIN symbols b ON b.id=e.dst
  JOIN files fa ON fa.id=a.file_id WHERE e.kind='calls'""").fetchall()
cache = {}
def src(p):
    if p not in cache:
        try: cache[p] = (root/p).read_text(errors="ignore").splitlines()
        except Exception: cache[p] = []
    return cache[p]

fab = []
for r in rows:
    lines = src(r["spath"])
    if r["line"] - 1 >= len(lines): continue
    line = lines[r["line"] - 1]
    t = re.escape(r["dst"].rsplit(".", 1)[-1])
    # receiver char, optional whitespace, dot, name, open paren
    if re.search(rf"[\w\)\]]\s*\.\s*{t}\s*\(", line):
        # self/this receivers are legitimately resolved
        if re.search(rf"(?:self|this)\s*\.\s*{t}\s*\(", line): continue
        fab.append((r["spath"], r["line"], r["dst"], line.strip()[:78]))
print(f"call edges: {len(rows)} | receiver-style fabricated: {len(fab)}")
for f in fab[:10]: print("   ", f[0], f[1], "->", f[2], "|", f[3])
