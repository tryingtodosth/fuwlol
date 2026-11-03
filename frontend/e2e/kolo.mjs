// Koło AI (routes/ai/, backend/kolo_ai/) end to end against the running dev servers:
// the list → "oczekujesz na zatwierdzenie" → the mailed link → a manager admits → a trial vote →
// the result. Mail is the console backend, so links are read from the API server's log.
//
//   E2E_FRONT=http://localhost:5731 E2E_API=http://127.0.0.1:8731/api E2E_API_LOG=/path/api.log \
//   E2E_BOSS_LINK="$(cat boss_link.txt)" PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright node e2e/kolo.mjs
//
// The manager is bootstrapped beforehand with `manage.py kolo_invite … --manager --print-link`.
import { chromium } from 'playwright-core';
import fs from 'node:fs';

const FRONT = process.env.E2E_FRONT || 'http://localhost:5173';
const API = process.env.E2E_API || 'http://localhost:8000/api';
const LOG = process.env.E2E_API_LOG;
const BOSS_LINK = process.env.E2E_BOSS_LINK;
const SHOTS = process.env.E2E_SHOTS || '/tmp/fuwlol-shots/kolo';
fs.mkdirSync(SHOTS, { recursive: true });
const RUN = String(Date.now()).slice(-6);
const EMAIL = `jan${RUN}@student.uw.edu.pl`;
let n = 0, failed = 0;
const errors = [];
function check(name, ok, extra = '') {
	n++;
	console.log(`${ok ? 'ok ' : 'FAIL'} ${n}. ${name}${extra ? ' — ' + extra : ''}`);
	if (!ok) failed++;
}
function lastLinkFor(email) {
	const log = fs.readFileSync(LOG, 'utf8');
	const at = log.lastIndexOf(`To: ${email}`);
	const m = at >= 0 && log.slice(at).match(/\/ai\/link\?token=([\w-]+)/);
	return m ? m[1] : null;
}
// E2E_CHROME: a system Chromium, for a machine where Playwright's cached build lacks libraries.
const browser = await chromium.launch(process.env.E2E_CHROME ? { executablePath: process.env.E2E_CHROME } : {});
async function ctx(width = 1280) {
	const c = await browser.newContext({ viewport: { width, height: 900 }, locale: 'pl-PL' });
	const p = await c.newPage();
	p.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
	p.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text().slice(0, 160)}`); });
	p.on('dialog', (d) => d.accept());
	return p;
}

// 1. The public page, desktop and phone.
const anon = await ctx();
await anon.goto(`${FRONT}/ai`, { waitUntil: 'networkidle' });
check('page title', (await anon.title()).startsWith('Koło AI'));
check('status feed shows the published entry', await anon.locator('.status-item', { hasText: 'Zebranie założycielskie' }).count() > 0);
check('no archive header on /ai', await anon.locator('header.kolo__top').count() === 1 && await anon.locator('.banner, nav.mainnav').count() === 0);
await anon.screenshot({ path: `${SHOTS}/01-ai-anon.png`, fullPage: true });
const phone = await ctx(390);
await phone.goto(`${FRONT}/ai`, { waitUntil: 'networkidle' });
await phone.screenshot({ path: `${SHOTS}/02-ai-phone.png`, fullPage: true });

// 2. Sign up on the list.
const join = anon.locator('form').first();
check('submit disabled before consent', await join.locator('button[type=submit]').isDisabled());
await anon.fill('#j-name', `Jan Testowy ${RUN}`);
await anon.fill('#j-email', EMAIL);
await anon.locator('.consent input').check();
await join.locator('button[type=submit]').click();
await anon.locator('.ok').waitFor({ timeout: 5000 });
check('says: oczekujesz na zatwierdzenie', (await anon.locator('.ok').innerText()).includes('Oczekujesz na zatwierdzenie'));
await anon.screenshot({ path: `${SHOTS}/03-joined.png`, fullPage: true });

// 3. The mailed link confirms the address; still waiting for approval.
await new Promise((r) => setTimeout(r, 500));
const token = lastLinkFor(EMAIL);
check('confirmation mail carries a link', !!token);
await anon.goto(`${FRONT}/ai/link?token=${token}`, { waitUntil: 'networkidle' });
check('link page: oczekujesz na zatwierdzenie', (await anon.locator('main').innerText()).includes('Oczekujesz na zatwierdzenie'));
check('token gone from the address bar', !anon.url().includes('token='));
await anon.screenshot({ path: `${SHOTS}/04-link-pending.png`, fullPage: true });
await anon.goto(`${FRONT}/ai/glosowania`, { waitUntil: 'networkidle' });
check('pending person sees no votes', (await anon.locator('main').innerText()).includes('Nie ma jeszcze żadnych głosowań'));

// 4. The manager's invitation, then the queue.
const boss = await ctx();
// A link is single-use, so every run asks for a fresh login link for the manager (E2E_BOSS_EMAIL);
// E2E_BOSS_LINK is only for the very first run, straight from `kolo_invite --print-link`.
let bossLink = BOSS_LINK && BOSS_LINK.replace(/^https?:\/\/[^/]+/, FRONT);
if (process.env.E2E_BOSS_EMAIL) {
	await fetch(`${API}/kolo/login/`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ email: process.env.E2E_BOSS_EMAIL }) });
	await new Promise((r) => setTimeout(r, 500));
	bossLink = `${FRONT}/ai/link?token=${lastLinkFor(process.env.E2E_BOSS_EMAIL)}`;
}
await boss.goto(bossLink, { waitUntil: 'networkidle' });
await boss.waitForURL(`${FRONT}/ai`, { timeout: 5000 }).catch(() => {});
await boss.goto(`${FRONT}/ai/zarzad`, { waitUntil: 'networkidle' });
const row = boss.locator('tr', { hasText: `Jan Testowy ${RUN}` });
check('queue lists the new person', await row.count() === 1);
await boss.screenshot({ path: `${SHOTS}/05-zarzad-queue.png`, fullPage: true });
await row.getByRole('button', { name: 'członek' }).click();
await boss.locator('dialog.dlg .dlg__acts .btn:not(.btn--ghost)').click();
const admitted = boss.locator('tr', { hasText: `Jan Testowy ${RUN}` }).filter({ hasText: 'ustanie członkostwa' });
check('admitted', await admitted.waitFor({ timeout: 5000 }).then(() => true, () => false));

// 5. A trial vote that is already open (trial skips the notice period).
const session = await boss.evaluate(() => localStorage.getItem('fuwlol.kolo'));
const now = Date.now();
// opens a moment from now: a vote that opened before Jan's admission would rightly refuse him
const created = await fetch(`${API}/kolo/polls/`, {
	method: 'POST', headers: { Authorization: `Kolo ${session}`, 'Content-Type': 'application/json' },
	body: JSON.stringify({ organ: 'walne', kind: 'uchwala', mode: 'tajne', majority: 'zwykla', trial: true,
		title: `próba głosowania ${RUN}`, body: 'Walne Zebranie Koła AI przyjmuje, że głosowanie zdalne działa.',
		opens_at: new Date(now + 1500).toISOString(), closes_at: new Date(now + 49 * 3600e3).toISOString() })
}).then((r) => r.json());
await fetch(`${API}/kolo/polls/${created.id}/announce/`, { method: 'POST', headers: { Authorization: `Kolo ${session}` } });
// eligibility is the register WHEN THE VOTE OPENS (§ 10a ust. 2): Jan was admitted just now, so the
// vote opens after that, and we wait for it
await new Promise((r) => setTimeout(r, 2000));
await anon.goto(`${FRONT}/ai/glosowania/${created.id}`, { waitUntil: 'networkidle' });
check('member sees the open vote', (await anon.locator('h1').innerText()).includes(`próba głosowania ${RUN}`));
await anon.locator('label.opt', { hasText: 'za' }).first().locator('input').check();
await anon.getByRole('button', { name: 'Oddaj głos' }).click();
await anon.getByRole('button', { name: 'Głosuję' }).click();
await anon.locator('.ok', { hasText: 'Głos oddany' }).first().waitFor({ timeout: 5000 });
check('vote recorded, results hidden', (await anon.locator('main').innerText()).includes('Wyniki po zakończeniu'));
await anon.fill('#note', 'Działa.');
await anon.getByRole('button', { name: 'Dodaj' }).click();
await anon.locator('.status-item', { hasText: 'Działa.' }).waitFor({ timeout: 5000 });
check('deliberation entry shown', true);
await anon.screenshot({ path: `${SHOTS}/06-voted.png`, fullPage: true });

// 6. fuw.lol itself is untouched.
await anon.goto(`${FRONT}/`, { waitUntil: 'networkidle' });
check('archive home still has its own layout', await anon.locator('header.kolo__top').count() === 0);

check('no page errors', errors.length === 0, errors.join(' | '));
await browser.close();
console.log(`${n - failed}/${n} ok`);
process.exit(failed ? 1 : 0);
