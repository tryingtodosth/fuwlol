<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { api, ApiError } from '$lib/api';
	import { kp } from '$lib/kolo.svelte';

	// The link from a mailing (`kolo_mail`): ?t=<signed id>. Opening the page changes nothing —
	// a mail scanner that follows every link must not unsubscribe anybody; the button does it.
	let token = $state('');
	let mail = $state<boolean | null>(null);
	let detail = $state<string | null>(null);
	let error = $state<string | null>(null);
	let busy = $state(false);

	onMount(() => {
		document.title = 'Koło AI — rezygnacja z maili';
		token = page.url.searchParams.get('t') ?? '';
		history.replaceState(history.state, '', kp('/wypisz'));
		if (!token) error = 'W linku brakuje klucza. Otwórz link z maila jeszcze raz albo odpowiedz na maila słowem WYPISZ.';
	});

	async function set(subscribe: boolean) {
		busy = true; error = null;
		try {
			const r = await api.post<{ mail: boolean; detail: string }>('/kolo/unsubscribe/', { token, subscribe });
			mail = r.mail; detail = r.detail;
		} catch (e) { error = e instanceof ApiError ? e.message : String(e); }
		busy = false;
	}
</script>

<h1>Rezygnacja z maili Koła AI</h1>
{#if error}
	<div class="error">{error}</div>
{:else if mail === null}
	<p>Jednym kliknięciem przestaniesz dostawać maile z ogłoszeniami Koła AI. Logowanie nie jest potrzebne,
		a Twój wpis na liście Koła zostaje bez zmian.</p>
	<button type="button" class="btn" disabled={busy || !token} onclick={() => set(false)}>Wypisz mnie z maili</button>
{:else}
	<div class="ok">{detail}</div>
	{#if mail}
		<button type="button" class="btn btn--ghost" disabled={busy} onclick={() => set(false)}>Jednak wypisz mnie</button>
	{:else}
		<p class="muted">Kliknięte przez pomyłkę?</p>
		<button type="button" class="btn btn--ghost" disabled={busy} onclick={() => set(true)}>Zapisz mnie z powrotem</button>
	{/if}
{/if}
<p><a href={kp()}>Strona główna Koła</a></p>
