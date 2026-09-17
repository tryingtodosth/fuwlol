#!/usr/bin/env python3
"""Buduje docs/fuwlol-dokumentacja.drawio — dokumentację techniczną fuw.lol po polsku, jedna
strona draw.io = jedna plansza 1920x1080, z prawdziwymi zrzutami ekranu z docs/img/
(zrobionymi na działającym serwisie: frontend/e2e/survey.mjs).

    ../.venv/bin/python build_docs.py            -> fuwlol-dokumentacja.drawio
    node render_docs.mjs                         -> render/NN.png + fuwlol-dokumentacja.pdf
                                                    (wymaga draw.io serwowanego na 127.0.0.1:8765)

Tylko biblioteka standardowa + Pillow (do przycinania zrzutów).
"""
import base64, datetime, html, io, pathlib

from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
W, H, M = 1920, 1080, 90
FONT = "Helvetica"
# paleta fuw.lol (frontend/src/app.css)
GREEN, GREEN_D, AMBER, RUST = "#175e4c", "#104336", "#fdba45", "#a84204"
INK, BODY, MUTED, LINE, BOX, BANNER = "#222222", "#444444", "#777777", "#cccccc", "#f6f6f6", "#d9d9d9"
GREEN_L, AMBER_L, RUST_L, BLUE, BLUE_L = "#e6f1ee", "#fff3d6", "#fbe9e0", "#2a5d8f", "#e8f0f8"
TODAY = datetime.date.today().strftime("%d.%m.%Y")
FOOTER = f"fuw.lol — dokumentacja techniczna · stan na {TODAY} · źródło: docs/build_docs.py"

_uid = [0]
def uid():
    _uid[0] += 1
    return f"c{_uid[0]}"

