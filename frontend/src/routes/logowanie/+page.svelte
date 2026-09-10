<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { ApiError } from '$lib/api';
	import { auth } from '$lib/auth.svelte';

	let username = $state('');
	let password = $state('');
	let busy = $state(false);
	let error = $state('');

	const next = $derived.by(() => {
		const n = page.url.searchParams.get('next');
		return n && n.startsWith('/') && !n.startsWith('//') ? n : '/';
	});
	const registerHref = $derived(next === '/' ? '/rejestracja' : `/rejestracja?next=${encodeURIComponent(next)}`);

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		if (busy) return;
		busy = true;
		error = '';
		try {
			await auth.login(username.trim(), password);
			goto(next, { replaceState: true });
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Nie udało się zalogować.';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>Logowanie — fuw.lol</title></svelte:head>

<div class="box narrow">
	<h1 class="box__title">Logowanie</h1>
	<div class="box__body">
		{#if auth.isAuthenticated}
			<p>Jesteś już zalogowany/a jako <strong>{auth.user?.username}</strong>.</p>
			<p><a href="/">Wróć na stronę główną</a> · <a href="/moje">Moje wpisy</a></p>
		{:else}
			<form onsubmit={submit}>
				<label for="l-user">Nazwa użytkownika albo e-mail</label>
				<input id="l-user" type="text" autocomplete="username" bind:value={username} required />

				<label for="l-pass">Hasło</label>
				<input id="l-pass" type="password" autocomplete="current-password" bind:value={password} required />

				{#if error}<div class="error">{error}</div>{/if}

				<p class="send">
					<button type="submit" disabled={busy}>{busy ? 'Loguję…' : 'Zaloguj się'}</button>
				</p>
			</form>
			<p class="small muted">
				Nie masz konta? <a href={registerHref}>Zarejestruj się</a>. Konto jest potrzebne tylko do
				dodawania wpisów, komentowania i reakcji — czytać można bez.
			</p>
		{/if}
	</div>
</div>

<style>
	.narrow {
		max-width: 420px;
	}
	.send {
		margin-top: 12px;
	}
</style>
