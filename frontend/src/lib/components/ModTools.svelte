<script lang="ts">
	/** Hide / restore / nuke / escalate for a post (by slug) or a comment (by id). Only
	 * rendered for trusted/staff callers; the server re-checks every call. Every action
	 * that changes what other people can read goes through the one confirm dialog — a
	 * cancelled dialog does nothing (the old window.prompt() flow hid a post with an empty
	 * reason when the prompt was dismissed). */
	import { api, ApiError } from '$lib/api';
	import { auth } from '$lib/auth.svelte';
	import { dialog } from '$lib/dialog.svelte';
	import type { ModerationState } from '$lib/types';

	let { kind, id, status, onChanged }: {
		kind: 'post' | 'comment'; id: string | number; status: ModerationState; onChanged: () => void;
	} = $props();
	let busy = $state(false);
	let error = $state<string | null>(null);
	const base = $derived(kind === 'post' ? `/posts/${id}` : `/comments/${id}`);
	const what = $derived(kind === 'post' ? 'wpis' : 'komentarz');

	async function send(verb: string, reason: string) {
		busy = true; error = null;
		try {
			await api.post(`${base}/${verb}/`, { reason });
			onChanged();
		} catch (e) { error = e instanceof ApiError ? e.message : String(e); }
		busy = false;
	}

	async function hide() {
		const reason = await dialog.ask({
			title: `Ukryj ${what}`,
			text: `Zniknie ze strony publicznej i trafi na tablicę moderacji, gdzie każdy zaufany może go przywrócić. Autor zobaczy powód.`,
			confirm: 'Ukryj', reason: 'optional', placeholder: 'np. prosiła osoba na zdjęciu'
		});
		if (reason !== null) await send('hide', reason);
	}
	async function restore() {
		const ok = await dialog.ask({ title: `Przywróć ${what}`, text: 'Wróci tam, gdzie był przed ukryciem. Zgłoszenia zostają zamknięte.', confirm: 'Przywróć' });
		if (ok !== null) await send('restore', '');
	}
	async function nuke() {
		const reason = await dialog.ask({
			title: '☢ Opcja nuklearna', danger: true,
			text: 'Tylko treści nielegalne lub obrzydliwie obraźliwe. Po tym zobaczy je wyłącznie administracja; inni zaufani widzą jedynie, że coś takiego było, kto to zrobił i dlaczego. Cofnąć może tylko administracja.',
			confirm: 'Ukryj nuklearnie', reason: 'required', placeholder: 'co i dlaczego — ten powód zostaje w rejestrze'
		});
		if (reason) await send('nuke', reason);
	}
	async function escalate() {
		const reason = await dialog.ask({
			title: '🚨 Zgłoszenie do NASK (Dyżurnet.pl)', danger: true,
			text: 'Wyłącznie treści nielegalne w rozumieniu prawa (np. materiały przedstawiające seksualne wykorzystywanie dzieci). Od tej chwili treść jest niewidoczna dla WSZYSTKICH — także dla moderatorów i administracji — aż do decyzji head-admina, a jej kopia zostaje zamrożona jako materiał dowodowy. Zwykła moderacja tej treści jest zablokowana do czasu decyzji.',
			confirm: 'Zgłoś do NASK', reason: 'required', placeholder: 'co widzisz i dlaczego to sprawa dla NASK — wymagane'
		});
		if (reason) await send('escalate', reason);
	}
</script>

<span class="modtools">
	{#if status === 'visible'}
		<button type="button" class="btn btn--sm btn--ghost" disabled={busy} onclick={hide}>Ukryj</button>
		<button type="button" class="btn btn--sm btn--warn" disabled={busy} onclick={nuke} title="Tylko treści nielegalne / obrzydliwie obraźliwe">☢ Opcja nuklearna</button>
	{:else if status === 'hidden'}
		<button type="button" class="btn btn--sm" disabled={busy} onclick={restore}>Przywróć</button>
		<button type="button" class="btn btn--sm btn--warn" disabled={busy} onclick={nuke}>☢ Opcja nuklearna</button>
	{:else if auth.isStaff}
		<button type="button" class="btn btn--sm" disabled={busy} onclick={restore}>Przywróć (administracja)</button>
	{/if}
	<span class="sep" aria-hidden="true">·</span>
	<button type="button" class="btn btn--sm nask" disabled={busy} onclick={escalate}
		title="Treść nielegalna — zgłoszenie do NASK, decyduje head-admin">🚨 Zgłoś do NASK</button>
	{#if error}<span class="err">{error}</span>{/if}
</span>

<style>
	.modtools { display: inline-flex; gap: 4px; align-items: center; flex-wrap: wrap; }
	.err { color: #b00020; font-size: 11px; }
	.sep { color: var(--muted); padding: 0 2px; }
	.nask { background: #fff; color: #7a2f02; border: 1px dashed #7a2f02; }
	.nask:hover { background: #fff0f0; }
</style>
