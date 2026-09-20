<script lang="ts">
	/** "Dodaj wpis" — the front door for a submission. Guests are turned away with a way in;
	 * everybody else gets the editor and, afterwards, the truth about what happened to their
	 * post: a moderator's own goes straight up, everybody else's waits in the queue. */
	import Breadcrumb from '$lib/components/Breadcrumb.svelte';
	import PostEditor from '$lib/components/editor/PostEditor.svelte';
	import { auth } from '$lib/auth.svelte';
	import type { Post } from '$lib/types';

	let saved = $state<Post | null>(null);
	let round = $state(0); // remounts the editor for a second submission

	function onSaved(post: Post) {
		saved = post;
		if (typeof window !== 'undefined') window.scrollTo({ top: 0, behavior: 'smooth' });
	}
	function again() {
		saved = null;
		round += 1;
	}
</script>

<svelte:head>
	<title>Dodaj wpis — fuw.lol</title>
	<meta name="description" content="Dodaj do archiwum fuw.lol zdjęcie, kartkę z drzwi albo anegdotę z Wydziału Fizyki UW." />
</svelte:head>

<Breadcrumb trail={[{ label: 'Dodaj wpis' }]} />

<div>
	{#if !auth.ready}
		<p class="muted">Ładowanie…</p>
	{:else if !auth.isAuthenticated}
		<div class="box">
			<h1 class="box__title">Żeby dodać wpis, zaloguj się</h1>
			<div class="box__body">
				<p>Archiwum przyjmuje wpisy tylko od zalogowanych — inaczej nikt nie wie, kogo zapytać, gdy coś się nie zgadza.</p>
				<p class="acts">
					<a class="btn" href="/logowanie?next=/dodaj">Zaloguj się</a>
					<a class="btn btn--ghost" href="/rejestracja?next=/dodaj">Załóż konto</a>
				</p>
			</div>
		</div>
	{:else if saved}
		<h1 class="ce_headline">Dodaj wpis do archiwum</h1>
		{#if saved.status === 'published'}
			<div class="ok">
				<strong>Opublikowano.</strong>
				Wpis <a href="/wpis/{saved.slug}">{saved.title}</a> jest już w archiwum.
			</div>
		{:else}
			<div class="ok">
				<strong>Dziękujemy! Wpis czeka na moderację.</strong>
				Zobaczysz go na liście <a href="/moje">swoich wpisów</a>, a gdy moderator go przepuści — w archiwum.
			</div>
		{/if}
		<p class="acts">
			<button type="button" class="btn" onclick={again}>Dodaj kolejny wpis</button>
			<a class="btn btn--ghost" href="/moje">Moje wpisy</a>
		</p>
	{:else}
		<h1 class="ce_headline">Dodaj wpis do archiwum</h1>
		<p class="lead muted">Wpis trafi do moderacji; moderatorzy publikują od ręki.</p>
		{#key round}
			<PostEditor {onSaved} />
		{/key}
	{/if}
</div>

<style>
	.lead { margin: 0 0 14px; }
	.acts { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 10px; }
	.acts a.btn:hover { text-decoration: none; }
</style>
