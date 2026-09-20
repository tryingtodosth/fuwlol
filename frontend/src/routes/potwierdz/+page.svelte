<script lang="ts">
	import Breadcrumb from '$lib/components/Breadcrumb.svelte';
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { api, ApiError } from '$lib/api';
	import { auth } from '$lib/auth.svelte';

	let phase = $state<'working' | 'ok' | 'error' | 'notoken'>('working');
	let institution = $state('');
	let error = $state('');

	onMount(async () => {
		document.title = 'Potwierdzenie adresu — fuw.lol';
		const token = page.url.searchParams.get('token');
		if (!token) { phase = 'notoken'; return; }
		try {
			const r = await api.post<{ ok: boolean; institution: string }>('/auth/verify/confirm/', { token });
			institution = r.institution; phase = 'ok';
			if (auth.isAuthenticated) await auth.init();
		} catch (e) { error = e instanceof ApiError ? e.message : String(e); phase = 'error'; }
	});
</script>


<Breadcrumb trail={[{ label: 'Twoje konto', href: '/konto' }, { label: 'Potwierdzenie adresu' }]} />

<h1>Potwierdzenie adresu</h1>
<div class="box"><div class="box__body">
	{#if phase === 'working'}
		<p class="muted">Sprawdzam link…</p>
	{:else if phase === 'ok'}
		<div class="ok">Gotowe — potwierdzono afiliację: <strong>{institution}</strong>. Masz teraz status zaufanego.</div>
		<p><a href="/konto">Przejdź do konta</a> · <a href="/tablica">Tablica moderacji</a></p>
	{:else if phase === 'notoken'}
		<div class="error">Brak tokenu w linku.</div>
	{:else}
		<div class="error">{error}</div>
		<p><a href="/konto">Poproś o nowy link</a></p>
	{/if}
</div></div>
