<script lang="ts">
	import { api, ApiError } from '$lib/api';
	import type { Person } from '$lib/types';

	let people = $state<Person[]>([]);
	let loading = $state(true);
	let error = $state('');

	let asked = false; // plain let: the list is fetched once
	$effect(() => {
		if (asked) return;
		asked = true;
		load();
	});

	async function load() {
		loading = true;
		error = '';
		try {
			people = await api.get<Person[]>('/people/');
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Nie udało się wczytać listy.';
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head><title>Ludzie — fuw.lol</title></svelte:head>

<div class="box">
	<h1 class="box__title">Ludzie <small>{people.length} osób</small></h1>
	<div class="box__body">
		<p class="small muted">
			Postacie w archiwum to folklor. Jeśli jesteś jedną z nich i wolisz nie być — kliknij
			<strong>Zgłoś</strong> przy wpisie.
		</p>

		{#if loading}
			<p class="muted">Wczytuję…</p>
		{:else if error}
			<div class="error">{error}</div>
		{:else if people.length === 0}
			<p class="muted">Nikogo tu jeszcze nie ma.</p>
		{:else}
			<div class="grid">
				{#each people as p (p.slug)}
					<a class="tile" href="/ludzie/{p.slug}">
						<div class="tile__name">{p.name}</div>
						{#if p.role}<div class="small muted">{p.role}</div>{/if}
						<div class="tile__count">{p.post_count} {p.post_count === 1 ? 'wpis' : 'wpisów'}</div>
					</a>
				{/each}
			</div>
		{/if}
	</div>
</div>
