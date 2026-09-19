<script lang="ts">
	/** The one place the image-consent state is drawn. `granted` is the badge — the person
	 * themself confirmed, through their mailbox and a staff check, that photos of them may be
	 * here (art. 81 pr. aut.); `refused` is the opposite request, worth showing to a would-be
	 * uploader before they upload. `unknown` and `opted_out` draw nothing: nothing is known, or
	 * the page is not supposed to exist. Both link to the explainer, because a badge nobody
	 * can look up is a rumour. */
	import type { ImageConsent } from '$lib/types';

	let { consent, compact = false }: { consent: ImageConsent; compact?: boolean } = $props();
</script>

{#if consent === 'granted'}
	<a
		class="badge badge--ok"
		href="/ludzie/zgoda"
		title="Ta osoba potwierdziła zgodę na publikację swojego wizerunku (art. 81 pr. aut.). Co to znaczy i jak ją cofnąć — kliknij."
		>✓{#if !compact}<span> zgoda na wizerunek</span>{/if}</a
	>
{:else if consent === 'refused'}
	<a
		class="badge badge--no"
		href="/ludzie/zgoda"
		title="Ta osoba prosi, by nie publikować jej zdjęć: wzmianki tak, zdjęć nie."
		>{#if compact}⊘{:else}bez zdjęć{/if}</a
	>
{/if}

<style>
	.badge { display: inline-block; font-size: 11px; line-height: 16px; padding: 0 6px; border: 1px solid; border-radius: 2px; vertical-align: 1px; white-space: nowrap; }
	.badge:hover { text-decoration: none; filter: brightness(0.97); }
	.badge--ok { color: #0b5a2a; background: #ecf8ef; border-color: #b6dfc2; }
	.badge--no { color: #7a2f02; background: #fff3e8; border-color: #e6c3a5; }
</style>
