<!-- Era 2: before fuw.lol there was fuw.edu.pl, and the Internet Archive kept it.
     The Archive resolves `/web/<stamp>if_/<url>` to the nearest capture by redirect and
     `if_` strips its toolbar, so the URL goes straight into an iframe. Our backend is
     asked only WHICH capture that turned out to be, for the caption. -->
<script lang="ts">
	import { api, qs } from '$lib/api';
	import { toISODate, type TravelDate } from './eras';

	let { date }: { date: TravelDate } = $props();

	interface WaybackAnswer {
		requested: string;
		embed_url: string;
		timestamp: string | null;
		earliest: string;
	}

	const iso = $derived(toISODate(date));
	const stamp = $derived(iso.replaceAll('-', ''));
	const asked = $derived(iso.split('-').reverse().join('.'));
	/** Works on its own: the Archive redirects it to the nearest capture. */
	const fallback = $derived(`https://web.archive.org/web/${stamp}000000if_/http://www.fuw.edu.pl/`);

	let answer = $state<WaybackAnswer | null>(null);
	let loading = $state(true);
	let seq = 0;

	$effect(() => {
		const on = iso;
		const mine = ++seq;
		loading = true;
		answer = null;
		api
			.get<WaybackAnswer>('/wayback/' + qs({ date: on }))
			.then((a) => {
				if (mine === seq) answer = a;
			})
			.catch(() => {
				// Nothing to report: the fallback URL reaches the same capture.
			})
			.finally(() => {
				if (mine === seq) loading = false;
			});
	});

	const embed = $derived(answer?.embed_url ?? fallback);
	const captured = $derived.by(() => {
		const t = answer?.timestamp;
		if (!t || t.length < 8) return null;
		return `${t.slice(6, 8)}.${t.slice(4, 6)}.${t.slice(0, 4)}`;
	});
	const openUrl = $derived(
		`https://web.archive.org/web/${answer?.timestamp ?? stamp + '000000'}/http://www.fuw.edu.pl/`
	);
</script>

<div class="box">
	<h2 class="box__title">
		www.fuw.edu.pl
		<small>Internet Archive</small>
	</h2>
	<div class="box__body">
		{#if loading}
			<p class="muted">Pytamy Internet Archive o zrzut z {asked}…</p>
		{:else}
			<p class="cap">
				{#if captured}
					Zrzut fuw.edu.pl z {captured} (Internet Archive)
				{:else}
					Zrzut fuw.edu.pl — najbliższy {asked} (Internet Archive)
				{/if}
			</p>
			<iframe
				src={embed}
				title="fuw.edu.pl w Internet Archive"
				sandbox="allow-same-origin allow-scripts allow-popups"
				referrerpolicy="no-referrer"
				loading="lazy"
			></iframe>
			<p class="small muted">
				Strona ładuje się z serwerów Internet Archive i potrafi to trwać — czasem kilkanaście
				sekund, czasem zrzut jest niekompletny (brakujące obrazki, martwe podstrony). To nie
				nasza awaria, to archiwum.
			</p>
			<p class="small">
				<a href={openUrl} target="_blank" rel="noreferrer noopener"
					>Otwórz w Internet Archive (nowa karta) →</a
				>
			</p>
		{/if}
	</div>
</div>

<style>
	.cap {
		font-weight: bold;
		color: #222;
	}
	iframe {
		display: block;
		width: 100%;
		height: 75vh;
		min-height: 380px;
		border: 1px solid var(--line);
		background: #fff;
	}
</style>
