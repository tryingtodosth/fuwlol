<script lang="ts">
	/** The queue: everything waiting to be published, plus everything somebody has reported.
	 * A decision either updates the row in place or takes it off the list. */
	import { api, ApiError, qs } from '$lib/api';
	import { auth } from '$lib/auth.svelte';
	import { fmtDate, yearLabel, type Page as ApiPage, type Person, type Post, type Status } from '$lib/types';
	import PostBody from '$lib/components/PostBody.svelte';
	import TagPicker from '$lib/components/editor/TagPicker.svelte';
	import type { Chip } from '$lib/components/editor/chips';
	import { loadClaimQueue } from '$lib/consent';
	import { loadPortraitQueue } from '$lib/portraits';
	import { queueSize } from '$lib/queues';

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
	/** "<post slug>|<person slug>" — which NOWA chip has its „scal z…” picker open. One at a
	 * time, because merging is a decision about a named human being and two open pickers is
	 * two half-made decisions. */
	let mergeKey = $state('');
	let mergeChips = $state<Chip[]>([]);

	const totalPages = $derived(Math.max(1, Math.ceil(count / PER_PAGE)));

	let loadedPage = 0; // plain let: guards the fetch so the effect cannot loop
	$effect(() => {
		if (!auth.ready || !auth.isStaff) return;
		if (pageNo === loadedPage) return;
		loadedPage = pageNo;
		load(pageNo);
	});

	// The other two queues live in their own apps (consent, portraits); this page only says how
	// long they are. null = not known (a failed fetch must not print „(0)” and look empty).
	let claimCount = $state<number | null>(null);
	let portraitCount = $state<number | null>(null);
	let askedQueues = false; // plain let: once per visit, not once per page
	$effect(() => {
		if (!auth.ready || !auth.isStaff || askedQueues) return;
		askedQueues = true;
		loadClaimQueue().then((r) => (claimCount = queueSize(r))).catch(() => (claimCount = null));
		loadPortraitQueue({ limit: 1 }).then((r) => (portraitCount = queueSize(r))).catch(() => (portraitCount = null));
	});
	const n = (v: number | null) => (v == null ? '' : ` (${v})`);

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

	/** Write a new `people` list onto a pending post. Staff may already PATCH a post, so this
	 * needs no endpoint of its own — and deliberately does not get one: „the moderator edits
	 * the post" is the rule that already exists, and a second door into the same field is a
	 * second place for the authority check to be wrong.
	 *
	 * The PATCH answers with the ordinary detail payload (no `reports`, no `is_new`), so the
	 * row is merged rather than replaced: reports stay, and a person who was not on the post
	 * a moment ago is by definition not one of its new names. */
	async function setPeople(p: Post, people: Person[]) {
		if (busySlug) return;
		busySlug = p.slug;
		error = '';
		try {
			const r = await api.patch<Post>(`/posts/${p.slug}/`, { people: people.map((x) => x.slug) });
			const wasNew = new Map(p.people.map((x) => [x.slug, !!x.is_new]));
			const merged: Post = { ...p, people: r.people.map((x) => ({ ...x, is_new: wasNew.get(x.slug) ?? false })) };
			items = items.map((x) => (x.slug === p.slug ? merged : x));
			mergeKey = '';
			mergeChips = [];
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Nie udało się zmienić osób przy wpisie.';
		} finally {
			busySlug = '';
		}
	}
	function dropPerson(p: Post, person: Person) {
		setPeople(p, p.people.filter((x) => x.slug !== person.slug));
	}
	/** Replace the proposed person by an existing one. The orphan is not deleted here: it has
	 * no posts left, so `manage.py sweep_people` takes it after 30 days — and until then an
	 * undo is one click in the Django admin rather than an archaeological dig. */
	function mergePerson(p: Post, person: Person, into: Chip) {
		if (!into.slug) return;
		const keep = p.people.filter((x) => x.slug !== person.slug);
		if (keep.some((x) => x.slug === into.slug)) {
			setPeople(p, keep);
			return;
		}
		setPeople(p, [...keep, { ...person, slug: into.slug, name: into.name }]);
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
		<div class="box__body queues">
			<p class="small muted">
				Inne kolejki: <a href="/moderacja/zgody">Zgody{n(claimCount)}</a> — wnioski osób o własny wizerunek ·
				<a href="/moderacja/portrety">Portrety{n(portraitCount)}</a> — zdjęcia osób czekające na decyzję
			</p>
		</div>
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

					{#if p.people.some((x) => x.is_new)}
						<div class="newppl">
							<strong class="small">Nowe osoby w spisie:</strong>
							<p class="small muted">
								Autor wpisał te osoby ręcznie — nie było ich w spisie. Opublikowanie wpisu doda je do
								<a href="/ludzie">/ludzie</a>; odrzucenie zostawi je niewidoczne i sprzątnie po 30 dniach.
								Zanim opublikujesz, sprawdź, czy to nie ta sama osoba pod innym zapisem.
							</p>
							<ul class="newppl__list">
								{#each p.people.filter((x) => x.is_new) as person (person.slug)}
									<li class="small">
										<span class="pill pill--amber" title="osoba zaproponowana przy tym wpisie">NOWA</span>
										<strong>{person.full_name || person.name}</strong>
										{#if person.role}<span class="muted">— {person.role}</span>{/if}
										<button
											type="button"
											class="linky"
											disabled={busySlug === p.slug}
											onclick={() => dropPerson(p, person)}>usuń z wpisu</button
										>
										<button
											type="button"
											class="linky"
											disabled={busySlug === p.slug}
											onclick={() => {
												const key = `${p.slug}|${person.slug}`;
												mergeKey = mergeKey === key ? '' : key;
												mergeChips = [];
											}}>scal z…</button
										>
										{#if mergeKey === `${p.slug}|${person.slug}`}
											<span class="merge">
												<TagPicker
													kind="people"
													single
													selected={mergeChips}
													onchange={(c) => {
														mergeChips = c;
														if (c[0]) mergePerson(p, person, c[0]);
													}}
													placeholder="kto to naprawdę jest…"
												/>
											</span>
										{/if}
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
	.queues { padding-top: 6px; padding-bottom: 6px; border-bottom: 1px solid #e6e6e6; }
	.queues p { margin: 0; }
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
	.linky:disabled {
		color: var(--muted);
		cursor: default;
	}
	.newppl {
		border: 1px solid #c98f1e;
		background: #fffbe8;
		padding: 6px 9px;
		margin: 6px 0;
	}
	.newppl p {
		margin: 3px 0 5px;
	}
	.newppl__list {
		margin: 0;
		padding-left: 18px;
	}
	.newppl__list li {
		margin-bottom: 3px;
	}
	.newppl__list button {
		margin-left: 8px;
	}
	.merge {
		display: block;
		max-width: 320px;
		margin: 4px 0 6px;
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
