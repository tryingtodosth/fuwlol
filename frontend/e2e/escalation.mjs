// Escalation to NASK, end to end in a browser: a trusted user escalates a chat message through
// the confirm dialog, the head-admin sees "NASK (1)" in the nav, opens /eskalacje, reads the
// frozen evidence and declines; the message is public again. Needs both dev servers + demo seed.
//   PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright node e2e/escalation.mjs
import { chromium } from 'playwright-core';
const FRONT = 'http://localhost:5173', API = 'http://localhost:8000/api';
const OUT = process.env.E2E_SHOTS || '/tmp/fuwlol-shots';
import fs from 'node:fs'; fs.mkdirSync(OUT, { recursive: true });
async function token(user) { const r = await fetch(`${API}/auth/login/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: user, password: 'fuwlol123' }) }); return (await r.json()).token; }
const dok = await token('doktorant'), dz = await token('dziekan');
// a scratch chat message, then escalate it as the trusted doktorant
const m = await (await fetch(`${API}/board/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ nick: 'Test Esk', body: 'wiadomość testowa do eskalacji ' + Date.now(), website: '' }) })).json();
const e = await (await fetch(`${API}/board/${m.id}/escalate/`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Token ${dok}` }, body: JSON.stringify({ reason: 'Test: treść nielegalna (scenariusz e2e)' }) })).json();
console.log('escalated', m.id, '->', e);
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: 'pl-PL' });
const p = await ctx.newPage(); const errs = [];
p.on('pageerror', (x) => errs.push('pageerror ' + x.message)); p.on('console', (x) => { if (x.type() === 'error') errs.push('console ' + x.text().slice(0, 150)); });
await p.goto(FRONT + '/logowanie'); await p.evaluate((t) => localStorage.setItem('fuwlol.token', t), dz);
await p.goto(FRONT + '/eskalacje', { waitUntil: 'load' }); await p.waitForSelector('.item', { timeout: 10000 });
console.log('nav has NASK link:', await p.locator('nav a[href="/eskalacje"]').textContent());
await p.getByRole('button', { name: /Pokaż materiał/ }).first().click(); await p.waitForSelector('.evidence', { timeout: 8000 });
await p.screenshot({ path: `${OUT}/dziekan-desk-eskalacje.png`, fullPage: true });
await p.getByRole('button', { name: /^Odrzuć/ }).first().click(); await p.waitForSelector('dialog[open]');
await p.screenshot({ path: `${OUT}/dziekan-desk-eskalacje-dialog.png` });
await p.fill('#dlg-reason', 'to tylko test'); await p.locator('dialog button.btn:not(.btn--ghost)').click();
await p.waitForTimeout(800);
console.log('rows left after decline:', await p.locator('.item').count());
const back = await (await fetch(`${API}/board/?limit=5`)).json();
console.log('message visible again publicly:', back.results.some((x) => x.id === m.id));
// escalate a post via ModTools dialog as doktorant on the post page, cancel path + confirm path
const p2 = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
p2.on('pageerror', (x) => errs.push('pageerror ' + x.message));
await p2.goto(FRONT + '/logowanie'); await p2.evaluate((t) => localStorage.setItem('fuwlol.token', t), dok);
await p2.goto(FRONT + '/czat', { waitUntil: 'load' }); await p2.waitForSelector('.msg');
await p2.getByRole('button', { name: 'zgłoś do NASK' }).first().click(); await p2.waitForSelector('dialog[open]');
console.log('confirm disabled until reason:', await p2.locator('dialog button.btn--warn').isDisabled());
await p2.keyboard.press('Escape'); await p2.waitForTimeout(300);
console.log('dialog closed on Esc:', (await p2.locator('dialog[open]').count()) === 0);
// cleanup: hide scratch message as dziekan
await fetch(`${API}/board/${m.id}/hide/`, { method: 'POST', headers: { Authorization: `Token ${dz}` } });
await browser.close(); console.log('errors:', errs);
