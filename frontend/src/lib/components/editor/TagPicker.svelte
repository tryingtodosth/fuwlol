<script lang="ts">
	/** One typeahead for one axis: people, subjects or tags.
	 *
	 * It replaces the two things the editor used to have — a checkbox list of every person in
	 * the database, and a comma-separated text box for tags — and it exists because neither
	 * could do the one thing that mattered: name somebody who is not there yet. The checkbox
	 * list could not grow, so the help text told writers to put the missing lecturer in the
	 * tags, and nothing ever promoted such a tag to a person. „Dodaj „Anna Nowak”" is the fix,
	 * and it is why `allowCreate` exists on all three axes rather than just on tags.
	 *
	 * A real ARIA 1.2 combobox, not a div that listens for clicks: `role="combobox"` on the
	 * input with `aria-expanded` / `aria-controls` / `aria-activedescendant`, a `role="listbox"`
	 * whose rows are `role="option"`, arrow keys to move, Enter to take, Escape to close, and
	 * Backspace on an empty input to take back the last chip. Focus never leaves the input —
	 * the options are pointed at, not visited — which is what `aria-activedescendant` is for
	 * and what makes the keyboard behaviour match what a screen reader announces.
	 *
	 * The list is the API's, not a local filter: `/people/?q=`, `/subjects/?q=`, `/tags/?q=`.
	 * That matters for people, because the directory decides who is listed
	 * (archive/people.visible_people) and a client-side filter over a full download would
	 * happily suggest somebody the server means to hide.
	 */
	import { tick } from 'svelte';
	import { api, qs } from '$lib/api';
	import type { Person, Subject, Tag } from '$lib/types';
	import { type Chip, chipKey, hasChip, personChip, subjectChip, tagChip } from './chips';

	type Kind = 'people' | 'subjects' | 'tags';
	let {
		kind,
		selected,
		onchange,
		allowCreate = false,
		single = false,
		placeholder = '',
		id = ''
	}: {
		kind: Kind;
		selected: Chip[];
		onchange: (chips: Chip[]) => void;
		allowCreate?: boolean;
		single?: boolean;
		placeholder?: string;
		id?: string;
	} = $props();

	const MAX_OPTIONS = 10;
	const DEBOUNCE_MS = 200;
	/** The stopped clock of Polish academia. „—" is first because most of the archive's cast
	 * never had a title and the folklore does not care. */
	const DEGREES = ['', 'dr', 'dr hab.', 'prof. dr hab.', 'mgr', 'mgr inż.', 'inż.', 'lic.'];

	const LABEL: Record<Kind, { add: string; empty: string; nothing: string }> = {
		people: {
			add: 'Dodaj osobę',
			empty: 'Nikt taki nie jest jeszcze w spisie.',
			nothing: 'Zacznij pisać nazwisko.'
		},
		subjects: {
			add: 'Dodaj przedmiot',
			empty: 'Nie ma takiego przedmiotu w programie.',
			nothing: 'Zacznij pisać nazwę przedmiotu.'
		},
		tags: { add: 'Dodaj tag', empty: 'Nie ma jeszcze takiego tagu.', nothing: 'Zacznij pisać tag.' }
	};

	const uid = `pk-${Math.random().toString(36).slice(2, 8)}`;
	const inputId = $derived(id || `${uid}-input`);
	const listId = `${uid}-list`;

	let query = $state('');
	let open = $state(false);
	let options = $state<Chip[]>([]);
	let loading = $state(false);
	let active = $state(-1);
	/** Which `kind:query` the options in hand are the answer to. `$state`, not the usual
	 * plain-`let` guard, because `settled` below has to react to it — the effect that writes
	 * it still cannot loop, since it compares first and the one write it makes is the write
	 * that stops it running again. */
	let fetchedKey = $state('');
	let inputEl = $state<HTMLInputElement | null>(null);
	/** The inline two-line form for a brand-new person: a name alone would throw away the
	 * title and the role, which are the two things the directory prints next to it. */
	let draft = $state<{ name: string; degree: string; role: string } | null>(null);

	const trimmed = $derived(query.trim());
	/** True once `options` is the answer to the text that is in the box RIGHT NOW. Everything
	 * about creating hangs off this: „no exact match, so offer to add it" is a claim about
	 * results, and while a fetch is in flight there are no results — only the previous
	 * query's. Without the gate, typing „Mechanika klas" and hitting Enter before the
	 * response landed created a second subject next to „Mechanika klasyczna", which is
	 * exactly the duplicate this picker exists to prevent. */
	const settled = $derived(fetchedKey === `${kind}:${trimmed}` && !loading);
	/** An „add this" row only when the text is not already one of the options, and never for
	 * a chip that is already on the post. */
	const canOffer = $derived(
		allowCreate &&
			settled &&
			trimmed.length >= 2 &&
			!options.some((o) => o.name.toLocaleLowerCase('pl') === trimmed.toLocaleLowerCase('pl')) &&
			!hasChip(selected, { name: trimmed })
	);
	const rows = $derived<Chip[]>(canOffer ? [...options, { name: trimmed, isNew: true }] : options);
	const activeId = $derived(active >= 0 && active < rows.length ? `${uid}-opt-${active}` : undefined);

	let timer: ReturnType<typeof setTimeout> | undefined;
	let run = 0;
	/** Also a plain let, and it fixes something a browser found in one click and no assertion
	 * would have: taking a chip closes the listbox and then puts focus back in the input so
	 * the next one can be typed — but `focus()` fires `onfocus`, which reopened the listbox,
	 * which then hung over the field below and swallowed clicks meant for it. So the one
	 * focus WE cause is marked as ours. */
	let refocusing = false;
	$effect(() => {
		const q = trimmed;
		const k = kind;
		const isOpen = open;
		if (!isOpen) return;
		const key = `${k}:${q}`;
		if (key === fetchedKey) return;
		clearTimeout(timer);
		timer = setTimeout(() => {
			fetchedKey = key;
			void search(k, q);
		}, DEBOUNCE_MS);
		return () => clearTimeout(timer);
	});

	async function search(k: Kind, q: string) {
		const mine = ++run;
		loading = true;
		try {
			const path = `/${k}/${qs({ q })}`;
			if (k === 'people') {
				const rowsIn = await api.get<Person[]>(path);
				if (mine !== run) return;
				options = rowsIn.slice(0, MAX_OPTIONS).map(personChip);
			} else if (k === 'subjects') {
				const rowsIn = await api.get<Subject[]>(path);
				if (mine !== run) return;
				options = rowsIn.slice(0, MAX_OPTIONS).map(subjectChip);
			} else {
				const rowsIn = await api.get<Tag[]>(path);
				if (mine !== run) return;
				options = rowsIn.slice(0, MAX_OPTIONS).map(tagChip);
			}
			active = rows.length ? 0 : -1;
		} catch {
			// a typeahead that cannot reach the server still lets you type a new name
			if (mine === run) options = [];
		} finally {
			if (mine === run) loading = false;
		}
	}

	function take(chip: Chip) {
		if (chip.isNew && kind === 'people') {
			draft = { name: chip.name, degree: '', role: '' };
			open = false;
			return;
		}
		add(chip);
	}

	function add(chip: Chip) {
		if (!hasChip(selected, chip)) onchange(single ? [chip] : [...selected, chip]);
		query = '';
		fetchedKey = '';
		options = [];
		active = -1;
		open = false;
		draft = null;
		refocus();
	}

	function remove(chip: Chip) {
		const k = chipKey(chip);
		onchange(selected.filter((c) => chipKey(c) !== k));
		refocus();
	}

	function refocus() {
		refocusing = true;
		tick().then(() => {
			inputEl?.focus();
			refocusing = false;
		});
	}

	function confirmDraft() {
		if (!draft) return;
		const name = draft.name.trim();
		if (name.length < 2) return;
		add({ name, degree: draft.degree, role: draft.role.trim(), isNew: true });
	}

	function onKey(e: KeyboardEvent) {
		if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
			e.preventDefault();
			if (!open) {
				open = true;
				return;
			}
			if (!rows.length) return;
			const step = e.key === 'ArrowDown' ? 1 : -1;
			active = (active + step + rows.length) % rows.length;
			return;
		}
		if (e.key === 'Enter') {
			// A closed picker keeps its hands off: on /przegladaj the form behind it should
			// filter, which is what Enter means there. An OPEN one always swallows the key —
			// half the archive would otherwise be posted by somebody finishing a tag.
			if (!open) return;
			e.preventDefault();
			if (active >= 0 && active < rows.length) {
				take(rows[active]);
			} else if (canOffer && trimmed) {
				take({ name: trimmed, isNew: true });
			} else {
				// nothing to take — get out of the way rather than sit there eating Enters
				open = false;
			}
			return;
		}
		if (e.key === 'Escape') {
			if (open) {
				e.stopPropagation();
				open = false;
				active = -1;
			}
			return;
		}
		if (e.key === 'Backspace' && !query && selected.length) {
			e.preventDefault();
			remove(selected[selected.length - 1]);
		}
	}

	function onInput() {
		open = true;
		active = -1;
	}
	function onFocus() {
		if (!refocusing) open = true;
	}
	/** A click inside the widget (an option, the × on a chip) must not close it before the
	 * click lands, so the blur is checked against where focus actually went. */
	function onBlur(e: FocusEvent) {
		const next = e.relatedTarget as Node | null;
		const box = (e.currentTarget as HTMLElement).closest('.pick');
		if (next && box && box.contains(next)) return;
		open = false;
		active = -1;
	}
