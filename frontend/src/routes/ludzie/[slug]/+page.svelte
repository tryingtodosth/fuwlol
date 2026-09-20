<script lang="ts">
	/** /ludzie/<slug> — one person, laid out like the faculty's own profile
	 * (m.fuw.edu.pl/osoby-fuw.html?show=…): the `single_record` table with a 130 px photo on the
	 * left and, on the right, the bold name with its title, the function in italics, the unit,
	 * then label/value rows. Where the faculty has a room, a phone and USOS, we have nicknames,
	 * posts, the years the archive covers (history), and — because a lecturer is not a publicly
	 * known person — what the person themself said about their image (law).
	 *
	 * The photo is the winner of the portrait vote when there is one (the portraits app; the
	 * gallery component below reports it through `onCurrent`), else the faculty's own silhouette
	 * for the person's `sex`, else the grey "Miejsce na foto" box the faculty shows when it has
	 * nothing either. */
	import Breadcrumb from '$lib/components/Breadcrumb.svelte';
	import { page } from '$app/state';
	import { api, ApiError, qs } from '$lib/api';
	import type { Page as ApiPage, Person, PostSummary } from '$lib/types';
	import PostCard from '$lib/components/PostCard.svelte';
	import ConsentBadge from '$lib/components/ConsentBadge.svelte';
	import PersonPortraits from '$lib/components/PersonPortraits.svelte';
	import PersonClaimBox from '$lib/components/PersonClaimBox.svelte';
	import { plural } from '$lib/plural';

	const slug = $derived(page.params.slug ?? '');

	let person = $state<Person | null>(null);
	let posts = $state<PostSummary[]>([]);
	let count = $state(0);
	let portraitUrl = $state<string | null>(null);
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
		portraitUrl = null;
		try {
			person = await api.get<Person>(`/people/${s}/`);
			const res = await api.get<ApiPage<PostSummary>>(`/posts/${qs({ person: s, sort: 'new' })}`);
			posts = res.results;
			count = res.count;
		} catch (e) {
			if (e instanceof ApiError && e.status === 404) notFound = true;
			else error = e instanceof ApiError ? e.message : 'Nie udało się wczytać.';
		} finally {
			loading = false;
		}
	}

	const placeholder = $derived(
		person?.sex === 'm' ? '/img/anonymousmabw.png' : person?.sex === 'f' ? '/img/anonymousfebw.png' : null
	);
	const years = $derived.by(() => {
		if (!person) return '';
		const a = person.year_min ?? null;
		const b = person.year_max ?? null;
		if (a == null && b == null) return 'rok nieznany';
		if (a === b || b == null) return String(a);
		if (a == null) return String(b);
		return `${a}–${b}`;
	});
	const consentLine = $derived.by(() => {
		switch (person?.image_consent) {
			case 'granted': return 'zgoda potwierdzona przez osobę';
			case 'refused': return 'bez zdjęć — na prośbę osoby';
			default: return 'brak deklaracji osoby — obowiązuje oświadczenie autora wpisu';
		}
	});
</script>

