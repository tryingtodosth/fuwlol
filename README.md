# fuw.lol — Archiwum Wydziału Fizyki UW

Nieoficjalne, społecznościowe archiwum śmiesznych rzeczy z Wydziału Fizyki Uniwersytetu
Warszawskiego: memy, cytaty, legendarne zadania, zdjęcia, historie, skany, folklor, stare
strony. Wygląd celowo kopiuje fuw.edu.pl (Tahoma 13 px, bursztynowy baner, zielony pasek `#175e4c`,
ramki 1 px `#bbb` z pomarańczowymi tytułami, ✱ Wydziału przed nagłówkami) — to część żartu.

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
  JPEG/PNG tracą metadane (GPS z telefonu). Nazwa pliku jest jego odnośnikiem w treści. Osoby, przedmioty i tagi
  wybiera się w trzech podpowiadajkach; osobę, której nie ma w spisie, dodaje się wpisując jej nazwisko — pojawi
  się w `/ludzie`, gdy wpis zostanie opublikowany (moderator widzi ją na karcie wpisu jako NOWĄ).
- **Moderacja**: wpis czeka na moderatora (staff publikuje od ręki); kolejka w `/moderacja`
  i w panelu Django; zgłoszenia (także anonimowe: „dotyczy mnie, proszę usunąć”) — z e-mailem i
  oświadczeniem o dobrej wierze są formalnym zawiadomieniem w rozumieniu art. 16 DSA i tak są
  oznaczone w kolejce. Autor odrzuconego lub ukrytego wpisu widzi powód i ścieżkę odwołania; nowy
  wpis wymaga oświadczenia o prawach do treści. Regulamin: `/o-archiwum`. Treść definiująca makra
  TeX-a (`\def`, rekurencyjny `\newcommand`) jest odrzucana na każdej ścieżce zapisu — taka bomba
  zawiesiłaby przeglądarkę każdego, kto otworzy wpis.
- **Społeczność**: reakcje (lol / klasyk / wow / cringe), komentarze wątkowe — też tekst
  lub LaTeX, z obrazami.
- **Przeglądanie**: kategorie, **osoby** (`/ludzie` — spis jak na fuw.edu.pl: tytuł, nazwisko, litera,
  a zamiast pokoju i telefonu **ksywki**, czyli alternatywne tagi: wpis otagowany ksywką jest wpisem tej
  osoby; profil jak na stronie wydziału, z sylwetką zastępczą albo zdjęciem wybranym w głosowaniu),
  **przedmioty** (`/przedmioty` — zajęcia z programu studiów Wydziału, od „Fizyki elementarnej” po „Kwantową
  teorię pola”; brakujący przedmiot dopisuje się przy wpisie), tagi, oś czasu (lata z niepewnością:
  dokładnie / około / dekada), szukanie (polskie znaki i wielkość liter nie mają znaczenia; wzory są
  kanonizowane, więc `x^2` znajduje `x^{2}`, a `\frac` znajduje `\dfrac`), losowy wpis, sygnatury `FUW-0001`.
- **Czat** (`/czat`): stary shoutbox — pisze każdy, także bez konta; linki i wzory tak, obrazki
  nie; 2048 znaków; długie wiadomości zwijają się po 100 znakach; kanał RSS (`/api/board/rss/`).
- **Zgoda na wizerunek** (`/ludzie/zgoda`): osoba, której dotyczą wpisy, potwierdza ze swojej skrzynki jedną
  z trzech opcji — zdjęcia mogą być / wzmianki tak, zdjęć nie / nie chcę być w archiwum. Prośby o ukrycie
  z adresu uczelnianego działają od razu, zgoda na zdjęcia dopiero po sprawdzeniu przez administrację
  (`/moderacja/zgody`); zatwierdzony wniosek zostaje jako dowód zgody (art. 81 pr. aut., art. 7 RODO),
  cofnięcie idzie jednym linkiem na tę samą skrzynkę. Odznaka ✓ przy nazwisku to właśnie to.
- **Portrety**: przy potwierdzonej zgodzie każdy zalogowany może dodać zdjęcie osoby, a zdjęcie profilowe
  wybiera głosowanie (jeden głos na osobę, można przenieść); kolejka moderacji w `/moderacja/portrety`.
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

