<script lang="ts">
	/** /przedmioty — the courses the archive is filed under, in the order they are usually
	 * sat in rather than alphabetically, because that is the order a physics student has them
	 * in their head. The list is the Faculty's own programme (seeded in migration 0008) plus
	 * whatever people have named while writing; a named one appears here once something
	 * published carries it, which is the same rule /ludzie uses for a named person. */
	import Breadcrumb from '$lib/components/Breadcrumb.svelte';
	import { api, ApiError } from '$lib/api';
	import type { Subject } from '$lib/types';
	import { plural } from '$lib/plural';

	let subjects = $state<Subject[]>([]);
	let loading = $state(true);
	let error = $state('');
	let q = $state('');

	let asked = false; // plain let: the list is fetched once
	$effect(() => {
		if (asked) return;
		asked = true;
		load();
	});

	async function load() {
		loading = true;
		error = '';
		try {
			subjects = await api.get<Subject[]>('/subjects/');
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Nie udało się wczytać listy przedmiotów.';
		} finally {
			loading = false;
		}
	}

	function fold(s: string): string {
		return s.toLocaleLowerCase('pl').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/ł/g, 'l');
	}
	const shown = $derived.by(() => {
		const needle = fold(q.trim());
		return needle ? subjects.filter((s) => fold(s.name + ' ' + s.short).includes(needle)) : subjects;
	});
	const withPosts = $derived(subjects.filter((s) => (s.post_count ?? 0) > 0).length);
</script>

<svelte:head>
	<title>Przedmioty — fuw.lol</title>
	<meta
		name="description"
		content="Folklor Wydziału Fizyki UW poukładany po przedmiotach: analiza, mechanika klasyczna, kwanty, pracownie."
	/>
</svelte:head>

<Breadcrumb trail={[{ label: 'Przedmioty' }]} />


<div class="box">
	<h1 class="box__title">
		Przedmioty
		<small>{subjects.length} {plural(subjects.length, 'przedmiot', 'przedmioty', 'przedmiotów')}</small>
	</h1>
	<div class="box__body">
		<p class="small muted">
			Zajęcia, na których to wszystko się działo — od „Fizyki elementarnej” do „Kwantowej teorii pola”.
			Lista pochodzi z programu studiów Wydziału; brakujący przedmiot dopisuje się przy wpisie, w polu
			<strong>Przedmioty</strong>, i pojawia się tutaj, kiedy wpis zostanie opublikowany.
			{#if !loading && !error}
				<span>Coś już mamy z {withPosts} {plural(withPosts, 'przedmiotu', 'przedmiotów', 'przedmiotów')}.</span>
			{/if}
		</p>

		<label for="pm-q">Szukaj przedmiotu</label>
		<input id="pm-q" type="text" bind:value={q} autocomplete="off" placeholder="np. kwant, pracownia, AM1" />

		{#if loading}
			<p class="muted">Wczytuję…</p>
		{:else if error}
			<div class="error">{error}</div>
		{:else if shown.length === 0}
			<p class="muted">
				{subjects.length ? 'Żaden przedmiot nie pasuje do szukanej frazy.' : 'Lista przedmiotów jest pusta.'}
			</p>
		{:else}
			<div class="grid">
				{#each shown as s (s.slug)}
					<a class="tile" href="/przedmioty/{s.slug}">
						<div class="tile__name">{s.name}</div>
						{#if s.short}<div class="small muted">{s.short}</div>{/if}
						<div class="tile__count">
							{#if s.post_count}
								{s.post_count} {plural(s.post_count, 'wpis', 'wpisy', 'wpisów')}
							{:else}
								jeszcze nic
							{/if}
						</div>
					</a>
				{/each}
			</div>
		{/if}
	</div>
</div>
