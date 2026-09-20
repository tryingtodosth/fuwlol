<script lang="ts">
	/** /ludzie — the people directory, a copy of fuw.edu.pl/osoby-fuw.html on purpose: the same
	 * breadcrumb, the same orange-barred "Osoby", the same alphabet strip, the same search form,
	 * the same `table.employers` with a title column, a name column and rows that alternate
	 * odd/even straight through the letter rows. Where the faculty prints a room, a phone and
	 * an e-mail icon, we print the person's nicknames — which are alternative tags
	 * (archive/people.py) — and how many posts the archive holds about them.
	 *
	 * Filing is the backend's: the list arrives ordered by the folded surname and each row
	 * carries its `letter` (with its diacritic — Ż is its own letter here, as in the faculty's
	 * strip). This page only groups what it is given and filters it as you type. */
	import Breadcrumb from '$lib/components/Breadcrumb.svelte';
	import { api, ApiError } from '$lib/api';
	import type { Person } from '$lib/types';
	import ConsentBadge from '$lib/components/ConsentBadge.svelte';
	import { plural } from '$lib/plural';

	// the faculty's alphabet strip, in its order (mirrors LETTERS in archive/people.py)
	const STRIP = 'ABCĆDEFGHIJKLŁMNOPRSŚTUVWYZŻ'.split('');
	type Field = 'surname' | 'name' | 'alias';

	let people = $state<Person[]>([]);
	let loading = $state(true);
	let error = $state('');
	let field = $state<Field>('surname');
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
			people = await api.get<Person[]>('/people/');
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Nie udało się wczytać spisu.';
		} finally {
			loading = false;
		}
	}

	// no case, no diacritics, ł → l: what somebody types on a phone keyboard
	function fold(s: string): string {
		return s.toLocaleLowerCase('pl').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/ł/g, 'l');
	}
	function matches(p: Person, needle: string, f: Field): boolean {
		if (f === 'surname') return fold(p.surname || p.name).includes(needle);
		if (f === 'name') return fold(p.name).includes(needle);
		return p.aliases.some((a) => fold(a.name).includes(needle));
	}

	const collator = new Intl.Collator('pl');
	const shown = $derived.by(() => {
		const needle = fold(q.trim());
		return needle ? people.filter((p) => matches(p, needle, field)) : people;
	});
	type Group = { letter: string; people: Person[] };
	const groups = $derived.by<Group[]>(() => {
		const by = new Map<string, Person[]>();
		for (const p of shown) {
			const L = p.letter || '?';
			if (!by.has(L)) by.set(L, []);
			by.get(L)!.push(p);
		}
		const known = STRIP.filter((L) => by.has(L)).map((L) => ({ letter: L, people: by.get(L)! }));
		const rest = [...by.keys()].filter((L) => !STRIP.includes(L)).sort(collator.compare).map((L) => ({ letter: L, people: by.get(L)! }));
		return [...known, ...rest];
	});
	const present = $derived(new Set(groups.map((g) => g.letter)));
	// odd/even alternates continuously, letter rows included — exactly like the original
	type Row = { key: string; cls: 'odd' | 'even'; letter?: string; person?: Person };
	const rows = $derived.by<Row[]>(() => {
		const out: Row[] = [];
		let i = 0;
		for (const g of groups) {
			out.push({ key: 'L:' + g.letter, cls: i++ % 2 ? 'even' : 'odd', letter: g.letter });
			for (const p of g.people) out.push({ key: p.slug, cls: i++ % 2 ? 'even' : 'odd', person: p });
		}
		return out;
	});
</script>

<svelte:head>
	<title>Ludzie — fuw.lol</title>
	<meta name="description" content="Spis osób z folkloru Wydziału Fizyki UW: wykładowcy, legendarni studenci, portiernia — z ksywkami i wpisami." />
</svelte:head>

