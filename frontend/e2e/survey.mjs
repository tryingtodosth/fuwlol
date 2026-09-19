// Screenshot survey of every fuw.lol page: 4 roles (anonymous, student, doktorant = trusted,
// dziekan = staff + head-admin) × desktop 1280 and phone 390. Needs both dev servers and the
// demo seed. Run from frontend/:
//   PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright node e2e/survey.mjs [out-dir]
// Prints one line per page and every console/page error; look at the PNGs afterwards —
// this is how the duplicated featured posts and the grey phone placeholders were found.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
// E2E_FRONT / E2E_API override the defaults — on a machine where :5173/:8000 belong to another project
// (it happened: the survey photographed somebody else's 404 page) run fuw.lol on other ports and say so.
const FRONT = process.env.E2E_FRONT || 'http://localhost:5173', API = process.env.E2E_API || 'http://localhost:8000/api';
const OUT = process.argv[2] || '/tmp/fuwlol-survey';
fs.mkdirSync(OUT, { recursive: true });
const errors = [];
async function token(user) {
  const r = await fetch(`${API}/auth/login/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: user, password: 'fuwlol123' }) });
  if (!r.ok) throw new Error(`login ${user}: ${r.status}`);
  return (await r.json()).token;
}
const posts = await (await fetch(`${API}/posts/`)).json();
const list = posts.results || posts;
const slug = list[0].slug;
const latex = (list.find((p) => p.format === 'latex') || list[0]).slug;
const people = await (await fetch(`${API}/people/`)).json();
const person = (people.results || people)[0].slug;
const browser = await chromium.launch();
const pages = {
  anon: ['/', '/przegladaj', `/przegladaj?category=legendarne-zadania`, '/os-czasu', '/ludzie', `/ludzie/${person}`, '/ludzie/zgoda', '/przedmioty', `/wpis/${slug}`, `/wpis/${latex}`, '/czat', '/o-archiwum', '/logowanie', '/rejestracja', '/losowe', '/dodaj', '/moderacja'],
  student: ['/', `/wpis/${slug}`, `/ludzie/${person}`, '/dodaj', '/moje', '/konto', '/czat'],
  doktorant: ['/', `/wpis/${slug}`, `/ludzie/${person}`, '/tablica', '/moderacja/portrety', '/konto', '/czat', '/moderacja'],
  dziekan: ['/', `/wpis/${slug}`, '/moderacja', '/moderacja/portrety', '/moderacja/zgody', '/tablica', '/czat', '/konto', `/edytuj/${slug}`],
};
// the plain demo account is `claude-slop` since the seed started naming its author honestly;
// the role keeps its old name so the screenshot filenames stay comparable across runs
const LOGIN = { student: 'claude-slop', doktorant: 'doktorant', dziekan: 'dziekan' };
for (const [role, urls] of Object.entries(pages)) {
  const tok = role === 'anon' ? null : await token(LOGIN[role] || role);
  for (const vp of [{ name: 'desk', width: 1280, height: 900 }, { name: 'phone', width: 390, height: 844 }]) {
    if (vp.name === 'phone' && role !== 'anon') continue; // phone only for anonymous pages
    const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, locale: 'pl-PL', deviceScaleFactor: vp.name === 'phone' ? 2 : 1 });
    const p = await ctx.newPage();
    p.on('pageerror', (e) => errors.push(`${role} pageerror: ${e.message}`));
    p.on('console', (m) => { if (m.type() === 'error') errors.push(`${role} console: ${m.text().slice(0, 200)}`); });
    if (tok) { await p.goto(FRONT + '/logowanie', { waitUntil: 'load' }); await p.evaluate((t) => localStorage.setItem('fuwlol.token', t), tok); }
    for (const u of urls) {
      const name = `${role}-${vp.name}-${(u === '/' ? 'home' : u.slice(1)).replace(/[^a-z0-9]+/gi, '_')}.png`;
      try {
        await p.goto(FRONT + u, { waitUntil: 'load' });
        await p.waitForTimeout(u === '/' ? 3500 : 2200);
        await p.screenshot({ path: `${OUT}/${name}`, fullPage: true });
        const h = await p.evaluate(() => document.documentElement.scrollHeight);
        console.log(`ok ${name} h=${h}`);
      } catch (e) { console.log(`FAIL ${name}: ${e.message.split('\n')[0]}`); }
    }
    await ctx.close();
  }
}
await browser.close();
console.log('errors:', errors.length); for (const e of [...new Set(errors)]) console.log(' ', e);
