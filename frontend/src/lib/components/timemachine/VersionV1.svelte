<!-- Version 1 of fuw.lol's home page: the ✱ list in the style of www.fuw.edu.pl.
     Registered in versions.ts. When the site is redesigned this component is NOT
     edited — a new one is added alongside it, so a date from before the redesign
     keeps rendering the look the site actually had that day. -->
<script lang="ts">
	import MathText from '$lib/components/MathText.svelte';
	import { api, qs } from '$lib/api';
	import type { Page, PostSummary } from '$lib/types';
	import { yearLabel } from '$lib/types';
	import { toISODate, type TravelDate } from './eras';

	let { date }: { date: TravelDate } = $props();

	let posts = $state<PostSummary[]>([]);
	let total = $state(0);
	let loading = $state(true);
	let error = $state('');
	let seq = 0;

	const iso = $derived(toISODate(date));
	const dayLabel = $derived(iso.split('-').reverse().join('.'));

	$effect(() => {
		const on = iso;
		const mine = ++seq;
		loading = true;
		error = '';
		api
			.get<Page<PostSummary>>('/posts/' + qs({ before: on }))
			.then((p) => {
				if (mine !== seq) return;
				posts = p.results;
				total = p.count;
			})
			.catch((e: unknown) => {
				if (mine !== seq) return;
				error = e instanceof Error ? e.message : 'Nie udało się wczytać archiwum.';
			})
			.finally(() => {
				if (mine === seq) loading = false;
			});
	});
</script>

<p class="asof">Archiwum tak, jak wyglądało {dayLabel}</p>

<div class="box">
	<h2 class="box__title">
		Aktualności
		{#if !loading && !error}<small>{total} {total === 1 ? 'wpis' : 'wpisów'} na ten dzień</small>{/if}
	</h2>
	{#if loading}
		<div class="box__body muted">Wczytywanie…</div>
	{:else if error}
		<div class="box__body"><p class="error">{error}</p></div>
	{:else if posts.length === 0}
		<div class="box__body muted">
			Tego dnia archiwum było jeszcze puste. Nic się nie zepsuło — po prostu nikt nic nie
			przysłał.
		</div>
	{:else}
		{#each posts as post (post.id)}
			<div class="item">
				<h3 class="item__title"><a href="/wpis/{post.slug}">{post.title}</a></h3>
				{#if post.summary}<div class="item__text"><MathText text={post.summary} /></div>{/if}
				<div class="item__meta">{yearLabel(post)} · {post.category_name}</div>
			</div>
		{/each}
	{/if}
</div>

<style>
	.asof {
		border-bottom: 1px solid var(--line);
		padding-bottom: 6px;
		margin-bottom: 14px;
		font-weight: bold;
		color: #222;
	}
	.item__text {
		text-align: justify;
	}
</style>
