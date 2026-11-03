<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api';
	import { kolo, kp, when, PHASE_LABEL, type Poll } from '$lib/kolo.svelte';

	let polls = $state<Poll[] | null>(null);
	let error = $state<string | null>(null);

	onMount(async () => {
		document.title = 'Koło AI — głosowania';
		try { polls = await api.get<Poll[]>('/kolo/polls/'); }
		catch (e) { error = e instanceof ApiError ? e.message : String(e); }
	});
</script>

<h1>Głosowania i obrady</h1>
{#if kolo.ready && !kolo.me}
	<p>Głosowania są dostępne dla członków Koła. <a href={kp() + '#lista'}>Zaloguj się linkiem z maila.</a></p>
{:else if error}
	<div class="error">{error}</div>
{:else if polls === null}
	<p class="muted">Ładuję…</p>
{:else if polls.length === 0}
	<p class="muted">Nie ma jeszcze żadnych głosowań{kolo.isVoter ? '' : ' dostępnych dla Ciebie — głosują członkowie wpisani do ewidencji'}.</p>
{:else}
	<table class="kt">
		<thead><tr><th>Sprawa</th><th>Organ</th><th>Termin</th><th>Stan</th></tr></thead>
		<tbody>
			{#each polls as p (p.id)}
				<tr>
					<td><a href={kp(`/glosowania/${p.id}`)}>{p.title}</a>{#if p.trial} <span class="pill">próba</span>{/if}</td>
					<td>{p.organ_label}, {p.mode}</td>
					<td>{when(p.opens_at)} – {when(p.closes_at)}</td>
					<td>{PHASE_LABEL[p.phase]}</td>
				</tr>
			{/each}
		</tbody>
	</table>
{/if}
