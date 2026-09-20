<script lang="ts">
	/** Editing an existing post. Two refusals are worth telling apart before the editor ever
	 * appears: a post that is not yours at all, and your own post that has already been
	 * published — the API allows the second only for moderators, so there is no point letting
	 * somebody rewrite it for ten minutes and then eat a 403. */
	import Breadcrumb from '$lib/components/Breadcrumb.svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import PostEditor from '$lib/components/editor/PostEditor.svelte';
	import { api, ApiError } from '$lib/api';
	import { auth } from '$lib/auth.svelte';
	import type { Post } from '$lib/types';

	let post = $state<Post | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let loadedSlug = '';

	$effect(() => {
		const slug = page.params.slug;
		if (!slug || !auth.ready || slug === loadedSlug) return;
		loadedSlug = slug;
		load(slug);
	});

	async function load(slug: string) {
		loading = true;
		error = null;
		post = null;
		try {
			post = await api.get<Post>(`/posts/${slug}/`);
		} catch (e) {
			error =
				e instanceof ApiError
					? e.status === 404
						? 'Nie ma takiego wpisu (albo nie jest jeszcze publiczny).'
						: e.message
					: 'Nie udało się wczytać wpisu.';
		} finally {
			loading = false;
		}
	}

	// the author may edit their own post only while it waits or after a rejection
	const lockedByStatus = $derived(!!post && post.status === 'published' && !auth.isStaff);

	function onSaved(saved: Post) {
		goto('/wpis/' + saved.slug);
	}
</script>

<svelte:head>
	<title>{post ? `Edycja: ${post.title}` : 'Edycja wpisu'} — fuw.lol</title>
	<meta name="robots" content="noindex" />
</svelte:head>

<Breadcrumb trail={[{ label: 'Przeglądaj', href: '/przegladaj' }, { label: post ? post.title : 'Wpis', href: post ? `/wpis/${post.slug}` : undefined }, { label: 'Edycja' }]} />

<div>
	<h1 class="ce_headline">Edycja wpisu</h1>

	{#if loading || !auth.ready}
		<p class="muted">Ładowanie…</p>
	{:else if error}
		<div class="error">{error}</div>
		<p><a href="/">Wróć do archiwum</a></p>
	{:else if post && !post.can_edit}
		<div class="box">
			<h2 class="box__title">Nie możesz edytować tego wpisu.</h2>
			<div class="box__body">
				<p>Zmieniać wpis może jego autor (dopóki czeka na moderację) albo moderator.</p>
				<p><a class="btn btn--ghost" href="/wpis/{post.slug}">Zobacz wpis</a></p>
			</div>
		</div>
	{:else if post && lockedByStatus}
		<div class="box">
			<h2 class="box__title">Wpis jest już opublikowany</h2>
			<div class="box__body">
				<p>Opublikowany wpis może zmienić tylko moderator — napisz w komentarzu, co poprawić, a ktoś to zrobi.</p>
				<p><a class="btn btn--ghost" href="/wpis/{post.slug}">Zobacz wpis</a></p>
			</div>
		</div>
	{:else if post}
		{#if post.status === 'rejected'}
			<div class="warn">
				Ten wpis został odrzucony{post.review_note ? ':' : '.'}
				{#if post.review_note}<em>{post.review_note}</em>{/if}
				Po zapisaniu zmian wróci do kolejki moderacji.
			</div>
		{:else if post.status === 'pending'}
			<p class="lead muted">Wpis czeka na moderację — zmiany zobaczy moderator przed publikacją.</p>
		{/if}
		<PostEditor initial={post} {onSaved} />
	{/if}
</div>

<style>
	.lead { margin: 0 0 14px; }
	.warn { border: 1px solid #c98f1e; background: #fffbe8; padding: 6px 9px; margin: 8px 0 14px; font-size: 12px; }
</style>
