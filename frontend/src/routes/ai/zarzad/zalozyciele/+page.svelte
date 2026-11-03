<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api';
	import { kolo, kp, type Founder } from '$lib/kolo.svelte';

	// The BOK template "Lista założycieli organizacji" (załącznik do Powiadomienia Rektora), the same
	// columns and footnotes as kolo_ai_zebrania/generuj.py lista_zalozycieli: filled rows first, then
	// blank rows for founders who sign up on paper. Signatures are always by hand.
	const PER_PAGE = 11;
	let rows = $state<Founder[] | null>(null);
	let error = $state<string | null>(null);
	// enough blank rows for founders who sign on paper: at least 22, rounded up to whole pages
	let blanks = $state(22);
	const total = $derived(rows ? Math.ceil((rows.length + blanks) / PER_PAGE) * PER_PAGE : 0);
	const all = $derived(rows ? [...rows, ...Array.from({ length: total - rows.length }, () => null)] : []);
	const pages = $derived(Array.from({ length: Math.max(1, Math.ceil(all.length / PER_PAGE)) }, (_, i) => all.slice(i * PER_PAGE, (i + 1) * PER_PAGE)));

	onMount(async () => {
		document.title = 'Lista założycieli — Koło AI';
		try { rows = await api.get<Founder[]>('/kolo/founders/'); }
		catch (e) { error = e instanceof ApiError ? e.message : String(e); }
	});

	function download() {
		const blob = new Blob([JSON.stringify(rows, null, 2)], { type: 'application/json' });
		const a = document.createElement('a');
		a.href = URL.createObjectURL(blob);
		a.download = 'zalozyciele.json';
		a.click();
		URL.revokeObjectURL(a.href);
	}
</script>

<div class="noprint">
	<p class="small"><a href={kp('/zarzad')}>← Zarząd</a></p>
	<h1>Lista założycieli do druku</h1>
	{#if error}<div class="error">{error}</div>{/if}
	{#if rows}
		<p>Wypełnione: <strong>{rows.length}</strong>. Pustych wierszy na dopisanie ręcznie:
			<input type="number" min="0" max="99" bind:value={blanks} style="width:5em" /> (dopełniane do pełnej strony)
			<button class="btn" onclick={() => print()}>Drukuj (A4 poziomo)</button>
			<button class="btn btn--ghost" onclick={download}>Pobierz JSON dla generatora</button></p>
		<p class="small muted">JSON zapisz jako <code>~/Projects/AI/kolo_ai_zebrania/zalozyciele.json</code> — generator wpisze te osoby do 04_Lista_zalozycieli.</p>
	{:else if !error && kolo.ready && !kolo.isManager}
		<p>Tylko dla zarządzających.</p>
	{/if}
</div>

{#if rows}
	{#each pages as page, p (p)}
		<section class="sheet">
			<div class="right">Załącznik<br />do Powiadomienia Rektora o powstaniu organizacji</div>
			<h2 class="center">Lista założycieli organizacji</h2>
			<p class="center sub">Koło AI – 3 listopada 2026 r.</p>
			<table class="bok">
				<thead><tr><th>LP.</th><th>Imię i nazwisko</th><th>Numer telefonu</th><th>Adres e-mail⁶</th><th>Kierunek⁷</th><th>Etap⁸</th><th>Numer albumu</th><th>Podpis</th></tr></thead>
				<tbody>
					{#each page as r, i (i)}
						<tr>
							<td>{p * PER_PAGE + i + 1}.</td>
							<td>{r?.name ?? ''}</td><td>{r?.phone ?? ''}</td><td>{r?.email ?? ''}</td>
							<td>{r?.kierunek ?? ''}</td><td>{r?.etap ?? ''}</td><td>{r?.nr_albumu ?? ''}</td><td></td>
						</tr>
					{/each}
				</tbody>
			</table>
			<p class="fn">⁶ osobisty adres konta elektronicznej poczty uniwersyteckiej<br />
				⁷ nazwa jednego z kierunków albo nazwa szkoły doktorskiej, na których kształci się założyciel<br />
				⁸ rok studiów na kierunku wskazanym przez założyciela albo etap kształcenia w szkole doktorskiej</p>
		</section>
	{/each}
{/if}

<style>
	.sheet { background: #fff; color: #000; padding: 10mm; margin: 16px 0; border: 1px solid #ccc; font-family: 'Times New Roman', serif; font-size: 11pt; }
	.right { text-align: right; font-size: 10pt; }
	.center { text-align: center; }
	h2.center { font-size: 15pt; margin: 6mm 0 1mm; }
	.sub { margin: 0 0 4mm; }
	table.bok { width: 100%; border-collapse: collapse; table-layout: fixed; }
	table.bok th, table.bok td { border: 1px solid #000; padding: 1.5mm 2mm; height: 11mm; font-size: 10pt; vertical-align: middle; word-break: break-word; }
	table.bok th { font-weight: bold; text-align: center; }
	table.bok th:nth-child(1) { width: 4%; } table.bok th:nth-child(2) { width: 17%; } table.bok th:nth-child(3) { width: 11%; }
	table.bok th:nth-child(4) { width: 19%; } table.bok th:nth-child(5) { width: 16%; } table.bok th:nth-child(6) { width: 7%; }
	table.bok th:nth-child(7) { width: 9%; } table.bok th:nth-child(8) { width: 17%; }
	.fn { font-size: 8pt; margin-top: 2mm; }
	@media print {
		@page { size: A4 landscape; margin: 12mm; }
		:global(.kolo__top), :global(.kolo__foot), .noprint { display: none !important; }
		:global(.kolo-bg) { background: #fff !important; }
		:global(.kolo) { max-width: none !important; padding: 0 !important; }
		.sheet { border: none; margin: 0; padding: 0; break-after: page; }
		.sheet:last-of-type { break-after: auto; }
	}
</style>
