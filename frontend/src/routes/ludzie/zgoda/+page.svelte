<script lang="ts">
	/** The explainer behind the ✓ badge. Static, and deliberately so: this page is what the
	 * badge MEANS, and a meaning that is fetched can be wrong in a way a meaning that is
	 * written cannot. Every legal claim on it is sourced, because the whole page exists to
	 * be read by somebody deciding whether to trust us with their face. */
	import ConsentBadge from '$lib/components/ConsentBadge.svelte';
	import { WISHES } from '$lib/consent';
</script>

<svelte:head><title>Odznaka „zgoda na wizerunek” — fuw.lol</title></svelte:head>

<div class="box">
	<h1 class="box__title">Odznaka „zgoda na wizerunek”</h1>
	<div class="box__body">
		<p>
			Przy niektórych nazwiskach w <a href="/ludzie">spisie osób</a> stoi
			<ConsentBadge consent="granted" />. Znaczy ona dokładnie tyle: <strong
				>ta osoba sama, ze swojej skrzynki, powiedziała nam, że zdjęcia z nią mogą tu być</strong
			> — a my to sprawdziliśmy na tyle, na ile da się sprawdzić adres e-mail.
		</p>
		<p><strong>Odznaka nie jest orderem. Jest podpisem.</strong></p>
	</div>
</div>

<div class="box">
	<h2 class="box__title"><span>Czego odznaka <em>nie</em> znaczy</span></h2>
	<div class="box__body">
		<ul>
			<li>
				<strong>Nie znaczy, że ktoś popiera to, co tu o nim jest.</strong> Zgoda dotyczy wizerunku, nie
				treści. Każdy pojedynczy wpis można nadal zgłosić — link „Zgłoś / poproś o usunięcie” jest pod
				każdym z nich i działa tak samo, z odznaką i bez.
			</li>
			<li>
				<strong>Nie znaczy „na zawsze”.</strong> Zgodę można cofnąć w każdej chwili, jednym kliknięciem
				w link, który przychodzi na tę samą skrzynkę. Nie trzeba się z tego tłumaczyć.
			</li>
			<li>
				<strong>Nie znaczy, że my kogoś rozpoznaliśmy.</strong> Sprawdzamy, czy adres wygląda
				wiarygodnie — nie legitymujemy nikogo. Wiemy o tym i mówimy to wprost.
			</li>
			<li>
				<strong>Brak odznaki nie znaczy nic złego.</strong> Większość osób w archiwum nigdy o niej nie
				słyszała. „Nie wiemy” to uczciwa odpowiedź i tak jest zapisana.
			</li>
		</ul>
	</div>
</div>

