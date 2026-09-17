<script lang="ts">
	/** The queue: everything waiting to be published, plus everything somebody has reported.
	 * A decision either updates the row in place or takes it off the list. */
	import { api, ApiError, qs } from '$lib/api';
	import { auth } from '$lib/auth.svelte';
	import { fmtDate, yearLabel, type Page as ApiPage, type Post, type Status } from '$lib/types';
	import PostBody from '$lib/components/PostBody.svelte';

	const PER_PAGE = 20;
	const REASON: Record<string, string> = {
		privacy: 'Dotyczy mnie i chcę usunięcia',
		wrong: 'Nieprawda / błąd',
		offensive: 'Obraźliwe',
		copyright: 'Prawa autorskie',
		other: 'Inne'
	};
	const LABEL: Record<Status, string> = {
		published: 'Opublikowany',
		pending: 'Czeka na moderację',
		rejected: 'Odrzucony',
		hidden: 'Ukryty',
		nuked: '☢ Nuklearne'
	};
	const PILL: Record<Status, string> = {
		published: 'pill--green',
		pending: 'pill--amber',
		rejected: 'pill--grey',
		hidden: 'pill--grey',
		nuked: '☢ Nuklearne'
	};

	let items = $state<Post[]>([]);
	let count = $state(0);
	let pageNo = $state(1);
	let loading = $state(true);
	let error = $state('');
	let notes = $state<Record<string, string>>({});
	let open = $state<Record<string, boolean>>({});
	let busySlug = $state('');

	const totalPages = $derived(Math.max(1, Math.ceil(count / PER_PAGE)));

	let loadedPage = 0; // plain let: guards the fetch so the effect cannot loop
	$effect(() => {
		if (!auth.ready || !auth.isStaff) return;
		if (pageNo === loadedPage) return;
		loadedPage = pageNo;
		load(pageNo);
	});

	async function load(n: number) {
		loading = true;
		error = '';
		try {
			const res = await api.get<ApiPage<Post>>(`/posts/queue/${qs({ page: n > 1 ? n : '' })}`);
			items = res.results;
			count = res.count;
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Nie udało się wczytać kolejki.';
		} finally {
			loading = false;
		}
	}

	async function act(p: Post, decision: string) {
		if (busySlug) return;
		busySlug = p.slug;
		error = '';
		try {
			const r = await api.post<Post>(`/posts/${p.slug}/moderate/`, {
				decision,
				note: notes[p.slug] ?? ''
			});
			const stillHere = r.status === 'pending' || (r.reports?.length ?? 0) > 0;
			if (stillHere) {
				items = items.map((x) => (x.slug === r.slug ? r : x));
			} else {
				items = items.filter((x) => x.slug !== r.slug);
				count = Math.max(0, count - 1);
			}
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Decyzja nie przeszła.';
		} finally {
			busySlug = '';
		}
	}
</script>

<svelte:head><title>Moderacja — fuw.lol</title></svelte:head>

