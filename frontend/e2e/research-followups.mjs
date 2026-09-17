// What the Gemini research changed, checked in a real browser (docs/gemini/note.md):
// maths survives Markdown, the report form is an art. 16 notice, a new post needs the rights
// declaration, the regulamin exists, and search understands LaTeX. Needs both dev servers + seed.
//   PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright node e2e/research-followups.mjs
import { chromium } from 'playwright-core';
const FRONT = process.env.E2E_FRONT || 'http://localhost:5173', API = process.env.E2E_API || 'http://localhost:8000/api';
let n = 0, failed = 0; const errors = [];
const check = (name, ok, extra = '') => { n++; console.log(`${ok ? 'ok ' : 'FAIL'} ${n}. ${name}${extra ? ' — ' + extra : ''}`); if (!ok) failed++; };
async function token(user) { const r = await fetch(`${API}/auth/login/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: user, password: 'fuwlol123' }) }); return (await r.json()).token; }
const dz = await token('dziekan');
const RUN = String(Date.now()).slice(-6);
// a post whose maths would be mangled by Markdown: *a* inside $$…$$ and a*b*c inline
const made = await (await fetch(`${API}/posts/`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Token ${dz}` },
	body: JSON.stringify({ title: `Test wzorów ${RUN}`, category: 'memy', format: 'text', rights_confirmed: true,
		body: 'Suma $$\\sum_{i} *a_i* \\cdot \\dfrac{1}{1+x^2}$$ i iloczyn $a*b*c$ — koniec.' }) })).json();
check('a post with Markdown-hostile maths is accepted', !!made.slug, JSON.stringify(made).slice(0, 120));
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: 'pl-PL' });
const p = await ctx.newPage();
p.on('pageerror', (e) => errors.push('pageerror ' + e.message)); p.on('console', (m) => { if (m.type() === 'error') errors.push('console ' + m.text().slice(0, 150)); });
await p.goto(`${FRONT}/wpis/${made.slug}`, { waitUntil: 'load' }); await p.waitForSelector('.katex', { timeout: 20000 });
const bodyHtml = await p.locator('.body-html').innerHTML();
check('KaTeX typeset both formulas (2 .katex, none wrecked into <em>)', (await p.locator('.body-html .katex').count()) === 2 && !/<em>/.test(bodyHtml));
check('the display formula kept its \\dfrac and a_i', bodyHtml.includes('annotation') && bodyHtml.includes('dfrac') && bodyHtml.includes('a_i'));
// search by a canonical-variant formula and by a diacritic-free word
const s1 = await (await fetch(`${API}/posts/?q=${encodeURIComponent('x^{2}')}`)).json();
check('search x^{2} finds the post written as x^2', s1.results.some((x) => x.slug === made.slug));
const s2 = await (await fetch(`${API}/posts/?q=${encodeURIComponent('\\frac{1}{1+x^{2}}')}`)).json();
check('search \\frac finds the post written as \\dfrac', s2.results.some((x) => x.slug === made.slug));
// the report form is an art. 16 notice: checkbox required, email explained
await p.getByRole('button', { name: /Zgłoś \/ poproś/ }).click(); await p.waitForSelector('form.report');
check('the report form carries the good-faith statement', (await p.locator('form.report input[type=checkbox]').count()) === 1);
check('…and explains what the e-mail is for (art. 16 DSA)', (await p.locator('form.report').textContent()).includes('art. 16 DSA'));
// a new post needs the rights declaration
await p.goto(`${FRONT}/logowanie`); await p.evaluate((t) => localStorage.setItem('fuwlol.token', t), dz);
await p.goto(`${FRONT}/dodaj`, { waitUntil: 'load' }); await p.waitForSelector('#ed-title');
check('/dodaj shows the rights declaration checkbox', (await p.locator('.rights input[type=checkbox]').count()) === 1);
check('…and warns about lecturers\' photos next to Osoby', (await p.locator('.help', { hasText: 'art. 81' }).count()) === 1);
await p.fill('#ed-title', `Bez oświadczenia ${RUN}`); await p.selectOption('#ed-cat', 'memy').catch(() => {});
await p.getByRole('button', { name: /Zapisz wpis/ }).click(); await p.waitForTimeout(600);
check('saving without the declaration is refused in words', (await p.locator('.error').textContent().catch(() => '')).includes('Potwierdź'));
// a macro bomb is refused by the editor's preview and by the API
await p.goto(`${FRONT}/o-archiwum`, { waitUntil: 'load' });
check('/o-archiwum has the regulamin with the DSA notice procedure', (await p.locator('.rules').textContent()).includes('art. 16 DSA'));
const bomb = await fetch(`${API}/posts/`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Token ${dz}` },
	body: JSON.stringify({ title: 'bomba', category: 'memy', format: 'latex', rights_confirmed: true, body: '\\def\\x{\\x\\x}\\x' }) });
check('a \\def macro bomb is refused (400)', bomb.status === 400);
// cleanup
await fetch(`${API}/posts/${made.slug}/`, { method: 'DELETE', headers: { Authorization: `Token ${dz}` } }).catch(() => {});
await browser.close();
console.log(`${n - failed}/${n} checks passed; ${errors.length} console/page errors`); for (const e of errors) console.log('  ', e);
process.exit(failed ? 1 : 0);
