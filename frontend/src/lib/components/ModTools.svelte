<script lang="ts">
	/** Hide / restore / nuke for a post (by slug) or a comment (by id). Only rendered for
	 * trusted/staff callers; the server re-checks every call. */
	import { api, ApiError } from '$lib/api';
	import { auth } from '$lib/auth.svelte';
	import type { ModerationState } from '$lib/types';

	let { kind, id, status, onChanged }: {
		kind: 'post' | 'comment'; id: string | number; status: ModerationState; onChanged: () => void;
	} = $props();
	let busy = $state(false);
	let error = $state<string | null>(null);
	const base = $derived(kind === 'post' ? `/posts/${id}` : `/comments/${id}`);

	async function act(verb: 'hide' | 'restore' | 'nuke') {
		let reason = '';
		if (verb === 'hide') reason = prompt('Powód ukrycia (opcjonalnie):') ?? '';
		if (verb === 'nuke') {
			reason = prompt('OPCJA NUKLEARNA — treść nielegalna lub obrzydliwie obraźliwa. Po tym zobaczy ją tylko administracja. Podaj powód (wymagany):') ?? '';
			if (!reason.trim()) return;
		}
		busy = true; error = null;
		try {
			await api.post(`${base}/${verb}/`, { reason });
			onChanged();
		} catch (e) { error = e instanceof ApiError ? e.message : String(e); }
		busy = false;
	}
</script>

<span class="modtools">
	{#if status === 'visible'}
		<button type="button" class="btn btn--sm btn--ghost" disabled={busy} onclick={() => act('hide')}>Ukryj</button>
		<button type="button" class="btn btn--sm btn--warn" disabled={busy} onclick={() => act('nuke')} title="Tylko treści nielegalne / obrzydliwie obraźliwe">☢ Opcja nuklearna</button>
	{:else if status === 'hidden'}
		<button type="button" class="btn btn--sm" disabled={busy} onclick={() => act('restore')}>Przywróć</button>
		<button type="button" class="btn btn--sm btn--warn" disabled={busy} onclick={() => act('nuke')}>☢ Opcja nuklearna</button>
	{:else if auth.isStaff}
		<button type="button" class="btn btn--sm" disabled={busy} onclick={() => act('restore')}>Przywróć (administracja)</button>
	{/if}
	{#if error}<span class="err">{error}</span>{/if}
</span>

<style>
	.modtools { display: inline-flex; gap: 4px; align-items: center; flex-wrap: wrap; }
	.err { color: #b00020; font-size: 11px; }
</style>
