"""HTML (Confluence page) -> readable text. Keeps headings, code blocks, tables, lists and links' text."""
import html, re, sys
from html.parser import HTMLParser

class P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.depth, self.on, self.pre, self.skip = [], 0, False, 0, 0
        self.stack = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if not self.on:
            if a.get("id") == "main-content" or "wiki-content" in (a.get("class") or ""):
                self.on, self.depth = True, 1
            return
        self.depth += 1
        if tag in ("script", "style"): self.skip += 1
        if tag == "pre": self.pre += 1; self.out.append("\n```\n")
        elif tag in ("h1","h2","h3","h4","h5","h6"): self.out.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag == "tr": self.out.append("\n| ")
        elif tag in ("td","th"): self.out.append(" ")
        elif tag == "li": self.out.append("\n- ")
        elif tag in ("p","div","br","ul","ol","table","blockquote"): self.out.append("\n")
        elif tag == "code" and not self.pre: self.out.append("`")
    def handle_endtag(self, tag):
        if not self.on: return
        self.depth -= 1
        if tag in ("script", "style"): self.skip -= 1
        if tag == "pre": self.pre -= 1; self.out.append("\n```\n")
        elif tag in ("td","th"): self.out.append(" |")
        elif tag == "code" and not self.pre: self.out.append("`")
        elif tag in ("p","div","ul","ol","table","h1","h2","h3","h4","h5","h6","blockquote"): self.out.append("\n")
        if self.depth <= 0: self.on = False
    def handle_data(self, d):
        if self.on and not self.skip: self.out.append(d)

p = P(); p.feed(open(sys.argv[1], encoding="utf-8", errors="replace").read())
t = "".join(p.out)
t = re.sub(r"[ \t]+\n", "\n", t); t = re.sub(r"\n{3,}", "\n\n", t)
open(sys.argv[2], "w", encoding="utf-8").write(t)
print("text chars:", len(t), "| lines:", t.count("\n"))
