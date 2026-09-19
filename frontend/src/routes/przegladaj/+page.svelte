<script lang="ts">
	/** Browsing and searching. Every filter lives in the URL, so a search is a link you can
	 * send to somebody — and the back button does what it should.
	 *
	 * The person, subject and tag filters are the editor's pickers in single-select mode
	 * rather than `<select>` elements, for the same reason the editor stopped using
	 * checkboxes: a `<select>` has to download every option first, which stops being a list
	 * and starts being a phone book somewhere around two hundred people. The URL still holds
	 * slugs; a chip is only how one is drawn, and its label is fetched for the slug the URL
	 * arrived with, so a shared link shows „prof. dr hab. Helena Hamiltonian”, not
	 * „helena-hamiltonian”.
	 */
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { api, ApiError, qs } from '$lib/api';
	import type { Category, Page as ApiPage, Person, PostSummary, Subject, Tag } from '$lib/types';
	import PostCard from '$lib/components/PostCard.svelte';
	import TagPicker from '$lib/components/editor/TagPicker.svelte';
	import { type Chip, personChip, subjectChip, tagChip } from '$lib/components/editor/chips';

	const PER_PAGE = 20;

	let q = $state('');
	let category = $state('');
	let personChips = $state<Chip[]>([]);
	let subjectChips = $state<Chip[]>([]);
	let tagChips = $state<Chip[]>([]);
	let format = $state('');
	let yearFrom = $state('');
	let yearTo = $state('');
	let sort = $state('new');

	let categories = $state<Category[]>([]);

	let results = $state<PostSummary[]>([]);
	let count = $state(0);
	let pageNo = $state(1);
	let loading = $state(true);
	let error = $state('');

	const totalPages = $derived(Math.max(1, Math.ceil(count / PER_PAGE)));
	const person = $derived(personChips[0]?.slug ?? '');
	const subject = $derived(subjectChips[0]?.slug ?? '');
	const tag = $derived(tagChips[0]?.slug ?? '');

	let gotCategories = false; // plain let: the category list never changes while you filter
	$effect(() => {
		if (gotCategories) return;
		gotCategories = true;
		api.get<Category[]>('/categories/')
			.then((c) => (categories = c))
			.catch(() => {
				/* filtering by text still works without the list */
			});
	});

	/** The chip for a slug that came in through the URL. Provisional first (the slug is its
	 * own label, so the filter is visibly on even if the lookup fails), then the real name. */
	async function chipFor(kind: 'people' | 'subjects' | 'tags', slug: string): Promise<Chip> {
		try {
			if (kind === 'people') return personChip(await api.get<Person>(`/people/${slug}/`));
			if (kind === 'subjects') return subjectChip(await api.get<Subject>(`/subjects/${slug}/`));
			return tagChip(await api.get<Tag>(`/tags/${slug}/`));
		} catch {
			return { slug, name: slug };
		}
	}
	function sync(kind: 'people' | 'subjects' | 'tags', slug: string, current: Chip[], set: (c: Chip[]) => void) {
		if ((current[0]?.slug ?? '') === slug) return;
		if (!slug) {
			set([]);
			return;
		}
		set([{ slug, name: slug }]);
		chipFor(kind, slug).then((c) => {
			// the reader may have changed the filter while the name was in flight
			if (c.slug === (page.url.searchParams.get(kind === 'people' ? 'person' : kind === 'subjects' ? 'subject' : 'tag') ?? ''))
				set([c]);
		});
	}

	let syncedSearch: string | null = null; // plain let: guards against an effect loop
	$effect(() => {
		const search = page.url.search;
		if (search === syncedSearch) return;
		syncedSearch = search;
		const p = new URLSearchParams(search);
		q = p.get('q') ?? '';
		category = p.get('category') ?? '';
		sync('people', p.get('person') ?? '', personChips, (c) => (personChips = c));
		sync('subjects', p.get('subject') ?? '', subjectChips, (c) => (subjectChips = c));
		sync('tags', p.get('tag') ?? '', tagChips, (c) => (tagChips = c));
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
			subject,
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
			<input id="f-q" type="text" bind:value={q} placeholder="tytuł, treść, tag, osoba, przedmiot…" />

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
					<TagPicker
						kind="people"
						id="f-person"
						single
						selected={personChips}
						onchange={(c) => (personChips = c)}
						placeholder="— ktokolwiek —"
					/>
				</div>
				<div>
					<label for="f-subject">Przedmiot</label>
					<TagPicker
						kind="subjects"
						id="f-subject"
						single
						selected={subjectChips}
						onchange={(c) => (subjectChips = c)}
						placeholder="— dowolny —"
					/>
				</div>
				<div>
					<label for="f-tag">Tag</label>
					<TagPicker
						kind="tags"
						id="f-tag"
						single
						selected={tagChips}
						onchange={(c) => (tagChips = c)}
						placeholder="— dowolny —"
					/>
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
	/* The three pickers sit in a .row next to a <select>. Two things they need that a
	   <select> does not: a floor, so an empty one is the same height as its neighbours; and
	   permission to shrink below their own content, because a chip saying „Mechanika
	   klasyczna” gives the column a min-content width that pushed „Tag” onto a second line
	   the moment anybody filtered by a long subject. The chip ellipsises instead. */
	.row > div {
		min-width: 0;
	}
	.row :global(.pick__box) {
		min-height: 29px;
	}
</style>
