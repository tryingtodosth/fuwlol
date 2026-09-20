<script lang="ts">
	/** /przedmioty/<slug> — one course and everything filed under it. The same shape as
	 * /ludzie/<slug>: a header with the count and a link into the browse page with its
	 * filters, then the posts as ordinary cards.
	 *
	 * Unlike a person's page this one does not narrow: `SubjectViewSet.retrieve` resolves any
	 * subject that exists, including one somebody named an hour ago on a post still in the
	 * queue. There is no privacy interest in a course name, and a link that 404s is worse
	 * than a page that says „jeszcze nic”. */
	import Breadcrumb from '$lib/components/Breadcrumb.svelte';
	import { page } from '$app/state';
	import { api, ApiError, qs } from '$lib/api';
	import type { Page as ApiPage, PostSummary, Subject } from '$lib/types';
	import PostCard from '$lib/components/PostCard.svelte';
	import { plural } from '$lib/plural';

	const slug = $derived(page.params.slug ?? '');

	let subject = $state<Subject | null>(null);
	let posts = $state<PostSummary[]>([]);
	let count = $state(0);
	let loading = $state(true);
	let error = $state('');
	let notFound = $state(false);

	let loadedFor = ''; // plain let: guards the fetch so the effect cannot loop
	$effect(() => {
		const s = slug;
		if (!s || s === loadedFor) return;
		loadedFor = s;
		load(s);
	});

	async function load(s: string) {
		loading = true;
		error = '';
		notFound = false;
		try {
			subject = await api.get<Subject>(`/subjects/${s}/`);
			const res = await api.get<ApiPage<PostSummary>>(`/posts/${qs({ subject: s, sort: 'new' })}`);
			posts = res.results;
			count = res.count;
		} catch (e) {
			if (e instanceof ApiError && e.status === 404) notFound = true;
			else error = e instanceof ApiError ? e.message : 'Nie udało się wczytać.';
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>{subject ? `${subject.name} — fuw.lol` : 'fuw.lol'}</title>
	{#if subject}
		<meta
			name="description"
			content="{subject.name}: {count} {plural(count, 'wpis', 'wpisy', 'wpisów')} w archiwum folkloru Wydziału Fizyki UW."
		/>
	{/if}
</svelte:head>

<Breadcrumb trail={[{ label: 'Przedmioty', href: '/przedmioty' }, { label: subject ? subject.name : notFound ? 'Nie ma takiego przedmiotu' : '…' }]} />


{#if loading}
	<div class="box"><div class="box__body"><p class="muted">Wczytuję…</p></div></div>
{:else if notFound}
	<div class="box">
		<h1 class="box__title">Nie ma takiego przedmiotu</h1>
		<div class="box__body">
			<p>Nikt jeszcze nie wpisał takich zajęć — a jeśli je prowadzono, to najwyraźniej bez świadków.</p>
			<p><a href="/przedmioty">Wróć do listy przedmiotów</a></p>
		</div>
	</div>
{:else if error}
	<div class="box"><div class="box__body"><div class="error">{error}</div></div></div>
{:else if subject}
	<div class="box">
		<h1 class="box__title">
			{subject.name}
			{#if subject.short}<small>{subject.short}</small>{/if}
		</h1>
		<div class="box__body">
			<p class="small muted">
				{count}
				{plural(count, 'wpis', 'wpisy', 'wpisów')} w archiwum ·
				<a href="/przegladaj?subject={subject.slug}">Przeglądaj z filtrami</a> ·
				<a href="/przedmioty">wszystkie przedmioty</a>
			</p>
		</div>
	</div>

	<div class="box">
		<h2 class="box__title">Wpisy</h2>
		{#if posts.length}
			{#each posts as p (p.slug)}
				<PostCard post={p} />
			{/each}
			{#if count > posts.length}
				<div class="box__body">
					<p><a href="/przegladaj?subject={subject.slug}">Zobacz wszystkie {count} →</a></p>
				</div>
			{/if}
		{:else}
			<div class="box__body">
				<p class="muted">
					Jeszcze nic. Te zajęcia na pewno miały swoje momenty — <a href="/dodaj">dodaj wpis</a>.
				</p>
			</div>
		{/if}
	</div>
{/if}
