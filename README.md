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

Konta demo: `dziekan` (moderator) i `student`, hasło `fuwlol123`. Panel Django: `/admin/`.

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
- **Wehikuł czasu** na stronie głównej: data z życia fuw.lol → archiwum z tego dnia
  (rejestr wersji układu strony w `versions.ts` to grunt pod „jak strona wyglądała”);
  1998–2026 → zrzut fuw.edu.pl z Internet Archive (po animacji Wielkiego Wybuchu);
  wcześniej → gazeta po polsku, po niemiecku, notatki Kopernika po łacinie, malowidła
  naskalne, dinozaury, a przed Wielkim Wybuchem — nic.

## Struktura

```
backend/   config/ (settings, urls)  accounts/ (rejestracja, logowanie)  archive/ (modele, API, walidacja plików, wayback, seed_demo, testy)
frontend/  src/lib/{api,types,auth}  src/lib/render/{markdown,latex,media}  src/lib/components/{editor,timemachine,…}  src/routes/…
deploy/    OVH.md — jak to postawić na hostingu OVH (FTP, Passenger)
```

Testy: `cd backend && ../.venv/bin/python manage.py test` · `cd frontend && npm run check && npm run build`.
Więcej o decyzjach: `DESIGN.md`.
