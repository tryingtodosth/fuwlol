<script lang="ts">
	/** The photo gallery under a person's entry, and the vote that picks the profile photo.
	 *
	 * Mounted by the person page, which owns the 130 px photo in the header: this component
	 * never draws that one. It reports the winner upwards through `onCurrent` after every
	 * load and after every vote, and the page swaps its silhouette for whatever comes back
	 * — `null` included, which is what happens the moment consent is withdrawn.
	 *
	 * **Two states, and the default is the small one.** A person's entry is a directory row
	 * with a photo and a few lines of unit; a gallery that opens 400 px tall underneath it
	 * turns the page into the gallery's page. So COMPACT is one 64 px strip and one line of
	 * text — about the height of the header photo it belongs to — and everything else
	 * (the large photo, the captions, the provenance, the vote, the moderation buttons, the
	 * sort and filter toolbar, the upload form) waits behind a click. EXPANDED is the
	 * gallery; compact is a mention of it.
	 *
	 * Nothing here decides who may do what. `can_upload`, `upload_block_reason` and
	 * `can_moderate` all arrive from the server (backend/portraits/rules.py), and the one
	 * piece of copy this file owns about consent is the line shown when there is no gallery
	 * to show at all. A component that worked out "she said no, so hide the form" from the
	 * `consent` value would be a second implementation of art. 81, and the second
	 * implementation is always the one that is out of date.
	 *
	 * After a vote and after a moderation decision the whole page of the gallery is
	 * re-fetched rather than patched in place. One vote moves, so it changes at least two
	 * rows' numbers and possibly which photograph is at the top of the page; re-asking
	 * costs one GET over at most twelve rows and cannot drift, while patching is four
	 * guesses in a row.
	 */
	import { ApiError } from '$lib/api';
	import { auth } from '$lib/auth.svelte';
	import { dialog } from '$lib/dialog.svelte';
	import { plural } from '$lib/plural';
	import {
		CONSENT_PAGE,
		PORTRAIT_STATUS_LABEL,
		SORT_OPTIONS,
		STATUS_OPTIONS,
		loadMore,
		loadPortraits,
		moderatePortrait,
		uploadPortrait,
		votePortrait,
		type Portrait,
		type PortraitDecision,
		type PortraitSort,
		type PortraitStatusFilter,
		type PortraitsResponse
	} from '$lib/portraits';

	let { slug, onCurrent }: { slug: string; onCurrent?: (url: string | null) => void } = $props();

	// --- what the server said ---------------------------------------------------------
	let data = $state<PortraitsResponse | null>(null);
	/** Accumulated across „Pokaż więcej"; `data` is always the LAST page's envelope, which
	 * is where `count`, `next`, `current` and the permissions live. */
	let items = $state<Portrait[]>([]);
	let loading = $state(true);
	let loadingMore = $state(false);
	let missing = $state(false);
	let error = $state('');
	let busyId = $state<number | null>(null);

	// --- how it is being shown ---------------------------------------------------------
	let expanded = $state(false);
	let selectedId = $state<number | null>(null);
	let showUpload = $state(false);
	/** Which thumbnail opened the gallery, so collapsing can put focus back where the
	 * reader left it rather than at the top of the document. */
	let openedFrom = $state<number | null>(null);
	let stripEl = $state<HTMLElement | null>(null);

	// --- the toolbar (expanded only) ----------------------------------------------------
	let sort = $state<PortraitSort>('votes');
	let statusFilter = $state<PortraitStatusFilter>('published');
	let onlyMine = $state(false);

	// --- the upload form ------------------------------------------------------------------
	let file = $state<File | null>(null);
	let fileInput = $state<HTMLInputElement | null>(null);
	let caption = $state('');
	let sourceNote = $state('');
	let rights = $state(false);
	let uploading = $state(false);
	let justSent = $state('');

	let loadedKey = ''; // plain let: guards the fetch so the $effect cannot loop
	$effect(() => {
		const key = `${slug}|${sort}|${statusFilter}|${onlyMine}`;
		if (!slug || key === loadedKey) return;
		loadedKey = key;
		load(key);
	});

	async function load(key = loadedKey) {
		loading = true;
		try {
			const res = await loadPortraits(slug, { sort, status: statusFilter, mine: onlyMine });
			if (key !== loadedKey) return; // the question changed while this was in flight
			data = res;
			items = res.items;
			missing = false;
			syncSelection();
			onCurrent?.(res.current?.url ?? null);
		} catch (e) {
			if (e instanceof ApiError && e.status === 404) {
				// no such person, or an entry that has been taken out of the index entirely —
				// the page around us says so; a second "nie znaleziono" box would just shout.
				missing = true;
				data = null;
				items = [];
				onCurrent?.(null);
			} else {
				error = e instanceof ApiError ? e.message : 'Nie udało się wczytać galerii.';
			}
		} finally {
			loading = false;
		}
	}

	/** Append the next page. The URL comes from the server and already carries the sort and
	 * the filter, so this cannot drift out of step with what is on screen. */
	async function more() {
		const next = data?.next;
		if (!next || loadingMore) return;
		loadingMore = true;
		error = '';
		try {
			const res = await loadMore<PortraitsResponse>(next);
			data = res;
			items = [...items, ...res.items];
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Nie udało się wczytać kolejnych zdjęć.';
		} finally {
			loadingMore = false;
		}
	}

	/** Keep a selection that still exists. A filter change, a rejection or a moved vote can
	 * all take the selected photograph off the page; falling back to the winner (when it is
	 * on this page at all) and then to the first row means the stage is never empty while
	 * there is something to put on it. */
	function syncSelection() {
		if (selectedId !== null && items.some((i) => i.id === selectedId)) return;
		const winner = data?.current?.id ?? null;
		selectedId = winner !== null && items.some((i) => i.id === winner) ? winner : (items[0]?.id ?? null);
	}

	const currentId = $derived(data?.current?.id ?? null);
	const count = $derived(data?.count ?? 0);
	const consent = $derived(data?.consent ?? 'unknown');
	const blockReason = $derived(data?.upload_block_reason ?? '');
	const selected = $derived(items.find((i) => i.id === selectedId) ?? null);
	const remaining = $derived(Math.max(0, count - items.length));
	/** The trusted tier, read the same way /tablica reads it — the server re-checks every
	 * call, so this only decides whether to draw the controls. */
	const moderator = $derived(auth.isStaff || !!auth.user?.is_trusted);
	/** The backend writes the explainer's path into the sentence itself; we print the
	 * sentence exactly as it came and turn that bare path into a real link. Splitting on
	 * the path rather than on the Polish words means a reworded refusal still links. */
	const reasonHead = $derived(
		blockReason.includes(CONSENT_PAGE) ? blockReason.slice(0, blockReason.indexOf(CONSENT_PAGE)) : blockReason
	);
	const linksToConsent = $derived(blockReason.includes(CONSENT_PAGE));
	/** Nothing to show and no consent behind it: one line, and a way to find out why. */
	const empty = $derived(consent !== 'granted' && items.length === 0);

	function thumbLabel(p: Portrait): string {
		const what = p.caption || 'zdjęcie bez podpisu';
		const state = p.status === 'published' ? '' : `, ${PORTRAIT_STATUS_LABEL[p.status]}`;
		const win = p.id === currentId ? ', zdjęcie profilowe' : '';
		return `${what}${win}${state}, głosów: ${p.votes}`;
	}

	function focusThumb(id: number) {
		stripEl?.querySelector<HTMLButtonElement>(`button[data-pid="${id}"]`)?.focus();
	}

	function pickThumb(p: Portrait) {
		if (!expanded) {
			openedFrom = p.id;
			expanded = true;
		}
		selectedId = p.id;
	}

	function collapse() {
		const back = openedFrom ?? selectedId;
		expanded = false;
		showUpload = false;
		openedFrom = null;
		if (back !== null) queueMicrotask(() => focusThumb(back));
	}

	/** From compact this opens the gallery AND the form — somebody who clicks "add a
	 * photo" has said what they want. Inside the gallery it is an ordinary toggle. */
	function openUpload() {
		if (!expanded) {
			expanded = true;
			showUpload = true;
			return;
		}
		showUpload = !showUpload;
	}

	/** ← / → walk the strip while it has focus: the selection follows the focus, which is
	 * what makes the strip behave like the picture-picker it looks like. Bound to each
	 * button rather than to the list, because a keyboard handler on a non-interactive
	 * <ul> is a handler that only fires when something inside it is focused anyway. */
	function stripKey(e: KeyboardEvent) {
		if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
		const at = items.findIndex((i) => i.id === selectedId);
		const from = at < 0 ? 0 : at;
		const to = e.key === 'ArrowRight' ? Math.min(from + 1, items.length - 1) : Math.max(from - 1, 0);
		const target = items[to];
		if (!target || target.id === selectedId) return;
		e.preventDefault();
		selectedId = target.id;
		queueMicrotask(() => focusThumb(target.id));
	}

	function pick(e: Event) {
		const input = e.currentTarget as HTMLInputElement;
		file = input.files?.[0] ?? null;
	}

	async function vote(p: Portrait) {
		if (busyId !== null) return;
		busyId = p.id;
		error = '';
		try {
			await votePortrait(p.id);
			await load();
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Nie udało się zagłosować.';
		} finally {
			busyId = null;
		}
	}

	/** Only the decisions that mean something from where the photograph currently is.
	 * Offering "Opublikuj" on something already published buys one 409 and no information;
	 * `rejected` and `hidden` are different words on purpose (refused vs taken down), so
	 * they get different ways back. */
	function decisionsFor(p: Portrait): PortraitDecision[] {
		if (p.status === 'pending') return ['publish', 'reject'];
		if (p.status === 'published') return ['hide'];
		if (p.status === 'hidden') return ['restore', 'reject'];
		return ['restore'];
	}

	const DECISION: Record<PortraitDecision, { label: string; title: string; text: string }> = {
		publish: {
			label: 'Opublikuj',
			title: 'Opublikuj zdjęcie',
			text: 'Trafi do galerii i stanie do głosowania na zdjęcie profilowe tej osoby.'
		},
		reject: {
			label: 'Odrzuć',
			title: 'Odrzuć zdjęcie',
			text: 'Nie trafi do galerii. Zostaje w bazie razem z decyzją — powód zobaczy osoba, która je przysłała.'
		},
		hide: {
			label: 'Ukryj',
			title: 'Ukryj zdjęcie',
			text: 'Zniknie z galerii i z głosowania. Zostaje w bazie; każdy zaufany może je przywrócić.'
		},
		restore: {
			label: 'Przywróć',
			title: 'Przywróć zdjęcie',
			text: 'Wróci do galerii i znów będzie mogło zbierać głosy.'
		}
	};

	async function moderate(p: Portrait, decision: PortraitDecision) {
		if (busyId !== null) return;
		const d = DECISION[decision];
		const note = await dialog.ask({
			title: d.title,
			text: d.text,
			confirm: d.label,
			reason: 'optional',
			placeholder: 'powód — zostanie w rejestrze decyzji'
		});
		if (note === null) return;
		busyId = p.id;
		error = '';
		try {
			await moderatePortrait(p.id, decision, note);
			await load();
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Decyzja nie przeszła.';
		} finally {
			busyId = null;
		}
	}

	async function send(e: SubmitEvent) {
		e.preventDefault();
		if (uploading) return;
		if (!file) {
			error = 'Najpierw wybierz plik ze zdjęciem.';
			return;
		}
		uploading = true;
		error = '';
		justSent = '';
		try {
			const fd = new FormData();
			fd.append('file', file);
			fd.append('caption', caption);
			fd.append('source_note', sourceNote);
			fd.append('rights_confirmed', String(rights));
			const created = await uploadPortrait(slug, fd);
			justSent =
				created.status === 'published'
					? 'Zdjęcie jest już w galerii.'
					: 'Zdjęcie czeka na moderację — pojawi się w galerii po decyzji. Znajdziesz je przez „tylko moje”.';
			file = null;
			caption = '';
			sourceNote = '';
			rights = false;
			showUpload = false;
			if (fileInput) fileInput.value = '';
			await load();
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Nie udało się wysłać zdjęcia.';
		} finally {
			uploading = false;
		}
	}
