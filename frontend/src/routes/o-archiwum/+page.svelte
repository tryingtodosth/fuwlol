<script lang="ts">
	// Static, and deliberately so: this page is the house rules, not data.
</script>

<svelte:head><title>O archiwum — fuw.lol</title></svelte:head>

<div class="box">
	<h1 class="box__title">O archiwum</h1>
	<div class="box__body">
		<p>
			<strong>fuw.lol</strong> to nieoficjalne, robione po godzinach archiwum folkloru Wydziału Fizyki
			Uniwersytetu Warszawskiego: memów, cytatów z wykładów, legendarnych zadań, zdjęć z korytarzy,
			ogłoszeń, które kiedyś wisiały na drzwiach, i całej reszty rzeczy, które inaczej przepadną
			razem z rocznikiem, który je pamiętał.
		</p>
		<p>
			<strong>To nie jest strona Wydziału.</strong> Wygląda podobnie, bo tak jest śmieszniej. Wydział
			ma swoją stronę pod adresem
			<a href="https://www.fuw.edu.pl" target="_blank" rel="noopener">www.fuw.edu.pl</a> i nie ma z tym
			miejscem nic wspólnego.
		</p>
	</div>
</div>

<div class="box">
	<h2 class="box__title">Zasady</h2>
	<div class="box__body">
		<ul>
			<li><strong>Śmieszne ≠ złośliwe.</strong> Śmiejemy się z sytuacji, nie z ludzi.</li>
			<li>
				<strong>Żadnych danych prywatnych.</strong> Numery telefonów, adresy, numery indeksu, oceny,
				sprawy zdrowotne — nie tutaj. Nie doksujemy nikogo, nawet w formie żartu.
			</li>
			<li>
				<strong>Każdy może poprosić o usunięcie.</strong> Przy każdym wpisie jest link
				<em>Zgłoś / poproś o usunięcie</em> — działa też bez konta. Jeśli jesteś osobą z wpisu i wolisz
				zniknąć, to wystarczy.
			</li>
			<li>
				<strong>Wszystko przechodzi przez moderację</strong> przed publikacją. Nowy wpis czeka w
				kolejce; zobaczysz go w <a href="/moje">Moich wpisach</a> ze statusem.
			</li>
			<li>
				<strong>Materiały z zajęć</strong> wrzucamy z głową: krótki cytat i anegdota tak, cudze skrypty
				w całości nie.
			</li>
		</ul>
	</div>
</div>

<div class="box">
	<h2 class="box__title">Formaty wpisów</h2>
	<div class="box__body">
		<p>Wpis można napisać na dwa sposoby:</p>
		<ul>
			<li>
				<strong>Tekst (Markdown)</strong> — zwykłe pisanie, z pogrubieniem, listami i linkami. Obrazy
				wstawia się po nazwie załączonego pliku, np. <code>![](zdjecie.jpg)</code>. Matematyka między
				znakami dolara, np. <code>$E=mc^2$</code>, renderuje się KaTeX-em.
			</li>
			<li>
				<strong>LaTeX</strong> — dla tych, którzy i tak myślą w LaTeX-u. Wpisujesz źródło, a
				przeglądarka je kompiluje (obsługiwany jest sensowny podrozdział LaTeX-a: struktura
				dokumentu, sekcje, listy, makra tekstowe, matematyka). Obrazy przez
				<code>\includegraphics&#123;zdjecie.jpg&#125;</code>, też po nazwie załącznika.
			</li>
		</ul>
		<p>
			Edytor działa trochę jak Overleaf: piszesz z jednej strony, a z drugiej widzisz podgląd i
			ewentualne błędy kompilacji. Komentarze można pisać tak samo — tekstem albo LaTeX-em, z
			obrazkami.
		</p>
	</div>
</div>

<div class="box">
	<h2 class="box__title">Wehikuł czasu</h2>
	<div class="box__body">
		<p>
			Na dole strony głównej stoi <strong>wehikuł czasu</strong>. Wpisujesz datę i patrzysz, jak
			wtedy wyglądał świat:
		</p>
		<ul>
			<li>
				<strong>Data z życia fuw.lol</strong> — pokazujemy archiwum takie, jakie było tamtego dnia:
				tylko te wpisy, które już wtedy były opublikowane.
			</li>
			<li>
				<strong>Data wcześniejsza</strong> — cofamy się do
				<a href="https://web.archive.org" target="_blank" rel="noopener">Internet Archive</a> i
				pokazujemy prawdziwą stronę www.fuw.edu.pl z tamtego czasu.
			</li>
			<li>
				<strong>Przed 1998</strong> — czyli zanim Wydział miał stronę — podróżujesz dalej. Im dalej,
				tym dziwniej. Nie zdradzamy, co tam jest.
			</li>
		</ul>
	</div>
</div>

<div class="box box--grey">
	<h2 class="box__title">Kontakt</h2>
	<div class="box__body">
		<p class="small">
			archiwum@fuw.lol (adres do ustawienia). W sprawach usunięcia treści najszybszy jest link
			<em>Zgłoś</em> przy wpisie — trafia prosto do kolejki moderacji.
		</p>
	</div>
</div>
