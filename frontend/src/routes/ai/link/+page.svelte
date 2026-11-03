<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { ApiError } from '$lib/api';
	import { kolo, kp, type KoloMember } from '$lib/kolo.svelte';

	let member = $state<KoloMember | null>(null);
	let error = $state<string | null>(null);

	onMount(async () => {
		document.title = 'Koło AI — potwierdzenie';
		const token = page.url.searchParams.get('token') ?? '';
		// drop the token from the address bar and history before anything else happens
		history.replaceState(history.state, '', kp('/link'));
		try {
			member = await kolo.openLink(token);
			if (member.status === 'member') setTimeout(() => goto(kp()), 1500);
		} catch (e) { error = e instanceof ApiError ? e.message : String(e); }
	});
</script>

<h1>Potwierdzenie adresu</h1>
{#if error}
	<div class="error">{error}</div>
	<p><a href={kp() + '#lista'}>Wróć i poproś o nowy link</a></p>
{:else if member}
	{#if member.status === 'pending_approval'}
		<div class="card card--accent">
			<strong>Adres potwierdzony. Oczekujesz na zatwierdzenie.</strong>
			<p>Twoje zgłoszenie trafiło do Zarządu. Do czasu wpisu Koła do rejestru UW wszystkie zgłoszenia czekają na
				zatwierdzenie; potem studenci z adresem @student.uw.edu.pl są wpisywani od razu.</p>
		</div>
	{:else if member.status === 'member'}
		<div class="ok">Witaj w Kole AI, {member.name}! Przenoszę na stronę główną…</div>
	{:else}
		<p>{member.name}: {member.status_label}.</p>
	{/if}
	<p><a href={kp()}>Strona główna Koła</a></p>
{:else}
	<p class="muted">Sprawdzam link…</p>
{/if}
