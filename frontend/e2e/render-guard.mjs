// docs/gemini/latex safety.txt's own promise, checked for real: `renderLatex` (LaTeX.js) always
// refused a macro bomb before compiling it, but `typeset()` (KaTeX, the Markdown/`format=text`
// path) did not — even though KaTeX implements \def/\edef/\gdef/\let itself, unconditionally,
// not gated by `trust`. Every submission path already runs the same guard on the whole body
// regardless of format, so this can't happen through the API — the gap was the SECOND layer,
// for content that got into the database another way (an old row, the Django admin), which is
// exactly what this fixture simulates: a Post built straight through the ORM, bypassing
// archive/serializers.py entirely, the same way the docstrings already claimed was covered.
//
// Needs both dev servers running (Django on :8000, the frontend on :5173) — see e2e/CLAUDE.md
// if that file exists, otherwise research-followups.mjs's own header for the pattern.
//   PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright node e2e/render-guard.mjs
import { execFileSync } from 'node:child_process';
import { writeFileSync, unlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { chromium } from 'playwright-core';

const FRONT = process.env.E2E_FRONT || 'http://localhost:5173';
const API = process.env.E2E_API || 'http://localhost:8000/api';
const BACKEND_DIR = process.env.E2E_BACKEND_DIR || '../backend';
const VENV_PY = process.env.E2E_PYTHON || '../.venv/bin/python';

let n = 0, failed = 0;
const errors = [];
const check = (name, ok, extra = '') => {
	n++;
	console.log(`${ok ? 'ok ' : 'FAIL'} ${n}. ${name}${extra ? ' — ' + extra : ''}`);
	if (!ok) failed++;
};

async function token(user) {
	const r = await fetch(`${API}/auth/login/`, {
		method: 'POST', headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ username: user, password: 'fuwlol123' })
	});
	return (await r.json()).token;
}

// \sqrt{\sqrt{\sqrt{…}}} 3000 deep — a real, currently-effective bomb against KaTeX (measured:
// ~370ms of pure string generation before the browser ever lays the DOM out) that touches no
// \def/\newcommand/\begin at all, so the macro-primitive check alone would never catch it.
const deepSqrt = '\\sqrt{'.repeat(3000) + 'x' + '}'.repeat(3000);

// Bypasses the API (and its own latexguard.check_source call) on purpose — this is the "an old
// row, the Django admin" scenario the reader-side guard exists for, not something reachable
// through /api/posts/ today (a second test already confirms the API itself refuses this body).
// Two separate posts, not one mixed body: `typeset()` guards the whole element's text at once
// (the same coarse, whole-body granularity `check_source` already uses server-side), so a post
// that mixes a bomb with a genuine formula skips typesetting entirely rather than picking one
// formula to spare — the safe, correct outcome, not a bug this test should paper over.
const RUN = String(Date.now()).slice(-6);
function createPost(suffix, body) {
	const bodyFile = join(tmpdir(), `render-guard-body-${RUN}-${suffix}.txt`);
	writeFileSync(bodyFile, body, 'utf8');
	// the body is written to a file, not interpolated into the Python source itself — avoids
	// stacking JS-template / shell-arg / Python-string-literal escaping for a string that
	// already contains hundreds of literal backslashes
	const script = `
from archive.models import Category, Post
with open('${bodyFile}', encoding='utf-8') as f:
    body = f.read()
cat = Category.objects.get(slug='memy')
p = Post.objects.create(title='Render guard fixture ${RUN}-${suffix}', category=cat, format='text',
                        status='published', rights_confirmed=True, body=body)
print(p.slug)
`;
	try {
		return execFileSync(VENV_PY, ['manage.py', 'shell', '-c', script], { cwd: BACKEND_DIR, encoding: 'utf8' })
			.trim().split('\n').pop();
	} finally {
		unlinkSync(bodyFile);
	}
}
const cleanSlug = createPost('clean', 'Zwykly wzor: $x^2+1$.');
const bombSlug = createPost('bomb',
	`Bomba makr: $\\def\\x{\\x\\x}\\x$. Glebokie zagniezdzenie: $$${deepSqrt}$$.`);
check('a clean post and a post bypassing latexguard were both created directly (Django admin)',
	!!cleanSlug && !!bombSlug, `${cleanSlug} / ${bombSlug}`);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: 'pl-PL' });
const p = await ctx.newPage();
p.on('pageerror', (e) => errors.push('pageerror ' + e.message));
p.on('console', (m) => { if (m.type() === 'error') errors.push('console ' + m.text().slice(0, 150)); });

await p.goto(`${FRONT}/wpis/${cleanSlug}`, { waitUntil: 'load', timeout: 20000 });
await p.waitForSelector('.body-html .katex', { timeout: 20000 });
check('a normal formula on its own still typesets after the fix', (await p.locator('.body-html .katex').count()) === 1);

// The real assertion is implicit in this call succeeding at all: `goto`/`waitForSelector` carry
// Playwright's ordinary bounded timeouts, so a genuine hang in the reader's own tab (the bug this
// guard closes) would time this step out rather than let the script quietly pass.
const start = Date.now();
await p.goto(`${FRONT}/wpis/${bombSlug}`, { waitUntil: 'load', timeout: 20000 });
await p.waitForSelector('.body-html', { timeout: 20000 });
check('the bomb post loaded within a bounded timeout too, no hang', Date.now() - start < 20000, `${Date.now() - start}ms`);

const bodyText = await p.locator('.body-html').innerText();
check('the macro-bomb formula was NOT executed — its raw source is still plain text',
	bodyText.includes('\\def\\x{\\x\\x}\\x'));
check('the deep-nesting bomb was NOT executed either — its raw source is still plain text',
	bodyText.includes('\\sqrt{\\sqrt{\\sqrt{'));
check('neither bomb became a real .katex node', (await p.locator('.body-html .katex').count()) === 0);

const dz = await token('dziekan');
for (const s of [cleanSlug, bombSlug]) {
	await fetch(`${API}/posts/${s}/`, { method: 'DELETE', headers: { Authorization: `Token ${dz}` } }).catch(() => {});
}
await browser.close();

console.log(`${n - failed}/${n} checks passed; ${errors.length} console/page errors`);
for (const e of errors) console.log('  ', e);
process.exit(failed ? 1 : 0);
