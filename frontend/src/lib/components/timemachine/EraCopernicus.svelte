<!-- Era 5: 1400-1795. No press worth the name, so the page becomes what a scholar of
     the period would actually have produced — a sheet of handwritten notes in Latin,
     with the diagram Copernicus is remembered for drawn in the margin of his own copy. -->
<script lang="ts">
	import MathText from '$lib/components/MathText.svelte';
	import { api, qs } from '$lib/api';
	import type { Page, PostSummary } from '$lib/types';
	import { toRoman, type TravelDate } from './eras';

	let { date }: { date: TravelDate } = $props();

	const MONTHS_LA = [
		'Ianuarii', 'Februarii', 'Martii', 'Aprilis', 'Maii', 'Iunii',
		'Iulii', 'Augusti', 'Septembris', 'Octobris', 'Novembris', 'Decembris'
	];

	const dateline = $derived.by(() => {
		const anno = `Anno Domini ${toRoman(date.year)}`;
		if (date.month === undefined) return anno;
		const mensis = MONTHS_LA[date.month - 1];
		if (date.day === undefined) return `Mense ${mensis}, ${anno}`;
		return `Die ${toRoman(date.day)} mensis ${mensis}, ${anno}`;
	});

	const SENTENCES = [
		'Sol in medio residet. Quis enim in hoc pulcherrimo templo lampadem hanc in alio vel meliori loco poneret?',
		'Nihil est in intellectu quod non prius fuerit in colloquio.',
		'Terra quoque movetur, quamvis nemo id sentiat, praeter eos qui mane surgunt.',
		'Hic sunt integrales.',
		'Mathemata mathematicis scribuntur.'
	];

	const MARGINALIA = ['manu propria', 'vide folium XII', 'probandum est', 'nota bene', 'quaere'];

	let posts = $state<PostSummary[]>([]);
	let loading = $state(true);

	$effect(() => {
		let alive = true;
		api
			.get<Page<PostSummary>>('/posts/' + qs({ page: 1 }))
			.then((p) => {
				if (alive) posts = p.results.slice(0, 6);
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
	<!-- Only this era pays for the handwriting faces; offline the stack falls through to
	     whatever script face the system has, and then to plain cursive. -->
	<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
	<link
		rel="stylesheet"
		href="https://fonts.googleapis.com/css2?family=Homemade+Apple&family=Reenie+Beanie&display=swap"
	/>
</svelte:head>

<div class="vellum" lang="la">
	<div class="folio">
		<p class="marg marg--a">{MARGINALIA[0]}</p>
		<p class="marg marg--b">{MARGINALIA[1]}</p>
		<p class="marg marg--c">{MARGINALIA[3]}</p>

		<h1 class="title">De Facultate Physicae Annotationes</h1>
		<p class="dateline">{dateline}</p>

		<div class="grid">
			<div class="text">
				{#each SENTENCES.slice(0, 3) as line, i (line)}
					<p class="ink" style="--tilt: {(i % 2 === 0 ? -0.35 : 0.45).toFixed(2)}deg">{line}</p>
				{/each}

				<h2 class="sub">Annotationes recentiores</h2>
				{#if loading}
					<p class="ink">Scriptor adhuc scribit…</p>
				{:else if posts.length === 0}
					<p class="ink">Nihil hodie annotatum est.</p>
				{:else}
					<ol class="notes">
						{#each posts as post, i (post.id)}
							<li style="--tilt: {(i % 2 === 0 ? 0.4 : -0.3).toFixed(2)}deg">
								<a href="/wpis/{post.slug}">{post.title}</a>
								<span class="tongue">(lingua polonica)</span>
								{#if post.summary}<span class="gloss"> — <MathText text={post.summary} /></span>{/if}
							</li>
						{/each}
					</ol>
				{/if}

				{#each SENTENCES.slice(3) as line, i (line)}
					<p class="ink" style="--tilt: {(i % 2 === 0 ? 0.5 : -0.4).toFixed(2)}deg">{line}</p>
				{/each}
			</div>

			<figure class="fig">
				<svg viewBox="0 0 300 300" role="img" aria-labelledby="cop-fig-title">
					<title id="cop-fig-title">
						Schemat heliocentryczny: Słońce w środku, wokół niego orbity planet
					</title>
					<g class="orb">
						<circle cx="150" cy="150" r="36" />
						<circle cx="150" cy="150" r="58" />
						<circle cx="150" cy="150" r="82" />
						<circle cx="150" cy="150" r="106" />
						<circle cx="150" cy="150" r="132" />
					</g>
					<!-- Sol -->
					<circle class="sol" cx="150" cy="150" r="11" />
					<g class="rays">
						<line x1="150" y1="128" x2="150" y2="118" />
						<line x1="150" y1="172" x2="150" y2="182" />
						<line x1="128" y1="150" x2="118" y2="150" />
						<line x1="172" y1="150" x2="182" y2="150" />
						<line x1="135" y1="135" x2="128" y2="128" />
						<line x1="165" y1="165" x2="172" y2="172" />
						<line x1="165" y1="135" x2="172" y2="128" />
						<line x1="135" y1="165" x2="128" y2="172" />
					</g>
					<!-- the planets, small and unequal, as a pen would put them -->
					<circle class="body" cx="186" cy="150" r="3.4" />
					<circle class="body" cx="109" cy="109" r="4.2" />
					<circle class="body terra" cx="150" cy="232" r="5.2" />
					<circle class="body" cx="225" cy="105" r="4" />
					<circle class="body saturn" cx="52" cy="196" r="5.8" />
					<ellipse class="ring" cx="52" cy="196" rx="12" ry="3.6" transform="rotate(-18 52 196)" />
					<!-- Luna, on her own little circle about Terra -->
					<circle class="orb-moon" cx="150" cy="232" r="14" />
					<circle class="body" cx="164" cy="232" r="2.6" />

					<text class="lbl" x="150" y="145" text-anchor="middle">Sol</text>
					<text class="lbl" x="150" y="256" text-anchor="middle">Terra</text>
					<text class="lbl" x="180" y="224" text-anchor="middle">Luna</text>
					<text class="lbl" x="52" y="222" text-anchor="middle">Saturnus</text>
				</svg>
				<figcaption>Figura I — Sol in medio</figcaption>
			</figure>
		</div>

		<p class="signature">— manu propria —</p>
		<p class="marg marg--d">{MARGINALIA[4]}</p>
	</div>
</div>

<style>
	.vellum {
		margin: 0 calc(50% - 50vw);
		width: 100vw;
		padding: 24px 0 40px;
		background:
			radial-gradient(ellipse at 15% 10%, rgba(255, 250, 235, 0.85), transparent 55%),
			radial-gradient(ellipse at 88% 82%, rgba(150, 112, 60, 0.22), transparent 58%),
			radial-gradient(ellipse at 40% 100%, rgba(120, 88, 44, 0.18), transparent 60%),
			#e9dcbd;
		color: #4a3520;
	}
	.folio {
		position: relative;
		width: 92%;
		max-width: 900px;
		margin: 0 auto;
		padding: 26px 30px 34px;
		background: linear-gradient(180deg, rgba(255, 253, 244, 0.5), rgba(226, 210, 176, 0.35));
		border: 1px solid #c9b48a;
		box-shadow: 0 2px 10px rgba(90, 66, 30, 0.14);
		font-family: 'Homemade Apple', 'Reenie Beanie', 'Segoe Script', 'Bradley Hand', cursive;
		font-size: 17px;
		line-height: 1.85;
	}
	.title {
		font-family: inherit;
		font-weight: normal;
		font-size: 27px;
		text-align: center;
		color: #3c2a17;
		letter-spacing: 1px;
		margin: 0 0 2px;
		transform: rotate(-0.5deg);
	}
	.dateline {
		text-align: center;
		font-size: 15px;
		color: #6a5334;
		margin: 0 0 18px;
		transform: rotate(0.3deg);
	}
	.grid {
		display: flex;
		gap: 26px;
		align-items: flex-start;
	}
	.text {
		flex: 1 1 auto;
		min-width: 0;
	}
	.ink {
		transform: rotate(var(--tilt, 0deg)) skewX(-0.6deg);
		margin: 0 0 12px;
	}
	.sub {
		font-family: inherit;
		font-weight: normal;
		font-size: 19px;
		color: #3c2a17;
		margin: 18px 0 6px;
		border-bottom: 1px solid rgba(74, 53, 32, 0.35);
		display: inline-block;
		transform: rotate(-0.4deg);
	}
	.notes {
		margin: 0 0 12px;
		padding-left: 24px;
	}
	.notes li {
		margin: 0 0 9px;
		transform: rotate(var(--tilt, 0deg));
	}
	.notes a {
		color: #3c2a17;
		border-bottom: 1px dotted rgba(74, 53, 32, 0.55);
	}
	.notes a:hover {
		color: #7a2f02;
		text-decoration: none;
	}
	.tongue {
		font-size: 13px;
		color: #7d6444;
	}
	.gloss {
		color: #5d472c;
	}
	.fig {
		flex: 0 0 300px;
		margin: 0;
		transform: rotate(1.1deg);
	}
	.fig svg {
		display: block;
		width: 100%;
		height: auto;
	}
	.fig figcaption {
		text-align: center;
		font-size: 14px;
		color: #6a5334;
	}
	.orb circle,
	.orb-moon {
		fill: none;
		stroke: #6b5233;
		stroke-width: 1;
		opacity: 0.75;
	}
	.orb-moon {
		stroke-dasharray: 2 3;
	}
	.sol {
		fill: #b8862f;
		stroke: #4a3520;
		stroke-width: 1.2;
	}
	.rays line {
		stroke: #8a6a34;
		stroke-width: 1.2;
		stroke-linecap: round;
	}
	.body {
		fill: #4a3520;
	}
	.terra {
		fill: #5d472c;
	}
	.saturn {
		fill: #6b5233;
	}
	.ring {
		fill: none;
		stroke: #6b5233;
		stroke-width: 1.1;
	}
	.lbl {
		font-family: inherit;
		font-size: 13px;
		fill: #3c2a17;
	}
	.signature {
		text-align: right;
		color: #6a5334;
		margin: 18px 0 0;
		transform: rotate(-0.8deg);
	}
	.marg {
		position: absolute;
		font-size: 14px;
		color: #8a6a34;
		margin: 0;
		white-space: nowrap;
		pointer-events: none;
	}
	.marg--a {
		top: 64px;
		left: -4px;
		transform: rotate(-90deg);
		transform-origin: left top;
	}
	.marg--b {
		top: 210px;
		right: 6px;
		transform: rotate(4deg);
	}
	.marg--c {
		top: 132px;
		right: 10px;
		transform: rotate(-6deg);
	}
	.marg--d {
		bottom: 8px;
		left: 18px;
		transform: rotate(-3deg);
	}
	@media (max-width: 760px) {
		.grid {
			flex-direction: column;
		}
		.fig {
			flex-basis: auto;
			align-self: center;
			max-width: 300px;
		}
		.marg {
			display: none;
		}
	}
</style>
