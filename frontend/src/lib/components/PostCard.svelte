<script module lang="ts">
	import { api } from '$lib/api';
	import type { Category } from '$lib/types';

	/** One shared category lookup for every card on the page — a summary carries the slug
	 * but not the emoji, and the placeholder thumbnail wants it. */
	let emojiCache: Promise<Map<string, string>> | null = null;
	function categoryEmojis(): Promise<Map<string, string>> {
		emojiCache ??= api
			.get<Category[]>('/categories/')
			.then((cs) => new Map(cs.map((c) => [c.slug, c.emoji])))
			.catch(() => new Map<string, string>());
		return emojiCache;
	}
</script>

<script lang="ts">
	import { yearLabel, type PostSummary } from '$lib/types';

	let { post }: { post: PostSummary } = $props();

	let emoji = $state('✱');
	$effect(() => {
		const slug = post.category;
		categoryEmojis().then((m) => (emoji = m.get(slug) || '✱'));
	});

	const reactions = $derived(Object.values(post.reaction_counts ?? {}).reduce((a, b) => a + b, 0));
</script>

<div class="item">
	<h3 class="item__title"><a href="/wpis/{post.slug}">{post.title}</a></h3>
	<div class="item__row">
		<div class="item__thumb">
			{#if post.cover}
				<img src={post.cover} alt="" loading="lazy" />
			{:else}
				<div class="ph" aria-hidden="true">{emoji}</div>
			{/if}
		</div>
		<div class="item__text">
			<p>
				{post.summary || 'Bez opisu — zajrzyj do środka.'}
				<a class="more" href="/wpis/{post.slug}">| Więcej</a>
			</p>
			<div class="item__meta">
				{#if post.catalog_no}<span class="stamp">{post.catalog_no}</span>&nbsp;{/if}
				<a href="/przegladaj?category={post.category}">{post.category_name}</a>
				· {yearLabel(post)}
				{#if post.people.length}
					·
					{#each post.people as p, i (p.slug)}<a href="/ludzie/{p.slug}">{p.name}</a>{#if i < post.people.length - 1},
						{/if}{/each}
				{/if}
				{#if reactions}· {reactions} reakcji{/if}
				{#if post.comment_count}· {post.comment_count} kom.{/if}
				{#if post.featured}· <span class="pill pill--amber">Wyróżnione</span>{/if}
			</div>
		</div>
	</div>
</div>

<style>
	.ph {
		width: 170px;
		height: 110px;
		border: 1px solid var(--line);
		background: var(--box);
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 34px;
		color: #999;
	}
	.item__text p {
		margin: 0;
	}
	@media (max-width: 640px) {
		.ph {
			width: 100%;
			height: 90px;
		}
	}
</style>
