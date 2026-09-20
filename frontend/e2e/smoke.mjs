// Browser smoke test against the running dev servers (see README). Run from frontend/:
//   PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright node e2e/smoke.mjs
// Needs the demo seed (manage.py seed_demo): dziekan (staff) / doktorant (trusted) / student.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import path from 'node:path';

const FRONT = process.env.E2E_FRONT || 'http://localhost:5173';
const API = process.env.E2E_API || 'http://localhost:8000/api';
const SHOTS = process.env.E2E_SHOTS || '/tmp/fuwlol-shots';
fs.mkdirSync(SHOTS, { recursive: true });
let n = 0, failed = 0;
const RUN = String(Date.now()).slice(-6);
const TITLE = `Test e2e ${RUN}: mem z obrazkiem`;
const errors = [];
function check(name, ok, extra = '') {
	n++;
	console.log(`${ok ? 'ok ' : 'FAIL'} ${n}. ${name}${extra ? ' — ' + extra : ''}`);
	if (!ok) failed++;
}
const browser = await chromium.launch();
async function ctx() {
	const c = await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: 'pl-PL' });
	const p = await c.newPage();
	p.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
	p.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text().slice(0, 160)}`); });
	return p;
}
async function login(p, user) {
	await p.goto(`${FRONT}/logowanie`, { waitUntil: 'load' });
	await p.getByLabel(/nazwa|e-mail|login/i).first().fill(user);
	await p.getByLabel(/hasło/i).first().fill('fuwlol123');
	await p.getByRole('button', { name: /zaloguj/i }).click();
	await p.waitForFunction(() => !!localStorage.getItem('fuwlol.token'), null, { timeout: 8000 });
}
const png = (w, h, color) => {
	// a real PNG through the browser: generated on a canvas inside the page
	return { w, h, color };
};

// ---------- anonymous ----------
let p = await ctx();
if (!process.env.E2E_SKIP_ANON) {
await p.goto(FRONT, { waitUntil: 'load' });
await p.waitForSelector('.item', { timeout: 15000 });
const navBg = await p.evaluate(() => getComputedStyle(document.querySelector('nav, .site-nav, ul.nav') || document.body).backgroundColor);
check('home renders the green nav bar', /23, 94, 76/.test(navBg), navBg);
check('home lists posts with ✱ items', (await p.locator('.item').count()) >= 5);
check('home has the chat widget and the time machine', (await p.getByText('Wehikuł czasu').count()) > 0 && (await p.getByText('Wejdź na czat').count()) > 0);
await p.screenshot({ path: path.join(SHOTS, 'home.png'), fullPage: true });

await p.goto(`${FRONT}/przegladaj?category=legendarne-zadania`, { waitUntil: 'load' });
await p.waitForSelector('.item', { timeout: 15000 });
check('browse filters by category', (await p.locator('.item').count()) >= 2);
await p.locator('.item__title a').first().click();
await p.waitForSelector('.katex', { timeout: 20000 });
check('a LaTeX post renders KaTeX math', (await p.locator('.katex').count()) > 0);
check('post shows its catalog number', (await p.locator('.stamp').count()) > 0);
await p.screenshot({ path: path.join(SHOTS, 'post-latex.png'), fullPage: true });

await p.goto(`${FRONT}/ludzie`, { waitUntil: 'load' });
// the directory is the faculty's table.employers since 19.09.2026, not a grid of tiles
await p.waitForSelector('table.employers', { timeout: 15000 });
check('people index lists fictional people', (await p.locator('table.employers td.nm a').count()) >= 3);
await p.goto(`${FRONT}/os-czasu`, { waitUntil: 'load' });
await p.waitForTimeout(1500);
check('timeline shows years', (await p.getByText(/2011/).count()) > 0);

// chat: guest posts a message with LaTeX and a link, long message folds after 100 chars
await p.goto(`${FRONT}/czat`, { waitUntil: 'load' });
await p.waitForSelector('#chat-body', { timeout: 15000 });
await p.fill('#chat-nick', 'Gość Testowy');
const long = 'Wzór $E=mc^2$ i link https://www.fuw.edu.pl/ ' + 'a'.repeat(120);
await p.fill('#chat-body', long);
await p.getByRole('button', { name: 'Wyślij' }).click();
await p.waitForSelector('.msg', { timeout: 10000 });
const first = p.locator('.msg').first();
check('guest message appears with nick and (gość)', (await first.textContent()).includes('Gość Testowy') && (await first.textContent()).includes('(gość)'));
check('long message is folded after 100 chars with a spoiler', (await first.locator('button.spoiler').count()) === 1);
check('math in the chat excerpt is typeset', (await first.locator('.katex').count()) > 0);
check('link in chat is a nofollow link', (await first.locator('a[rel~="nofollow"]').count()) > 0);
await p.waitForTimeout(1000);
await p.fill('#chat-body', '![x](evil.png)');
await p.waitForTimeout(300);
await p.getByRole('button', { name: 'Wyślij' }).click();
await p.waitForSelector('.error', { timeout: 8000 });
check('an image in the chat is refused', (await p.locator('.error').textContent()).includes('Obrazki'));
const rss = await (await fetch(`${API}/board/rss/`)).text();
check('RSS feed serves the chat', rss.includes('<rss') && rss.includes('Testowy'));
await p.screenshot({ path: path.join(SHOTS, 'czat.png'), fullPage: true });

// time machine eras
async function era(date, expectText, shot) {
	await p.goto(`${FRONT}/?czas=${date}`, { waitUntil: 'load' });
	const skip = p.getByRole('button', { name: /pomiń/i });
	try { await skip.click({ timeout: 4000 }); } catch { /* reduced motion or already done */ }
	await p.waitForTimeout(800);
	const body = await p.locator('body').innerText();
	check(`time machine ${date} → ${expectText}`, body.includes(expectText));
	await p.screenshot({ path: path.join(SHOTS, shot), fullPage: false });
}
await era('1850-05-01', 'KURYER', 'era-paper-pl.png');
await era('1800-01-01', 'ANZEIGER', 'era-paper-de.png');
await era('1543-05-24', 'Annotationes', 'era-copernicus.png');
await era('-20000', 'Prawa fizyki', 'era-cave.png');
await era('-66000000', 'Wydział Fizyki jeszcze nie istnieje', 'era-dinos.png');
await era('-20000000000', 't < 0', 'era-void.png');
await p.goto(`${FRONT}/?czas=2005-06-01`, { waitUntil: 'load' });
try { await p.getByRole('button', { name: /pomiń/i }).click({ timeout: 4000 }); } catch { /* */ }
await p.waitForSelector('iframe', { timeout: 15000 });
check('2005 → Internet Archive iframe of fuw.edu.pl', (await p.locator('iframe').getAttribute('src')).includes('web.archive.org/web/2005'));
await p.screenshot({ path: path.join(SHOTS, 'era-wayback.png') });
await p.goto(`${FRONT}/?czas=2026-09-10`, { waitUntil: 'load' });
await p.waitForTimeout(1500);
check('launch day → our own archive as of that day', (await p.locator('body').innerText()).includes('Archiwum tak, jak wyglądało'));
}
await p.close();

// ---------- student: text post with an image through the editor ----------
p = await ctx();
await login(p, 'student');
await p.goto(`${FRONT}/dodaj`, { waitUntil: 'load' });
await p.waitForSelector('#ed-title', { timeout: 15000 });
await p.fill('#ed-title', TITLE);
await p.locator('.rights input[type=checkbox]').check(); // the rights declaration (regulamin)
await p.selectOption('#ed-cat', 'memy');
const imgBytes = await p.evaluate(() => {
	const c = document.createElement('canvas'); c.width = 64; c.height = 48;
	const g = c.getContext('2d'); g.fillStyle = '#175e4c'; g.fillRect(0, 0, 64, 48);
	return c.toDataURL('image/png').split(',')[1];
});
await p.locator('#ed-files').setInputFiles({ name: 'mem.png', mimeType: 'image/png', buffer: Buffer.from(imgBytes, 'base64') });
await p.waitForTimeout(500);
const bodyArea = p.locator('#ed-body');
await bodyArea.fill('Oto mem: ![mem](mem.png) i wzór $\\int_0^1 x\\,dx$.');
await p.getByRole('button', { name: /^zapisz/i }).click();
await p.waitForSelector('.ok', { timeout: 20000 });
check('student submits a text post with an image (goes to moderation)', (await p.locator('.ok').textContent()).includes('moderacj'));
await p.goto(`${FRONT}/moje`, { waitUntil: 'load' });
await p.waitForTimeout(1500);
check('/moje lists the pending post', (await p.locator('body').innerText()).includes(TITLE));
await p.close();

// ---------- staff: moderation queue publishes it; comments with latex; hide ----------
p = await ctx();
await login(p, 'dziekan');
await p.goto(`${FRONT}/moderacja`, { waitUntil: 'load' });
await p.waitForSelector('button', { timeout: 15000 });
await p.waitForTimeout(1500);
const row = p.locator('.q').filter({ hasText: TITLE }).first();
await row.getByRole('button', { name: /opublikuj/i }).click();
await p.waitForTimeout(1500);
const list = await (await fetch(`${API}/posts/?q=${encodeURIComponent('Test e2e ' + RUN)}`)).json();
check('staff publishes the post from the queue', list.count === 1 && list.results[0].cover, JSON.stringify(list.results[0]?.cover));
const slug = list.results[0].slug;
await p.goto(`${FRONT}/wpis/${slug}`, { waitUntil: 'load' });
await p.waitForSelector('.katex', { timeout: 20000 });
check('published post renders the uploaded image inline', (await p.locator('img[src*="/media/attachments/"]').count()) >= 1);
const ta = p.locator('textarea').last();
await ta.fill('Komentarz z LaTeX-em: $\\pi^4/15$');
await p.getByRole('button', { name: /latex/i }).last().click().catch(() => {});
await p.getByRole('button', { name: /wyślij/i }).last().click();
await p.waitForTimeout(2000);
check('a comment posts and shows up', (await p.locator('.cmt').count()) >= 1);
check('staff sees hide / nuke controls on the post', (await p.getByRole('button', { name: /^ukryj/i }).count()) >= 1);
await p.screenshot({ path: path.join(SHOTS, 'post-staff.png'), fullPage: true });
await p.goto(`${FRONT}/tablica`, { waitUntil: 'load' });
await p.waitForTimeout(2000);
const tb = await p.locator('body').innerText();
check('moderation board lists the seeded hidden post and the nuked stub', tb.includes('Mem, który był trochę za bardzo') && tb.includes('nuklearn'));
await p.screenshot({ path: path.join(SHOTS, 'tablica-staff.png'), fullPage: true });
await p.close();

// ---------- trusted (doktorant): sees hidden content but not the nuked one; own post publishes at once ----------
p = await ctx();
await login(p, 'doktorant');
await p.goto(`${FRONT}/tablica`, { waitUntil: 'load' });
await p.waitForTimeout(2000);
const tt = await p.locator('body').innerText();
check('trusted user sees the hidden post on the board', tt.includes('Mem, który był trochę za bardzo'));
check('trusted user does NOT see the nuked post title', !tt.includes('Wpis usunięty opcją nuklearną') && tt.includes('tylko dla administracji'));
await p.goto(`${FRONT}/konto`, { waitUntil: 'load' });
await p.waitForTimeout(1500);
check('/konto shows the trusted badge', (await p.locator('body').innerText()).includes('zaufany'));
await p.screenshot({ path: path.join(SHOTS, 'konto.png'), fullPage: true });
await p.close();

// ---------- plain user asks for verification: refused for gmail, accepted for fuw.edu.pl ----------
p = await ctx();
await login(p, 'student');
await p.goto(`${FRONT}/konto`, { waitUntil: 'load' });
await p.waitForSelector('#aff-email', { timeout: 15000 });
await p.fill('#aff-email', 'ktos@gmail.com');
await p.getByRole('button', { name: /wyślij link/i }).click();
await p.waitForSelector('.error', { timeout: 8000 });
check('gmail is refused with the institution list', (await p.locator('.error').textContent()).length > 10);
await p.fill('#aff-email', 'student.test@fuw.edu.pl');
await p.getByRole('button', { name: /wyślij link/i }).click();
await p.waitForSelector('.ok', { timeout: 8000 });
check('fuw.edu.pl address is accepted (mail sent to console)', (await p.locator('.ok').textContent()).includes('@fuw.edu.pl'));
await p.close();

await browser.close();
const realErrors = errors.filter((e) => !/favicon|web\.archive\.org|fonts\.g|net::ERR|429|400 \(Bad|403 \(Forb|404 \(Not/.test(e));
console.log(`\n${n - failed}/${n} checks passed; ${realErrors.length} console/page errors`);
for (const e of realErrors.slice(0, 10)) console.log('  ' + e);
process.exit(failed || realErrors.length ? 1 : 0);
