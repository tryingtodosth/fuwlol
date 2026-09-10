<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api';
	import { auth } from '$lib/auth.svelte';
	import type { ModerationBlock, Post, Comment } from '$lib/types';
	import { fmtDate } from '$lib/types';
	import ModTools from '$lib/components/ModTools.svelte';
	import PostBody from '$lib/components/PostBody.svelte';

	// A nuked row for a non-staff reader is a STUB: no title/body. `title?: undefined` /
	// `body?: undefined` make the stub distinguishable from the full row for TypeScript.
	type PostStub = { id: number; catalog_no: string; status: 'nuked'; moderation: ModerationBlock; title?: undefined };
	type FullPost = Post & { moderation: ModerationBlock };
	type BoardPost = FullPost | PostStub;
	type CommentStub = { id: number; post_id: number; moderation: ModerationBlock; body?: undefined };
	type FullComment = Comment & { post_id: number; post_slug?: string; post_title?: string; moderation: ModerationBlock };
	type BoardComment = FullComment | CommentStub;
	interface Board { count: number; page: number; pages: number; posts: BoardPost[]; comments: BoardComment[] }

	let board = $state<Board | null>(null);
	let error = $state<string | null>(null);
	let status = $state<'' | 'hidden' | 'nuked'>('');
	let kind = $state<'' | 'posts' | 'comments'>('');
	let pageNo = $state(1);
	let open = $state<Set<number>>(new Set());
	let loadedFor = '';

	const allowed = $derived(auth.isStaff || !!auth.user?.is_trusted);
	const isStub = (p: BoardPost): p is PostStub => typeof p.title !== 'string';
	const isCStub = (c: BoardComment): c is CommentStub => typeof c.body !== 'string';

	async function load() {
		error = null;
		const u = new URLSearchParams();
		if (status) u.set('status', status);
		if (kind) u.set('kind', kind);
		u.set('page', String(pageNo));
		try { board = await api.get<Board>(`/moderation/board/?${u}`); }
		catch (e) { error = e instanceof ApiError ? e.message : String(e); }
	}
	$effect(() => {
		if (!auth.ready || !allowed) return;
		const key = `${status}|${kind}|${pageNo}`;
		if (key === loadedFor) return;
		loadedFor = key;
		load();
	});
	onMount(() => { document.title = 'Tablica moderacji — fuw.lol'; });
	function toggle(id: number) { const s = new Set(open); s.has(id) ? s.delete(id) : s.add(id); open = s; }
	const when = (b: ModerationBlock) => (b.at ? fmtDate(b.at) : '');
	function reload() { loadedFor = ''; load(); }
</script>

