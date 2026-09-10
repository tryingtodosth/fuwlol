<!-- The control on the home page. Two ways in, because one input cannot do both jobs:
     a date picker for anything a browser will accept, and a plain text field for the
     rest of the timeline — `<input type="date">` has no way to say -13 800 000 000. -->
<script lang="ts">
	import { goto } from '$app/navigation';
	import { eraFor, eraLabel, formatTravel, parseTravel } from './eras';

	const now = new Date();
	const todayIso = [
		now.getFullYear(),
		String(now.getMonth() + 1).padStart(2, '0'),
		String(now.getDate()).padStart(2, '0')
	].join('-');

	const JUMPS: { label: string; value: string }[] = [
		{ label: 'Dziś', value: todayIso },
		{ label: '2010', value: '2010-01-01' },
		{ label: '2003', value: '2003-01-01' },
		{ label: '1998 (najstarszy zrzut)', value: '1998-01-20' },
		{ label: '1900', value: '1900-01-01' },
		{ label: '1800', value: '1800-01-01' },
		{ label: '1543 (Kopernik)', value: '1543-05-24' },
		{ label: '10 000 p.n.e.', value: '-10000' },
		{ label: 'Dinozaury (66 mln lat temu)', value: '-66000000' },
		{ label: 'Wielki Wybuch', value: '-13800000000' },
		{ label: 'Przed Wielkim Wybuchem', value: '-13800000001' }
	];

	let dateVal = $state(todayIso);
	let yearVal = $state('');
	let jumpVal = $state('');
	/** Which of the two fields the visitor touched last is the one that counts. */
	let source = $state<'date' | 'year'>('date');

	const chosen = $derived(parseTravel(source === 'date' ? dateVal : yearVal));
	const era = $derived(chosen ? eraFor(chosen) : null);

	function pickJump(e: Event) {
		const value = (e.currentTarget as HTMLSelectElement).value;
		jumpVal = '';
		if (!value) return;
		const d = parseTravel(value);
		if (!d) return;
		// A modern, complete date belongs in the picker; everything else in the text field,
		// which is the only one that can hold it.
		if (d.year >= 1900 && d.month !== undefined && d.day !== undefined) {
			dateVal = value;
			source = 'date';
		} else {
			yearVal = value;
			source = 'year';
		}
	}

	function travel(e: SubmitEvent) {
		e.preventDefault();
		if (!chosen) return;
		goto('/?czas=' + formatTravel(chosen));
	}
</script>

<div class="box">
	<h2 class="box__title">Wehikuł czasu <small>fuw.lol</small></h2>
	<div class="box__body">
		<p>Zobacz, jak wyglądała ta strona — albo poprzedniczka — w wybranym dniu.</p>

		<form onsubmit={travel}>
			<div class="row">
				<div>
					<label for="tm-date">Data</label>
					<input
						id="tm-date"
						type="date"
						min="1900-01-01"
						max={todayIso}
						bind:value={dateVal}
						oninput={() => (source = 'date')}
					/>
					<p class="help">Od 1900 do dziś.</p>
				</div>
				<div>
					<label for="tm-year">Rok (ujemny = p.n.e., np. -13800000000)</label>
					<input
						id="tm-year"
						type="text"
						inputmode="numeric"
						placeholder="np. 1543, -10000, -66000000"
						bind:value={yearVal}
						oninput={() => (source = 'year')}
					/>
					<p class="help">Można też podać <code>1543-05-24</code> albo <code>1543-05</code>.</p>
				</div>
				<div>
					<label for="tm-jump">Skoki</label>
					<select id="tm-jump" bind:value={jumpVal} onchange={pickJump}>
						<option value="">— wybierz —</option>
						{#each JUMPS as j (j.value)}
							<option value={j.value}>{j.label}</option>
						{/each}
					</select>
					<p class="help">Gotowe przystanki na osi czasu.</p>
				</div>
			</div>

			<p class="verdict">
				{#if era}
					Trafisz do: <b>{eraLabel(era)}</b>
				{:else}
					<span class="muted">Podaj datę albo rok — wtedy powiem, co zobaczysz.</span>
				{/if}
			</p>

			<button type="submit" class="btn" disabled={!chosen}>Jedź!</button>
		</form>
	</div>
</div>

<style>
	.verdict {
		margin: 10px 0 8px;
		padding-top: 8px;
		border-top: 1px dotted var(--line);
		font-size: 12px;
	}
	code {
		background: var(--box);
		border: 1px solid var(--line);
		padding: 0 3px;
	}
</style>
