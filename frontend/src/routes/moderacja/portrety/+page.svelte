<script lang="ts">
	/** The portrait queue: every photograph of a person waiting for a decision.
	 *
	 * A separate page from /moderacja on purpose. That queue is about posts — a text, a
	 * scan, a meme — and the question it asks is whether the archive wants the thing. This
	 * one asks a different question with a statute behind it: is this a photograph of the
	 * person it claims to be, and does the provenance line hold up (art. 81 pr. aut. lets
	 * us publish a likeness only because that person said yes, and the gallery only exists
	 * for people who did). Mixing the two would mean answering both with one glance.
	 *
	 * Trusted tier, like /tablica — the same people who can hide a post. The server
	 * re-checks every call; this page only decides what to draw.
	 */
	import { onMount } from 'svelte';
	import { ApiError } from '$lib/api';
	import { auth } from '$lib/auth.svelte';
	import { fmtDate } from '$lib/types';
	import { plural } from '$lib/plural';
	import {
		loadMore,
		loadPortraitQueue,
		moderatePortrait,
		type PortraitQueueResponse,
		type QueuePortrait
	} from '$lib/portraits';

	let page = $state<PortraitQueueResponse | null>(null);
	/** Accumulated across „Pokaż więcej"; `page` is the last envelope, which is where
	 * `count` and `next` live. */
	let items = $state<QueuePortrait[]>([]);
	let loading = $state(true);
	let loadingMore = $state(false);
	let error = $state('');
	let notes = $state<Record<number, string>>({});
	let busyId = $state<number | null>(null);

	// the toolbar
	let sort = $state<'old' | 'new'>('old');
	/** A slug, not a name. The queue spans every person and a typeahead over the whole
	 * directory is a bigger feature than this page is; the <select> is built from the
	 * people actually present in what has been loaded, which is the useful subset. */
	let personSlug = $state('');

	const allowed = $derived(auth.isStaff || !!auth.user?.is_trusted);
	const count = $derived(page?.count ?? 0);
	const remaining = $derived(Math.max(0, count - items.length));
	/** Every person with something in the loaded pages, for the filter. Kept from the
	 * WIDEST listing seen so far, so choosing a person and then choosing "wszyscy" does
	 * not leave the select with one option in it. */
	let known = $state<{ slug: string; name: string }[]>([]);

	let loadedKey = ''; // plain let: guards the fetch so the $effect cannot loop
	$effect(() => {
		if (!auth.ready || !allowed) return;
		const key = `${sort}|${personSlug}`;
		if (key === loadedKey) return;
		loadedKey = key;
		load();
	});
	onMount(() => {
		document.title = 'Portrety — moderacja — fuw.lol';
	});

	function remember(rows: QueuePortrait[]) {
		const seen = new Map(known.map((k) => [k.slug, k]));
		for (const r of rows) seen.set(r.person.slug, { slug: r.person.slug, name: r.person.full_name });
		known = [...seen.values()].sort((a, b) => a.name.localeCompare(b.name, 'pl'));
	}

	async function load() {
		loading = true;
		error = '';
		try {
			const res = await loadPortraitQueue({ sort, person: personSlug || undefined });
			page = res;
			items = res.items;
			remember(res.items);
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Nie udało się wczytać kolejki.';
		} finally {
			loading = false;
		}
	}

	async function more() {
		const next = page?.next;
		if (!next || loadingMore) return;
		loadingMore = true;
		error = '';
		try {
			const res = await loadMore<PortraitQueueResponse>(next);
			page = res;
			items = [...items, ...res.items];
			remember(res.items);
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Nie udało się wczytać kolejnych zdjęć.';
		} finally {
			loadingMore = false;
		}
	}

	async function decide(p: QueuePortrait, decision: 'publish' | 'reject') {
		if (busyId !== null) return;
		busyId = p.id;
		error = '';
		try {
			await moderatePortrait(p.id, decision, notes[p.id] ?? '');
			// Off the list either way — a decided photograph is not pending any more. The
			// row itself survives in the database with the decision on it; this list is
			// the queue, not the history. The count follows, so „Pokaż więcej (k)" keeps
			// telling the truth without a second round trip.
			items = items.filter((x) => x.id !== p.id);
			if (page) page = { ...page, count: Math.max(0, page.count - 1) };
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Decyzja nie przeszła.';
		} finally {
			busyId = null;
		}
	}
</script>

<svelte:head><title>Portrety — moderacja — fuw.lol</title></svelte:head>

<h1>Portrety w kolejce</h1>