<h1>Tablica moderacji</h1>
{#if !auth.ready}
	<p class="muted">Ładuję…</p>
{:else if !allowed}
	<div class="box"><div class="box__body">
		<p>Tablica jest dla zaufanych użytkowników (zweryfikowana afiliacja) i administracji.</p>
		<p><a href="/konto">Zweryfikuj adres instytucjonalny</a> albo <a href="/logowanie?next=/tablica">zaloguj się</a>.</p>
	</div></div>
{:else}
	<div class="box box--grey">
		<div class="box__body">
			<p class="small">Tu leży wszystko, co zniknęło ze strony publicznej. Treści <strong>ukryte</strong> widzi każdy zaufany i może je
				przywrócić. Treści po <strong>opcji nuklearnej</strong> (nielegalne, obrzydliwie obraźliwe) widzi tylko administracja — reszta
				widzi jedynie, że coś takiego było, kto to zrobił i dlaczego.</p>
			<div class="row">
				<label>Status
					<select bind:value={status} onchange={() => (pageNo = 1)}>
						<option value="">wszystko</option><option value="hidden">ukryte</option><option value="nuked">nuklearne</option>
					</select>
				</label>
				<label>Rodzaj
					<select bind:value={kind} onchange={() => (pageNo = 1)}>
						<option value="">wpisy i komentarze</option><option value="posts">wpisy</option><option value="comments">komentarze</option>
					</select>
				</label>
			</div>
		</div>
	</div>
	{#if error}<div class="error">{error}</div>{/if}
	{#if board}
		<div class="box">
			<h2 class="box__title">Wpisy <small>{board.count} pozycji na tablicy, strona {board.page} z {board.pages}</small></h2>
			{#if board.posts.length === 0}<div class="box__body muted">Brak wpisów na tej stronie.</div>{/if}
			{#each board.posts as p (p.id)}
				<div class="item">
					{#if isStub(p)}
						<h3 class="item__title">☢ {p.catalog_no} <span class="pill pill--grey">opcja nuklearna</span></h3>
						<p class="small muted">Treść widoczna tylko dla administracji. Ukrył/a: <strong>{p.moderation.actor}</strong> {when(p.moderation)} — powód: {p.moderation.reason || '—'}</p>
						<ModTools kind="post" id={p.id} status="nuked" onChanged={reload} />
					{:else}
						<h3 class="item__title">
							<a href="/wpis/{p.slug}">{p.title}</a>
							<span class="pill" class:pill--amber={p.status === 'hidden'} class:pill--grey={p.status === 'nuked'}>{p.status === 'nuked' ? '☢ nuklearne' : 'ukryte'}</span>
						</h3>
						<p class="small muted">{p.catalog_no} · {p.category_name} · dodał/a {p.submitted_by || '—'} · akcja: <strong>{p.moderation.actor}</strong> {when(p.moderation)} — powód: {p.moderation.reason || '—'}</p>
						{#if p.summary}<p>{p.summary}</p>{/if}
						<button type="button" class="btn btn--sm btn--ghost" onclick={() => toggle(p.id)}>{open.has(p.id) ? 'Zwiń treść' : 'Pokaż treść'}</button>
						<ModTools kind="post" id={p.slug} status={p.status === 'nuked' ? 'nuked' : 'hidden'} onChanged={reload} />
						{#if open.has(p.id)}
							<div class="preview"><PostBody format={p.format} body={p.body} attachments={p.attachments} /></div>
						{/if}
					{/if}
				</div>
			{/each}
		</div>
		<div class="box">
			<h2 class="box__title">Komentarze</h2>
			{#if board.comments.length === 0}<div class="box__body muted">Brak komentarzy na tej stronie.</div>{/if}
			{#each board.comments as c (c.id)}
				<div class="item">
					{#if isCStub(c)}
						<p>☢ komentarz #{c.id} <span class="pill pill--grey">opcja nuklearna</span> <span class="small muted">— treść tylko dla administracji. {c.moderation.actor} {when(c.moderation)}: {c.moderation.reason || '—'}</span></p>
						<ModTools kind="comment" id={c.id} status="nuked" onChanged={reload} />
					{:else}
						<p class="small muted">
							{#if c.post_slug}pod <a href="/wpis/{c.post_slug}">{c.post_title}</a>{:else}pod wpisem #{c.post_id}{/if}
							· autor {c.author || '—'} · akcja: <strong>{c.moderation.actor}</strong> {when(c.moderation)} — powód: {c.moderation.reason || '—'}
						</p>
						<div class="preview"><PostBody format={c.format} body={c.body} attachments={c.attachments} /></div>
						<ModTools kind="comment" id={c.id} status={c.moderation.action === 'nuke' ? 'nuked' : 'hidden'} onChanged={reload} />
					{/if}
				</div>
			{/each}
		</div>
		{#if board.pages > 1}
			<p class="center">
				<button type="button" class="btn btn--ghost btn--sm" disabled={pageNo <= 1} onclick={() => pageNo--}>‹ Poprzednia</button>
				strona {board.page} z {board.pages}
				<button type="button" class="btn btn--ghost btn--sm" disabled={pageNo >= board.pages} onclick={() => pageNo++}>Następna ›</button>
			</p>
		{/if}
	{/if}
{/if}

<style>
	.preview { border: 1px dashed var(--line); padding: 8px; margin: 8px 0; background: #fff; }
	.row label { flex: 0 1 220px; }
</style>
