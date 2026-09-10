<script lang="ts">
	import { api, ApiError } from '$lib/api';
	import { auth } from '$lib/auth.svelte';
	import { REACTIONS, type Post, type ReactionKind } from '$lib/types';

	let { post }: { post: Post } = $props();

	type Counts = Record<ReactionKind, number>;
	interface ReactResponse {
		reaction_counts: Counts;
		my_reaction: ReactionKind | null;
	}

	// The post prop is the truth; a click leaves an override until the page hands us
	// a different post (this component is reused as you walk from exhibit to exhibit).
	let override = $state<{ slug: string; counts: Counts; mine: ReactionKind | null } | null>(null);
	let busy = $state(false);
	let error = $state('');

	const live = $derived(override && override.slug === post.slug ? override : null);
	const counts = $derived<Counts>(live ? live.counts : post.reaction_counts);
	const mine = $derived<ReactionKind | null>(live ? live.mine : post.my_reaction);

	async function react(kind: ReactionKind) {
		if (busy) return;
		busy = true;
		error = '';
		try {
			const r =
				mine === kind
					? await api.delete<ReactResponse>(`/posts/${post.slug}/react/`)
					: await api.post<ReactResponse>(`/posts/${post.slug}/react/`, { kind });
			override = { slug: post.slug, counts: r.reaction_counts, mine: r.my_reaction };
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Nie udało się zapisać reakcji.';
		} finally {
			busy = false;
		}
	}
</script>

<div class="reactions">
	{#each REACTIONS as r (r.kind)}
		{#if auth.isAuthenticated}
			<button
				type="button"
				class="btn btn--ghost btn--sm"
				class:is-active={mine === r.kind}
				disabled={busy}
				aria-pressed={mine === r.kind}
				onclick={() => react(r.kind)}
			>
				<span aria-hidden="true">{r.emoji}</span>
				{r.label}
				<span class="n">{counts[r.kind] ?? 0}</span>
			</button>
		{:else}
			<a
				class="btn btn--ghost btn--sm"
				href="/logowanie?next=/wpis/{post.slug}"
				title="Zaloguj się, żeby zareagować"
			>
				<span aria-hidden="true">{r.emoji}</span>
				{r.label}
				<span class="n">{counts[r.kind] ?? 0}</span>
			</a>
		{/if}
	{/each}
</div>
{#if error}<div class="error">{error}</div>{/if}

<style>
	.reactions {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
		margin: 10px 0 4px;
	}
	.reactions a.btn {
		display: inline-block;
	}
	.n {
		color: var(--muted);
		font-size: 11px;
	}
	.is-active .n {
		color: #6b4f10;
	}
</style>
