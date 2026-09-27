"""
Documentation tools (no Blender connection needed).

  get_python_api_docs IDENTIFIER     exact / namespace / definition / partial / suggestions / missing
  search_api_docs QUERY              full-text search of the bundled Python API reference
  search_manual_docs QUERY           full-text search of the bundled user manual

They read the RST corpus the official MCP server ships in ``blmcp/data/{api,manual}``.
Locating it, in order: ``--data-dir``, env ``BLMCP_DATA_DIR``, an installed ``blmcp`` package,
the Claude Desktop extension folder (incl. the MSIX-virtualised AppData), or ``./data``.
To get it yourself: ``git clone https://projects.blender.org/lab/blender_mcp`` and point
``BLMCP_DATA_DIR`` at ``mcp/blmcp/data``.

Search semantics follow the official tool: whitespace-tokenised, case-insensitive, stop-words
dropped, every token must appear in the paragraph, its section/definition breadcrumb, or the path;
hits are ranked; ``--context N`` adds N paragraphs each side; ``--index I`` returns hit I alone widened
to its enclosing section. The ranking itself is a reimplementation, so scores differ from the official one.
Derived from Blender Lab's blender_mcp (GPL-3.0-or-later).
"""
import glob
import math
import os
import re
import sys
import textwrap

from .cli import Tool, main

_data_dir_override = None
_SUMMARY_THRESHOLD = 32 * 1024


def data_dir():
    """Return the docs ``data`` directory (containing ``api/`` and ``manual/``) or raise."""
    cands = []
    if _data_dir_override:
        cands.append(_data_dir_override)
    if os.environ.get("BLMCP_DATA_DIR"):
        cands.append(os.environ["BLMCP_DATA_DIR"])
    try:
        import blmcp  # the official package, if pip-installed
        cands.append(os.path.join(os.path.dirname(blmcp.__file__), "data"))
    except ImportError:
        pass
    for base in (os.path.expandvars(r"%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\Claude Extensions"),
                 os.path.expandvars(r"%APPDATA%\Claude\Claude Extensions"),
                 os.path.expanduser("~/Library/Application Support/Claude/Claude Extensions"),
                 os.path.expanduser("~/.config/Claude/Claude Extensions")):
        cands += glob.glob(os.path.join(base, "*blender*", "blmcp", "data"))
    cands.append(os.path.join(os.getcwd(), "data"))
    for c in cands:
        if os.path.isdir(os.path.join(c, "api")):
            return c
    raise RuntimeError("Blender docs corpus not found. Use --data-dir or set BLMCP_DATA_DIR to the folder "
                       "containing api/ and manual/ (from https://projects.blender.org/lab/blender_mcp, "
                       "mcp/blmcp/data). Tried: " + "; ".join(cands))


# ---------------------------------------------------------------------------
# get_python_api_docs

_IDENT = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$")
_DEF = re.compile(r"^(\s*)\.\.\s+(class|function|method|attribute|data|classmethod|staticmethod)::\s*(.*)$")
_NAME = re.compile(r"[A-Za-z_][\w]*")


def _api_names(api):
    return [f[:-4] for f in os.listdir(api) if f.endswith(".rst")]


def _children(api, prefix):
    depth = prefix.count(".") + 1 if prefix else 0
    out = set()
    for n in _api_names(api):
        if prefix and not n.startswith(prefix + "."):
            continue
        out.add(".".join(n.split(".")[: depth + 1]))
    out.discard(prefix)
    return sorted(out)


def _definitions(lines):
    """[(qualified_name, kind, start_line, end_line, indent)] for every directive definition."""
    defs, stack = [], []
    for i, line in enumerate(lines):
        m = _DEF.match(line)
        if not m:
            continue
        indent = len(m.group(1))
        nm = _NAME.match(m.group(3))
        if not nm:
            continue
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, nm.group(0)))
        end = len(lines)
        for j in range(i + 1, len(lines)):
            if lines[j].strip() and (len(lines[j]) - len(lines[j].lstrip())) <= indent:
                end = j
                break
        defs.append((".".join(n for _, n in stack), m.group(2), i, end, indent))
    return defs


def _examples(content, api):
    out = []
    for m in re.finditer(r"\.\. literalinclude::\s*(\S+)", content):
        p = os.path.normpath(os.path.join(api, m.group(1)))
        if p.startswith(os.path.normpath(api)) and os.path.isfile(p):
            with open(p, encoding="utf-8", errors="replace") as fh:
                out.append({"path": os.path.relpath(p, api).replace("\\", "/"), "content": fh.read()[:20000]})
    return out


def _summarize(identifier, lines, size):
    out = ["[%s is %d bytes (> %d); showing a summary of its definitions. Query a member for its full text.]"
           % (identifier, size, _SUMMARY_THRESHOLD)]
    for q, kind, start, end, _ in _definitions(lines):
        desc = next((l.strip() for l in lines[start + 1:end]
                     if l.strip() and not l.strip().startswith(":") and not l.strip().startswith("..")), "")
        out.append("- %s %s%s" % (kind, q, (": " + desc[:120]) if desc else ""))
    return "\n".join(out)