{#if !auth.ready}
	<div class="box"><div class="box__body"><p class="muted">Chwileczkę…</p></div></div>
{:else if !allowed}
	<div class="box">
		<div class="box__body">
			<p>Kolejka portretów jest dla zaufanych użytkowników (zweryfikowana afiliacja) i administracji.</p>
			<p>
				<a href="/konto">Zweryfikuj adres instytucjonalny</a> albo
				<a href="/logowanie?next=/moderacja/portrety">zaloguj się</a>.
			</p>
		</div>
	</div>
{:else}
	<div class="box box--grey">
		<div class="box__body">
			<p class="small">
				Zdjęcia osób czekające na decyzję. Publikujemy wyłącznie zdjęcia osób, które potwierdziły
				zgodę na wizerunek (art. 81 pr. aut.) — jeśli zgoda zniknęła, zdjęcie zniknie z tej kolejki
				samo. Sprawdź trzy rzeczy: czy to ta osoba, czy proweniencja („skąd to zdjęcie”) się trzyma
				kupy i czy zdjęcie nie jest złośliwe. Odrzucone zostaje w bazie razem z powodem.
			</p>
		</div>
	</div>

	{#if error}<div class="error">{error}</div>{/if}

	<div class="box">
		<h2 class="box__title">
			Kolejka
			<small>
				{#if loading}
					wczytuję…
				{:else if items.length < count}
					{items.length} z {count}
				{:else}
					{count}
					{plural(count, 'zdjęcie', 'zdjęcia', 'zdjęć')}
				{/if}
			</small>
		</h2>
		<div class="box__body tools">
			<label class="tool">
				<span>Sortuj</span>
				<select bind:value={sort}>
					<option value="old">Najstarsze (kolejka)</option>
					<option value="new">Najnowsze</option>
				</select>
			</label>
			<label class="tool">
				<span>Osoba</span>
				<select bind:value={personSlug}>
					<option value="">wszyscy</option>
					{#each known as k (k.slug)}<option value={k.slug}>{k.name}</option>{/each}
				</select>
			</label>
		</div>
		{#if loading}
			<div class="box__body"><p class="muted">Wczytuję…</p></div>
		{:else if items.length === 0}
			<div class="box__body">
				<p class="muted">Pusto. Nikt nikomu nie zrobił zdjęcia — albo wszystko już przejrzane.</p>
			</div>
		{:else}
			{#each items as p (p.id)}
				<div class="q">
					<div class="q__row">
						<div class="q__thumb">
							{#if p.url}
								<a href={p.url} target="_blank" rel="noopener" title="Otwórz pełne zdjęcie">
									<img src={p.url} alt={p.caption || 'Zdjęcie bez podpisu'} />
								</a>
							{:else}
								<div class="q__gone small muted">plik niedostępny</div>
							{/if}
						</div>
						<div class="q__text">
							<h3 class="q__title">
								<a href="/ludzie/{p.person.slug}">{p.person.full_name}</a>
							</h3>
							<div class="small muted">
								dodał/a {p.uploaded_by || 'ktoś'} · {fmtDate(p.created_at)}
							</div>
							{#if p.caption}<p class="q__caption">{p.caption}</p>{/if}
							<p class="small">
								<strong>Skąd:</strong>
								{p.source_note || '— nie podano, i to samo w sobie jest argumentem'}
							</p>

							<label for="note-{p.id}">Powód / notatka (trafia do rejestru decyzji)</label>
							<textarea
								id="note-{p.id}"
								rows="2"
								value={notes[p.id] ?? ''}
								oninput={(e) => (notes = { ...notes, [p.id]: e.currentTarget.value })}
							></textarea>

							<div class="q__acts">
								<button type="button" disabled={busyId !== null} onclick={() => decide(p, 'publish')}>
									Opublikuj
								</button>
								<button
									type="button"
									class="btn btn--warn"
									disabled={busyId !== null}
									onclick={() => decide(p, 'reject')}
								>
									Odrzuć
								</button>
								<a class="btn btn--ghost btn--sm" href="/ludzie/{p.person.slug}">Zobacz stronę osoby</a>
							</div>
						</div>
					</div>
				</div>
			{/each}
			{#if page?.next}
				<div class="box__body center">
					<button type="button" class="btn btn--ghost btn--sm" disabled={loadingMore} onclick={more}>
						{loadingMore ? 'Wczytuję…' : `Pokaż więcej (${remaining})`}
					</button>
				</div>
			{/if}
		{/if}
	</div>
{/if}

<style>
	.q {
		padding: 12px;
		border-bottom: 1px solid #e6e6e6;
	}
	.q:last-child {
		border-bottom: 0;
	}
	.q__row {
		display: flex;
		gap: 14px;
		align-items: flex-start;
	}
	.q__thumb {
		flex: 0 0 130px;
	}
	.q__thumb img {
		width: 130px;
		height: 170px;
		object-fit: cover;
		border: 1px solid #ccc;
		background: var(--box);
		display: block;
	}
	.q__gone {
		width: 130px;
		height: 170px;
		border: 1px dashed #ccc;
		background: var(--box);
		display: flex;
		align-items: center;
		justify-content: center;
		text-align: center;
	}
	.q__text {
		flex: 1;
		min-width: 0;
	}
	.q__title {
		margin: 0 0 2px;
		font-size: 15px;
	}
	.q__caption {
		margin: 6px 0 4px;
	}
	.q__acts {
		display: flex;
		gap: 6px;
		align-items: center;
		flex-wrap: wrap;
		margin-top: 8px;
	}
	.q__acts a.btn {
		display: inline-block;
	}
	.tools {
		display: flex;
		flex-wrap: wrap;
		gap: 8px 14px;
		align-items: center;
		background: var(--box);
		border-bottom: 1px solid var(--line);
		padding: 6px 12px;
	}
	.tool {
		display: flex;
		align-items: center;
		gap: 5px;
		margin: 0;
		font-size: 11px;
		color: #333;
	}
	.tool select {
		width: auto;
		padding: 2px 4px;
		font-size: 11px;
	}
	@media (max-width: 640px) {
		.q__row {
			flex-direction: column;
		}
	}
</style>