<svelte:head>
	<title>{person ? `${person.full_name} — fuw.lol` : 'fuw.lol'}</title>
	{#if person}<meta name="description" content="{person.full_name}{person.role ? ' — ' + person.role : ''}: {count} {plural(count, 'wpis', 'wpisy', 'wpisów')} w archiwum folkloru Wydziału Fizyki UW." />{/if}
</svelte:head>

<div class="osoby">
	<Breadcrumb trail={[{ label: 'Osoby', href: '/ludzie' }, { label: person ? person.full_name : notFound ? 'Nie ma takiej osoby' : '…' }]} />
	<h1 class="ce_headline">Osoby</h1>

	{#if loading}
		<p class="muted">Wczytuję…</p>
	{:else if notFound}
		<div class="ce_text">
			<p>Nie ma takiej osoby w spisie — albo nigdy nie było, albo poprosiła, żeby jej nie było. Obie odpowiedzi wyglądają tak samo, i tak ma być.</p>
			<p><a href="/ludzie">Wróć do spisu</a></p>
		</div>
	{:else if error}
		<div class="error">{error}</div>
	{:else if person}
		<div class="mod_employers">
			<table class="single_record">
				<tbody>
					<tr>
						<td class="img">
							{#if portraitUrl}
								<img src={portraitUrl} alt={person.full_name} title="Zdjęcie profilowe — wybrane głosowaniem" />
							{:else if placeholder}
								<img src={placeholder} alt="" title="Miejsce na foto" />
							{:else}
								<div class="nophoto" title="Miejsce na foto">Miejsce<br />na foto</div>
							{/if}
						</td>
						<td class="value">
							<table class="single_record">
								<tbody>
									<tr>
										<td class="name" colspan="2">
											{person.full_name}
											{#if person.image_consent === 'granted' || person.image_consent === 'refused'}
												<ConsentBadge consent={person.image_consent} />
											{/if}
										</td>
									</tr>
									<tr><td class="header" colspan="2"><em>{person.role}</em></td></tr>
									{#if person.unit}
										<tr><td class="header" colspan="2">{person.unit}</td></tr>
									{/if}
									<tr>
										<td class="label">Ksywki</td>
										<td class="value">
											{#if person.aliases.length}
												{#each person.aliases as a, i (a.slug)}<a href="/przegladaj?tag={a.slug}" title="wszystkie wpisy z tagiem „{a.name}”">{a.name}</a>{#if i < person.aliases.length - 1}{', '}{/if}{/each}
											{:else}-{/if}
										</td>
									</tr>
									<tr>
										<td class="label">Wpisy</td>
										<td class="value">
											{#if count}<a href="/przegladaj?person={person.slug}">{count} {plural(count, 'wpis', 'wpisy', 'wpisów')}</a>{:else}-{/if}
										</td>
									</tr>
									<tr>
										<td class="label">W archiwum</td>
										<td class="value" title="lata, których dotyczą wpisy o tej osobie">{years}</td>
									</tr>
									<tr>
										<td class="label">Wizerunek</td>
										<td class="value">{consentLine} · <a href="/ludzie/zgoda">co to znaczy</a></td>
									</tr>
									<tr class="USOSdetails">
										<td class="label">Rozkład zajęć</td>
										<td class="value"><a href="/przegladaj?person={person.slug}&sort=old" title="wpisy o tej osobie od najstarszego roku">chronologicznie</a></td>
									</tr>
								</tbody>
							</table>
						</td>
					</tr>
				</tbody>
			</table>
			{#if person.bio}
				<div class="ce_text"><p>{person.bio}</p></div>
			{/if}
		</div>
	{/if}
</div>

{#if person}
	<!-- the vote decides the photo above; the component reports the winner through onCurrent -->
	<PersonPortraits slug={person.slug} onCurrent={(url) => (portraitUrl = url)} />
	<div class="box">
		<h2 class="box__title">Wpisy <small>{count} {plural(count, 'wpis', 'wpisy', 'wpisów')}</small></h2>
		{#if posts.length}
			{#each posts as p (p.slug)}
				<PostCard post={p} />
			{/each}
			{#if count > posts.length}
				<div class="box__body">
					<p><a href="/przegladaj?person={person.slug}">Zobacz wszystkie {count} →</a></p>
				</div>
			{/if}
		{:else}
			<div class="box__body"><p class="muted">Jeszcze nic. Historia nie zapisała się sama — <a href="/dodaj">dodaj wpis</a>.</p></div>
		{/if}
	</div>
	<!-- "Jesteś tą osobą?" — the person's own say over their image (consent app); last on the page,
	     after the posts, because the reader comes for the folklore and the person comes for this -->
	<PersonClaimBox slug={person.slug} personName={person.full_name} consent={person.image_consent} />
{/if}
