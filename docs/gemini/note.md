# docs/gemini — notatka o tych plikach (17.09.2026)

Pięć raportów z Gemini Deep Research, każdy ~25–30 KB, odpowiedzi na część pytań z
`docs/research-brief-gemini.md`. Tekst jest jednym akapitem bez podziałów (Gemini eksportuje tak
listy i tabele — czytelniejsze po `fold -s -w 120`). Poniżej: co jest w każdym, co z tego weszło do
kodu, czego świadomie nie, i jak używać ich dalej.

## Co jest w plikach i co z nich wynika dla fuw.lol

| Plik | O czym | Wartość dla projektu | Co poszło do kodu (commit „Gemini research”) |
|---|---|---|---|
| `latex safety.txt` | wektory ataków w potoku Markdown + KaTeX + LaTeX.js: ReDoS, bomby makr TeX-a, mXSS przez MathML/SVG, limity KaTeX, Web Worker z twardym budżetem CPU | **najwyższa** — trafia dokładnie w nasz stos i przewidziała realny błąd | (1) maths wycinane z tekstu **przed** marked — `$$\sum_i *a*$$` wychodziło jako `<em>a</em>`, potwierdzone testem w node; (2) KaTeX `maxExpand: 1000`, `maxSize: 25`, `trust: false`; (3) DOMPurify dla LaTeX.js: `FORBID_TAGS foreignObject / annotation-xml / maction`, `xlink:href`, `ALLOW_DATA_ATTR: false`; (4) `archive/latexguard.py` + `lib/render/guard.ts`: zakaz `\def`-rodziny, rekurencyjnych `\newcommand`, limity długości i liczby środowisk — na wpisach, komentarzach i czacie |
| `latex serach.txt` | wyszukiwanie: polska fleksja vs. składnia LaTeX-a, kanonizacja wzorów, porównanie SQLite FTS5 / Postgres tsvector+pg_trgm / Meilisearch na małym VPS-ie | wysoka, konkretna architektura | `archive/search.py`: dwie kolumny pochodne na `Post` (`search_text` = złożona proza bez diakrytyków, `search_math` = wzory po kanonizacji), zapytanie przechodzi przez to samo; `x^2` znajduje `x^{2}`, `\dfrac` znajduje `\frac`, `calkowanie` znajduje „Całkowanie” |
| `legal.txt` | memy a art. 29¹ pr. aut. (parodia, nie cytat), wizerunek wykładowcy (art. 81 — NIE jest osobą powszechnie znaną, V CSK 51/17), materiały dydaktyczne, RODO (NSA III OSK 2603/23 o listach ocen), DSA art. 6/16/17/20 zamiast art. 14 uśude, lista punktów do regulaminu | wysoka — to jest lista rzeczy, których serwis nie miał | regulamin na `/o-archiwum`; formularz zgłoszenia jako zawiadomienie z art. 16 (e-mail + oświadczenie o dobrej wierze, `Report.good_faith`, znacznik „formalne (DSA)” w kolejce); oświadczenie o prawach przy dodawaniu wpisu (`Post.rights_confirmed`, wymagane); powód i ścieżka odwołania dla autora w „Moich wpisach” i na wpisie (art. 17/20); ostrzeżenie o wizerunku przy „Osobach” |
| `konkurencja.txt` | MIT Zephyr/SIPB, UCBMFET, Oxfess, Fizz, Sidechat: weryfikacja tożsamości, cykl życia konta absolwenta, karma i jej patologie, moderacja rówieśnicza z konsensusem, pięć mechanizmów zaangażowania bez algorytmu | średnia — potwierdza wybory (feed chronologiczny, weryfikacja adresem, brak karmy), daje pomysły | nic w kodzie; wnioski niżej |
| `history.txt` | odzyskiwanie folkloru 1995–2010: Wayback CDX API (`collapse=digest`, `id_`, `resumeKey`), korpus Usenetu `usenet-uat-pl`, mojibake ISO-8859-2/CP1250 (`charset-normalizer` + `ftfy`), html5lib, ekstrakcja „rodzynków”, MinHash do deduplikacji, art. 26² pr. aut. (TDM) | średnia — to osobny projekt badawczy, nie funkcja serwisu | nic w kodzie; wnioski niżej |

## Jak z nich korzystać dalej

- **Traktuj jak notatki dobrego stażysty, nie jak źródło.** Gemini nie podaje linków, więc każdy
  numer CVE, sygnatura wyroku i nazwa pakietu wymaga sprawdzenia, zanim się na nią powołasz.
  Sprawdziłem to, co weszło do kodu: mechanizmy (mXSS przez `annotation-xml`, bomby makr, `maxExpand`
  KaTeX-a) się zgadzają z tym, jak te biblioteki działają; sygnatur sądowych i CVE (np.
  „CVE-2025-23207”) **nie** weryfikowałem — w regulaminie cytuję tylko te, które są powszechnie
  znane (V CSK 51/17, NSA III OSK 2603/23), i przed publikacją serwisu warto, żeby spojrzał na to
  ktoś z prawem.
