<script lang="ts">
	/** The discussion under a post. The API hands back a flat list; the thread is built here
	 * from `parent`, and a deleted comment stays as a tombstone so replies keep their place. */
	import { api, ApiError } from '$lib/api';
	import { auth } from '$lib/auth.svelte';
	import { fmtDate, type Comment } from '$lib/types';
	import PostBody from './PostBody.svelte';
	import CommentBox from './CommentBox.svelte';
	import ModTools from './ModTools.svelte';

	let { slug, canModerate = false }: { slug: string; canModerate?: boolean } = $props();

	interface Node {
		c: Comment;
		kids: Node[];
	}

	let comments = $state<Comment[]>([]);
	let loading = $state(true);
	let error = $state('');
	let replyTo = $state<number | null>(null);

	// plain let: guards the fetch so the effect cannot loop
	let loadedFor = '';
	$effect(() => {
		const s = slug;
		if (!s || s === loadedFor) return;
		loadedFor = s;
		load(s);
	});

	async function load(s: string) {
		loading = true;
		error = '';
		try {
			comments = await api.get<Comment[]>(`/posts/${s}/comments/`);
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Nie udało się wczytać komentarzy.';
		} finally {
			loading = false;
		}
	}

	const tree = $derived.by<Node[]>(() => {
		const nodes = new Map<number, Node>();
		for (const c of comments) nodes.set(c.id, { c, kids: [] });
		const roots: Node[] = [];
		for (const c of comments) {
			const n = nodes.get(c.id);
			if (!n) continue;
			const p = c.parent != null ? nodes.get(c.parent) : undefined;
			if (p) p.kids.push(n);
			else roots.push(n);
		}
		return roots;
	});

	const visibleCount = $derived(comments.filter((c) => !c.is_removed).length);

	function added(c: Comment) {
		comments = [...comments, c];
		replyTo = null;
	}

	function canDelete(c: Comment): boolean {
		return !c.is_removed && (auth.isStaff || auth.user?.id === c.author_id);
	}

	async function remove(id: number) {
		if (!confirm('Usunąć ten komentarz?')) return;
		try {
			await api.delete(`/comments/${id}/`);
			comments = comments.map((c) =>
				c.id === id ? { ...c, is_removed: true, body: '', author: '', attachments: [] } : c
			);
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Nie udało się usunąć komentarza.';
		}
	}
</script>

{#snippet node(n: Node)}
	<div class="cmt" id="k{n.c.id}">
		{#if n.c.is_removed}
			<p class="gone">[komentarz usunięty]</p>
		{:else if n.c.moderation && n.c.moderation !== 'visible' && !n.c.body}
			<p class="gone">
				{n.c.moderation === 'nuked' ? '[komentarz usunięty opcją nuklearną]' : '[komentarz ukryty przez moderację]'}
				{#if canModerate}<ModTools kind="comment" id={n.c.id} status={n.c.moderation} onChanged={() => { loadedFor = ''; load(slug); }} />{/if}
			</p>
		{:else}
			<div class="cmt__head small">
				<strong>{n.c.author || 'ktoś'}</strong>
				<span class="muted">· {fmtDate(n.c.created_at)}</span>
				{#if n.c.format === 'latex'}<span class="pill">LaTeX</span>{/if}
			</div>
			<div class="cmt__body">
				<PostBody format={n.c.format} body={n.c.body} attachments={n.c.attachments} />
			</div>
			<div class="cmt__act small">
				{#if auth.isAuthenticated}
					<button type="button" class="linky" onclick={() => (replyTo = replyTo === n.c.id ? null : n.c.id)}>
						Odpowiedz
					</button>
				{:else}
					<a href="/logowanie?next=/wpis/{slug}">Odpowiedz</a>
				{/if}
				{#if canDelete(n.c)}
					· <button type="button" class="linky" onclick={() => remove(n.c.id)}>Usuń</button>
				{/if}
				{#if canModerate}
					{#if n.c.moderation && n.c.moderation !== 'visible'}<span class="pill pill--amber">{n.c.moderation === 'nuked' ? '☢ nuklearne' : 'ukryty'}</span>{/if}
					<ModTools kind="comment" id={n.c.id} status={n.c.moderation ?? 'visible'} onChanged={() => { loadedFor = ''; load(slug); }} />
				{/if}
			</div>
			{#if replyTo === n.c.id}
				<CommentBox {slug} parent={n.c.id} onPosted={added} onCancel={() => (replyTo = null)} />
			{/if}
		{/if}

		{#if n.kids.length}
			<div class="kids">
				{#each n.kids as k (k.c.id)}
					{@render node(k)}
				{/each}
			</div>
		{/if}
	</div>
{/snippet}

<div class="box" id="komentarze">
	<h2 class="box__title">
		Komentarze
		<small>{visibleCount === 1 ? '1 komentarz' : `${visibleCount} komentarzy`}</small>
	</h2>
	<div class="box__body">
		{#if loading}
			<p class="muted">Wczytuję komentarze…</p>
		{:else}
			{#if error}<div class="error">{error}</div>{/if}
			{#if tree.length === 0}
				<p class="muted">Jeszcze nikt nic nie napisał.</p>
			{:else}
				{#each tree as n (n.c.id)}
					{@render node(n)}
				{/each}
			{/if}
			<hr />
			<CommentBox {slug} onPosted={added} />
		{/if}
	</div>
</div>

<style>
	.cmt {
		margin: 0 0 10px;
	}
	.kids {
		margin-left: 24px;
		padding-left: 10px;
		border-left: 2px solid #e6e6e6;
		margin-top: 8px;
	}
	.cmt__head {
		margin-bottom: 3px;
	}
	.cmt__body :global(p:last-child) {
		margin-bottom: 4px;
	}
	.cmt__body :global(.gallery img) {
		max-height: 200px;
	}
	.cmt__act {
		color: var(--muted);
	}
	.gone {
		color: var(--muted);
		font-style: italic;
		margin: 0 0 4px;
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
</style>
