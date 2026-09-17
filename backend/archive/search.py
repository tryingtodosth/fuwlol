"""Search over Polish prose AND LaTeX formulas, without a search engine.

The two do not tokenise the same way (docs/gemini/latex serach.txt): a prose index wants
diacritics folded and case ignored, a formula index wants `x^2` to equal `x^{2}` and
`\\dfrac` to equal `\\frac`, and a naive `icontains` over the raw body gives neither. So a
post is split into two derived columns at save time — `search_text` (title, summary and
prose, folded to lowercase ASCII) and `search_math` (every formula, canonicalised) — and
a query is put through the same two functions before it is compared. Substring matching
on the canonical form is what makes sub-formula search work (`1+x^{2}` finds the
denominator of `\\frac{1}{1+x^{2}}`), which is what people actually type.

This is the SQLite-and-Postgres-neutral half of the design the research recommends; the
Postgres-only half (hunspell stemming for Polish, pg_trgm GIN indexes) would slot in
behind the same two columns without changing any caller."""
import re
import unicodedata

MATH_RE = re.compile(r'\$\$([\s\S]*?)\$\$|\\\[([\s\S]*?)\\\]|\\\(([\s\S]*?)\\\)|\$([^$\n]+?)\$')
MATH_ENVS = re.compile(r'\\begin\{(equation|align|gather|multline|eqnarray|displaymath|math)\*?\}([\s\S]*?)\\end\{\1\*?\}')
SPACING = re.compile(r'\\(?:[,;:!>]|quad|qquad|displaystyle|textstyle|scriptstyle|limits|nolimits|left|right|big|Big|bigg|Bigg)(?![A-Za-z])')
SYNONYMS = [(re.compile(r'\\[dt]frac(?![A-Za-z])'), r'\\frac'), (re.compile(r'\\le(?![A-Za-z])'), r'\\leq'),
            (re.compile(r'\\ge(?![A-Za-z])'), r'\\geq'), (re.compile(r'\\ne(?![A-Za-z])'), r'\\neq'),
            (re.compile(r'\\to(?![A-Za-z])'), r'\\rightarrow'), (re.compile(r'\\(?:cdots|ldots|dotsc|dotsb)(?![A-Za-z])'), r'\\dots'),
            (re.compile(r'\\mathrm\{d\}'), 'd')]
BRACE = re.compile(r'([\^_])\s*([0-9A-Za-z])(?![0-9A-Za-z{])')
TOKEN = re.compile(r'\\[A-Za-z]+|\S')
COMMAND = re.compile(r'\\[A-Za-z]+\*?')
_ASCII = {'ł': 'l', 'Ł': 'L', 'ø': 'o', 'đ': 'd', 'ß': 'ss'}


def canonicalize_math(formula):
    f = SPACING.sub('', formula)
    for pattern, replacement in SYNONYMS:
        f = pattern.sub(replacement, f)
    f = BRACE.sub(r'\1{\2}', f)
    tokens = TOKEN.findall(f)
    out = []
    for i, t in enumerate(tokens):
        out.append(t)
        # `\alpha x` must not fuse into `\alphax`; every other whitespace is meaningless in TeX
        if t.startswith('\\') and i + 1 < len(tokens) and tokens[i + 1][0].isalpha():
            out.append(' ')
    return ''.join(out)


def normalize_text(s):
    s = ''.join(_ASCII.get(ch, ch) for ch in s)
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r'[^0-9A-Za-z]+', ' ', s.lower())
    return re.sub(r'\s+', ' ', s).strip()


def split_math(text):
    """(prose, [formulas]) — the formulas taken out of the prose in source order."""
    formulas = []

    def take(m):
        formulas.append(next(g for g in m.groups() if g is not None))
        return ' '

    prose = MATH_ENVS.sub(lambda m: take(m), text or '')
    prose = MATH_RE.sub(take, prose)
    return prose, formulas


def _strip_latex_prose(prose):
    prose = re.sub(r'(^|[^\\])%.*$', r'\1', prose, flags=re.M)
    prose = COMMAND.sub(' ', prose)
    return prose.replace('{', ' ').replace('}', ' ')


def index_fields(title, summary, body, fmt):
    """The two derived columns for a post."""
    prose, formulas = split_math(body)
    if fmt == 'latex':
        prose = _strip_latex_prose(prose)
    text = normalize_text(' '.join([title or '', summary or '', prose]))
    math = ' '.join(canonicalize_math(f) for f in formulas if f.strip())
    return text, math


def query_parts(q):
    """(text, math) to compare against the two columns. A query with maths delimiters is
    split like a body; one that merely LOOKS like TeX (`x^2`, `\\frac`) is tried as both."""
    q = (q or '').strip()
    prose, formulas = split_math(q)
    if formulas:
        return normalize_text(prose), ' '.join(canonicalize_math(f) for f in formulas)
    if re.search(r'[\\^_{}]', q):
        return normalize_text(q), canonicalize_math(q)
    return normalize_text(q), ''
