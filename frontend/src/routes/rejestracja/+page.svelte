<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { ApiError } from '$lib/api';
	import { auth } from '$lib/auth.svelte';

	const NAME_RE = /^[A-Za-z0-9._-]{3,30}$/;

	let username = $state('');
	let email = $state('');
	let password = $state('');
	let repeat = $state('');
	let busy = $state(false);
	let error = $state('');

	const next = $derived.by(() => {
		const n = page.url.searchParams.get('next');
		return n && n.startsWith('/') && !n.startsWith('//') ? n : '/';
	});
	const loginHref = $derived(next === '/' ? '/logowanie' : `/logowanie?next=${encodeURIComponent(next)}`);

	function localProblem(): string {
		if (!NAME_RE.test(username.trim()))
			return 'Nazwa użytkownika: 3–30 znaków, tylko litery, cyfry oraz . _ -';
		if (password.length < 8) return 'Hasło musi mieć co najmniej 8 znaków.';
		if (password !== repeat) return 'Hasła się nie zgadzają.';
		return '';
	}

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		if (busy) return;
		const problem = localProblem();
		if (problem) {
			error = problem;
			return;
		}
		busy = true;
		error = '';
		try {
			await auth.register(username.trim(), email.trim(), password);
			goto(next, { replaceState: true });
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Nie udało się założyć konta.';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>Rejestracja — fuw.lol</title></svelte:head>

<div class="box narrow">
	<h1 class="box__title">Rejestracja</h1>
	<div class="box__body">
		{#if auth.isAuthenticated}
			<p>Masz już konto i jesteś zalogowany/a jako <strong>{auth.user?.username}</strong>.</p>
			<p><a href="/">Wróć na stronę główną</a></p>
		{:else}
			<form onsubmit={submit}>
				<label for="r-user">Nazwa użytkownika</label>
				<input id="r-user" type="text" autocomplete="username" bind:value={username} required />
				<div class="help">3–30 znaków: litery, cyfry oraz . _ -</div>

				<label for="r-mail">E-mail (opcjonalnie)</label>
				<input id="r-mail" type="email" autocomplete="email" bind:value={email} />
				<div class="help">Tylko do odzyskania konta. Nie pokazujemy go nikomu.</div>

				<label for="r-pass">Hasło</label>
				<input id="r-pass" type="password" autocomplete="new-password" bind:value={password} required />
				<div class="help">Co najmniej 8 znaków.</div>

				<label for="r-pass2">Powtórz hasło</label>
				<input id="r-pass2" type="password" autocomplete="new-password" bind:value={repeat} required />

				{#if error}<div class="error">{error}</div>{/if}

				<p class="send">
					<button type="submit" disabled={busy}>{busy ? 'Zakładam konto…' : 'Załóż konto'}</button>
				</p>
			</form>
			<p class="small muted">
				Masz już konto? <a href={loginHref}>Zaloguj się</a>. Wpisy nowych osób przechodzą przez
				moderację — to nie jest nic osobistego.
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
