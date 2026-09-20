<script lang="ts">
	/** The click in the mailbox. Same shape as /potwierdz (the institutional-address
	 * confirmation), and deliberately so — a person who has done one of these recognises
	 * the other.
	 *
	 * What it must not do is say „dziękujemy” and stop. Two different things can have
	 * happened by the time this page renders: the wish is already in force (a tightening
	 * one, from an institutional mailbox), or it is waiting for a human. Somebody who has
	 * just asked to disappear needs to know which, in words, before they close the tab —
	 * so the server composes that sentence (`consent.rules._confirm_message`) and this page
	 * prints it rather than inventing a cheerful one of its own. */
	import Breadcrumb from '$lib/components/Breadcrumb.svelte';
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { ApiError } from '$lib/api';
	import { confirmClaim, type ConfirmResult } from '$lib/consent';

	const slug = $derived(page.params.slug ?? '');

	let phase = $state<'working' | 'ok' | 'error' | 'notoken'>('working');
	let result = $state<ConfirmResult | null>(null);
	let error = $state('');

	onMount(async () => {
		document.title = 'Potwierdzenie — fuw.lol';
		const token = page.url.searchParams.get('token');
		if (!token) {
			phase = 'notoken';
			return;
		}
		try {
			result = await confirmClaim(token);
			phase = 'ok';
		} catch (e) {
			error = e instanceof ApiError ? e.message : String(e);
			phase = 'error';
		}
	});

	const gone = $derived(result?.wish === 'no_mention' && result?.applied);
</script>

<svelte:head><title>Potwierdzenie — fuw.lol</title></svelte:head>

<Breadcrumb trail={[{ label: 'Osoby', href: '/ludzie' }, { label: result ? result.person.full_name : 'Osoba', href: `/ludzie/${page.params.slug}` }, { label: 'Potwierdzenie' }]} />


<div class="box">
	<h1 class="box__title">
		Potwierdzenie
		{#if result}<small>{result.person.full_name}</small>{/if}
	</h1>
	<div class="box__body">
		{#if phase === 'working'}
			<p class="muted">Sprawdzam link…</p>
		{:else if phase === 'ok' && result}
			<div class="ok"><strong>{result.wish_label}</strong></div>
			<p>{result.message}</p>
			{#if result.applied}
				<p class="small muted">
					Ukryte znaczy: zdjęte ze strony i czekające na moderatora — nie skasowane. Człowiek musi
					zdecydować, co z każdym wpisem dalej, i dlatego to nie dzieje się jednym kliknięciem.
				</p>
			{/if}
			<p>
				{#if gone}
					<a href="/ludzie">Wróć do spisu osób</a> · <a href="/o-archiwum">Regulamin</a>
				{:else}
					<a href="/ludzie/{slug}">Wróć na stronę osoby</a> ·
					<a href="/ludzie/zgoda">Co znaczy odznaka</a>
				{/if}
			</p>
		{:else if phase === 'notoken'}
			<div class="error">Brak tokenu w linku.</div>
			<p class="small">
				Skopiuj adres z wiadomości w całości — token bywa łamany na dwie linie przez program
				pocztowy. Albo poproś o nowy link na <a href="/ludzie/{slug}">stronie osoby</a>.
			</p>
		{:else}
			<div class="error">{error}</div>
			<p class="small">
				Link działa 24 godziny i tylko raz. Po nowy wróć na <a href="/ludzie/{slug}">stronę osoby</a>
				— formularz „Jesteś tą osobą?” jest na dole.
			</p>
		{/if}
	</div>
</div>