def api_get(identifier):
    if identifier != "*" and not re.match(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*(\.\*)?$", identifier):
        return {"kind": "missing", "found": False, "identifier": identifier}
    api = os.path.join(data_dir(), "api")
    base = {"found": True, "identifier": identifier}

    if identifier == "*":
        return dict(base, kind="namespace", submodules=_children(api, ""))
    if identifier.endswith(".*"):
        return dict(base, kind="namespace", submodules=_children(api, identifier[:-2]))

    path = os.path.join(api, identifier + ".rst")
    if os.path.isfile(path):
        with open(path, encoding="utf-8", errors="replace") as fh:
            content = fh.read()
        if len(content) > _SUMMARY_THRESHOLD:
            return dict(base, kind="exact", content=_summarize(identifier, content.splitlines(), len(content)),
                        examples=[])
        return dict(base, kind="exact", content=content, examples=_examples(content, api))

    kids = _children(api, identifier)
    if kids:
        return dict(base, kind="namespace", submodules=kids)

    parts = identifier.split(".")
    for strip in range(1, len(parts)):
        parent, tail = ".".join(parts[:-strip]), ".".join(parts[-strip:])
        ppath = os.path.join(api, parent + ".rst")
        if not os.path.isfile(ppath):
            continue
        with open(ppath, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
        defs = _definitions(lines)
        hit = next((d for d in defs if d[0] == tail or d[0].endswith("." + tail)), None)
        if hit:
            block = textwrap.dedent("\n".join(lines[hit[2]:hit[3]])).rstrip()
            return dict(base, kind="definition", content=block, examples=_examples(block, api))
        low = tail.lower()
        near = [c for c in _children(api, parent) if set(low) <= set(c.rsplit(".", 1)[-1].lower())]
        return {"kind": "partial", "found": False, "identifier": identifier, "parent": parent,
                "available": [d[0] for d in defs if d[0].count(".") <= 1][:200], "submodules": near[:50]}

    last = parts[-1]
    sugg = sorted({n for n in _api_names(api) if last in n.split(".")})[:30]
    if sugg:
        return {"kind": "suggestions", "found": False, "identifier": identifier, "suggestions": sugg}
    return {"kind": "missing", "found": False, "identifier": identifier}


# ---------------------------------------------------------------------------
# search_*_docs

_STOP = set("a an and are as at be but by can do does for from how i if in into is it its of on or that the "
            "this to use using what when where which with you".split())
_UNDER = re.compile(r"^([=\-~+^\"'`#*:._<>])\1{1,}\s*$")


def _parse(text):
    """Split RST into paragraphs: [{start, text, crumb, sec}] where sec identifies the enclosing section."""
    lines = text.splitlines()
    n = len(lines)
    levels, headings, dstack = {}, [], []          # headings: [(level, title)]; dstack: [(indent, label)]
    paras, i = [], 0
    while i < n:
        if not lines[i].strip():
            i += 1
            continue
        # heading (title + underline, optionally overlined)
        title = None
        if i + 2 < n and _UNDER.match(lines[i]) and lines[i + 1].strip() and _UNDER.match(lines[i + 2]) \
                and lines[i + 2][0] == lines[i][0]:
            title, key, adv = lines[i + 1].strip(), ("o", lines[i][0]), 3
        elif i + 1 < n and not _UNDER.match(lines[i]) and _UNDER.match(lines[i + 1]) \
                and len(lines[i + 1].strip()) >= len(lines[i].strip()):
            title, key, adv = lines[i].strip(), ("u", lines[i + 1][0]), 2
        if title is not None:
            lvl = levels.setdefault(key, len(levels))
            while headings and headings[-1][0] >= lvl:
                headings.pop()
            headings.append((lvl, title))
            dstack.clear()
            i += adv
            continue
        j = i
        while j < n and lines[j].strip():
            j += 1
        block = lines[i:j]
        indent = len(block[0]) - len(block[0].lstrip())
        while dstack and dstack[-1][0] >= indent:
            dstack.pop()
        m = _DEF.match(block[0])
        if m:
            nm = _NAME.match(m.group(3))
            if nm:
                dstack.append((indent, "%s %s" % (m.group(2), nm.group(0))))
        crumb = [t for _, t in headings] + [lab for _, lab in dstack]
        paras.append({"start": i, "text": textwrap.dedent("\n".join(block)), "crumb": " > ".join(crumb),
                      "sec": tuple(t for _, t in headings)})
        i = j
    return paras


def _tokens(query):
    toks = [t for t in re.split(r"\s+", query.lower().strip()) if t]
    kept = [t for t in toks if t not in _STOP]
    return kept or toks


_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
_rebuild_cache = False


def _corpus(scope):
    """
    {relative path: text} for every .rst under ``<data>/<scope>``.

    Reading ~4000 small files is slow on some filesystems (tens of seconds through the MSIX-virtualised
    AppData), so the text is cached in one pickle under ``bmcp/.cache/``, keyed by the source folder and its
    mtime. Delete the folder or pass ``--rebuild-cache`` to refresh.
    """
    import hashlib
    import pickle
    root = os.path.join(data_dir(), scope)
    key = "%s|%s" % (os.path.abspath(root), os.path.getmtime(root))
    cache = os.path.join(_CACHE_DIR, "%s_%s.pkl" % (scope, hashlib.sha1(key.encode()).hexdigest()[:12]))
    if not _rebuild_cache and os.path.isfile(cache):
        try:
            with open(cache, "rb") as fh:
                return pickle.load(fh)
        except (OSError, pickle.PickleError, EOFError):
            pass
    corpus = {}
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.endswith(".rst"):
                full = os.path.join(dirpath, f)
                with open(full, encoding="utf-8", errors="replace") as fh:
                    corpus[scope + "/" + os.path.relpath(full, root).replace("\\", "/")] = fh.read()
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        with open(cache, "wb") as fh:
            pickle.dump(corpus, fh, protocol=pickle.HIGHEST_PROTOCOL)
    except OSError:
        pass  # cache is an optimisation only
    return corpus


def search(query, scope, max_results=20, context=0, index=None):
    toks = _tokens(query)
    if not toks:
        raise ValueError("Empty query")
    phrase = " ".join(toks)
    hits = []
    for rel, text in _corpus(scope).items():
        low, lpath = text.lower(), rel.lower()
        if not all(t in low or t in lpath for t in toks):   # cheap whole-file pre-filter
            continue
        paras = _parse(text)
        for k, p in enumerate(paras):
            body, crumb = p["text"].lower(), p["crumb"].lower()
            if not all(t in body or t in crumb or t in lpath for t in toks):
                continue
            score = sum(min(body.count(t), 5) + 2.0 * (t in crumb) + 1.5 * (t in lpath) for t in toks)
            if phrase in body:
                score += 2 * len(toks)
            score /= 1 + math.log1p(len(body) / 200.0)
            hits.append((score, rel, paras, k))
    hits.sort(key=lambda h: (-h[0], h[1], h[3]))

    def render(rank, h, ctx, widen):
        score, rel, paras, k = h
        lo, hi = max(0, k - ctx), min(len(paras), k + ctx + 1)
        if widen:  # whole enclosing section
            sec = paras[k]["sec"]
            lo, hi = k, k + 1
            while lo > 0 and paras[lo - 1]["sec"] == sec:
                lo -= 1
            while hi < len(paras) and paras[hi]["sec"] == sec:
                hi += 1
        body = "\n\n".join(p["text"] for p in paras[lo:hi])
        return {"path": rel, "text": body[:20000], "breadcrumb": paras[k]["crumb"], "index": rank,
                "score": round(score, 3)}

    if index is not None:
        if not 0 <= index < len(hits):
            raise ValueError("index %d out of range (0..%d)" % (index, len(hits) - 1))
        return {"query": query, "total_hits": len(hits), "results": [render(index, hits[index], context, True)]}
    top = hits[:max_results]
    return {"query": query, "total_hits": len(hits),
            "results": [render(r, h, context, False) for r, h in enumerate(top)]}


# ---------------------------------------------------------------------------
# CLI

def _data_arg(p):
    p.add_argument("--data-dir", help="folder containing api/ and manual/ (env BLMCP_DATA_DIR)")


def _apply(args):
    global _data_dir_override, _rebuild_cache
    _data_dir_override = args.data_dir
    _rebuild_cache = getattr(args, "rebuild_cache", False)


def _api_args(p):
    p.add_argument("identifier", help="e.g. bpy.app, bpy.types.Scene.frame_current, '*' or 'bpy.*'")
    _data_arg(p)


def _search_args(p):
    p.add_argument("query")
    p.add_argument("-n", "--max-results", type=int, default=20)
    p.add_argument("-c", "--context", type=int, default=0, help="paragraphs of context each side")
    p.add_argument("-i", "--index", type=int, help="return only hit INDEX, widened to its section")
    p.add_argument("--rebuild-cache", action="store_true", help="re-read the corpus and refresh bmcp/.cache")
    _data_arg(p)


def _search_tool(name, help_text, scope):
    def run(a):
        _apply(a)
        return search(a.query, scope, a.max_results, a.context, a.index)
    return Tool(name, help_text, _search_args, run, needs_blender=False)


def _run_api(a):
    _apply(a)
    return api_get(a.identifier)


TOOLS = [
    Tool("get_python_api_docs", "Blender Python API docs for IDENTIFIER, or list modules with a trailing '*'.",
         _api_args, _run_api, needs_blender=False),
    _search_tool("search_api_docs", "Full-text search over the bundled Blender Python API reference.", "api"),
    _search_tool("search_manual_docs", "Full-text search over the bundled Blender user manual.", "manual"),
]

if __name__ == "__main__":
    sys.exit(main(TOOLS, prog="python -m bmcp.tools_docs"))