</script>

<div class="pick">
	<div class="pick__box" class:pick__box--open={open} class:pick__box--single={single}>
		{#each selected as chip (chipKey(chip))}
			<span class="chip" class:chip--new={chip.isNew}>
				{#if chip.consent === 'granted'}<span class="chip__ok" title="zgoda na wizerunek">✓</span>{/if}
				<span class="chip__name">{chip.name}</span>
				{#if chip.isNew}<span class="chip__tag">nowa</span>{/if}
				<button type="button" class="chip__x" aria-label="Usuń {chip.name}" onclick={() => remove(chip)}>×</button>
			</span>
		{/each}
		<!-- always rendered, even in single mode with a chip already in the box: the `<label
		     for=…>` beside this picker points at THIS input, and a label whose target comes and
		     goes is a label that is sometimes attached to nothing. Typing over a single
		     selection replaces it. -->
		<input
			class="pick__in"
			id={inputId}
			type="text"
			role="combobox"
			autocomplete="off"
			aria-expanded={open}
			aria-controls={listId}
			aria-autocomplete="list"
			aria-activedescendant={activeId}
			placeholder={selected.length ? '' : placeholder}
			bind:this={inputEl}
			bind:value={query}
			oninput={onInput}
			onfocus={onFocus}
			onblur={onBlur}
			onkeydown={onKey}
		/>
	</div>

	<ul class="pick__list" class:pick__list--open={open} id={listId} role="listbox" aria-label={LABEL[kind].add}>
		{#each rows as row, i (chipKey(row) + (row.isNew ? ':new' : ''))}
			<li
				class="opt"
				class:opt--active={i === active}
				class:opt--add={row.isNew}
				id="{uid}-opt-{i}"
				role="option"
				aria-selected={i === active}
				onmousedown={(e) => {
					e.preventDefault();
					take(row);
				}}
				onmousemove={() => (active = i)}
			>
				{#if row.isNew}
					<span class="opt__plus" aria-hidden="true">+</span> {LABEL[kind].add} „{row.name}”
				{:else}
					<span class="opt__name">
						{#if row.consent === 'granted'}<span class="chip__ok" title="zgoda na wizerunek">✓</span>{/if}
						{row.name}
					</span>
					{#if row.role}<span class="opt__role muted">{row.role}</span>{/if}
					{#if row.aliases}<span class="opt__alias muted" title="ksywki">„{row.aliases}”</span>{/if}
				{/if}
			</li>
		{:else}
			<li class="opt opt--none" role="option" aria-selected="false" aria-disabled="true">
				{loading ? 'Szukam…' : trimmed ? LABEL[kind].empty : LABEL[kind].nothing}
			</li>
		{/each}
	</ul>

	{#if draft}
		<div class="mini">
			<div class="mini__row">
				<label class="mini__lbl" for="{uid}-nm">Imię i nazwisko</label>
				<input class="mini__in" id="{uid}-nm" type="text" maxlength="120" bind:value={draft.name} />
				<label class="mini__lbl" for="{uid}-deg">Tytuł</label>
				<select class="mini__sel" id="{uid}-deg" bind:value={draft.degree}>
					{#each DEGREES as d (d)}<option value={d}>{d || '—'}</option>{/each}
				</select>
			</div>
			<div class="mini__row">
				<label class="mini__lbl" for="{uid}-role">Kim jest</label>
				<input
					class="mini__in"
					id="{uid}-role"
					type="text"
					maxlength="120"
					placeholder="np. wykładowczyni mechaniki, portierka, legenda rocznika"
					bind:value={draft.role}
				/>
				<button type="button" class="btn btn--sm" onclick={confirmDraft}>Dodaj</button>
				<button type="button" class="btn btn--sm btn--ghost" onclick={() => (draft = null)}>Anuluj</button>
			</div>
		</div>
	{/if}
</div>

<style>
	.pick { position: relative; }
	.pick__box { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; min-height: 28px;
		border: 1px solid #aaa; background: #fff; padding: 3px 4px; }
	.pick__box--open { border-color: var(--green); outline: 2px solid var(--amber); outline-offset: 0; }
	/* A single-select picker sits in a row of `<select>`s (the browse filters) and has to be
	   the same height as one. So its chip and its input share the line: no wrapping, the chip
	   gives way first, the input keeps a thumb's width to click into. */
	.pick__box--single { flex-wrap: nowrap; }
	.pick__box--single .chip { min-width: 0; }
	.pick__box--single .pick__in { flex: 1 1 40px; min-width: 40px; }
	.pick__in { flex: 1 1 120px; min-width: 90px; width: auto; border: 0; padding: 2px 3px; font-size: 13px; }
	.pick__in:focus { outline: 0; }

	.chip { display: inline-flex; align-items: center; gap: 3px; font-size: 11px; line-height: 18px;
		border: 1px solid var(--line); background: var(--box); color: #333; padding: 0 2px 0 6px; border-radius: 2px; }
	.chip--new { background: #fffbe8; border-color: #c98f1e; }
	.chip__name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.chip__ok { color: #0b5a2a; font-weight: bold; }
	.chip__tag { font-size: 9px; letter-spacing: .5px; color: #8a5a00; }
	.chip__x { background: none; border: 0; color: var(--muted); font-size: 13px; line-height: 1;
		padding: 0 3px; cursor: pointer; }
	.chip__x:hover { background: none; color: var(--rust); }

	.pick__list { display: none; position: absolute; z-index: 20; left: 0; right: 0; margin: 0; padding: 0;
		list-style: none; max-height: 210px; overflow: auto; border: 1px solid #aaa; border-top: 0; background: #fff;
		box-shadow: 0 2px 4px rgba(0, 0, 0, .18); }
	.pick__list--open { display: block; }
	.opt { display: flex; gap: 6px; align-items: baseline; padding: 3px 7px; font-size: 12px; cursor: pointer; }
	.opt--active { background: var(--box); }
	.opt--add { color: var(--green); border-top: 1px solid #eee; }
	.opt--none { color: var(--muted); cursor: default; }
	.opt__name { flex: 0 1 auto; }
	.opt__role { flex: 1 1 auto; min-width: 0; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.opt__alias { flex: 0 1 auto; min-width: 0; font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.opt__plus { font-weight: bold; }

	.mini { border: 1px solid #c98f1e; background: #fffbe8; padding: 5px 7px; margin-top: 4px; }
	.mini__row { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; margin-bottom: 4px; }
	.mini__row:last-child { margin-bottom: 0; }
	.mini__lbl { margin: 0; font-size: 11px; color: #6b4a00; flex: 0 0 auto; }
	.mini__in { flex: 1 1 120px; width: auto; min-width: 0; font-size: 12px; padding: 2px 5px; }
	.mini__sel { flex: 0 0 auto; width: auto; font-size: 12px; padding: 2px 4px; }
</style>
