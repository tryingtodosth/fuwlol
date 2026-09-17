# fuw.lol — Archiwum Wydziału Fizyki UW

Nieoficjalne, społecznościowe archiwum śmiesznych rzeczy z Wydziału Fizyki Uniwersytetu
Warszawskiego: memy, cytaty, legendarne zadania, zdjęcia, historie, skany, folklor, stare
strony. Wygląd celowo kopiuje www.fuw.edu.pl (Tahoma 13 px, zielony pasek `#175e4c`, ramki
1 px `#ccc`, ✱ przed nagłówkami) — to część żartu.

**Stos:** Django 5.2 + Django REST Framework (SQLite, tokeny) · SvelteKit 2 / Svelte 5 (SPA,
`adapter-static`) · LaTeX.js + KaTeX w przeglądarce · marked + DOMPurify.

## Uruchomienie

```bash
./setup.sh   # venv, zależności, migracje, treści demo, npm install
./run.sh     # API :8000, front :5173 — Ctrl+C zatrzymuje oba
```

Konta demo: `dziekan` (administracja i head-admin), `doktorant` (zaufany) i `student`, hasło `fuwlol123`
(tylko na serwerze deweloperskim — poza `FUWLOL_DEBUG=1` seed losuje hasła i wypisuje je raz).
Panel Django: `/admin/`. Mail weryfikacyjny w trybie deweloperskim ląduje w konsoli backendu.
Porty zajęte? `FUWLOL_CORS_ORIGINS` + `frontend/.env` (`PUBLIC_API_BASE_URL`) sterują adresami.

## Co jest

- **Wpisy** w dwóch formatach: *tekst* (Markdown + wzory `$…$` + obrazy) albo *LaTeX*
  (edytor w stylu Overleafa: źródło z numerami linii, podgląd kompilowany w przeglądarce,
  panel błędów, lista plików z wstawianiem `\includegraphics`). Do 6 plików na wpis
  (obrazy, PDF, audio, wideo, `.txt`/`.tex`, 25 MB). Pliki są sprawdzane po zawartości,
  JPEG/PNG tracą metadane (GPS z telefonu). Nazwa pliku jest jego odnośnikiem w treści.
- **Moderacja**: wpis czeka na moderatora (staff publikuje od ręki); kolejka w `/moderacja`
  i w panelu Django; zgłoszenia (także anonimowe: „dotyczy mnie, proszę usunąć”).
- **Społeczność**: reakcje (lol / klasyk / wow / cringe), komentarze wątkowe — też tekst
  lub LaTeX, z obrazami.
- **Przeglądanie**: kategorie, osoby (postacie folkloru), tagi, oś czasu (lata z niepewnością:
  dokładnie / około / dekada), szukanie, losowy wpis, sygnatury `FUW-0001`.
- **Czat** (`/czat`): stary shoutbox — pisze każdy, także bez konta; linki i wzory tak, obrazki
  nie; 2048 znaków; długie wiadomości zwijają się po 100 znakach; kanał RSS (`/api/board/rss/`).
- **Zaufani użytkownicy**: potwierdzenie adresu w domenie FUW/UW/PAN (`/konto`) daje wyższe
  uprawnienia — wpisy bez kolejki, ukrywanie treści jednym kliknięciem (trafiają na **tablicę
  moderacji** `/tablica`, widoczną dla wszystkich zaufanych) i opcja nuklearna dla treści
  nielegalnych lub obrzydliwie obraźliwych (wtedy treść widzi już tylko administracja).
  Szczegóły: `backend/MODERATION-API.md`.
- **Eskalacja do NASK** (`🚨 Zgłoś do NASK` na wpisie, komentarzu i wiadomości na czacie, dla
  zaufanych i staff): treść znika dla WSZYSTKICH — także dla moderatorów — a jej kopia (treść,
  autor, pliki, SHA-256) zostaje zamrożona jako pakiet dowodowy; pliki trafiają do kwarantanny
  poza `/media`. Decyduje **head-admin** (konto `is_superuser`) na `/eskalacje`: zatwierdza
  (i sam, ręcznie, zgłasza przez Dyżurnet.pl — aplikacja nigdy nie kontaktuje się z instytucją)
  albo odrzuca (treść wraca pod zwykłą moderację). Zgłoszenia na czacie: każdy może zgłosić
  wiadomość; trzy zgłoszenia od różnych zaufanych kont ukrywają ją same, a decyzja moderatora
  potem podnosi lub obniża reputację zgłaszających.
- **Wehikuł czasu** na stronie głównej: data z życia fuw.lol → archiwum z tego dnia
  (rejestr wersji układu strony w `versions.ts` to grunt pod „jak strona wyglądała”);
  1998–2026 → zrzut fuw.edu.pl z Internet Archive (po animacji Wielkiego Wybuchu);
  wcześniej → gazeta po polsku, po niemiecku, notatki Kopernika po łacinie, malowidła
  naskalne, dinozaury, a przed Wielkim Wybuchem — nic.

## Struktura

```
backend/   config/ (settings, urls, middleware — adres za proxy)  accounts/ (rejestracja, logowanie, zaufani)  archive/ (modele, API, walidacja plików, wayback, seed_demo, testy)
           board/ (czat, zgłoszenia, reputacja)  escalation/ (eskalacja do NASK: dowody, kwarantanna plików, widoczność, mixin panelu Django)
frontend/  src/lib/{api,types,auth}  src/lib/render/{markdown,latex,media}  src/lib/components/{editor,timemachine,…}  src/routes/…
deploy/    HETZNER.md — Hetzner + Coolify + Cloudflare; Dockerfiles w backend/ i frontend/, docker-compose.yml
docs/      fuwlol-dokumentacja.drawio (+ .pdf, render/NN.png) — dokumentacja techniczna po polsku z prawdziwymi zrzutami,
           generowana przez build_docs.py + render_docs.mjs; research-brief-gemini.md — brief do researchu rynkowego
```

Testy: `cd backend && ../.venv/bin/python manage.py test` (135) · `cd frontend && npm run check && npm run build`
· przy działających serwerach: `npm run e2e` (smoke, 34 kroki), `npm run e2e:escalation` (eskalacja od kliknięcia
do decyzji) i `npm run survey` (zrzuty każdej strony dla 4 ról × 2 szerokości — do oglądania, nie do asercji).
Więcej o decyzjach: `DESIGN.md`.
