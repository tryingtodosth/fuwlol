<script lang="ts">
	/** The one modal. Mounted once in +layout.svelte; driven by $lib/dialog.svelte.ts. */
	import { dialog } from '$lib/dialog.svelte';

	let el = $state<HTMLDialogElement | null>(null);
	let reason = $state('');
	let box = $state<HTMLTextAreaElement | null>(null);

	const req = $derived(dialog.current);
	const needsReason = $derived(req?.reason === 'required');
	const canConfirm = $derived(!needsReason || reason.trim().length > 0);

	$effect(() => {
		if (!el) return;
		if (req) {
			reason = '';
			if (!el.open) el.showModal();
			queueMicrotask(() => (box ?? el?.querySelector<HTMLElement>('button'))?.focus());
		} else if (el.open) el.close();
	});

	function confirm() {
		if (!req || !canConfirm) return;
		dialog.close(req.reason === 'none' ? '' : reason.trim());
	}
	function cancel() { dialog.close(null); }
	function onKey(e: KeyboardEvent) {
		if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); confirm(); }
	}
</script>

<dialog bind:this={el} class="dlg" class:dlg--danger={req?.danger} oncancel={(e) => { e.preventDefault(); cancel(); }} onkeydown={onKey}
	aria-labelledby="dlg-title">
	{#if req}
		<div class="dlg__title" id="dlg-title">{req.title}</div>
		<div class="dlg__body">
			<p class="dlg__text">{req.text}</p>
			{#if req.reason !== 'none'}
				<label for="dlg-reason">Powód{needsReason ? ' (wymagany)' : ' (opcjonalnie)'}</label>
				<textarea id="dlg-reason" rows="3" bind:this={box} bind:value={reason} placeholder={req.placeholder ?? ''} maxlength="2000"></textarea>
				<div class="help">Ctrl+Enter zatwierdza, Esc anuluje.</div>
			{/if}
		</div>
		<div class="dlg__acts">
			<button type="button" class="btn btn--ghost" onclick={cancel}>Anuluj</button>
			<button type="button" class="btn" class:btn--warn={req.danger} disabled={!canConfirm} onclick={confirm}>{req.confirm ?? 'Potwierdź'}</button>
		</div>
	{/if}
</dialog>

<style>
	.dlg { border: 1px solid var(--line); padding: 0; width: min(520px, 92vw); font-family: inherit; color: var(--text); box-shadow: 0 8px 30px rgba(0,0,0,.25); }
	.dlg::backdrop { background: rgba(0, 0, 0, .45); }
	.dlg__title { padding: 8px 12px; font-weight: bold; font-size: 14px; color: #222; border-bottom: 1px solid var(--line); background: var(--box); }
	.dlg--danger .dlg__title { background: #fff0f0; border-bottom-color: #f2b8b8; color: #7a2f02; }
	.dlg__body { padding: 12px; }
	.dlg__text { white-space: pre-line; margin: 0 0 6px; }
	.dlg__acts { display: flex; justify-content: flex-end; gap: 6px; padding: 8px 12px 12px; }
</style>
