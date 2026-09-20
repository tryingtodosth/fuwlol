<script lang="ts">
	/** Spin the wheel: ask the API for one published post and step aside. */
	import Breadcrumb from '$lib/components/Breadcrumb.svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { api, ApiError } from '$lib/api';
	import type { Post } from '$lib/types';

	let error = $state('');
	let empty = $state(false);

	let asked = false; // plain let: one roll per visit
	$effect(() => {
		if (asked) return;
		asked = true;
		roll(page.url.search);
	});

	async function roll(search: string) {
		try {
			const p = await api.get<Post>(`/posts/random/${search}`);
			goto(`/wpis/${p.slug}`, { replaceState: true });
		} catch (e) {
			if (e instanceof ApiError && e.status === 404) empty = true;
			else error = e instanceof ApiError ? e.message : 'Nie udało się wylosować wpisu.';
		}
	}
</script>

<svelte:head><title>Losowy wpis — fuw.lol</title></svelte:head>

<Breadcrumb trail={[{ label: 'Losowy wpis' }]} />


<div class="box">
	<h1 class="box__title">Losowy wpis</h1>
	<div class="box__body">
		{#if empty}
			<p>Archiwum jest puste (albo filtr nic nie łapie). <a href="/dodaj">Dodaj coś</a>?</p>
		{:else if error}
			<div class="error">{error}</div>
			<p><a href="/losowe">Spróbuj jeszcze raz</a></p>
		{:else}
			<p class="muted">Losuję…</p>
		{/if}
	</div>
</div>
