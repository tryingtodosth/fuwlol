<script lang="ts">
	/** Browsing and searching. Every filter lives in the URL, so a search is a link you can
	 * send to somebody — and the back button does what it should. */
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { api, ApiError, qs } from '$lib/api';
	import type { Category, Page as ApiPage, Person, PostSummary, Tag } from '$lib/types';
	import PostCard from '$lib/components/PostCard.svelte';

	const PER_PAGE = 20;

	let q = $state('');
	let category = $state('');
	let person = $state('');
	let tag = $state('');
	let format = $state('');
	let yearFrom = $state('');
	let yearTo = $state('');
	let sort = $state('new');

	let categories = $state<Category[]>([]);
	let people = $state<Person[]>([]);
	let tags = $state<Tag[]>([]);

	let results = $state<PostSummary[]>([]);
	let count = $state(0);
	let pageNo = $state(1);
	let loading = $state(true);
	let error = $state('');

	const totalPages = $derived(Math.max(1, Math.ceil(count / PER_PAGE)));

	let gotOptions = false; // plain let: the option lists never change while you filter
	$effect(() => {
		if (gotOptions) return;
		gotOptions = true;
		Promise.all([
			api.get<Category[]>('/categories/'),
			api.get<Person[]>('/people/'),
			api.get<Tag[]>('/tags/')
		])
			.then(([c, p, t]) => {
				categories = c;
				people = p;
				tags = t;
			})
			.catch(() => {
				/* filtering by text still works without the lists */
			});
	});

	let syncedSearch: string | null = null; // plain let: guards against an effect loop
	$effect(() => {
		const search = page.url.search;
		if (search === syncedSearch) return;
		syncedSearch = search;
		const p = new URLSearchParams(search);
		q = p.get('q') ?? '';
		category = p.get('category') ?? '';
		person = p.get('person') ?? '';
		tag = p.get('tag') ?? '';
		format = p.get('format') ?? '';
		const single = p.get('year') ?? '';
		yearFrom = p.get('year_from') ?? single;
		yearTo = p.get('year_to') ?? single;
		sort = p.get('sort') ?? 'new';
		pageNo = Number(p.get('page') || '1') || 1;
		load(p);
	});

	async function load(p: URLSearchParams) {
		loading = true;
		error = '';
		try {
			const s = p.toString();
			const res = await api.get<ApiPage<PostSummary>>(`/posts/${s ? `?${s}` : ''}`);
			results = res.results;
			count = res.count;
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Nie udało się wczytać wyników.';
			results = [];
			count = 0;
		} finally {
			loading = false;
		}
	}

	function query(overrides: Record<string, string | number> = {}): string {
		return qs({
			q,
			category,
			person,
			tag,
			format,
			year_from: yearFrom,
			year_to: yearTo,
			sort: sort === 'new' ? '' : sort,
			...overrides
		});
	}

	function submit(e: SubmitEvent) {
		e.preventDefault();
		goto(`/przegladaj${query()}`, { keepFocus: true, noScroll: true });
	}

	function goPage(n: number) {
		goto(`/przegladaj${query({ page: n > 1 ? n : '' })}`, { noScroll: false });
	}
</script>

<svelte:head>
	<title>Przeglądaj — fuw.lol</title>
</svelte:head>

<div class="box">
	<h1 class="box__title">Przeglądaj archiwum</h1>
	<div class="box__body">
		<form onsubmit={submit}>
			<label for="f-q">Szukaj</label>
			<input id="f-q" type="text" bind:value={q} placeholder="tytuł, treść, tag, osoba…" />

			<div class="row">
				<div>
					<label for="f-cat">Kategoria</label>
					<select id="f-cat" bind:value={category}>
						<option value="">— wszystkie —</option>
						{#each categories as c (c.slug)}
							<option value={c.slug}>{c.emoji} {c.name} ({c.post_count})</option>
						{/each}
					</select>
				</div>
				<div>
					<label for="f-person">Osoba</label>
					<select id="f-person" bind:value={person}>
						<option value="">— ktokolwiek —</option>
						{#each people as p (p.slug)}
							<option value={p.slug}>{p.name} ({p.post_count})</option>
						{/each}
					</select>
				</div>
				<div>
					<label for="f-tag">Tag</label>
					<select id="f-tag" bind:value={tag}>
						<option value="">— dowolny —</option>
						{#each tags as t (t.slug)}
							<option value={t.slug}>{t.name} ({t.post_count})</option>
						{/each}
					</select>
				</div>
			</div>

			<div class="row">
				<div>
					<label for="f-format">Format</label>
					<select id="f-format" bind:value={format}>
						<option value="">— dowolny —</option>
						<option value="text">Tekst / Markdown</option>
						<option value="latex">LaTeX</option>
					</select>
				</div>
				<div>
					<label for="f-yf">Rok od</label>
					<input id="f-yf" type="text" inputmode="numeric" bind:value={yearFrom} placeholder="1998" />
				</div>
				<div>
					<label for="f-yt">Rok do</label>
					<input id="f-yt" type="text" inputmode="numeric" bind:value={yearTo} placeholder="2026" />
				</div>
				<div>
					<label for="f-sort">Sortuj</label>
					<select id="f-sort" bind:value={sort}>
						<option value="new">Najnowsze</option>
						<option value="top">Najwięcej reakcji</option>
						<option value="views">Najczęściej oglądane</option>
						<option value="old">Najstarsze</option>
						<option value="year">Wg roku (malejąco)</option>
					</select>
				</div>
			</div>

			<div class="buttons">
				<button type="submit">Filtruj</button>
				<a class="btn btn--ghost" href="/przegladaj">Wyczyść</a>
			</div>
		</form>
	</div>
</div>

<div class="box">
	<h2 class="box__title">
		Wyniki
		<small>{loading ? 'szukam…' : `${count} ${count === 1 ? 'wpis' : 'wpisów'}`}</small>
	</h2>
	{#if error}
		<div class="box__body"><div class="error">{error}</div></div>
	{:else if loading}
		<div class="box__body"><p class="muted">Szukam w archiwum…</p></div>
	{:else if results.length === 0}
		<div class="box__body">
			<p class="muted">Nic nie znaleziono — może <a href="/dodaj">dodasz</a>?</p>
		</div>
	{:else}
		{#each results as p (p.slug)}
			<PostCard post={p} />
		{/each}
	{/if}
</div>

{#if !loading && totalPages > 1}
	<div class="pager">
		<button type="button" class="btn btn--ghost" disabled={pageNo <= 1} onclick={() => goPage(pageNo - 1)}>
			← Poprzednia
		</button>
		<span class="small muted">strona {pageNo} z {totalPages}</span>
		<button
			type="button"
			class="btn btn--ghost"
			disabled={pageNo >= totalPages}
			onclick={() => goPage(pageNo + 1)}
		>
			Następna →
		</button>
	</div>
{/if}

<style>
	.buttons {
		display: flex;
		gap: 8px;
		margin-top: 12px;
	}
	.pager {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 12px;
		margin: 4px 0 16px;
	}
</style>
