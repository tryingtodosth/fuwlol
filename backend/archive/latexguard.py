"""Server-side guard for user-written LaTeX/Markdown+maths, before it is stored.

Everything the site typesets runs IN THE READER'S BROWSER (KaTeX for `$…$`, LaTeX.js for a
whole LaTeX post), and a browser's JavaScript thread cannot be interrupted once a parser
is busy. That makes a TeX macro bomb — `\\def\\x{\\x\\x}\\x`, a dozen levels of `\\newcommand`
each calling the previous one twice — a way to freeze the tab of every person who opens
the post, moderators first (docs/gemini/latex safety.txt walks through the mechanics:
Packrat memoisation in LaTeX.js's PEG parser is linear in memory, macro expansion is
exponential, and neither KaTeX's maxExpand nor AbortSignal reaches LaTeX.js at all).

The archive has no legitimate use for `\\def` — a meme is not a macro package — so the
cheapest sufficient defence is to refuse the primitives outright and to refuse a
`\\newcommand` that refers to itself, plus plain size caps. The frontend mirrors these rules
(`lib/render/guard.ts`) so the editor says no before the upload does; this copy is the one
that counts."""
import re

MAX_POST_CHARS = 60_000
MAX_COMMENT_CHARS = 10_000
MAX_ENVIRONMENTS = 400

# TeX primitives that define or manipulate macros / tokens. None of them has a place in a
# post; LaTeX.js implements \def and KaTeX implements \def/\edef inside maths.
FORBIDDEN = re.compile(r'\\(def|edef|gdef|xdef|let|futurelet|csname|expandafter|loop|catcode|'
                       r'noexpand|afterassignment|aftergroup|input|include|write|openout)\b')
NEWCOMMAND = re.compile(r'\\(?:re)?newcommand\*?\s*\{?\\([A-Za-z@]+)\}?')
NEWENV = re.compile(r'\\(?:re)?newenvironment\*?\s*\{([A-Za-z@*]+)\}')

TOO_LONG = 'Za długa treść (limit {n} znaków).'
MACRO = 'Makra \\{name} nie są tu obsługiwane — ze względów bezpieczeństwa treść nie może definiować własnych poleceń TeX-a.'
RECURSIVE = 'Polecenie \\{name} odwołuje się do samego siebie — takie makro zawiesiłoby przeglądarkę czytelnika.'
TOO_MANY_ENVS = 'Za dużo środowisk \\begin{{…}} (limit {n}).'


def _definition_body(src, start):
    """The macro body: the first {…} group after the (already matched) name, skipping any
    [n] argument-count groups; '' if the braces never balance."""
    i = start
    while i < len(src) and src[i] in ' \t\r\n':
        i += 1
    while i < len(src) and src[i] == '[':
        j = src.find(']', i)
        if j == -1:
            return ''
        i = j + 1
        while i < len(src) and src[i] in ' \t\r\n':
            i += 1
    if i >= len(src) or src[i] != '{':
        return ''
    depth, j = 0, i
    while j < len(src):
        if src[j] == '{' and (j == 0 or src[j - 1] != '\\'):
            depth += 1
        elif src[j] == '}' and src[j - 1] != '\\':
            depth -= 1
            if depth == 0:
                return src[i + 1:j]
        j += 1
    return ''


def check_source(src, *, max_chars=MAX_POST_CHARS):
    """Return None if `src` is acceptable, else a Polish message for the user."""
    src = src or ''
    if len(src) > max_chars:
        return TOO_LONG.format(n=max_chars)
    m = FORBIDDEN.search(src)
    if m:
        return MACRO.format(name=m.group(1))
    for m in NEWCOMMAND.finditer(src):
        name = m.group(1)
        body = _definition_body(src, m.end())
        if re.search(r'\\' + re.escape(name) + r'(?![A-Za-z@])', body):
            return RECURSIVE.format(name=name)
    for m in NEWENV.finditer(src):
        name = m.group(1)
        body = src[m.end():m.end() + 2000]
        if f'\\begin{{{name}}}' in body:
            return RECURSIVE.format(name='begin{' + name + '}')
    if src.count('\\begin{') > MAX_ENVIRONMENTS:
        return TOO_MANY_ENVS.format(n=MAX_ENVIRONMENTS)
    return None