- **FwUMU pod `/fwumu`** — to *nie* jest archiwum. Pod adresem `fuw.lol/fwumu` stoi osobna
  aplikacja (prototyp zdrowotny MedApp z innego repozytorium), wpuszczona na ten sam adres, żeby
  ludzie, którzy już tu są, mogli ją obejrzeć i powiedzieć, co o niej myślą. Jedyne, co wysyła na
  serwer, to **uwaga o konkretnym ekranie**: rodzaj (błąd / sugestia / pomysł / komentarz) i tekst —
  a to, na którym ekranie ktoś był, dopisuje się samo, bez pytania piszącego. Uwagi czyta się w
  panelu Django (`/admin/feedback/feedback/`). Szczegóły: `deploy/OVH.md` („FwUMU") i
  `backend/feedback/CLAUDE.md`.

## Struktura

```
backend/   config/ (settings, urls, middleware — adres za proxy)  accounts/ (rejestracja, logowanie, zaufani)  archive/ (modele, API, walidacja plików, wayback, seed_demo, testy)
           board/ (czat, zgłoszenia, reputacja)  escalation/ (eskalacja do NASK: dowody, kwarantanna plików, widoczność, mixin panelu Django)
           feedback/ (uwagi o ekranach aplikacji FwUMU spod /fwumu — jedno POST, bez odczytu przez API)
           consent/ (zgoda na wizerunek: wnioski osób, kolejka, dowód zgody)  portraits/ (zdjęcia osób i głosowanie na zdjęcie profilowe)
           share/ (podglądy linków dla scraperów pod /share/…, sitemap.xml)
frontend/  src/lib/{api,types,auth}  src/lib/render/{markdown,latex,media}  src/lib/components/{editor,timemachine,…}  src/routes/…
deploy/    OVH.md — runbook produkcji (OVHcloud VPS w Warszawie, Caddy, Cloudflare, R2, Brevo) i lista sprawdzeń po wdrożeniu;
           Caddyfile, firewall.sh, backup.sh; HETZNER.md — zastąpiony plan Coolify. Dockerfiles w backend/ i frontend/,
           docker-compose.yml (lokalnie / Coolify) i docker-compose.prod.yml (to, co działa na fuw.lol; wdraża .github/workflows/deploy.yml)
docs/      fuwlol-dokumentacja.drawio (+ .pdf, render/NN.png) — dokumentacja techniczna po polsku z prawdziwymi zrzutami,
           generowana przez build_docs.py + render_docs.mjs; research-brief-gemini.md — brief do researchu rynkowego
           gemini/ — pięć raportów Gemini Deep Research + note.md (co z nich weszło do kodu, jak ich używać dalej)
```

Testy: `cd backend && ../.venv/bin/python manage.py test` (374) · `cd frontend && npm run check && npm run build`
· przy działających serwerach: `npm run e2e` (smoke, 34 kroki), `npm run e2e:escalation` (eskalacja od kliknięcia
do decyzji), `npm run e2e:research` (wzory w Markdownie, wyszukiwanie LaTeX-a, zgłoszenie DSA, oświadczenie o prawach),
`npm run e2e:render-guard` (treść, która ominęła `check_source` inną drogą niż API — np. panel administracyjny —
nigdy nie wykonuje się w przeglądarce czytelnika) i `npm run survey` (zrzuty każdej strony dla 4 ról × 2 szerokości
— do oglądania, nie do asercji).

## Dokumentacja

| Plik | Co w nim jest |
|---|---|
| `CLAUDE.md` | kontrakt inżynierski: zasady, komendy, pułapki — dla każdego, kto zmienia kod (także dla agentów) |
| `backend/CLAUDE.md`, `frontend/CLAUDE.md`, `backend/<app>/CLAUDE.md`, `frontend/e2e/CLAUDE.md` | zasady i pułapki lokalne dla danej części |
| `DESIGN.md` | *dlaczego* każdy podsystem jest taki, jaki jest |
| `PRODUCT.md` | czym archiwum jest i nie jest, role, decyzje produktowe, co zostawione otwarte |
| `LEGAL.md` | prawo, na które odpowiada kod: dwa rodzaje zdjęcia treści, zgoda na wizerunek, RODO, DSA, Dyżurnet |
| `SECURITY.md` | stan bezpieczeństwa i zaakceptowane ryzyka |
| `test.md` | każdy zestaw testów i skrypt przeglądarkowy: co sprawdza, jak go uruchomić |
| `backend/MODERATION-API.md` | API warstwy zaufanych, moderacji, eskalacji, wysyłki do R2 i czatu |
| `deploy/OVH.md` | jak serwis działa na produkcji i jak go wdrożyć |
| `docs/` | dokumentacja techniczna po polsku (draw.io + PDF) i raporty badawcze Gemini z notatką, co z nich weszło do kodu |
