<script lang="ts">
	/** The front page — the faculty site's front page, only funnier: „Aktualności” in a wide
	 * left column, the short boxes (who we are, the featured posts as one-line rows with a
	 * 65px picture, the categories, the numbers, the chat) in a narrow right one, and the time
	 * machine across the full width below. With `?czas=` in the URL it steps aside completely
	 * and the time machine takes over the page. */
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
			// a post already shown under "Wyróżnione" is not news twice on the same page
			const shown = new Set(featured.map((p) => p.slug));
			latest = l.results.filter((p) => !shown.has(p.slug)).slice(0, 10);
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
	{#if error}<div class="error">{error}</div>{/if}

	<div class="subcolumns">
		<div class="col--main">
			<div class="box">
				<h1 class="box__title">
					Aktualności
					<small><a href="/przegladaj">Więcej wpisów →</a></small>
				</h1>
				{#if loading}
					<div class="box__body"><p class="muted">Wczytuję archiwum…</p></div>
				{:else if latest.length}
					{#each latest as p (p.slug)}
						<PostCard post={p} />
					{/each}
				{:else}
					<div class="box__body"><p class="muted">Archiwum jest jeszcze puste.</p></div>
				{/if}
			</div>
		</div>

		<div class="col--side">
			<div class="box">
				<h2 class="box__title">fuw.lol</h2>
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

			{#if !loading && featured.length}
				<div class="box">
					<h2 class="box__title">Wyróżnione <small>wybór moderatorów</small></h2>
					{#each featured as p, i (p.slug)}
						{#if i > 0}<hr />{/if}
						<div class="side-item">
							{#if p.cover}
								<a href="/wpis/{p.slug}" tabindex="-1" aria-hidden="true"><img src={p.cover} alt="" loading="lazy" /></a>
							{/if}
							<p>
								<a href="/wpis/{p.slug}">{p.title}</a>
								{#if p.catalog_no}<span class="small muted">· {p.catalog_no}</span>{/if}
							</p>
						</div>
					{/each}
				</div>
			{/if}

			{#if categories.length}
				<div class="box">
					<h2 class="box__title">Kategorie</h2>
					<ul class="side-list">
						{#each categories as c (c.slug)}
							<li>
								<a href="/przegladaj?category={c.slug}" title={c.description || undefined}>
									<span aria-hidden="true">{c.emoji}</span> {c.name}
									<span class="cnt">({c.post_count})</span>
								</a>
							</li>
						{/each}
					</ul>
				</div>
			{/if}

			{#if stats}
				<div class="box">
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

			<ChatWidget />
		</div>
	</div>

	<TimeMachine />
{/if}
