<script module lang="ts">
	import { api } from '$lib/api';
	import type { Category } from '$lib/types';

	/** One shared category lookup for every card on the page — a summary carries the slug
	 * but not the emoji, and the meta line wants it. */
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
	/** One news item, shaped like the faculty's `.layout_short`: a ✱ headline in rust, the
	 * picture floated left at 170px with the text wrapping round it, „| Więcej” at the end of
	 * the paragraph — and, ours alone, a grey meta line underneath. A post without a picture
	 * simply has no picture; the faculty puts no placeholder there and neither do we. */
	import MathText from './MathText.svelte';
	import { LOCK_PILL, yearLabel, type PostSummary } from '$lib/types';

	let { post }: { post: PostSummary } = $props();

	let emoji = $state('');
	$effect(() => {
		const slug = post.category;
		categoryEmojis().then((m) => (emoji = m.get(slug) || ''));
	});

	const reactions = $derived(Object.values(post.reaction_counts ?? {}).reduce((a, b) => a + b, 0));
</script>

<div class="item">
	<h3 class="item__title"><a href="/wpis/{post.slug}">{post.title}</a></h3>
	{#if post.cover}
		<div class="item__thumb">
			<a href="/wpis/{post.slug}" tabindex="-1" aria-hidden="true"><img src={post.cover} alt="" loading="lazy" /></a>
		</div>
	{/if}
	<div class="item__text">
		<p>
			{#if post.locked}<em class="muted">Treść tylko dla zweryfikowanych — tytuł zostaje, reszta czeka na potwierdzony adres.</em>
			{:else if post.summary}<MathText text={post.summary} />{:else}Bez opisu — zajrzyj do środka.{/if}
			| <a class="more" href="/wpis/{post.slug}">Więcej</a>
		</p>
	</div>
	<div class="item__meta">
		{#if post.catalog_no}<span class="stamp">{post.catalog_no}</span>&nbsp;{/if}
		<a href="/przegladaj?category={post.category}">{emoji ? `${emoji} ` : ''}{post.category_name}</a>
		· {yearLabel(post)}
		{#if post.people.length}
			·
			{#each post.people as p, i (p.slug)}<a href="/ludzie/{p.slug}">{p.name}</a>{#if i < post.people.length - 1}{', '}{/if}{/each}
		{/if}
		{#if post.subjects?.length}
			·
			<!-- `{', '}` rather than a comma typed into the markup: Svelte trims the
			     whitespace that follows one, and „Mech.,MK” is not a list. -->
			{#each post.subjects as s, i (s.slug)}<a href="/przedmioty/{s.slug}" title={s.name}
				>{s.short || s.name}</a
				>{#if i < post.subjects.length - 1}{', '}{/if}{/each}
		{/if}
		{#if reactions}· {reactions} reakcji{/if}
		{#if post.comment_count}· {post.comment_count} kom.{/if}
		{#if post.featured}· <span class="pill pill--amber">Wyróżnione</span>{/if}
		<!-- `trusted_only`, not `locked`: a trusted reader must see that the post is restricted,
		     and for them `locked` is false. -->
		{#if post.trusted_only}· <span class="pill pill--rust">{LOCK_PILL}</span>{/if}
	</div>
</div>
