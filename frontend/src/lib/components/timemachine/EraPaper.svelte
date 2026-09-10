<!-- Eras 3 and 4: before the web, before the faculty, there was print. Polish from the
     founding of the University of Warsaw (1816) onwards; German for 1795-1816, when
     Warsaw was under Prussian rule and the local press set its type in German.
     One component, two languages — the layout of a broadsheet does not change with the
     language, only the words on it do. -->
<script lang="ts">
	import MathText from '$lib/components/MathText.svelte';
	import { api, qs } from '$lib/api';
	import type { Page, PostSummary } from '$lib/types';
	import type { TravelDate } from './eras';

	let { lang, date }: { lang: 'pl' | 'de'; date: TravelDate } = $props();

	interface Filler {
		head: string;
		body: string;
	}

	const MONTHS_PL_NEW = [
		'stycznia', 'lutego', 'marca', 'kwietnia', 'maja', 'czerwca',
		'lipca', 'sierpnia', 'września', 'października', 'listopada', 'grudnia'
	];
	// Pre-1900 spelling, capitalised the way the papers of the day set it.
	const MONTHS_PL_OLD = [
		'Stycznia', 'Lutego', 'Marca', 'Kwietnia', 'Maia', 'Czerwca',
		'Lipca', 'Sierpnia', 'Września', 'Października', 'Listopada', 'Grudnia'
	];
	const MONTHS_DE = [
		'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
		'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'
	];

	const day = $derived(date.day ?? 1);
	const month = $derived(date.month ?? 1);
	/** Deterministic, so the same date always prints the same issue number. */
	const issue = $derived(((Math.abs(date.year) * 7 + month * 31 + day) % 300) + 1);

	const dateline = $derived.by(() => {
		if (lang === 'de') {
			return `Nr. ${issue} — Warschau, den ${day}. ${MONTHS_DE[month - 1]} ${date.year}`;
		}
		if (date.year < 1900) {
			return `Nr. ${issue} — Warszawa, dnia ${day} ${MONTHS_PL_OLD[month - 1]} ${date.year} roku`;
		}
		return `Nr ${issue} — Warszawa, dnia ${day} ${MONTHS_PL_NEW[month - 1]} ${date.year} r.`;
	});

	const t = $derived(
		lang === 'de'
			? {
					masthead: 'PHYSIKALISCHER ANZEIGER ZU WARSCHAU',
					motto: 'Wöchentliche Nachrichten von Naturlehre und Mathesis',
					dispatches: 'Nachrichten aus der Fakultät',
					kicker: 'Bericht',
					classifieds: 'Kleine Anzeigen',
					price: 'Preis: 4 Groschen',
					loading: 'Der Satz wird noch gesetzt…',
					empty: 'Heute keine Nachrichten aus der Fakultät.',
					foot: 'Gedruckt auf Kosten der Redaction. Nachdruck nur mit Angabe der Quelle.',
					polish: '(poln.)'
				}
			: {
					masthead: 'KURYER FIZYCZNY',
					motto: 'Pismo poświęcone naukom przyrodzonym i rachunkowi',
					dispatches: 'Doniesienia z Wydziału',
					kicker: 'Doniesienie',
					classifieds: 'Ogłoszenia drobne',
					price: 'Cena: groszy 10',
					loading: 'Skład jeszcze w robocie…',
					empty: 'Dziś doniesień z Wydziału brak.',
					foot: 'Drukiem własnym Redakcyi. Przedruk dozwolony za wskazaniem źródła.',
					polish: ''
				}
	);

	const FILLERS_PL: Filler[] = [
		{
			head: 'O sile zwanéy elektrycznością',
			body: 'W sali odczytowéy pokazywano wczoraj machinę, która iskrą przeskakuiącą zapala spirytus. Publiczność licznie zgromadzona; ieden kapelusz nadpalony. Prelegent zapewnia, iż siła ta znaydzie kiedyś użytek praktyczny, czemu wielu obecnych przeczyło.'
		},
		{
			head: 'Zguba',
			body: 'Zgubiono suwak logarytmiczny, kość biała, podziałka nieco starta, na odwrocie wyryte dwie litery. Uczciwy znalazca zechce oddać u odźwiernego; nagroda: wdzięczność i pół funta herbaty.'
		},
		{
			head: 'Ostrzeżenie',
			body: 'Przeciągi w sali wykładowéy gaszą świece w czasie doświadczeń, przez co wynik bywa niepewny. Prosi się o zamykanie okien od strony podwórza, osobliwie w dni wietrzne.'
		},
		{
			head: 'Poszukuie się',
			body: 'Assystenta do przepisywania tablic rachunkowych. Pismo czytelne warunkiem koniecznym; znaiomość rachunku różniczkowego mile widziana. Zgłaszać się rano.'
		}
	];

	const FILLERS_DE: Filler[] = [
		{
			head: 'Von der Kraft, Elektricität genannt',
			body: 'Gestern ward im Hörsaale eine Maschine vorgeführt, welche mit überspringendem Funken Weingeist entzündet. Zahlreiche Zuhörerschaft; ein Hut leicht versengt. Der Vortragende meint, diese Kraft werde dereinst Nutzen bringen, was mehrere Anwesende bestritten.'
		},
		{
			head: 'Verloren',
			body: 'Ein Rechenschieber aus Bein, die Theilung etwas abgegriffen, auf der Rückseite zwei eingeritzte Buchstaben. Der ehrliche Finder wolle ihn beim Pförtner abgeben; Belohnung zugesichert.'
		},
		{
			head: 'Warnung',
			body: 'Der Zugwind im Hörsaale löscht während der Versuche die Kerzen, wodurch das Ergebniss ungewiss wird. Man bittet, die Fenster nach dem Hofe hin zu schliessen.'
		},
		{
			head: 'Gesucht',
			body: 'Ein Gehülfe zum Abschreiben der Rechentafeln. Leserliche Handschrift Bedingung; Kenntniss der Differenzialrechnung erwünscht. Meldung des Morgens.'
		}
	];

	const CLASSIFIEDS_PL = [
		'Sprzedam wagę szalkową, mało używaną. Odważniki komplet, prócz naymnieyszego.',
		'Kto widział kota z laboratoryum, proszony o wiadomość. Kot czarny, bardzo ciekawy.',
		'Lekcye z arytmetyki dla panien i chłopców. Ceny umiarkowane, cierpliwość gwarantowana.',
		'Zamienię lunetę na dobry zegar. Luneta sprawna, zegar ma chodzić.'
	];
	const CLASSIFIEDS_DE = [
		'Verkaufe eine Waage nebst Gewichten, wenig gebraucht; das kleinste Gewicht fehlt.',
		'Wer die Katze aus dem Laboratorium gesehen hat, melde es. Schwarz, sehr neugierig.',
		'Unterricht in der Rechenkunst für Knaben und Mädchen. Billige Preise, viel Geduld.',
		'Tausche ein Fernrohr gegen eine gute Uhr. Das Fernrohr geht, die Uhr soll gehen.'
	];

	const fillers = $derived(lang === 'de' ? FILLERS_DE : FILLERS_PL);
	const classifieds = $derived(lang === 'de' ? CLASSIFIEDS_DE : CLASSIFIEDS_PL);

	let posts = $state<PostSummary[]>([]);
	let loading = $state(true);

	$effect(() => {
		let alive = true;
		api
			.get<Page<PostSummary>>('/posts/' + qs({ page: 1 }))
			.then((p) => {
				if (alive) posts = p.results.slice(0, 8);
			})
			.catch(() => {
				if (alive) posts = [];
			})
			.finally(() => {
				if (alive) loading = false;
			});
		return () => {
			alive = false;
		};
	});