<div class="box">
	<h2 class="box__title">Trzy wybory i co dokładnie robią</h2>
	<div class="box__body">
		<p>Na stronie każdej osoby jest pudełko „Jesteś tą osobą?”. Są w nim trzy opcje:</p>
		<ul>
			{#each WISHES as w (w.value)}
				<li><strong>{w.label}</strong> — {w.hint}</li>
			{/each}
		</ul>
		<p>
			„Ukryjemy” znaczy: wpis znika ze strony publicznej i trafia na tablicę moderacji.
			<strong>Ukryty, nie skasowany</strong> — i mówimy to wprost, bo różnica jest istotna. Wpis o
			kimś nie zawsze jest bezprawny w całości: bywa cytatem, który jest w porządku bez nazwiska,
			albo zdjęciem, które jest w porządku po kadrowaniu. Co z nim dalej, decyduje człowiek, jeden
			wpis po drugim — i właśnie dlatego to trwa dłużej niż kliknięcie.
		</p>
		<p>
			Wpisy ukryte na czyjś wniosek dostają w rejestrze moderacji notatkę „na wniosek osoby, której
			wpis dotyczy”. <strong>Bez Twojego adresu</strong> — moderator widzi powód, nie skrzynkę.
		</p>
	</div>
</div>

<div class="box">
	<h2 class="box__title">Jak to zdobyć (i jak oddać)</h2>
	<div class="box__body">
		<ol>
			<li>Na stronie osoby otwierasz „Jesteś tą osobą?”, podajesz adres e-mail i wybierasz opcję.</li>
			<li>
				Dostajesz link. Kliknięcie w niego jest jedynym dowodem, jaki mamy, że to Twoja skrzynka.
				Link działa 24 godziny i tylko raz.
			</li>
			<li>
				Wniosek ogląda administracja. Sprawdza rzeczy przyziemne: czy domena jest uczelniana, czy w
				adresie siedzi Twoje nazwisko, czy ktoś już wcześniej zgłaszał się do tej samej strony.
				<strong>Adres rzadko pasuje do ksywki</strong>, więc brak dopasowania niczego nie przesądza —
				to sygnały, nie wyrok.
			</li>
			<li>Decyzja idzie na ten sam adres. Przy zgodzie dostajesz w niej link do ustawień.</li>
		</ol>
		<p>
			<strong>Prośby o ukrycie działają szybciej niż zgody.</strong> Jeśli piszesz z adresu w domenie
			Wydziału, uczelni albo instytutu, „zdjęć nie” i „nie chcę być w archiwum” wchodzą w życie od
			razu, jeszcze zanim ktokolwiek to przejrzy — a administracja sprawdza to potem i może cofnąć.
			Odwrotnie nie robimy tego nigdy: fałszywa zgoda to publiczna odznaka pod cudzym nazwiskiem,
			a fałszywa prośba o ukrycie to kilka wpisów zdjętych na jeden dzień. To nie jest to samo ryzyko,
			więc nie traktujemy go tak samo.
		</p>
		<p>
			<strong>Cofnięcie jest tak samo łatwe jak zgoda</strong> — to nie uprzejmość, to art. 7 ust. 3
			RODO. Na stronie osoby (albo w pudełku „Jesteś tą osobą?”) jest „Wyślij sobie link do
			ustawień”. Przychodzi link, w nim zmieniasz wybór albo wycofujesz go całkiem. Bez konta, bez
			hasła, bez kolejki.
		</p>
	</div>
</div>

<div class="box">
	<h2 class="box__title">Podstawa prawna</h2>
	<div class="box__body">
		<ul>
			<li>
				<strong>Art. 81 ust. 1 ustawy o prawie autorskim i prawach pokrewnych:</strong> rozpowszechnianie
				wizerunku wymaga zezwolenia osoby na nim przedstawionej. Nie „braku sprzeciwu” — zezwolenia.
			</li>
			<li>
				<strong>Wykładowca nie jest osobą powszechnie znaną.</strong> Wyjątek z art. 81 ust. 2 pkt 1
				dotyczy osób powszechnie znanych, i to wyłącznie przy wizerunku wykonanym w związku z
				pełnieniem przez nie funkcji publicznych. Prowadzenie zajęć nie czyni nikogo osobą
				powszechnie znaną — bycie rozpoznawalnym na jednym wydziale to nie to samo co bycie znanym
				publicznie. Dlatego domyślną odpowiedzią jest tu „nie wiemy”, a nie „można”.
			</li>
			<li>
				<strong>Art. 7 ust. 3 RODO:</strong> zgodę można wycofać w dowolnym momencie, a wycofanie musi
				być równie łatwe jak jej wyrażenie. Stąd link do ustawień zamiast konta.
			</li>
			<li>
				<strong>Art. 21 RODO:</strong> prawo sprzeciwu wobec przetwarzania — w praktyce to jest ta
				trzecia opcja, „nie chcę być w archiwum”.
			</li>
			<li>
				<strong>Art. 7 ust. 1 RODO:</strong> to my musimy umieć wykazać, że zgoda była. Dlatego
				zatwierdzonego wniosku nie kasujemy (niżej).
			</li>
		</ul>
	</div>
</div>

<div class="box">
	<h2 class="box__title">Co po tym zostaje w bazie</h2>
	<div class="box__body">
		<p>
			Zgoda, której nie da się wykazać, nie jest zgodą — więc zatwierdzony wniosek zostaje u nas
			jako dowód. Konkretnie:
		</p>
		<ul>
			<li><strong>adres e-mail</strong>, z którego przyszedł, i data jego potwierdzenia;</li>
			<li><strong>wybrana opcja</strong> i <strong>wersja tekstu zgody</strong>, na którą się zgodziłaś lub zgodziłeś (data — żebyśmy umieli powiedzieć, <em>na co</em>, a nie tylko <em>kiedy</em>);</li>
			<li>
				<strong>adres IP i przeglądarka</strong> z chwili złożenia wniosku — przez 90 dni, tyle samo co
				przy wpisach; potem kasuje je nocne zadanie. Przy wniosku <em>zatwierdzonym</em> zostają, bo to
				właśnie on jest dowodem zgody;
			</li>
			<li>
				<strong>treść Twojej wiadomości do moderatora</strong>, jeśli ją napisałaś lub napisałeś.
				Widzi ją tylko administracja i <strong>nigdy nie wysyłamy jej mailem</strong> — nawet Tobie.
			</li>
		</ul>
		<p>
			Zmiana wyboru nie nadpisuje starego wpisu: powstaje nowy, a stary zostaje oznaczony jako
			zastąpiony. Historia zgód, które ktoś dawał i cofał, jest częścią tego, co znaczy „mieliśmy
			zgodę w marcu”.
		</p>
		<p class="small">
			Reszta zasad, w tym ścieżka zgłoszenia pojedynczego wpisu i kontakt do człowieka:
			<a href="/o-archiwum">O archiwum</a>.
		</p>
	</div>
</div>
