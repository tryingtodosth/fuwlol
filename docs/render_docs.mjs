// Renders every page of fuwlol-dokumentacja.drawio through draw.io itself (the drawio-lasso web build
// served on 127.0.0.1:8765, embed protocol) -> slides/NN.png, slides/NN.svg, and the PDF to upload.
//   node render_deck.mjs [drawio-file] [out-dir] [pdf-path]
// Needs Node >= 20 and playwright-core (uses the frontend's copy).
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from '/Projects/edmat/frontend/node_modules/playwright-core/index.mjs';

const here = path.dirname(new URL(import.meta.url).pathname);
const drawio = process.argv[2] || path.join(here, 'fuwlol-dokumentacja.drawio');
const outDir = process.argv[3] || path.join(here, 'render');
const pdfPath = process.argv[4] || path.join(here, 'fuwlol-dokumentacja.pdf');
fs.mkdirSync(outDir, { recursive: true });
const xml = fs.readFileSync(drawio, 'utf8');
const pages = [...xml.matchAll(/<diagram\b[^>]*>[\s\S]*?<\/diagram>/g)].map((m) => m[0]);
console.log(`pages: ${pages.length}`);

const browser = await chromium.launch();
// draw.io's embed protocol talks to window.parent, so the app is hosted in an iframe of a blank page.
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
page.on('pageerror', (e) => console.log('pageerror', String(e).slice(0, 200)));
const appUrl = 'http://127.0.0.1:8765/index.html?embed=1&proto=json&spin=1&ui=min&splash=0&libraries=0&noSaveBtn=1&noExitBtn=1&lang=pl';
await page.setContent(`<html><body style="margin:0"><iframe id="f" src="${appUrl}" style="width:1920px;height:1080px;border:0"></iframe><script>window.__msgs=[];window.addEventListener('message',(e)=>{try{window.__msgs.push(typeof e.data==='string'?e.data:JSON.stringify(e.data));}catch{}});</script></body></html>`);
const waitEvent = async (ev, timeout = 60000) => {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    const found = await page.evaluate((ev) => {
      const i = window.__msgs.findIndex((m) => { try { return JSON.parse(m).event === ev; } catch { return false; } });
      if (i < 0) return null;
      const m = window.__msgs[i]; window.__msgs.splice(0, i + 1); return m;
    }, ev);
    if (found) return JSON.parse(found);
    await page.waitForTimeout(100);
  }
  throw new Error('timeout waiting for ' + ev);
};
await waitEvent('init');
const send = (obj) => page.evaluate((s) => document.getElementById('f').contentWindow.postMessage(s, '*'), JSON.stringify(obj));
const svgs = [];
for (let i = 0; i < pages.length; i++) {
  const n = String(i + 1).padStart(2, '0');
  await send({ action: 'load', xml: `<mxfile>${pages[i]}</mxfile>`, autosave: 0 });
  await waitEvent('load', 20000).catch(() => {});
  await page.waitForTimeout(400);
  await send({ action: 'export', format: 'png', scale: 1, border: 0, background: '#ffffff' });
  const r = await waitEvent('export');
  fs.writeFileSync(path.join(outDir, `${n}.png`), Buffer.from(r.data.split(',')[1], 'base64'));
  try {
    await send({ action: 'export', format: 'svg', border: 0, background: '#ffffff', embedImages: true });
    const s = await waitEvent('export', 30000);
    const svg = Buffer.from(s.data.split(',')[1], 'base64').toString('utf8');
    fs.writeFileSync(path.join(outDir, `${n}.svg`), svg);
    svgs.push(svg);
  } catch (e) { console.log(`svg export failed on page ${n}: ${String(e).slice(0, 80)}`); }
  console.log(`page ${n} done`);
}
if (svgs.length === pages.length) {
  const doc = `<!doctype html><html><head><meta charset="utf-8"><style>@page{size:1920px 1080px;margin:0}html,body{margin:0;padding:0}.s{width:1920px;height:1080px;overflow:hidden;break-after:page;page-break-after:always;background:#fff;position:relative}.s svg{position:absolute;left:0;top:0;width:1920px;height:1080px}</style></head><body>${svgs.map((s) => `<div class="s">${s.replace(/^<\?xml[^>]*>\s*/, '').replace(/<!DOCTYPE[^>]*>\s*/, '')}</div>`).join('')}</body></html>`;
  const htmlPath = path.join(outDir, 'deck.html');
  fs.writeFileSync(htmlPath, doc);
  const p2 = await browser.newPage();
  await p2.goto('file://' + htmlPath, { waitUntil: 'load' });
  await p2.waitForTimeout(2000);
  await p2.pdf({ path: pdfPath, width: '1920px', height: '1080px', printBackground: true, preferCSSPageSize: true });
  console.log(`pdf: ${pdfPath} (${Math.round(fs.statSync(pdfPath).size / 1024)} KB)`);
} else {
  console.log('no vector PDF (svg export incomplete)');
}
await browser.close();