class Page:
    def __init__(self, name):
        self.name, self.cells = name, []
    def cell(self, x, y, w, h, style, value=""):
        cid = uid()
        self.cells.append(f'<mxCell id="{cid}" value="{html.escape(value, quote=True)}" style="{style}" vertex="1" parent="1">'
                          f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        return cid
    def edge(self, src, dst, label="", color=GREEN, dashed=False, exit_=None, entry=None, straight=False):
        cid = uid()
        style = (f"edgeStyle={'none' if straight else 'orthogonalEdgeStyle'};rounded=1;html=1;endArrow=block;endFill=1;strokeColor={color};"
                 f"strokeWidth=2;fontFamily={FONT};fontSize=16;fontColor={BODY};labelBackgroundColor=#ffffff;"
                 + ("dashed=1;" if dashed else "") + (exit_ or "") + (entry or ""))
        self.cells.append(f'<mxCell id="{cid}" value="{html.escape(label, quote=True)}" style="{style}" edge="1" parent="1" '
                          f'source="{src}" target="{dst}"><mxGeometry relative="1" as="geometry"/></mxCell>')
        return cid
    def xml(self):
        return (f'<diagram id="{uid()}" name="{html.escape(self.name, quote=True)}">'
                f'<mxGraphModel dx="0" dy="0" grid="0" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" '
                f'page="1" pageScale="1" pageWidth="{W}" pageHeight="{H}" background="#ffffff" math="0" shadow="0">'
                f'<root><mxCell id="0"/><mxCell id="1" parent="0"/>{"".join(self.cells)}</root></mxGraphModel></diagram>')

def tstyle(size=22, color=BODY, align="left", valign="top", bold=False):
    return (f"text;html=1;strokeColor=none;fillColor=none;align={align};verticalAlign={valign};whiteSpace=wrap;"
            f"overflow=visible;fontFamily={FONT};fontSize={size};fontColor={color};fontStyle={1 if bold else 0};"
            f"spacing=0;spacingTop=0;spacingLeft=0;spacingRight=0;spacingBottom=0;")
def rstyle(fill=BOX, stroke=LINE, radius=0, sw=1, dashed=False):
    return (f"rounded={1 if radius else 0};arcSize={radius};whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
            f"strokeWidth={sw};fontFamily={FONT};" + ("dashed=1;" if dashed else ""))
def lh(s, f=1.3): return f'<div style="line-height:{f}">{s}</div>'
def ul(items, gap=8): return '<ul style="margin:0;padding-left:26px">' + "".join(f'<li style="margin:0 0 {gap}px 0">{i}</li>' for i in items) + "</ul>"
def b(s): return f"<b>{s}</b>"
def g(s): return f'<span style="color:{GREEN}">{s}</span>'
def r(s): return f'<span style="color:{RUST}">{s}</span>'
def mu(s): return f'<span style="color:{MUTED}">{s}</span>'
def code(s): return f'<span style="font-family:monospace;background:{BOX};padding:0 4px">{s}</span>'

def frame(p, n, total):
    p.cell(0, 0, W, H, rstyle("#ffffff", "none"))
    p.cell(0, 0, W, 14, rstyle(GREEN, "none"))
    p.cell(M, H - 52, 1400, 28, tstyle(15, MUTED), FOOTER)
    p.cell(W - M - 200, H - 52, 200, 28, tstyle(15, MUTED, align="right"), f"{n} / {total}")

def head(p, kicker, title, size=42):
    p.cell(M, 44, W - 2 * M, 30, tstyle(18, RUST, bold=True), f'<span style="letter-spacing:2px">✱ {kicker.upper()}</span>')
    p.cell(M, 78, W - 2 * M, 70, tstyle(size, INK, bold=True), lh(title, 1.12))

def text(p, x, y, w, h, value, size=22, color=BODY, bold=False, align="left", valign="top", f=1.3):
    return p.cell(x, y, w, h, tstyle(size, color, align, valign, bold), lh(value, f))

def card(p, x, y, w, h, fill=BOX, stroke=LINE, dashed=False, title=None, title_fill=None):
    cid = p.cell(x, y, w, h, rstyle(fill, stroke, dashed=dashed))
    if title:
        p.cell(x, y, w, 36, rstyle(title_fill or "#ffffff", stroke))
        p.cell(x + 10, y + 5, w - 20, 28, tstyle(18, INK, bold=True), title)
    return cid

def node(p, x, y, w, h, label, fill="#ffffff", stroke=GREEN, size=18, bold=True, color=INK, dashed=False, radius=0):
    return p.cell(x, y, w, h, rstyle(fill, stroke, radius=radius, dashed=dashed) + f"align=center;verticalAlign=middle;fontSize={size};"
                  f"fontColor={color};fontStyle={1 if bold else 0};", lh(label, 1.2))

def shot(p, x, y, w, name, crop=None, max_h=None, caption=None):
    """Zrzut z docs/img/<name>, przycięty do (x0,y0,x1,y1) w pikselach źródła, wpasowany w szerokość w
    (i opcjonalnie wysokość max_h). Zwraca wysokość na planszy."""
    src = HERE / "img" / name
    img = Image.open(src)
    if crop:
        img = img.crop(crop)
    if max_h:
        ratio_h = max_h / (img.height * w / img.width)
        if ratio_h < 1:
            img = img.crop((0, 0, img.width, int(img.height * ratio_h)))
    h = round(w * img.height / img.width)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    data = base64.b64encode(buf.getvalue()).decode()
    p.cell(x - 6, y - 6, w + 12, h + 12, rstyle("#ffffff", LINE))
    p.cell(x, y, w, h, f"shape=image;imageAspect=0;aspect=fixed;verticalAlign=top;image=data:image/png,{data};")
    if caption:
        p.cell(x, y + h + 10, w, 30, tstyle(15, MUTED), caption)
    return h

def table(p, x, y, col_w, rows, row_h=36, head_fill=GREEN, size=16):
    """rows[0] to nagłówek. col_w: lista szerokości kolumn."""
    cy = y
    for ri, row in enumerate(rows):
        cx = x
        for ci, val in enumerate(row):
            fill = head_fill if ri == 0 else ("#ffffff" if ri % 2 else BOX)
            color = "#ffffff" if ri == 0 else BODY
            p.cell(cx, cy, col_w[ci], row_h, rstyle(fill, LINE) + f"align={'center' if ci else 'left'};verticalAlign=middle;"
                   f"fontSize={size};fontColor={color};fontStyle={1 if ri == 0 else 0};spacingLeft=8;", val)
            cx += col_w[ci]
        cy += row_h
    return cy - y

pages = []
def slide(name):
    p = Page(name); pages.append(p); return p

# ------------------------------------------------------------------------------- 1 Tytuł
p = slide("1 Tytuł")
p.cell(M, 190, 900, 40, tstyle(18, RUST, bold=True), '<span style="letter-spacing:3px">DOKUMENTACJA TECHNICZNA I ANALIZA PRZEPŁYWÓW</span>')
p.cell(M, 240, 900, 120, tstyle(92, GREEN, bold=True), "fuw.lol")
text(p, M, 360, 860, 120, "Nieoficjalne, społecznościowe archiwum śmiesznych rzeczy z Wydziału Fizyki UW — "
     "memy, cytaty, legendarne zadania, zdjęcia, folklor, stare strony.", 30, INK, bold=True, f=1.25)
text(p, M, 520, 860, 260, ul([
    f"{b('Stos:')} Django 5.2 + Django REST Framework (Postgres / SQLite lokalnie, tokeny) · SvelteKit 2 / Svelte 5 (SPA, adapter-static) · LaTeX.js + KaTeX w przeglądarce · marked + DOMPurify.",
    f"{b('Wdrożenie:')} Hetzner + Coolify + Cloudflare, trzy kontenery (Postgres, Django/gunicorn, nginz ze zbudowaną aplikacją).",
    f"{b('Wygląd')} celowo kopiuje www.fuw.edu.pl (Tahoma 13 px, zielony pasek #175e4c, ramki 1 px #ccc, ✱ przed nagłówkami) — to część żartu.",
    f"{b('Ten dokument:')} architektura, model danych, role, cykl życia wpisu, zaufani i tablica moderacji, eskalacja do NASK, czat, wehikuł czasu, bezpieczeństwo (po przeglądzie z 16.09.2026), wdrożenie, testy i analiza przepływów z rekomendacjami.",
], 10), 20)
text(p, M, 830, 860, 60, mu(f"Zrzuty ekranu pochodzą z działającej instancji deweloperskiej z treścią demo (postacie są fikcyjne). Stan na {TODAY}."), 17)
shot(p, 1030, 190, 780, "home.png", max_h=760, caption="Strona główna — „Aktualności” Wydziału, tylko śmieszniej.")

# ------------------------------------------------------------------------------- 2 Mapa serwisu
p = slide("2 Mapa serwisu")
head(p, "Mapa serwisu", "Wszystkie strony i to, kto je widzi")
cols = [
    ("Każdy (bez konta)", GREEN_L, GREEN, [("/", "Strona główna"), ("/przegladaj", "Przeglądaj + szukaj"), ("/wpis/[slug]", "Wpis"), ("/ludzie, /ludzie/[slug]", "Osoby folkloru"),
        ("/os-czasu", "Oś czasu"), ("/losowe", "Losowy wpis"), ("/czat", "Czat (pisze każdy)"), ("/o-archiwum", "O archiwum"), ("/logowanie, /rejestracja", "Konto"), ("/?czas=…", "Wehikuł czasu")]),
    ("Zalogowany", AMBER_L, "#c98f1e", [("/dodaj", "Dodaj wpis → kolejka"), ("/edytuj/[slug]", "Edycja własnego wpisu"), ("/moje", "Moje wpisy + statusy"), ("/konto", "Weryfikacja afiliacji"), ("/potwierdz?token=", "Potwierdzenie adresu"), ("wpis", "Reakcje, komentarze, zgłoszenia")]),
    ("Zaufany (adres FUW/UW/PAN)", BLUE_L, BLUE, [("/dodaj", "Publikuje od ręki"), ("wpis / czat", "Ukryj · przywróć"), ("wpis / czat", "☢ Opcja nuklearna"), ("/tablica", "Tablica moderacji"), ("wpis / czat", "🚨 Zgłoś do NASK")]),
    ("Administracja (is_staff)", RUST_L, RUST, [("/moderacja", "Kolejka + zgłoszenia"), ("wpis", "Odnuklearnij, wyróżnij"), ("/admin/", "Panel Django")]),
    ("Head-admin (superuser)", "#efe6f6", "#5b3a8a", [("/eskalacje", "Decyzje NASK"), ("/admin/", "Widzi także treści eskalowane")]),
]
cw, gap = 330, 22
x = M
for title, fill, stroke, items in cols:
    card(p, x, 175, cw, 760, fill, stroke, title=title, title_fill="#ffffff")
    yy = 225
    for path, label in items:
        p.cell(x + 14, yy, cw - 28, 58, rstyle("#ffffff", stroke) + "align=left;verticalAlign=middle;spacingLeft=10;fontSize=16;",
               lh(f"{b(label)}<br>{mu(code(path))}", 1.25))
        yy += 66
    x += cw + gap
text(p, M, 950, W - 2 * M, 60, mu("Każdy wyższy poziom dziedziczy wszystko z niższych. Staff jest zawsze zaufany. Uprawnienia rozstrzyga ZAWSZE backend (archive/moderation.py, escalation/visibility.py) — frontend tylko chowa przyciski."), 17)

# ------------------------------------------------------------------------------- 3 Architektura
p = slide("3 Architektura")
head(p, "Architektura", "Przeglądarka → Cloudflare → nginx → Django → Postgres; pliki na wolumenie, dowody poza nim")
n_browser = node(p, M, 220, 280, 150, f"Przeglądarka<br>{mu('SvelteKit SPA · LaTeX.js · KaTeX<br>marked + DOMPurify<br>token w localStorage')}", "#ffffff", GREEN, 16)
n_cf = node(p, 470, 240, 200, 110, f"Cloudflare<br>{mu('proxy, TLS, cache')}", BOX, MUTED, 16)
n_web = node(p, 770, 180, 320, 230, f"web (nginx)<br>{mu('zbudowana aplikacja (200.html)<br>/api /admin /static → proxy<br>/media z wolumenu: nosniff,<br>CSP sandbox, PDF = attachment<br>CSP · X-Frame-Options · Referrer-Policy')}", "#ffffff", GREEN, 15)
n_api = node(p, 1190, 180, 320, 230, f"api (Django + gunicorn)<br>{mu('DRF, TokenAuthentication<br>archive · accounts · board · escalation<br>throttle w cache plikowym<br>RealIpMiddleware (hops, Cloudflare)')}", "#ffffff", GREEN, 15)
n_db = node(p, 1610, 240, 220, 110, f"db<br>{mu('Postgres 16<br>(SQLite lokalnie)')}", "#ffffff", GREEN, 16)
p.edge(n_browser, n_cf, "https", straight=True); p.edge(n_cf, n_web, ":80", straight=True); p.edge(n_web, n_api, ":8000", straight=True); p.edge(n_api, n_db, "SQL", straight=True)
n_media = node(p, 770, 500, 240, 90, f"wolumen media<br>{mu('załączniki, UUID.ext')}", AMBER_L, "#c98f1e", 15)
n_cache = node(p, 1050, 500, 240, 90, f"wolumen cachedata<br>{mu('liczniki throttle, wayback')}", AMBER_L, "#c98f1e", 15)
n_ev = node(p, 1330, 500, 500, 90, f"wolumen evidence {r('(poza /media)')}<br>{mu('pakiety dowodowe NASK + kwarantanna plików')}", RUST_L, RUST, 15)
p.edge(n_web, n_media, "odczyt", dashed=True, color=MUTED, straight=True, exit_="exitX=0.3;exitY=1;", entry="entryX=0.3;entryY=0;")
p.edge(n_api, n_media, "zapis", dashed=True, color=MUTED, straight=True, exit_="exitX=0.15;exitY=1;", entry="entryX=0.8;entryY=0;")
p.edge(n_api, n_cache, "", dashed=True, color=MUTED, straight=True, exit_="exitX=0.5;exitY=1;", entry="entryX=0.5;entryY=0;")
p.edge(n_api, n_ev, "", dashed=True, color=RUST, straight=True, exit_="exitX=0.85;exitY=1;", entry="entryX=0.3;entryY=0;")
n_ia = node(p, M, 500, 280, 90, f"Internet Archive<br>{mu('web.archive.org — wehikuł czasu')}", BLUE_L, BLUE, 15)
n_smtp = node(p, M, 620, 280, 90, f"SMTP<br>{mu('mail weryfikacyjny (24 h, jednorazowy)')}", BLUE_L, BLUE, 15)
n_nask = node(p, M, 740, 280, 90, f"Dyżurnet.pl / NASK<br>{mu('RĘCZNIE, przez head-admina')}", BLUE_L, BLUE, 15)
p.edge(n_browser, n_ia, "iframe (sandbox)", dashed=True, color=BLUE, straight=True, exit_="exitX=0.5;exitY=1;", entry="entryX=0.5;entryY=0;")
p.edge(n_api, n_ia, "", dashed=True, color=BLUE, straight=True, exit_="exitX=0;exitY=0.9;", entry="entryX=1;entryY=0.3;")
p.edge(n_api, n_smtp, "", dashed=True, color=BLUE, straight=True, exit_="exitX=0;exitY=1;", entry="entryX=1;entryY=0.3;")
text(p, 420, 640, 440, 320, ul([
    f"{b('Niebieskie przerywane strzałki z api:')} /api/wayback/ (proxy z cache 24 h) i mail weryfikacyjny; do NASK aplikacja nie wysyła nic sama.",
    f"{b('Jedno wejście HTTP:')} Traefik (Coolify) kieruje domenę na web:80; api i db nie mają portów publicznych.",
    f"{b('Sesja:')} token DRF w localStorage, wysyłany tylko do PUBLIC_API_BASE_URL; logout kasuje token po obu stronach.",
    f"{b('Pliki są sądzone po bajtach')} (archive/validators.py); JPEG/PNG/WebP tracą metadane (GPS).",
], 7), 15)
text(p, 900, 640, 930, 320, ul([
    f"{b('Kwarantanna:')} pliki treści eskalowanej lub po opcji nuklearnej są PRZENOSZONE z /media do wolumenu evidence — zapamiętany URL odpowiada 404 (escalation/quarantine.py). Cache Cloudflare trzeba wyczyścić po URL-u osobno.",
    f"{b('Adres klienta:')} X-Forwarded-For czytany od prawej wg FUWLOL_PROXY_HOPS (Traefik + nginx = 2); CF-Connecting-IP honorowany tylko z FUWLOL_CLOUDFLARE=1, gdy origin przyjmuje ruch wyłącznie z Cloudflare.",
    f"{b('Kompilacja LaTeX-a dzieje się w przeglądarce')} — na serwerze nie ma TeX-a; ten sam kod renderuje edytor („Rekompiluj”) i stronę wpisu.",
], 7), 15)

# ------------------------------------------------------------------------------- 4 Model danych
p = slide("4 Model danych")
head(p, "Model danych", "backend/archive · accounts · board · escalation")
def ent(x, y, w, h, name, fields, fill="#ffffff", stroke=GREEN):
    cid = p.cell(x, y, w, h, rstyle(fill, stroke))
    p.cell(x, y, w, 34, rstyle(stroke, stroke) + f"align=center;verticalAlign=middle;fontSize=17;fontColor=#ffffff;fontStyle=1;", name)
    text(p, x + 10, y + 40, w - 20, h - 44, "<br>".join(fields), 14, BODY, f=1.35)
    return cid
e_post = ent(M, 180, 330, 300, "archive.Post", ["slug, catalog_no (FUW-0001), title, summary", "format: text | latex · body", "year + year_precision (exact/approx/decade) + date_note", "source_note, source_url", "status: pending | published | rejected | hidden | nuked", "featured, views, submitted_by, reviewed_by, review_note", "category → Category · people ↔ Person · tags ↔ Tag"])
e_att = ent(470, 180, 260, 120, "Attachment", ["post →, file (UUID.ext), original_name", "kind: image/pdf/audio/video/other", "caption, order"])
e_cmt = ent(470, 330, 260, 150, "Comment", ["post →, parent → (wątek), author →", "format, body, attachments (≤3 obrazy)", "is_removed (nagrobek)", "moderation: visible | hidden | nuked"])
e_react = ent(780, 180, 220, 100, "Reaction", ["post →, user →", "kind: lol/classic/wow/cringe", "1 na użytkownika i wpis"])
e_rep = ent(780, 310, 220, 170, "Report", ["post →, reporter → (może być None)", "reason: privacy/wrong/offensive/", "copyright/other · note · contact_email", "resolved"])
e_act = ent(1050, 180, 270, 130, "ModerationAction", ["actor →, post → | comment →", "action: hide/nuke/restore/unnuke/", "publish/reject · reason · previous_status"])
e_tax = ent(1050, 340, 270, 140, "Category · Person · Tag", ["Category: slug, name, emoji, description", "Person: slug, name, role, bio, is_listed", "Tag: slug, name (wolne)"], fill="#ffffff", stroke=MUTED)
e_prof = ent(1370, 180, 460, 150, "accounts.Profile / TrustedDomain / EmailVerification", ["Profile: user, affiliation_email, affiliation_domain →, verified_at, reputation", "TrustedDomain: domain, institution, kind, match_subdomains, is_active", "EmailVerification: user, email, token (32 B), created_at, used_at"], stroke=BLUE)
e_msg = ent(1370, 360, 220, 150, "board.Message", ["author → | nick (gość)", "format, body (≤ 2048 zn.)", "ip_hash (HMAC z solą)", "is_hidden, hidden_by"], stroke=BLUE)
e_brep = ent(1610, 360, 220, 150, "board.Report", ["message →, reporter → | ip_hash", "reason: spam/offensive/illegal/", "privacy/other · note", "resolved, upheld"], stroke=BLUE)
e_esc = ent(M, 560, 520, 190, "escalation.Escalation", ["content_type + object_id → Post | Comment | Message (GenericFK)", "requested_by →, reason (WYMAGANY)", "status: pending | approved | declined", "decided_by →, decision_note, decided_at", "evidence_ref = SHA-256 zamrożonego pakietu (EVIDENCE_ROOT/&lt;id&gt;/)", "unikalność: jedno pending na cel"], stroke=RUST)
for a, bb in [(e_att, e_post), (e_cmt, e_post), (e_react, e_post), (e_rep, e_post), (e_act, e_post)]:
    p.edge(a, bb, "", color=MUTED, straight=True, exit_="exitX=0;exitY=0.5;", entry="entryX=1;entryY=0.5;")
p.edge(e_brep, e_msg, "", color=MUTED, straight=True, exit_="exitX=0;exitY=0.5;", entry="entryX=1;entryY=0.5;")
p.edge(e_esc, e_post, "cel: Post | Comment | Message", color=RUST, dashed=True, exit_="exitX=0.3;exitY=0;", entry="entryX=0.3;entryY=1;")
text(p, 660, 560, 1170, 400, ul([
    f"{b('Pliki są cytowane po nazwie oryginalnej:')} wpis i jego pliki przychodzą w JEDNYM żądaniu multipart; treść mówi {code('![](zdjecie.jpg)')} albo {code('\\\\includegraphics{{zdjecie.jpg}}')}, a czytnik mapuje nazwę na URL (render/media.ts). Brak endpointu „wgraj najpierw” = brak osieroconych plików.",
    f"{b('Nagrobek zamiast kasowania:')} usunięty komentarz zostaje w wątku jako placeholder (is_removed), żeby odpowiedzi nie straciły rodzica.",
    f"{b('Data rozmyta:')} rok + dokładność (dokładnie / około / dekada) + notatka — folklor rzadko ma datę.",
    f"{b('Każde przejście stanu pisze ModerationAction')} — tablica pokazuje kto, kiedy, dlaczego; restore wraca do stanu sprzed pierwszego ukrycia.",
    f"{b('Eskalacja nie ma osobnych kolumn na 3 typy celów:')} GenericForeignKey, więc aplikacja escalation nie importuje modeli archive/board — jest liściem, o który pytają inni.",
], 10), 17)

# ------------------------------------------------------------------------------- 5 Role
p = slide("5 Role i uprawnienia")
head(p, "Role i uprawnienia", "Kto może co — jedna tabela, backend jest jej źródłem prawdy")
Y, N = "✓", "—"
rows = [["Czynność", "Gość", "Użytkownik", "Zaufany", "Staff", "Head-admin"],
        ["Czytanie opublikowanych wpisów, osób, osi czasu, czatu, RSS", Y, Y, Y, Y, Y],
        ["Pisanie na czacie (nick gościa ≠ istniejący login)", Y, Y, Y, Y, Y],
        ["Zgłoszenie wpisu / wiadomości (także anonimowo: „dotyczy mnie”)", Y, Y, Y, Y, Y],
        ["Dodanie wpisu → kolejka moderacji", N, Y, "od ręki", "od ręki", "od ręki"],
        ["Edycja własnego wpisu (pending/rejected/published → wraca do kolejki)", N, Y, Y, Y, Y],
        ["Reakcje, komentarze (tekst / LaTeX, ≤ 3 obrazy)", N, Y, Y, Y, Y],
        ["Ukryj / przywróć wpis, komentarz, wiadomość; tablica moderacji", N, N, Y, Y, Y],
        ["☢ Opcja nuklearna (powód wymagany); cofnięcie", N, N, "tylko nałożyć", Y, Y],
        ["Kolejka moderacji: publikuj / odrzuć / wyróżnij; panel Django", N, N, N, Y, Y],
        ["🚨 Zgłoś do NASK (treść znika dla wszystkich, także staff)", N, N, Y, Y, Y],
        ["Decyzja NASK (zatwierdź / odrzuć), wgląd w dowody, treści eskalowane", N, N, N, N, Y],
        ["Widzi treść po opcji nuklearnej", N, N, "tylko stub", Y, Y],
        ["Widzi e-mail i notatkę zgłaszającego", N, N, "tylko powód", Y, Y]]
table(p, M, 180, [760, 190, 190, 200, 200, 200], rows, row_h=44, size=16)
text(p, M, 820, W - 2 * M, 150, ul([
    f"{b('Zaufany')} = konto z potwierdzonym adresem w domenie z tabeli TrustedDomain (fuw.edu.pl, uw.edu.pl, student.uw.edu.pl, instytuty PAN…). Dopasowanie ścisłe: lowercase ASCII, jedno @, subdomeny tylko tam, gdzie wiersz na to pozwala; {code('x@fuw.edu.pl.evil.com')} nie przechodzi.",
    f"{b('Staff')} = Django is_staff. {b('Head-admin')} = is_superuser — jedyny poziom, na którym „staff” przestaje cokolwiek znaczyć (escalation/visibility.py). Nadawaj go jak najmniejszej liczbie osób.",
    f"{b('Reputacja')} (Profile.reputation): +1 gdy moderator potwierdzi ukrycie, do którego przyczyniło się Twoje zgłoszenie, −1 gdy je cofnie. Jeszcze niczego nie blokuje — jest zapisem, nie dźwignią.",
], 8), 16)

# ------------------------------------------------------------------------------- 6 Cykl życia wpisu
p = slide("6 Cykl życia wpisu")
head(p, "Cykl życia wpisu", "Od formularza do archiwum — i z powrotem, jeśli trzeba")
s_form = node(p, M, 190, 200, 80, f"Formularz /dodaj<br>{mu('tekst lub LaTeX + ≤ 6 plików')}", "#ffffff", MUTED, 15, color=BODY)
s_pend = node(p, 380, 190, 200, 80, f"pending<br>{mu('czeka na moderatora')}", AMBER_L, "#c98f1e", 17)
s_pub = node(p, 680, 190, 200, 80, f"published<br>{mu('publiczny, ma FUW-nnnn')}", GREEN_L, GREEN, 17)
s_rej = node(p, 380, 350, 200, 80, f"rejected<br>{mu('z notatką dla autora')}", BOX, MUTED, 17)
s_hid = node(p, 680, 350, 200, 80, f"hidden<br>{mu('na tablicy; każdy zaufany widzi')}", BLUE_L, BLUE, 17)
s_nuk = node(p, 680, 510, 200, 80, f"nuked ☢<br>{mu('tylko staff; pliki w kwarantannie')}", RUST_L, RUST, 17)
s_esc = node(p, 380, 510, 200, 80, f"eskalowany 🚨<br>{mu('nikt poza head-adminem')}", "#efe6f6", "#5b3a8a", 17)
p.edge(s_form, s_pend, "użytkownik", straight=True)
p.edge(s_form, s_pub, "zaufany / staff", exit_="exitX=0.5;exitY=0;", entry="entryX=0.5;entryY=0;")
p.edge(s_pend, s_pub, "publikuj", straight=True)
p.edge(s_pend, s_rej, "odrzuć", straight=True, exit_="exitX=0.3;exitY=1;", entry="entryX=0.3;entryY=0;")
p.edge(s_rej, s_pend, "autor poprawia", color=MUTED, dashed=True, straight=True, exit_="exitX=0.7;exitY=0;", entry="entryX=0.7;entryY=1;")
p.edge(s_pub, s_hid, "ukryj", straight=True, exit_="exitX=0.3;exitY=1;", entry="entryX=0.3;entryY=0;")
p.edge(s_hid, s_pub, "przywróć", color=MUTED, dashed=True, straight=True, exit_="exitX=0.7;exitY=0;", entry="entryX=0.7;entryY=1;")
p.edge(s_hid, s_nuk, "☢", straight=True, exit_="exitX=0.3;exitY=1;", entry="entryX=0.3;entryY=0;")
p.edge(s_nuk, s_hid, "odnuklearnij (staff)", color=MUTED, dashed=True, straight=True, exit_="exitX=0.7;exitY=0;", entry="entryX=0.7;entryY=1;")
p.edge(s_pub, s_nuk, "☢", exit_="exitX=1;exitY=0.5;", entry="entryX=1;entryY=0.5;")
p.edge(s_hid, s_esc, "🚨 z każdego stanu", color="#5b3a8a", straight=True, exit_="exitX=0;exitY=0.7;", entry="entryX=1;entryY=0.3;")
text(p, M, 630, 780, 330, ul([
    f"{b('Numer katalogowy')} FUW-nnnn nadawany przy pierwszej publikacji; nie zmienia się przy ukryciu i przywróceniu.",
    f"{b('Odrzucony wpis')} autor może poprawić — edycja wraca do kolejki. Notatka moderatora jest widoczna tylko dla autora i staff (poprawka z przeglądu 16.09).",
    f"{b('Edycja opublikowanego wpisu')} przez zwykłego użytkownika też wraca do kolejki; zaufany i staff edytują w miejscu.",
    f"{b('Każda strzałka pisze ModerationAction')} (kto, kiedy, powód, stan poprzedni); „przywróć” czyta ten dziennik, żeby wrócić do stanu sprzed pierwszego ukrycia — nigdy prosto do „published”, jeśli wpis nie był zatwierdzony.",
    f"{b('Limity:')} 30 wpisów/h na konto, 25 MB na plik, 6 plików; komentarze 60/h (nowy limit).",
], 8), 16)
shot(p, 980, 180, 390, "dodaj.png", crop=(190, 130, 1090, 1600), max_h=560, caption="/dodaj — dane wpisu, pliki, treść z podglądem")
shot(p, 1390, 180, 440, "moderacja.png", crop=(190, 150, 1090, 400), caption="/moderacja — kolejka: publikuj / odrzuć / ukryj / wyróżnij")
shot(p, 1390, 470, 440, "moje.png", crop=(190, 120, 1090, 430), caption="/moje — autor widzi status każdego swojego wpisu")

# ------------------------------------------------------------------------------- 7 Zaufani
p = slide("7 Weryfikacja afiliacji")
head(p, "Zaufani użytkownicy", "Potwierdzony adres instytucjonalny daje narzędzia moderacji — bez kolejki i bez etatu")
v1 = node(p, M, 200, 230, 90, "1. Rejestracja<br>" + mu("login + hasło (walidatory Django)"), "#ffffff", GREEN, 16)
v2 = node(p, 360, 200, 230, 90, "2. /konto → adres<br>" + mu("np. imie@fuw.edu.pl"), "#ffffff", GREEN, 16)
v3 = node(p, 630, 200, 260, 90, "3. Sprawdzenie domeny<br>" + mu("TrustedDomain, ścisłe dopasowanie"), "#ffffff", GREEN, 16)
v4 = node(p, 930, 200, 230, 90, "4. Mail z linkiem<br>" + mu("token 32 B, 24 h, jednorazowy"), "#ffffff", GREEN, 16)
v5 = node(p, 1200, 200, 230, 90, "5. /potwierdz?token=<br>" + mu("ponowne sprawdzenie domeny"), "#ffffff", GREEN, 16)
v6 = node(p, 1470, 200, 230, 90, "6. zaufany ✓<br>" + mu("Profile.verified_at"), GREEN_L, GREEN, 16)
for a, bb in [(v1, v2), (v2, v3), (v3, v4), (v4, v5), (v5, v6)]:
    p.edge(a, bb)
text(p, M, 330, 760, 600, ul([
    f"{b('Dlaczego adres, a nie prośba do admina:')} członkostwo w społeczności jest sprawdzalne bez etatu moderatora — a to właśnie moderator jest wąskim gardłem takiego archiwum.",
    f"{b('Co daje status zaufanego:')} wpisy publikują się od ręki; ukrywanie jednym kliknięciem (treść trafia na tablicę, gdzie każdy zaufany może ją przywrócić); opcja nuklearna dla treści nielegalnych lub obrzydliwie obraźliwych; zgłoszenie do NASK.",
    f"{b('Czego nie daje:')} kolejki moderacji, cofnięcia opcji nuklearnej, wglądu w e-mail zgłaszającego, decyzji NASK.",
    f"{b('Adres służy tylko do weryfikacji')} — nie jest pokazywany nikomu; w API wraca zamaskowany ({code('j***@fuw.edu.pl')}). Domena może zostać wyłączona w panelu — wtedy {code('is_trusted')} gaśnie, choć afiliacja pozostaje zapisana.",
    f"{b('Limity:')} 5 maili/h na konto; logowanie 20/min na adres IP {b('i')} 10/min na login (nowe — przeciw rozproszonemu zgadywaniu hasła jednego konta).",
    f"{b('Zostawione otwarte:')} brak resetu hasła (nie ma jeszcze maili poza weryfikacją); brak blokady konta po n nieudanych próbach — throttle liczy próby, nie porażki.",
], 9), 16)
shot(p, 920, 330, 910, "konto.png", crop=(190, 120, 1090, 600), caption="/konto — weryfikacja afiliacji z listą akceptowanych domen")

# ------------------------------------------------------------------------------- 8 Tablica
p = slide("8 Tablica moderacji")
head(p, "Tablica moderacji i opcja nuklearna", "Wszystko, co zniknęło ze strony publicznej — z podpisem, datą i powodem")
shot(p, M, 180, 900, "tablica.png", crop=(190, 120, 1090, 720), caption="/tablica — ukryte widzi każdy zaufany; nuklearne to dla niego tylko stub (numer, kto, kiedy, dlaczego)")
rows = [["Stan", "Publiczność", "Zaufany", "Staff", "Head-admin"],
        ["hidden", "404", "pełna treść + kto/kiedy/dlaczego", "pełna treść", "pełna treść"],
        ["nuked ☢", "404", "stub: FUW-nnnn, aktor, powód", "pełna treść", "pełna treść"],
        ["eskalowany 🚨", "404", "404 (nawet dla zgłaszającego)", "404", "pełna treść + pakiet dowodowy"],
        ["komentarz hidden", "placeholder", "treść", "treść", "treść"],
        ["komentarz pod wpisem nuked", "404", "403 (należy do treści, której nie widzi)", "treść", "treść"]]
table(p, 1030, 180, [200, 110, 250, 120, 120], rows, row_h=46, size=14)
text(p, 1030, 480, 800, 480, ul([
    f"{b('Jedna reguła, dwie postacie:')} {code('can_see_post(user, post)')} dla pojedynczego obiektu i {code('visible_posts_q(user)')} dla querysetów — trzymane razem, żeby lista i szczegół nie mogły się rozjechać.",
    f"{b('Serializery wygaszają, a nie widoki filtrują:')} to, czego wywołujący nie może zobaczyć, jest wymazywane w serializerze (body='', author=''), więc żaden nowy endpoint nie musi pamiętać o regule.",
    f"{b('Opcja nuklearna:')} powód obowiązkowy, zapis w dzienniku, pliki przenoszone do kwarantanny; cofnąć może tylko staff, a przywrócenie wraca do stanu sprzed ukrycia.",
    f"{b('Nie ma kasowania.')} Nagrobki, ukrycia, stuby — archiwum pamięta, że coś było, nawet gdy nie pokazuje co.",
    f"{b('Panel Django')} też respektuje eskalację (escalation/adminmixin.py) — poprawka z 16.09: wcześniej staff widział eskalowany wpis w /admin/.",
], 8), 15)

# ------------------------------------------------------------------------------- 9 NASK
p = slide("9 Eskalacja do NASK")
head(p, "Eskalacja do NASK (Dyżurnet.pl)", "Jedyny stan, w którym „zaufany” i nawet „staff” nic nie znaczą")
lanes = [("Zaufany / moderator", GREEN_L, GREEN), ("System (escalation)", BOX, MUTED), ("Head-admin", "#efe6f6", "#5b3a8a"), ("Dyżurnet.pl", BLUE_L, BLUE)]
lx, lw = M, 400
lane_x = {}
for i, (name, fill, stroke) in enumerate(lanes):
    x = M + i * (lw + 10)
    p.cell(x, 170, lw, 40, rstyle(stroke, stroke) + "align=center;verticalAlign=middle;fontSize=17;fontColor=#ffffff;fontStyle=1;", name)
    p.cell(x, 210, lw, 340, rstyle(fill, stroke, dashed=True))
    lane_x[i] = x
def step(lane, y, label, h=64, **kw):
    return node(p, lane_x[lane] + 15, y, lw - 30, h, label, "#ffffff", lanes[lane][2], 15, bold=False, color=BODY, **kw)
a1 = step(0, 225, "🚨 „Zgłoś do NASK” + POWÓD (wymagany) w oknie potwierdzenia")
a2 = step(1, 225, "Escalation(pending) + zamrożony pakiet: manifest.json (treść, autor, e-mail, data) + kopie plików, chmod 400, SHA-256 → evidence_ref", 90)
a3 = step(1, 330, "Pliki z /media → kwarantanna; treść znika ze WSZYSTKICH list, RSS, tablicy, panelu Django; zwykła moderacja = 403/404")
a4 = step(2, 225, "Link „NASK (n)” w nawigacji; /eskalacje: powód, pakiet, pliki do pobrania przez uwierzytelniony widok", 80)
a5 = step(2, 330, "Decyzja: ZATWIERDŹ (pakiet kompletny) albo ODRZUĆ (to nie sprawa dla NASK), z notatką", 64)
a6 = step(3, 330, "Zgłoszenie przez formularz dyzurnet.pl — RĘCZNIE, przez człowieka. Aplikacja nigdy sama nie kontaktuje się z instytucją.", 90)
a7 = step(1, 440, "approved: treść niewidoczna na stałe, pliki zostają w kwarantannie<br>declined: treść wraca pod zwykłą moderację, pliki wracają (chyba że ☢)", 90)
a8 = step(0, 440, "Powrót do tablicy — ukryj / przywróć działają znowu (po „odrzuć”)", 64)
p.edge(a1, a2); p.edge(a2, a3); p.edge(a2, a4, exit_="exitX=1;exitY=0.5;", entry="entryX=0;entryY=0.5;"); p.edge(a4, a5); p.edge(a5, a6, "", straight=True, exit_="exitX=1;exitY=0.5;", entry="entryX=0;entryY=0.5;")
p.edge(a5, a7, "", straight=True, exit_="exitX=0;exitY=0.8;", entry="entryX=1;entryY=0.2;"); p.edge(a7, a8, "", dashed=True, color=MUTED, straight=True, exit_="exitX=0;exitY=0.5;", entry="entryX=1;entryY=0.5;")
text(p, M, 580, 1000, 380, ul([
    f"{b('Dlaczego dowody są zamrażane w tej samej transakcji:')} autor może usunąć konto, moderator przywrócić wiadomość, plik może zostać podmieniony — pakiet ma przeżyć treść. Manifest i każdy plik mają SHA-256; katalog jest tylko do odczytu.",
    f"{b('Fail-closed:')} jeśli sprawdzenie „czy eskalowane?” rzuci wyjątek, odpowiedź brzmi „tak” — błąd w tym pliku ma powodować znikanie treści, nigdy jej ponowne pokazanie.",
    f"{b('Brak wyroczni:')} zaufany, który sam eskalował, dostaje 404, nie „już eskalowane”; identyfikatory eskalacji są sekwencyjne, ale każdy nie-head-admin dostaje 403 zanim widok cokolwiek wyszuka.",
    f"{b('Limit:')} 10 eskalacji/dobę na konto. {b('Rejestr:')} wiersz w bazie + linia w logu „security” (kompromitacja samej bazy nie zaciera śladu).",
], 8), 15)
shot(p, 1120, 580, 710, "eskalacje.png", crop=(190, 150, 1090, 745), max_h=380, caption="/eskalacje — pakiet dowodowy i dwie decyzje (widok tylko dla head-admina)")

# ------------------------------------------------------------------------------- 10 Czat
p = slide("10 Czat")
head(p, "Czat (shoutbox)", "Pisze każdy, także bez konta — więc obrona jest tania i wielowarstwowa")
shot(p, M, 180, 820, "czat.png", crop=(190, 120, 1090, 500), caption="/czat — nick gościa, tekst lub LaTeX, 2048 znaków, linki tak, obrazki nie")
c1 = node(p, 950, 180, 260, 70, "Wiadomość<br>" + mu("gość lub konto"), "#ffffff", GREEN, 15)
c2 = node(p, 950, 290, 260, 70, "Zgłoszenie (każdy)<br>" + mu("spam / obraźliwe / niezgodne z prawem / dotyczy mnie / inne"), "#ffffff", GREEN, 14)
c3 = node(p, 1290, 290, 260, 70, "3 różne konta ZAUFANE<br>" + mu("→ auto-ukrycie, hidden_by = None"), AMBER_L, "#c98f1e", 14)
c4 = node(p, 1290, 400, 260, 70, "Moderator: ukryj / przywróć<br>" + mu("rozstrzyga wszystkie otwarte zgłoszenia"), "#ffffff", GREEN, 14)
c5 = node(p, 1290, 510, 260, 70, "Reputacja zgłaszających<br>" + mu("+1 (ukrycie utrzymane) / −1 (cofnięte); nie dla samego moderatora"), BLUE_L, BLUE, 13)
c6 = node(p, 1600, 290, 230, 70, "🚨 do NASK<br>" + mu("zaufany / staff; znika dla wszystkich"), RUST_L, RUST, 14)
p.edge(c1, c2); p.edge(c2, c3, "kworum"); p.edge(c3, c4); p.edge(c4, c5); p.edge(c2, c6, exit_="exitX=1;exitY=0.2;", entry="entryX=0;entryY=0.5;")
text(p, 950, 620, 880, 340, ul([
    f"{b('Warstwy obrony:')} honeypot (pole website), limity 20/h gość i 60/h konto na adres IP, ≤ 5 linków, zakaz obrazków (![, &lt;img, \\\\includegraphics, data:image), nick gościa ≠ żaden login — także po NFKC, wielkości liter, kropkach i mieszaniu alfabetów (Pіotr z cyrylicą і).",
    f"{b('Zgłoszenia gości nigdy nie ukrywają same')} — IP to nie tożsamość (NAT, wifi kampusu); liczą się tylko konta zaufane, każde raz.",
    f"{b('Ukryj, nie kasuj:')} hidden_by = None znaczy „zrobiły to zgłoszenia”, hidden_by = użytkownik — „moderator”. Moderator widzi liczbę otwartych zgłoszeń (⚑ n); gość nie widzi, ilu innych już zgłosiło.",
    f"{b('Adres IP')} jest przechowywany tylko jako HMAC-SHA256 z osobną solą (FUWLOL_IP_SALT) — wystarcza, by poznać „to samo miejsce”, nie by je odtworzyć.",
    f"{b('Stronicowanie po id')} (before / since), bo strumień rośnie od góry; RSS z 50 ostatnich, bez eskalowanych.",
], 8), 15)

# ------------------------------------------------------------------------------- 11 Wehikuł czasu
p = slide("11 Wehikuł czasu")
head(p, "Wehikuł czasu", "Jedna czysta funkcja eraFor(date) i rejestr wersji układu strony")
eras = [("przed Wielkim Wybuchem", "nic — „przed” tam nie istnieje", "#ffffff", MUTED), ("−13,8 mld → −66 mln", "Wielki Wybuch (animacja), dinozaury", "#efe6f6", "#5b3a8a"),
        ("→ 1400", "malowidła naskalne", BOX, MUTED), ("1400 → 1795", "łacina, notatki Kopernika", BLUE_L, BLUE), ("1795 → 1816", "gazeta po niemiecku (pruska Warszawa)", BLUE_L, BLUE),
        ("1816 → 1998", "gazeta po polsku (UW od 1816)", AMBER_L, "#c98f1e"), ("20.01.1998 → 10.09.2026", "fuw.edu.pl z Internet Archive (iframe, sandbox)", GREEN_L, GREEN), ("od 10.09.2026", "nasze archiwum z tego dnia (?before=), układ z versions.ts", GREEN, GREEN)]
x = M; ew = (W - 2 * M - 7 * 8) / 8
for i, (rng, what, fill, stroke) in enumerate(eras):
    p.cell(x, 190, ew, 120, rstyle(fill, stroke) + f"align=center;verticalAlign=middle;fontSize=14;fontColor={'#ffffff' if fill == GREEN else INK};", lh(f"{b(rng)}<br>{what}", 1.25))
    x += ew + 8
p.cell(M, 320, W - 2 * M, 6, rstyle(GREEN, "none"))
text(p, M, 350, 860, 420, ul([
    f"{b('Dwa wejścia, bo jedno nie uniesie obu zadań:')} {code('&lt;input type=date&gt;')} dla dat, które przeglądarka przyjmie, i pole tekstowe dla reszty osi (−13800000000 nie mieści się w kalendarzu). Lista „Skoki” wpisuje wartość do właściwego pola.",
    f"{b('Werdykt przed podróżą:')} pod formularzem stoi „Trafisz do: …” — użytkownik wie, co zobaczy, zanim kliknie „Jedź!”.",
    f"{b('Internet Archive:')} {code('/api/wayback/')} rozwiązuje najbliższy zrzut po dacie (walidacja {code('\\\\d{{8}}')}, stałe host i ścieżka — bez SSRF, timeout 8 s, cache 24 h); ramka ma sandbox bez allow-top-navigation i referrerpolicy=no-referrer.",
    f"{b('versions.ts')} to rejestr układów strony: każda przyszła przebudowa dopisuje wersję i ZOSTAWIA stary komponent — dzięki temu stara data renderuje stary wygląd.",
    f"{b('Otwarte:')} niemieckie i łacińskie epoki zachowują polskie tytuły wpisów (treść nie jest tłumaczona); wehikuł ma tylko strona główna.",
], 8), 15)
shot(p, 1000, 350, 830, "home.png", crop=(190, 2330, 1090, 2610), caption="Formularz wehikułu na stronie głównej: data, rok, skoki, werdykt")
shot(p, 1000, 660, 830, "os-czasu.png", crop=(190, 120, 1090, 520), max_h=300, caption="/os-czasu — lata z liczbą wpisów, pogrupowane w dekady")

# ------------------------------------------------------------------------------- 12 Bezpieczeństwo
p = slide("12 Bezpieczeństwo")
head(p, "Bezpieczeństwo", "Trzy warstwy — i co zamknął przegląd z 16.09.2026")
def col(x, title, items, fill, stroke):
    card(p, x, 180, 560, 470, fill, stroke, title=title, title_fill="#ffffff")
    text(p, x + 14, 226, 532, 420, ul(items, 7), 14)
col(M, "Pliki i treść", [
    "Rozszerzenie z listy (bez SVG/HTML); decyzja po BAJTACH: Pillow musi zdekodować obraz (limit 40 Mpx z nagłówka — bomba dekompresyjna), PDF zaczyna się od %PDF, audio/wideo mają sygnaturę kontenera, tekst bez NUL.",
    "Nazwa na dysku = UUID + rozszerzenie; nazwa oryginalna tylko do cytowania w treści.",
    "JPEG/PNG/WebP zapisywane od nowa bez EXIF/ICC (GPS z telefonu); GIF i animowany WebP zostają (animacja to połowa memów).",
    f"{r('NOWE:')} pliki treści eskalowanej i nuklearnej przenoszone poza /media (kwarantanna) — zapamiętany URL → 404.",
    "nginx: /media z nosniff, CSP „sandbox”, PDF/txt/tex jako attachment (nigdy nie renderują się na naszym originie).",
], AMBER_L, "#c98f1e")
col(M + 580, "Renderowanie w przeglądarce", [
    "Markdown (marked) → DOMPurify z listą tagów/atrybutów; LaTeX.js → DOMPurify (bez &lt;style&gt;, formularzy, ramek); KaTeX z trust=false po sanityzacji.",
    f"{r('NOWE:')} obraz przeżywa sanityzację tylko, gdy jego src to URL naszego załącznika (albo blob: podglądu) — dotąd regex łapał tylko składnię ![](), a &lt;img&gt; i obrazy referencyjne przechodziły (piksel śledzący na każdego moderatora).",
    f"{r('NOWE:')} atrybut class niedozwolony w treści użytkownika (podszywanie się pod plakietki „Wyróżnione”, fałszywe komunikaty moderacji).",
    "Każdy link: target=_blank, rel=nofollow noopener; javascript:/data: odrzucane.",
    f"{r('NOWE:')} CSP w nginx (img-src self blob: data:, frame-src web.archive.org, frame-ancestors self), X-Frame-Options, Referrer-Policy, Permissions-Policy; HSTS z Django dla /api i /admin.",
], GREEN_L, GREEN)
col(M + 1160, "Sieć, tożsamość, limity", [
    f"{r('NOWE:')} X-Forwarded-For czytany od prawej wg liczby zaufanych proxy (FUWLOL_PROXY_HOPS); CF-Connecting-IP tylko z FUWLOL_CLOUDFLARE=1. Dotąd pierwszy (kliencki) element sterował każdym limitem na IP.",
    f"{r('NOWE:')} throttle per akcja na ViewSecie był cichym no-opem (scope czytany z widoku) — post_create 30/h, escalate 10/d i nowy comment_create 60/h działają teraz naprawdę, z testem regresji.",
    f"{r('NOWE:')} logowanie limitowane także per login (10/min); walidatory haseł: długość, lista pospolitych, nie-numeryczne, niepodobne do loginu.",
    f"{r('NOWE:')} seed_demo nie resetuje haseł istniejących kont, a poza DEBUG losuje hasła i wypisuje je raz; obraz Dockera ma FUWLOL_DEBUG=0 i odmawia startu z domyślnym SECRET_KEY.",
    f"{r('NOWE:')} e-mail i notatka zgłaszającego tylko dla staff; review_note tylko dla autora; usunięcie komentarza i liczniki respektują eskalację; panel Django ukrywa treści eskalowane.",
], RUST_L, RUST)
text(p, M, 670, W - 2 * M, 300, f"{b('Przyjęte świadomie, nie zapomniane:')} " + " · ".join([
    "token w localStorage (XSS = przejęcie sesji; CSP jest zabezpieczeniem drugiej linii, ciasteczko httpOnly to zmiana modelu auth)",
    "jedno konto zaufane może eskalować (i zablokować) dowolną treść — 10/dobę, z pełnym rejestrem; to cena szybkiego działania przy CSAM",
    "brak ClamAV (hosting go nie ma) — powiedziane, nie udawane",
    "throttle liczy próby, nie porażki — pełna blokada konta po n nieudanych wymaga własnego mechanizmu",
    "cache Cloudflare po kwarantannie trzeba wyczyścić ręcznie po URL-u",
    "kwarantanna działa dla FileSystemStorage (jeden host) — S3 wymagałoby innej implementacji",
]), 15)

# ------------------------------------------------------------------------------- 13 Wdrożenie
p = slide("13 Wdrożenie")
head(p, "Wdrożenie", "docker-compose: trzy kontenery, cztery wolumeny, wszystko z FUWLOL_* w środowisku")
d_web = node(p, M, 200, 300, 130, f"web {mu('(frontend/Dockerfile)')}<br>{mu('nginx + zbudowana aplikacja<br>port 80 → Traefik/Coolify')}", GREEN_L, GREEN, 16)
d_api = node(p, 520, 200, 300, 130, f"api {mu('(backend/Dockerfile)')}<br>{mu('gunicorn, użytkownik fuwlol (uid 1000)<br>entrypoint: migrate, collectstatic, [seed]')}", GREEN_L, GREEN, 16)
d_db = node(p, 960, 200, 220, 130, f"db<br>{mu('postgres:16-alpine, healthcheck')}", GREEN_L, GREEN, 16)
p.edge(d_web, d_api, "/api", straight=True); p.edge(d_api, d_db, "SQL", straight=True)
vols = [(M, "media", "załączniki (web: ro)", d_api, 0.2), (380, "cachedata", "throttle, wayback", d_api, 0.5),
        (670, "evidence", "dowody NASK + kwarantanna", d_api, 0.8), (960, "pgdata", "baza", d_db, 0.5)]
for x, name, what, owner, ex in vols:
    v = node(p, x, 400, 260, 70, f"{name}<br>{mu(what)}", AMBER_L, "#c98f1e", 15)
    p.edge(owner, v, "", dashed=True, color=MUTED, straight=True, exit_=f"exitX={ex};exitY=1;", entry="entryX=0.5;entryY=0;")
rows = [["Zmienna", "Znaczenie", "Domyślnie"],
        ["FUWLOL_SECRET_KEY", "klucz Django — wymagany, gdy FUWLOL_DEBUG=0 (inaczej start odmówi)", "—"],
        ["FUWLOL_DEBUG", "1 lokalnie (run.sh); obraz Dockera ustawia 0", "1 / 0 w obrazie"],
        ["FUWLOL_ALLOWED_HOSTS / CSRF_ORIGINS / CORS_ORIGINS / SITE_URL", "domena, pochodzenia, adres linków w mailach", "z FUWLOL_DOMAIN"],
        ["FUWLOL_TRUST_PROXY, FUWLOL_PROXY_HOPS, FUWLOL_CLOUDFLARE", "prawdziwy adres klienta za proxy (config/middleware.py)", "1, 2, 0"],
        ["FUWLOL_IP_SALT", "sól do hashy adresów (czat, dowody)", "= SECRET_KEY"],
        ["FUWLOL_MEDIA_ROOT / CACHE_DIR / EVIDENCE_ROOT", "ścieżki wolumenów", "/app/…"],
        ["FUWLOL_EMAIL_*", "SMTP na 587 (Hetzner blokuje 25) — mail weryfikacyjny", "puste"],
        ["FUWLOL_SEED_DEMO", "1 = załóż treść demo przy starcie (wyłącz potem)", "0"]]
table(p, M, 510, [540, 900, 300], rows, row_h=40, size=14)
text(p, 1260, 200, 570, 290, ul([
    f"{b('Lokalnie:')} {code('./setup.sh')} (venv, zależności, migracje, seed, npm install) i {code('./run.sh')} (API :8000, front :5173). Konta demo dziekan / doktorant / student, hasło fuwlol123 — tylko w DEBUG.",
    f"{b('Produkcja:')} {code('cp .env.example .env')}, uzupełnij sekrety, {code('docker compose up -d')} albo Coolify z tym samym plikiem; szczegóły deploy/HETZNER.md.",
    f"{b('Kopie:')} pgdata + media + evidence. Bez evidence utrata pakietu = w bazie zostaje tylko hash.",
], 8), 15)

# ------------------------------------------------------------------------------- 14 Testy
p = slide("14 Testy i weryfikacja")
head(p, "Testy i weryfikacja", "Co jest sprawdzane automatycznie, a co ręcznie w przeglądarce")
stat = lambda x, num, cap, fill=GREEN_L, color=GREEN: (card(p, x, 190, 400, 150, fill), text(p, x + 20, 205, 360, 70, num, 46, color, bold=True, f=1.05), text(p, x + 20, 270, 360, 60, cap, 16))
stat(M, "135", "testów backendu (Django/DRF), w tym 23 nowe po przeglądzie 16.09")
stat(M + 430, "0 / 0", "błędów i ostrzeżeń svelte-check (238 plików)")
stat(M + 860, "34", "kroków smoke testu w przeglądarce (frontend/e2e/smoke.mjs)", AMBER_L, "#b4530a")
stat(M + 1290, "49", "zrzutów z 4 ról × 2 szerokości — frontend/e2e/survey.mjs, 0 błędów konsoli", BLUE_L, BLUE)
text(p, M, 370, 860, 560, ul([
    f"{b('backend/…/tests.py')}: uploady (bomba dekompresyjna, exe w .png, EXIF), uprawnienia (właściciel, staff), moderacja (hide/nuke/restore, stany, dziennik), zaufani (domeny, spoofing, token), czat (nick, limity, obrazki, zgłoszenia, kworum, reputacja), eskalacja (IDOR, „staff to nie head-admin”, zamrożenie, wyścig decyzji, dowody).",
    f"{b('escalation/test_hardening.py')} (nowe): panel Django, kwarantanna plików (eskalacja, nuke, odrzucenie przy nuke), wyrocznie (liczniki, zgłoszenie, usunięcie komentarza, parent), e-mail zgłaszającego, review_note, throttle wpisów/komentarzy/logowania per login, nicki-homoglify, sól hasha IP, seed nie resetuje haseł.",
    f"{b('Uruchomienie:')} {code('cd backend &amp;&amp; ../.venv/bin/python manage.py test')} · {code('cd frontend &amp;&amp; npm run check &amp;&amp; npm run build')} · przy działających serwerach {code('npm run e2e')} i {code('node e2e/survey.mjs')}.",
    f"{b('Czego testy nie łapią:')} wyglądu — stąd survey.mjs i oglądanie zrzutów (tak znaleziono zdublowane wpisy na stronie głównej i szare placeholdery na telefonie); realnej konfiguracji proxy na serwerze (FUWLOL_PROXY_HOPS trzeba sprawdzić raz na produkcji, np. logując REMOTE_ADDR).",
], 9), 15)
shot(p, 980, 370, 850, "przegladaj.png", crop=(190, 120, 1090, 700), max_h=540, caption="/przegladaj — filtry w URL-u, więc wyszukiwanie jest linkiem")

# ------------------------------------------------------------------------------- 15 Analiza przepływów
p = slide("15 Analiza przepływów i rekomendacje")
head(p, "Analiza przepływów", "Trzy ścieżki użytkownika, ich tarcia i co warto zrobić następne")
flows = [
    ("Gość: „szukam tego mema z kolokwium”", GREEN_L, GREEN, [
        "Strona główna → Przeglądaj (filtry w URL) → wpis → reakcja wymaga konta.",
        f"{b('Tarcie:')} na telefonie filtry zajmują cały ekran zanim pojawi się pierwszy wynik.",
        f"{b('Tarcie:')} lista osób i oś czasu to jeden klik dalej niż wyszukiwarka — mało kto tam trafia.",
        f"{b('Zrobione:')} placeholdery bez obrazka znikają na telefonie; strona główna nie powtarza wyróżnionych.",
        f"{b('Rekomendacja:')} zwinięte filtry na telefonie („Filtruj (2)”), wyszukiwanie w nagłówku zamiast lupy prowadzącej do /przegladaj."]),
    ("Student: „dodam wpis”", AMBER_L, "#c98f1e", [
        "Rejestracja → /dodaj (dane, pliki, treść z podglądem) → pending → /moje pokazuje status.",
        f"{b('Tarcie:')} długi formularz bez autozapisu — odświeżenie strony gubi treść.",
        f"{b('Tarcie:')} o odrzuceniu autor dowiaduje się tylko, jeśli sam zajrzy do /moje; nie ma maila ani znacznika „nowe”.",
        f"{b('Tarcie:')} brak resetu hasła — zablokowane konto to koniec.",
        f"{b('Rekomendacja:')} szkic w localStorage; mail/„dzwonek” o decyzji; reset hasła (SMTP już jest do weryfikacji)."]),
    ("Zaufany / staff: „coś tu nie powinno wisieć”", RUST_L, RUST, [
        "Wpis lub czat → Ukryj (dialog z powodem) → tablica; opcja nuklearna z powodem; NASK z powodem → head-admin.",
        f"{b('Zrobione:')} okna potwierdzenia zamiast prompt(); NASK odróżniony wizualnie; strona /eskalacje z dowodami i dwiema decyzjami; licznik „NASK (n)” w nawigacji.",
        f"{b('Tarcie:')} tablica i kolejka nie powiadamiają — moderator musi zaglądać; head-admin o eskalacji dowiaduje się dopiero po zalogowaniu.",
        f"{b('Tarcie:')} przy 12 linkach nawigacja staff zawija się w dwie linie.",
        f"{b('Rekomendacja:')} mail do head-admina przy eskalacji (najpilniejsze), dzienny mail „n w kolejce”, grupa „Moderacja ▾” w nawigacji."]),
]
x = M
for title, fill, stroke, items in flows:
    card(p, x, 175, 560, 640, fill, stroke, title=title, title_fill="#ffffff")
    text(p, x + 14, 222, 532, 590, ul(items, 8), 15)
    x += 580
text(p, M, 830, W - 2 * M, 150, f"{b('Kolejność proponowana:')} 1) mail o eskalacji do head-admina i reset hasła (ten sam SMTP) · 2) autozapis szkicu i powiadomienie o decyzji · 3) zwinięte filtry i wyszukiwanie w nagłówku na telefonie · 4) grupa „Moderacja” w nawigacji · 5) research rynkowy (docs/research-brief-gemini.md) zanim dojdą kolejne funkcje — najpierw sprawdzić, skąd studenci naprawdę przynieśliby treść.", 16)

# ------------------------------------------------------------------------------- write
total = len(pages)
for i, pg in enumerate(pages, 1):
    frame(pg, i, total)
    # ramka jest dopisywana na końcu listy komórek, a ma być pod spodem: przenieś 4 ostatnie na początek
    pg.cells = pg.cells[-4:] + pg.cells[:-4]
out = HERE / "fuwlol-dokumentacja.drawio"
out.write_text('<mxfile host="fuw.lol" type="device">' + "".join(pg.xml() for pg in pages) + "</mxfile>", encoding="utf-8")
print(f"{out.name}: {total} stron, {out.stat().st_size // 1024} KB")
