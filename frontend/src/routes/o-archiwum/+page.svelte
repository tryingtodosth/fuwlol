<script lang="ts">
	import Breadcrumb from '$lib/components/Breadcrumb.svelte';

	// Static, and deliberately so: this page is the house rules, not data.
</script>

<svelte:head><title>O archiwum — fuw.lol</title></svelte:head>

<Breadcrumb trail={[{ label: 'O archiwum' }]} />


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

<style>
	.rules { padding-left: 20px; }
	.rules li { margin: 0 0 8px; }
</style>
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

<div class="box">
	<h2 class="box__title">Regulamin <small>skrót; obowiązuje od 17.09.2026</small></h2>
	<div class="box__body">
		<ol class="rules">
			<li>
				<strong>Kim jesteśmy.</strong> fuw.lol świadczy usługę hostingu treści użytkowników w rozumieniu art. 6
				Aktu o usługach cyfrowych (DSA) i art. 14 ustawy o świadczeniu usług drogą elektroniczną: nie
				sprawdzamy wpisów z góry, odpowiadamy za nie od chwili, gdy dowiemy się, że są bezprawne. Punkt
				kontaktowy (art. 11–12 DSA): adres w sekcji „Kontakt” poniżej.
			</li>
			<li>
				<strong>Czego nie wolno wrzucać.</strong> Wizerunku kogokolwiek — także wykładowcy — bez jego wyraźnej
				zgody (art. 81 pr. aut.; wykładowca nie jest osobą powszechnie znaną). Cudzych materiałów z zajęć w
				całości: skryptów, autorskich zadań, kluczy odpowiedzi, nagrań i stenogramów wykładów (art. 27 pr. aut.
				nas nie obejmuje — nie jesteśmy uczelnią). Danych studentów: list ocen, wyników, numerów indeksu (RODO;
				wyrok NSA III OSK 2603/23). Hejtu, pomówień o czyny karalne, ataków na sferę prywatną (art. 23–24 KC,
				art. 212 i 216 KK). Śmiejemy się z sytuacji, nie z ludzi.
			</li>
			<li>
				<strong>Co wolno.</strong> Memy, cytaty, anegdoty i przeróbki mieszczą się w parodii, pastiszu i
				karykaturze (art. 29¹ pr. aut.) — o ile odnoszą się do faktów, dotyczą sfery zawodowej i zachowują
				umiar. Dodając wpis, oświadczasz, że masz do niego prawa albo działasz w tych granicach, że masz zgody
				osób na zdjęciach, i udzielasz nam nieodpłatnej, niewyłącznej licencji na przechowywanie i pokazywanie
				treści w archiwum.
			</li>
			<li>
				<strong>Zgłoszenia (art. 16 DSA).</strong> Formularz „Zgłoś / poproś o usunięcie” przy każdym wpisie.
				Formalne zawiadomienie zawiera: wyjaśnienie, dlaczego treść jest bezprawna, wskazanie wpisu (robimy to za
				Ciebie), Twój adres e-mail oraz oświadczenie o dobrej wierze. Zgłoszenie bez adresu trafia do moderacji,
				ale nie dostaniesz odpowiedzi. Zgłoszenia treści przedstawiających wykorzystywanie dzieci mogą być
				anonimowe; takie treści trafiają do NASK (Dyżurnet.pl).
			</li>
			<li>
				<strong>Decyzje i odwołania (art. 17 i 20 DSA).</strong> Autor ukrytego lub odrzuconego wpisu widzi w
				„Moich wpisach” powód i podstawę. Od decyzji można się odwołać w ciągu 14 dni na adres kontaktowy,
				podając numer wpisu (FUW-nnnn); odwołanie rozpatruje człowiek. Konta uporczywie łamiące zasady albo
				składające oczywiście bezzasadne zgłoszenia mogą zostać ograniczone lub usunięte (art. 23 DSA).
			</li>
			<li>
				<strong>Dane (RODO).</strong> Przetwarzamy login, e-mail, treści i — w czacie oraz w pakietach dowodowych
				— skrót adresu IP (HMAC z solą, nie sam adres), na podstawie art. 6 ust. 1 lit. b i f RODO. Dane
				pracowników Wydziału pojawiają się wyłącznie w zakresie ich działalności zawodowej i mogą zostać usunięte
				na wniosek (art. 17 i 21 RODO) przez formularz „Zgłoś”. Na żądanie uprawnionego organu udostępniamy to,
				co mamy (art. 15 i 18 uśude).
			</li>
			<li>
				<strong>Odpowiedzialność.</strong> Za treść wpisu odpowiada jego autor. Jeśli osoba trzecia (wykładowca,
				uczelnia, student) wystąpi z roszczeniem z powodu Twojego wpisu, zobowiązujesz się pokryć wynikłe z tego
				koszty.
			</li>
		</ol>
	</div>
</div>

<div class="box box--grey">
	<h2 class="box__title">Kontakt</h2>
	<div class="box__body">
		<p class="small">
			<a href="mailto:admin@fuw.lol">admin@fuw.lol</a> — to jest nasz punkt kontaktowy
			w rozumieniu art. 12 DSA. W sprawach usunięcia treści najszybszy jest link
			<em>Zgłoś</em> przy wpisie — trafia prosto do kolejki moderacji.
		</p>
	</div>
</div>
