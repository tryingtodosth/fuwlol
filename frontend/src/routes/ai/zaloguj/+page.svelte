<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api';
	import { kolo, kp } from '$lib/kolo.svelte';

	let email = $state('');
	let sent = $state<string | null>(null);
	let error = $state<string | null>(null);
	let busy = $state(false);

	onMount(() => { document.title = 'Zaloguj się — Koło AI'; });

	async function send(e: Event) {
		e.preventDefault();
		busy = true; error = null; sent = null;
		try { sent = (await api.post<{ detail: string }>('/kolo/login/', { email })).detail; }
		catch (err) { error = err instanceof ApiError ? err.message : String(err); }
		busy = false;
	}
</script>

<h1>Zaloguj się</h1>
{#if kolo.me}
	<p>Jesteś zalogowany jako <strong>{kolo.me.name}</strong>. <a href={kp()}>Strona główna</a></p>
{:else}
	<div class="card">
		<p>Bez hasła: wpisz adres, z którym jesteś na liście Koła, a wyślemy na niego link do logowania
			(ważny 24 godziny, jednorazowy). Otwórz go na urządzeniu, na którym chcesz być zalogowany.</p>
		<form onsubmit={send}>
			<label for="z-email">Adres e-mail</label>
			<input id="z-email" type="email" bind:value={email} required autocomplete="email" placeholder="imie.nazwisko@student.uw.edu.pl" />
			<button type="submit" class="btn" disabled={busy}>{busy ? 'Wysyłam…' : 'Wyślij link do logowania'}</button>
		</form>
		{#if sent}<div class="ok">{sent}</div>{/if}
		{#if error}<div class="error">{error}</div>{/if}
	</div>
	<p class="small muted">Nie ma Cię jeszcze na liście? <a href={kp() + '#lista'}>Zapisz się</a>.</p>
{/if}

<style>
	form .btn { margin-top: 10px; }
</style>