<div class="osoby">
	<Breadcrumb trail={[{ label: 'Osoby', href: '/ludzie' }, { label: 'Wszyscy' }]} />
	<h1 class="ce_headline">Osoby</h1>
	<div class="ce_text">
		<p>
			Oznaczenia literowe przed nazwiskami wskazują stopnie i tytuły, jakie dana postać zdążyła zebrać —
			w folklorze nadawane bywają szybciej niż przez Radę Wydziału i nie podlegają habilitacji. <strong>Ksywki</strong> to
			alternatywne tagi: wpis otagowany ksywką trafia na stronę osoby, nawet jeśli autor nie wybrał jej z listy. Kliknięcie
			ksywki otwiera wszystkie wpisy pod tym tagiem, kliknięcie liczby — wszystkie wpisy osoby.
		</p>
		<p>
			Postacie w archiwum to folklor, ale wizerunek jest prawem (art. 81 pr. aut.): <ConsentBadge consent="granted" compact />
			przy nazwisku oznacza, że osoba sama potwierdziła zgodę na zdjęcia. Jesteś jedną z tych osób? Na swojej stronie możesz to
			potwierdzić — albo poprosić, żeby zdjęć nie było. <a href="/ludzie/zgoda">Jak to działa</a>.
			{#if !loading && !error}<span class="muted">W spisie: {people.length} {plural(people.length, 'osoba', 'osoby', 'osób')}.</span>{/if}
		</p>
	</div>

	<div class="mod_employers">
		<p class="letters">
			{#each STRIP as L (L)}
				{#if present.has(L)}[<a href="#litera-{L}">{L}</a>]{:else}<span>[{L}]</span>{/if}{' '}
			{/each}
		</p>
		<div class="list_search">
			<form onsubmit={(e) => e.preventDefault()}>
				<div class="formbody">
					<label class="visually-hidden" for="os-field">Szukaj według</label>
					<select id="os-field" class="select" bind:value={field}>
						<option value="surname">Nazwisko</option>
						<option value="name">Imię</option>
						<option value="alias">Ksywka</option>
					</select>
					<label class="visually-hidden" for="os-q">Szukana fraza</label>
					<input id="os-q" class="text" type="text" bind:value={q} autocomplete="off" />
					<input class="submit" type="submit" value="Szukaj" />
				</div>
			</form>
		</div>

		{#if loading}
			<p class="muted">Wczytuję…</p>
		{:else if error}
			<div class="error">{error}</div>
		{:else if people.length === 0}
			<p class="muted">Nikogo tu jeszcze nie ma. Pierwsza osoba pojawi się z pierwszym wpisem, który ją wymieni.</p>
		{:else}
			<table class="employers">
				<tbody>
					<tr class="head">
						<td class="deg"></td>
						<td class="nm"><strong>Imię i nazwisko</strong></td>
						<td><strong>Ksywki</strong></td>
						<td class="cnt"><strong>Wpisy</strong></td>
					</tr>
					{#each rows as r (r.key)}
						{#if r.letter}
							<tr class={r.cls}>
								<td class="deg">&nbsp;</td>
								<td class="nm"><strong><a class="letter" id="litera-{r.letter}" href="#litera-{r.letter}">{r.letter}</a></strong></td>
								<td>&nbsp;</td>
								<td class="cnt">&nbsp;</td>
							</tr>
						{:else if r.person}
							{@const p = r.person}
							<tr class={r.cls}>
								<td class="deg">{p.degree}</td>
								<td class="nm">
									<a href="/ludzie/{p.slug}" title={p.role || undefined}>{p.name}</a>
									{#if p.image_consent === 'granted' || p.image_consent === 'refused'}
										<ConsentBadge consent={p.image_consent} compact />
									{/if}
								</td>
								<td>
									{#if p.aliases.length}
										{#each p.aliases as a, i (a.slug)}<a href="/przegladaj?tag={a.slug}">{a.name}</a>{#if i < p.aliases.length - 1}{', '}{/if}{/each}
									{:else}-{/if}
								</td>
								<td class="cnt">
									{#if p.post_count}<a href="/przegladaj?person={p.slug}" title="{p.post_count} {plural(p.post_count, 'wpis', 'wpisy', 'wpisów')}">{p.post_count}</a>{:else}-{/if}
								</td>
							</tr>
						{/if}
					{:else}
						<tr class="odd"><td class="deg">&nbsp;</td><td class="nm" colspan="3"><span class="muted">Nikt nie pasuje do szukanej frazy.</span></td></tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</div>
</div>