{#if !auth.ready}
	<div class="box"><div class="box__body"><p class="muted">Chwileczkę…</p></div></div>
{:else if !auth.isStaff}
	<div class="box">
		<h1 class="box__title">Moderacja</h1>
		<div class="box__body"><p>Tylko dla moderatorów.</p></div>
	</div>
{:else}
	<div class="box">
		<h1 class="box__title">
			Kolejka moderacji
			<small>{loading ? 'wczytuję…' : `${count} do przejrzenia`}</small>
		</h1>
		{#if error}
			<div class="box__body"><div class="error">{error}</div></div>
		{/if}
		{#if loading}
			<div class="box__body"><p class="muted">Wczytuję…</p></div>
		{:else if items.length === 0}
			<div class="box__body"><p class="muted">Pusto. Nic nie czeka i nikt się nie skarży.</p></div>
		{:else}
			{#each items as p (p.slug)}
				<div class="q">
					<h3 class="q__title">
						{#if p.catalog_no}<span class="stamp">{p.catalog_no}</span>{/if}
						<a href="/wpis/{p.slug}">{p.title}</a>
						<span class="pill {PILL[p.status]}">{LABEL[p.status]}</span>
						{#if p.featured}<span class="pill pill--amber">Wyróżnione</span>{/if}
					</h3>
					<div class="small muted">
						{p.submitted_by || 'ktoś'} · dodano {fmtDate(p.created_at)} · {p.category_name} ·
						{yearLabel(p)} · {p.format === 'latex' ? 'LaTeX' : 'Tekst'}
					</div>
					{#if p.summary}<p class="small">{p.summary}</p>{/if}

					{#if p.reports?.length}
						<div class="reports">
							<strong class="small">Zgłoszenia ({p.reports.length}):</strong>
							<ul>
								{#each p.reports as r (r.id)}
									<li class="small">
										<strong>{REASON[r.reason] ?? r.reason}</strong>
										{#if r.formal}<span class="pill pill--amber" title="Zgłaszający podał kontakt i oświadczył dobrą wiarę — formalne zawiadomienie z art. 16 DSA">formalne (DSA)</span>{/if}
										{#if r.note} — {r.note}{/if}
										{#if r.contact_email}
											<span class="muted">· kontakt: {r.contact_email}</span>
										{/if}
										<span class="muted">· {fmtDate(r.created_at)}</span>
									</li>
								{/each}
							</ul>
						</div>
					{/if}

					<p class="small">
						<button
							type="button"
							class="linky"
							onclick={() => (open = { ...open, [p.slug]: !open[p.slug] })}
						>
							{open[p.slug] ? 'Ukryj podgląd' : 'Pokaż podgląd treści'}
						</button>
					</p>
					{#if open[p.slug]}
						<div class="prev">
							<PostBody format={p.format} body={p.body} attachments={p.attachments} />
						</div>
					{/if}

					<label for="n-{p.slug}">Notatka moderatora (trafia do autora)</label>
					<textarea
						id="n-{p.slug}"
						rows="2"
						value={notes[p.slug] ?? ''}
						oninput={(e) => (notes = { ...notes, [p.slug]: e.currentTarget.value })}
					></textarea>

					<div class="q__acts">
						<button type="button" disabled={busySlug === p.slug} onclick={() => act(p, 'publish')}>
							Opublikuj
						</button>
						<button
							type="button"
							class="btn btn--warn"
							disabled={busySlug === p.slug}
							onclick={() => act(p, 'reject')}
						>
							Odrzuć
						</button>
						<button
							type="button"
							class="btn btn--ghost"
							disabled={busySlug === p.slug}
							onclick={() => act(p, 'hide')}
						>
							Ukryj
						</button>
						<button
							type="button"
							class="btn btn--ghost"
							disabled={busySlug === p.slug}
							onclick={() => act(p, p.featured ? 'unfeature' : 'feature')}
						>
							{p.featured ? 'Cofnij wyróżnienie' : 'Wyróżnij'}
						</button>
						{#if p.reports?.length}
							<button
								type="button"
								class="btn btn--ghost"
								disabled={busySlug === p.slug}
								onclick={() => act(p, 'resolve_reports')}
							>
								Zamknij zgłoszenia
							</button>
						{/if}
					</div>
				</div>
			{/each}
		{/if}
	</div>

	{#if !loading && totalPages > 1}
		<div class="pager">
			<button type="button" class="btn btn--ghost" disabled={pageNo <= 1} onclick={() => (pageNo -= 1)}>
				← Poprzednia
			</button>
			<span class="small muted">strona {pageNo} z {totalPages}</span>
			<button
				type="button"
				class="btn btn--ghost"
				disabled={pageNo >= totalPages}
				onclick={() => (pageNo += 1)}
			>
				Następna →
			</button>
		</div>
	{/if}
{/if}

<style>
	.q {
		padding: 12px;
		border-bottom: 1px solid #e6e6e6;
	}
	.q:last-child {
		border-bottom: 0;
	}
	.q__title {
		font-size: 15px;
		font-weight: normal;
		margin: 0 0 4px;
	}
	.q__title .stamp {
		margin-right: 6px;
	}
	.q__acts {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
		margin-top: 8px;
	}
	.reports {
		border: 1px solid #f2b8b8;
		background: #fff0f0;
		padding: 6px 9px;
		margin: 6px 0;
	}
	.reports ul {
		margin: 4px 0 0;
		padding-left: 18px;
	}
	.prev {
		border: 1px dashed var(--line);
		background: var(--box);
		padding: 8px 10px;
		margin: 6px 0;
		max-height: 420px;
		overflow: auto;
	}
	.linky {
		background: none;
		border: 0;
		padding: 0;
		font-size: 11px;
		color: var(--rust);
		cursor: pointer;
		font-family: inherit;
	}
	.linky:hover {
		background: none;
		text-decoration: underline;
	}
	.pager {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 12px;
		margin: 4px 0 16px;
	}
</style>