- **Pytaj o mechanizmy i decyzje, nie o kod.** Fragmenty kodu w raportach (aiohttp do CDX,
  `SecureRenderEngine` z Web Workerem, `LatexNormalizer`) są poglądowe: np. worker z DOMPurify nie
  ma sensu, bo DOMPurify potrzebuje DOM-u (raport sam to zauważa), a LaTeX.js też generuje DOM,
  więc do workera nie wejdzie bez jsdom. Użyłem ich jako specyfikacji, nie jako źródła do wklejenia.
- **Dobre następne pytania** (na tym samym briefie): (a) czy uczelnia może mieć pretensje o kopię
  wyglądu fuw.edu.pl — raport prawny tego nie dotknął; (b) proces Dyżurnet.pl krok po kroku — jest
  tylko wzmianka; (c) gdzie DZIŚ żyją memy studentów FUW (grupy FB, Discord) — raport o konkurencji
  mówi o MIT i Stanfordzie, nie o Hożej; (d) ile kosztuje i co daje `hunspell-pl` w Postgresie na
  Hetznerze — druga połowa architektury wyszukiwania.
- **Odświeżaj raz na semestr.** DSA i orzecznictwo się zmieniają; raport prawny ma datę ważności.
  Trzymaj wersje z datą w nazwie pliku (`legal-2026-09.txt`), a nie nadpisuj.

## Moje zdanie o każdym

- **latex safety** — najlepszy z pięciu. Poziom „ktoś naprawdę zna KaTeX i DOMPurify”, i przewidział
  konkretny błąd, który mieliśmy (marked psuł `*` i `_` w formułach). Jedyna rzecz, której nie da
  się wziąć: Web Worker z twardym `terminate()` jako obrona przed zawieszeniem — LaTeX.js buduje
  DOM, więc musiałby dostać emulację DOM-u w workerze. Zamiast tego jest guard po obu stronach;
  to zamyka bomby makr, ale NIE zamyka patologicznie dużego, legalnego dokumentu — limit 60 000
  znaków i 400 środowisk to kompromis, nie dowód. Jeśli kiedyś przejdziemy na LaTeX.js w workerze
  (wymaga `linkedom`/`jsdom` w bundlu), to jest miejsce, gdzie warto wrócić do tego raportu.
- **latex serach** — solidny i uczciwy o zasobach (Meilisearch na 1 GB RAM to OOM). Rekomendacja
  „przejdź na Postgres + hunspell + pg_trgm” jest właściwa i docelowa; ja zrobiłem połowę, która
  działa na SQLite i Postgresie bez zmiany schematu zapytań. Druga połowa to: `hunspell-pl` w
  obrazie Postgresa, `SearchVectorField` + `GinIndex(opclasses=['gin_trgm_ops'])` na tych samych
  dwóch kolumnach. Kanonizacja wzorów w raporcie gubi `\alpha x` → `\alphax`; poprawiłem.
- **legal** — najbardziej użyteczny praktycznie: lista punktów do regulaminu jest w zasadzie gotowa
  do użycia i taką dostała strona „O archiwum”. Dwie rzeczy, o których raport milczy, a które
  są dla nas kluczowe: (1) parodia całej strony Wydziału jako ryzyko znaku towarowego/dóbr
  osobistych osoby prawnej, (2) status „postaci fikcyjnych” — czy fikcyjny „prof. Hamiltonian”
  chroni przed art. 81 i 23 KC, jeśli wszyscy wiedzą, o kogo chodzi. Oba do dopytania.
- **konkurencja** — ładna synteza, ale o Stanfordzie i Oksfordzie. Trzy rzeczy, które warto z niej
  wziąć: moderacja z konsensusem (u nas: 3 zaufane zgłoszenia ukrywają czat — to już jest;
  rozważyć to samo dla wpisów zamiast jednego kliknięcia „ukryj”), brak karmy (raport
  dokumentuje, jak karma niszczy nisze — nasz `reputation` jest zapisem, nie dźwignią, i niech
  tak zostanie), oraz „shibbolethy” — hermetyczność jako cecha, nie wada. Zero-knowledge
  weryfikacja absolwentów (ZK-Email) to ciekawostka, nie plan.
- **history** — to jest plan osobnego projektu („odzyskaj rodzynki ze studenci.fuw.edu.pl
  1998–2008”), nie ulepszenie serwisu. Wartościowe konkrety: parametry CDX API, korpus
  `usenet-uat-pl`, `ftfy` do mojibake. Jeśli ktoś to podejmie, wynik powinien wchodzić do archiwum
  jako zwykłe wpisy z `source_url` do Wayback — model danych już to unosi (`year_precision`,
  `source_note`). Uwaga prawna z raportu (art. 26² — wyjątek TDM dla uczelni) NIE dotyczy fuw.lol,
  bo nie jesteśmy jednostką naukową.

## Czego nie zrobiłem i dlaczego

- Web Worker + `terminate()` dla LaTeX.js — patrz wyżej (DOM w workerze).
- Postgres FTS — wymaga Postgresa również lokalnie (dziś SQLite) i pakietu `hunspell-pl` w obrazie;
  dwie kolumny są już gotowe pod to.
- Potwierdzenie odbioru zgłoszenia mailem (art. 16 ust. 4 DSA) — nie ma jeszcze backendu poczty
  poza weryfikacją; ta sama brakująca cegiełka co reset hasła i alert do head-admina.
- Moderacja wpisów przez konsensus (jak na czacie) — decyzja produktowa, nie techniczna.
