<script lang="ts">
	/** The front page — the faculty site's "Aktualności" column, only funnier. With `?czas=`
	 * in the URL it steps aside completely and the time machine takes over the page. */
	import { page } from '$app/state';
	import { api, ApiError, qs } from '$lib/api';
	import type { Category, Page, PostSummary } from '$lib/types';
	import PostCard from '$lib/components/PostCard.svelte';
	import TimeMachine from '$lib/components/timemachine/TimeMachine.svelte';
	import TimeTravel from '$lib/components/timemachine/TimeTravel.svelte';
	import ChatWidget from '$lib/components/board/ChatWidget.svelte';

	interface Stats {
		posts: number;
		people: number;
		tags: number;
		attachments: number;
		year_min: number | null;
		year_max: number | null;
		pending: number;
	}

	const czas = $derived(page.url.searchParams.get('czas'));

	let featured = $state<PostSummary[]>([]);
	let latest = $state<PostSummary[]>([]);
	let categories = $state<Category[]>([]);
	let stats = $state<Stats | null>(null);
	let loading = $state(true);
	let error = $state('');

	let loaded = false; // plain let: the front page's own data never changes with the URL
	$effect(() => {
		if (czas || loaded) return;
		loaded = true;
		load();
	});

	async function load() {
		loading = true;
		error = '';
		try {
			const [f, l, c, s] = await Promise.all([
				api.get<Page<PostSummary>>(`/posts/${qs({ featured: 1, sort: 'new' })}`),
				api.get<Page<PostSummary>>(`/posts/${qs({ sort: 'new' })}`),
				api.get<Category[]>('/categories/'),
				api.get<Stats>('/posts/stats/')
			]);
			featured = f.results.slice(0, 4);
			latest = l.results.slice(0, 10);
			categories = c;
			stats = s;
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Nie udało się wczytać archiwum.';
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>fuw.lol — archiwum Wydziału Fizyki UW</title>
</svelte:head>

{#if czas}
	<TimeTravel date={czas} />
{:else}
	<div class="box">
		<h1 class="box__title">fuw.lol</h1>
		<div class="box__body">
			<p>
				Archiwum śmiesznych rzeczy z Wydziału Fizyki UW. Memy, cytaty, legendarne zadania, zdjęcia,
				folklor — od 1998 roku (a w wehikule czasu i wcześniej).
			</p>
			<p class="small muted">
				Coś pamiętasz, a tego tu nie ma? <a href="/dodaj">Dodaj wpis</a> — moderator przejrzy i
				opublikuje.
			</p>
		</div>
	</div>

	{#if error}<div class="error">{error}</div>{/if}

	{#if loading}
		<div class="box"><div class="box__body"><p class="muted">Wczytuję archiwum…</p></div></div>
	{:else}
		{#if featured.length}
			<div class="box">
				<h2 class="box__title">Wyróżnione <small>ręcznie wybrane przez moderatorów</small></h2>
				{#each featured as p (p.slug)}
					<PostCard post={p} />
				{/each}
			</div>
		{/if}

		<div class="box">
			<h2 class="box__title">
				Najnowsze wpisy
				<small><a href="/przegladaj">Więcej wpisów →</a></small>
			</h2>
			{#if latest.length}
				{#each latest as p (p.slug)}
					<PostCard post={p} />
				{/each}
			{:else}
				<div class="box__body"><p class="muted">Archiwum jest jeszcze puste.</p></div>
			{/if}
		</div>

		{#if categories.length}
			<div class="box">
				<h2 class="box__title">Kategorie</h2>
				<div class="box__body">
					<div class="grid">
						{#each categories as c (c.slug)}
							<a class="tile" href="/przegladaj?category={c.slug}">
								<div class="tile__name"><span aria-hidden="true">{c.emoji}</span> {c.name}</div>
								<div class="tile__count">
									{c.post_count}
									{c.post_count === 1 ? 'wpis' : 'wpisów'}
								</div>
								{#if c.description}<div class="small muted">{c.description}</div>{/if}
							</a>
						{/each}
					</div>
				</div>
			</div>
		{/if}

		{#if stats}
			<div class="box box--grey">
				<h2 class="box__title">Statystyki</h2>
				<div class="box__body">
					<p class="small">
						{stats.posts} wpisów · {stats.people} osób · {stats.tags} tagów · {stats.attachments} plików
						{#if stats.year_min && stats.year_max}
							· lata {stats.year_min}–{stats.year_max}
						{/if}
					</p>
				</div>
			</div>
		{/if}
	{/if}

	<ChatWidget />
	<TimeMachine />
{/if}