</script>

{#snippet strip()}
	<ul class="strip" bind:this={stripEl} aria-label="Zdjęcia tej osoby — wybierz, żeby powiększyć">
		{#each items as p (p.id)}
			<li>
				<button
					type="button"
					class="thumb"
					class:thumb--on={expanded && p.id === selectedId}
					class:thumb--dim={p.status !== 'published'}
					data-pid={p.id}
					aria-current={expanded && p.id === selectedId ? 'true' : undefined}
					aria-label={thumbLabel(p)}
					title={p.id === currentId ? 'zdjęcie profilowe' : p.caption || 'zdjęcie bez podpisu'}
					onclick={() => pickThumb(p)}
					onkeydown={stripKey}
				>
					{#if p.url}
						<img src={p.url} alt="" />
					{:else}
						<span class="thumb__gone" aria-hidden="true">?</span>
					{/if}
					{#if p.id === currentId}
						<span class="thumb__win" aria-hidden="true">✓</span>
					{/if}
					<span class="thumb__n" aria-hidden="true">{p.votes}</span>
				</button>
			</li>
		{/each}
	</ul>
{/snippet}

{#if !missing}
	<div class="box">
		<h2 class="box__title">
			Galeria
			<small>
				{#if loading && !data}
					wczytuję…
				{:else if expanded && items.length < count}
					{items.length} z {count}
				{:else}
					{count}
					{plural(count, 'zdjęcie', 'zdjęcia', 'zdjęć')}
				{/if}
			</small>
		</h2>
		<div class="box__body" class:box__body--tight={!expanded}>
			{#if error}<div class="error">{error}</div>{/if}
			{#if justSent}<div class="ok">{justSent}</div>{/if}

			{#if empty}
				<p class="muted">
					Galeria pojawi się, gdy osoba potwierdzi zgodę na wizerunek —
					<a href={CONSENT_PAGE}>jak to działa</a>.
				</p>
			{:else}
				<!-- The toolbar is drawn whenever the gallery is open, EVEN with nothing in
				     it: a filter that matches nothing is exactly when the reader needs the
				     control that would undo it. -->
				{#if expanded}
					<div class="tools">
						<label class="tool">
							<span>Sortuj</span>
							<select bind:value={sort}>
								{#each SORT_OPTIONS as o (o.value)}<option value={o.value}>{o.label}</option>{/each}
							</select>
						</label>
						{#if moderator}
							<label class="tool">
								<span>Status</span>
								<select bind:value={statusFilter}>
									{#each STATUS_OPTIONS as o (o.value)}<option value={o.value}>{o.label}</option>{/each}
								</select>
							</label>
						{/if}
						{#if auth.isAuthenticated}
							<label class="tool tool--check">
								<input type="checkbox" bind:checked={onlyMine} />
								<span>tylko moje</span>
							</label>
						{/if}
					</div>
				{/if}

				{#if items.length === 0}
					{#if !loading}
						<p class="muted">
							{#if statusFilter !== 'published' || onlyMine}
								Nic tu nie pasuje do wybranego filtra.
							{:else}
								Jeszcze żadnych zdjęć. Pierwsze zostaje pierwsze — i zwykle wygrywa.
							{/if}
						</p>
					{/if}
				{:else}
					{#if expanded && selected}
						<div class="stage">
							{#if selected.url}
								<a href={selected.url} target="_blank" rel="noopener" title="Otwórz pełne zdjęcie">
									<img class="stage__img" src={selected.url} alt={selected.caption || 'Zdjęcie bez podpisu'} />
								</a>
							{:else}
								<p class="muted">Plik tego zdjęcia jest niedostępny.</p>
							{/if}
							<div class="stage__meta">
								{#if selected.id === currentId}
									<span class="pill pill--green">zdjęcie profilowe</span>
								{/if}
								{#if selected.status !== 'published'}
									<span class="pill pill--grey">{PORTRAIT_STATUS_LABEL[selected.status]}</span>
								{/if}
								{#if selected.caption}<div class="stage__caption">{selected.caption}</div>{/if}
								{#if selected.source_note}<div class="small muted">{selected.source_note}</div>{/if}
								<div class="small muted">dodał/a {selected.uploaded_by || 'ktoś'}</div>
								<div class="stage__acts">
									{#if selected.status === 'published'}
										{#if auth.isAuthenticated}
											<button
												type="button"
												class="btn btn--ghost btn--sm"
												class:is-active={selected.my_vote}
												aria-pressed={selected.my_vote}
												disabled={busyId !== null}
												onclick={() => selected && vote(selected)}
											>
												{selected.my_vote ? 'Twój głos ✓' : 'Głosuj'}
												<span class="n">{selected.votes}</span>
											</button>
										{:else}
											<a class="btn btn--ghost btn--sm" href="/logowanie?next=/ludzie/{slug}" title="Zaloguj się, żeby zagłosować">
												Głosuj <span class="n">{selected.votes}</span>
											</a>
										{/if}
									{/if}
									{#if selected.can_moderate}
										{#each decisionsFor(selected) as d (d)}
											<button
												type="button"
												class="btn btn--sm btn--ghost"
												disabled={busyId !== null}
												onclick={() => selected && moderate(selected, d)}
											>
												{DECISION[d].label}
											</button>
										{/each}
									{/if}
								</div>
							</div>
						</div>
					{/if}

					{@render strip()}

					{#if expanded && data?.next}
						<p class="more">
							<button type="button" class="btn btn--ghost btn--sm" disabled={loadingMore} onclick={more}>
								{loadingMore ? 'Wczytuję…' : `Pokaż więcej (${remaining})`}
							</button>
						</p>
					{/if}
				{/if}

				<p class="small muted line">
					{#if items.length}Zdjęcie profilowe wybiera głosowanie — jeden głos na osobę.{/if}
					{#if expanded}
						<button type="button" class="linky" onclick={collapse}>Zwiń galerię</button>
					{:else if items.length}
						<button type="button" class="linky" onclick={() => (expanded = true)}>Pokaż galerię</button>
					{/if}
					{#if data?.can_upload}
						<button type="button" class="linky" aria-expanded={showUpload} onclick={openUpload}>
							Dodaj zdjęcie
						</button>
					{:else if !auth.isAuthenticated}
						<a href="/logowanie?next=/ludzie/{slug}">Zaloguj się, żeby dodać zdjęcie</a>
					{/if}
				</p>

				<!-- The other refusals (the caps) are long, and compact is one line by
				     contract — so they are shown where there is room for them. -->
				{#if expanded && !data?.can_upload && blockReason && auth.isAuthenticated}
					<p class="help">
						{reasonHead}{#if linksToConsent}<a href={CONSENT_PAGE}>{CONSENT_PAGE}</a>{/if}
					</p>
				{/if}
			{/if}

			{#if expanded && showUpload && data?.can_upload}
				<form class="add" onsubmit={send}>
					<h3>Dodaj zdjęcie</h3>
					<label for="portrait-file">Plik (obraz)</label>
					<input id="portrait-file" type="file" accept="image/*" bind:this={fileInput} onchange={pick} />

					<label for="portrait-caption">Podpis (opcjonalnie)</label>
					<input id="portrait-caption" type="text" maxlength="200" bind:value={caption} placeholder="np. przy tablicy, po kolokwium" />

					<label for="portrait-source">Skąd to zdjęcie (opcjonalnie)</label>
					<input id="portrait-source" type="text" maxlength="300" bind:value={sourceNote} placeholder="np. zdjęcie własne, 2019; albo: z gazetki koła naukowego" />
					<div class="help">Archiwum bez proweniencji to folder ze zdjęciami. Napisz, skąd to masz.</div>

					<label class="check">
						<input type="checkbox" bind:checked={rights} />
						<span>
							Mam prawo opublikować to zdjęcie (jest moje albo mam zgodę autora), a osoba na nim
							potwierdziła na tej stronie zgodę na wizerunek
						</span>
					</label>

					<div class="add__acts">
						<button type="submit" disabled={uploading || !file || !rights}>
							{uploading ? 'Wysyłam…' : 'Wyślij zdjęcie'}
						</button>
						<span class="small muted">JPG, PNG, GIF lub WebP, do 25 MB. Metadane (w tym GPS) są usuwane.</span>
					</div>
				</form>
			{/if}
		</div>
	</div>
{/if}

<style>
	/* Compact is meant to be about as tall as the header photo it belongs to: one 64 px
	   row and one line of text. The padding is trimmed from the global .box__body's 12 px
	   for the same reason — this box is a mention of a gallery, not the gallery. */
	.box__body--tight {
		padding: 8px 12px;
	}
	.strip {
		list-style: none;
		margin: 0;
		padding: 0 0 2px;
		display: flex;
		flex-wrap: nowrap;
		gap: 6px;
		overflow-x: auto;
	}
	.strip li {
		flex: 0 0 auto;
	}
	/* A real <button>, so it is reachable and announced — but none of the green chrome the
	   global button rule gives it. */
	.thumb {
		position: relative;
		width: 64px;
		height: 64px;
		padding: 0;
		border: 1px solid #ccc;
		background: var(--box);
		display: block;
		cursor: pointer;
		line-height: 0;
	}
	.thumb:hover {
		background: var(--box);
		border-color: var(--green);
	}
	.thumb:focus-visible {
		outline: 2px solid var(--amber);
		outline-offset: 1px;
	}
	.thumb--on {
		border-color: #c98f1e;
		outline: 2px solid var(--amber);
		outline-offset: -2px;
	}
	.thumb--dim img {
		opacity: 0.55;
	}
	.thumb img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}
	.thumb__gone {
		display: block;
		line-height: 62px;
		text-align: center;
		color: var(--muted);
		font-size: 16px;
	}
	.thumb__win {
		position: absolute;
		top: 0;
		left: 0;
		background: var(--green);
		color: #fff;
		font-size: 10px;
		line-height: 13px;
		padding: 0 3px;
	}
	.thumb__n {
		position: absolute;
		right: 0;
		bottom: 0;
		background: rgba(255, 255, 255, 0.88);
		border-top: 1px solid #ccc;
		border-left: 1px solid #ccc;
		color: #333;
		font-size: 10px;
		line-height: 13px;
		padding: 0 3px;
	}
	.line {
		margin: 6px 0 0;
	}
	/* A button that reads as a link: the row is a sentence, and three green buttons in the
	   middle of a sentence is a toolbar pretending to be prose. */
	.linky {
		background: none;
		border: 0;
		padding: 0 0 0 6px;
		font: inherit;
		font-size: 11px;
		color: var(--rust);
		cursor: pointer;
	}
	.linky:hover {
		background: none;
		text-decoration: underline;
	}
	.tools {
		display: flex;
		flex-wrap: wrap;
		gap: 8px 14px;
		align-items: flex-end;
		margin: 0 0 10px;
		padding: 6px 8px;
		background: var(--box);
		border: 1px solid var(--line);
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
	.tool--check input {
		width: auto;
		margin: 0;
	}
	.stage {
		margin: 0 0 10px;
		text-align: center;
	}
	.stage__img {
		max-height: 360px;
		max-width: 100%;
		border: 1px solid #ccc;
		background: var(--box);
	}
	.stage__meta {
		margin-top: 6px;
	}
	.stage__caption {
		font-size: 13px;
		color: #222;
	}
	.stage__acts {
		margin-top: 6px;
		display: flex;
		gap: 5px;
		flex-wrap: wrap;
		justify-content: center;
	}
	.stage__acts a.btn {
		display: inline-block;
	}
	.n {
		color: var(--muted);
		font-size: 11px;
	}
	.is-active .n {
		color: #6b4f10;
	}
	.more {
		margin: 8px 0 0;
		text-align: center;
	}
	.add {
		border-top: 1px solid var(--line);
		margin-top: 12px;
		padding-top: 6px;
	}
	.add h3 {
		margin: 6px 0 2px;
	}
	.add__acts {
		display: flex;
		align-items: center;
		gap: 10px;
		flex-wrap: wrap;
		margin-top: 10px;
	}
	.check {
		display: flex;
		gap: 6px;
		align-items: flex-start;
		margin: 10px 0 0;
		font-size: 12px;
		color: #333;
	}
	.check input {
		width: auto;
		margin-top: 2px;
		flex: 0 0 auto;
	}
</style>
