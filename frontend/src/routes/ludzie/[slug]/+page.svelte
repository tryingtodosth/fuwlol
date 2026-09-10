<script lang="ts">
	import { page } from '$app/state';
	import { api, ApiError, qs } from '$lib/api';
	import type { Page as ApiPage, Person, PostSummary } from '$lib/types';
	import PostCard from '$lib/components/PostCard.svelte';

	const slug = $derived(page.params.slug ?? '');

	let person = $state<Person | null>(null);
	let posts = $state<PostSummary[]>([]);
	let count = $state(0);
	let loading = $state(true);
	let error = $state('');
	let notFound = $state(false);

	let loadedFor = ''; // plain let: guards the fetch so the effect cannot loop
	$effect(() => {
		const s = slug;
		if (!s || s === loadedFor) return;
		loadedFor = s;
		load(s);
	});

	async function load(s: string) {
		loading = true;
		error = '';
		notFound = false;
		try {
			person = await api.get<Person>(`/people/${s}/`);
			const res = await api.get<ApiPage<PostSummary>>(`/posts/${qs({ person: s, sort: 'new' })}`);
			posts = res.results;
			count = res.count;
		} catch (e) {
			if (e instanceof ApiError && e.status === 404) notFound = true;
			else error = e instanceof ApiError ? e.message : 'Nie udało się wczytać.';
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head><title>{person ? `${person.name} — fuw.lol` : 'fuw.lol'}</title></svelte:head>

{#if loading}
	<div class="box"><div class="box__body"><p class="muted">Wczytuję…</p></div></div>
{:else if notFound}
	<div class="box">
		<h1 class="box__title">Nie ma takiej osoby</h1>
		<div class="box__body"><p><a href="/ludzie">Wróć do listy</a></p></div>
	</div>
{:else if error}
	<div class="box"><div class="box__body"><div class="error">{error}</div></div></div>
{:else if person}
	<div class="box">
		<h1 class="box__title">{person.name}</h1>
		<div class="box__body">
			{#if person.role}<p><strong>{person.role}</strong></p>{/if}
			{#if person.bio}<p>{person.bio}</p>{/if}
			<p class="small muted">
				{count}
				{count === 1 ? 'wpis' : 'wpisów'} w archiwum ·
				<a href="/przegladaj?person={person.slug}">Przeglądaj z filtrami</a>
			</p>
		</div>
	</div>

	<div class="box">
		<h2 class="box__title">Wpisy</h2>
		{#if posts.length}
			{#each posts as p (p.slug)}
				<PostCard post={p} />
			{/each}
			{#if count > posts.length}
				<div class="box__body">
					<p><a href="/przegladaj?person={person.slug}">Zobacz wszystkie {count} →</a></p>
				</div>
			{/if}
		{:else}
			<div class="box__body"><p class="muted">Jeszcze nic.</p></div>
		{/if}
	</div>
{/if}