</script>

<svelte:head>
	{#if lang === 'de'}
		<!-- Only this era pays for the Fraktur face; offline it falls back down the stack. -->
		<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
		<link
			rel="stylesheet"
			href="https://fonts.googleapis.com/css2?family=UnifrakturMaguntia&display=swap"
		/>
	{/if}
</svelte:head>

<div class="paper" class:paper--de={lang === 'de'} lang={lang === 'de' ? 'de' : 'pl'}>
	<div class="sheet">
		<header class="mast">
			<h1 class="mast__name">{t.masthead}</h1>
			<p class="mast__motto">{t.motto}</p>
			<div class="rule"></div>
			<p class="mast__line">
				<span>{dateline}</span>
				<span>{t.price}</span>
			</p>
			<div class="rule rule--thin"></div>
		</header>

		<h2 class="section">{t.dispatches}</h2>

		<div class="cols">
			{#if loading}
				<p class="art__body">{t.loading}</p>
			{:else if posts.length === 0}
				<p class="art__body">{t.empty}</p>
			{:else}
				{#each posts as post, i (post.id)}
					<article class="art">
						<p class="art__kicker">{t.kicker}</p>
						<h3 class="art__head">
							<a href="/wpis/{post.slug}">{post.title}</a>{#if lang === 'de'}<span class="poln"
									>{t.polish}</span
								>{/if}
						</h3>
						<p class="art__body" class:art__body--first={i === 0}>
							{#if post.summary}<MathText text={post.summary} />{:else}{lang === 'de' ? 'Näheres in der Sache selbst.' : 'Rzecz sama mówi za siebie.'}{/if}
						</p>
					</article>
				{/each}
			{/if}

			{#each fillers as f (f.head)}
				<article class="art art--filler">
					<h3 class="art__head">{f.head}</h3>
					<p class="art__body">{f.body}</p>
				</article>
			{/each}
		</div>

		<div class="rule rule--thin"></div>

		<section class="ads">
			<h3 class="ads__head">{t.classifieds}</h3>
			<ul>
				{#each classifieds as ad (ad)}
					<li>{ad}</li>
				{/each}
			</ul>
		</section>

		<p class="foot">{t.foot}</p>
	</div>
</div>

<style>
	.paper {
		/* Out of the 900 px column: a newspaper that stops at the text width is a leaflet. */
		margin: 0 calc(50% - 50vw);
		width: 100vw;
		padding: 22px 0 34px;
		background:
			radial-gradient(ellipse at 20% 0%, rgba(255, 255, 255, 0.55), transparent 60%),
			radial-gradient(ellipse at 85% 100%, rgba(160, 130, 80, 0.16), transparent 55%),
			#f3ead6;
		color: #2b2419;
		font-family: Georgia, 'Times New Roman', Times, serif;
	}
	.sheet {
		width: 92%;
		max-width: 940px;
		margin: 0 auto;
		background: #f7efdd;
		border: 1px solid #d8cbaa;
		box-shadow: 0 1px 0 #fff inset;
		padding: 24px 26px 20px;
	}
	.mast {
		text-align: center;
	}
	.mast__name {
		font-size: 42px;
		letter-spacing: 3px;
		margin: 0 0 2px;
		color: #1d1810;
		font-weight: normal;
		font-family: Georgia, 'Times New Roman', Times, serif;
	}
	.paper--de .mast__name {
		font-family: 'UnifrakturMaguntia', 'Old English Text MT', Georgia, serif;
		font-size: 46px;
		letter-spacing: 1px;
	}
	.mast__motto {
		font-style: italic;
		font-size: 13px;
		margin: 0 0 8px;
		color: #574a35;
	}
	.rule {
		border-top: 3px double #3a3122;
		margin: 6px 0;
	}
	.rule--thin {
		border-top: 1px solid #a2937a;
	}
	.mast__line {
		display: flex;
		justify-content: space-between;
		gap: 10px;
		font-size: 12px;
		font-variant: small-caps;
		letter-spacing: 0.5px;
		margin: 0;
		color: #4a3f2c;
	}
	.section {
		font-size: 15px;
		font-variant: small-caps;
		letter-spacing: 2px;
		text-align: center;
		margin: 14px 0 10px;
		color: #1d1810;
		font-weight: normal;
	}
	.paper--de .section,
	.paper--de .art__head,
	.paper--de .ads__head {
		font-family: 'UnifrakturMaguntia', 'Old English Text MT', Georgia, serif;
		letter-spacing: 0;
	}
	.cols {
		column-count: 2;
		column-gap: 26px;
		column-rule: 1px solid #cdbf9f;
	}
	.art {
		break-inside: avoid;
		margin: 0 0 14px;
	}
	.art--filler {
		color: #3a3226;
	}
	.art__kicker {
		font-size: 10px;
		font-variant: small-caps;
		letter-spacing: 2px;
		color: #7d6c4d;
		margin: 0 0 1px;
	}
	.art__head {
		font-size: 15px;
		font-weight: normal;
		font-variant: small-caps;
		letter-spacing: 1px;
		margin: 0 0 3px;
		color: #1d1810;
		line-height: 1.25;
	}
	.art__head a {
		color: #1d1810;
		text-decoration: none;
		border-bottom: 1px dotted #9a8a68;
	}
	.art__head a:hover {
		color: #6b2f06;
	}
	.poln {
		font-size: 10px;
		font-variant: normal;
		letter-spacing: 0;
		color: #7d6c4d;
		margin-left: 5px;
		font-family: Georgia, serif;
	}
	.art__body {
		margin: 0;
		font-size: 13.5px;
		line-height: 1.5;
		text-align: justify;
		hyphens: auto;
	}
	.art__body--first::first-letter {
		float: left;
		font-size: 44px;
		line-height: 0.82;
		padding: 3px 6px 0 0;
		color: #1d1810;
	}
	.ads {
		margin: 12px 0 0;
		border: 1px solid #a2937a;
		padding: 8px 12px 10px;
		background: #f2e7cf;
	}
	.ads__head {
		font-size: 13px;
		font-variant: small-caps;
		letter-spacing: 2px;
		font-weight: normal;
		margin: 0 0 5px;
		color: #1d1810;
	}
	.ads ul {
		margin: 0;
		padding: 0 0 0 16px;
		column-count: 2;
		column-gap: 22px;
		font-size: 12.5px;
	}
	.ads li {
		break-inside: avoid;
		margin-bottom: 3px;
	}
	.foot {
		margin: 12px 0 0;
		text-align: center;
		font-size: 11px;
		font-style: italic;
		color: #6b5c42;
	}
	@media (min-width: 1100px) {
		.cols {
			column-count: 3;
		}
	}
	@media (max-width: 620px) {
		.cols,
		.ads ul {
			column-count: 1;
		}
		.mast__name {
			font-size: 30px;
		}
		.paper--de .mast__name {
			font-size: 32px;
		}
	}
</style>
