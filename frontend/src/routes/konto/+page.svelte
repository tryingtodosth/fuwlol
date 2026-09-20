<script lang="ts">
	import Breadcrumb from '$lib/components/Breadcrumb.svelte';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { api, ApiError } from '$lib/api';
	import { auth } from '$lib/auth.svelte';

	interface Domain { domain: string; institution: string; kind: string }
	let domains = $state<Domain[]>([]);
	let email = $state('');
	let sent = $state<string | null>(null);
	let error = $state<string | null>(null);
	let busy = $state(false);
	let redirected = false;

	$effect(() => {
		if (auth.ready && !auth.isAuthenticated && !redirected) { redirected = true; goto('/logowanie?next=/konto'); }
	});
	onMount(() => {
		document.title = 'Konto — fuw.lol';
		api.get<Domain[]>('/auth/trusted-domains/').then((d) => (domains = d)).catch(() => {});
	});

	async function request(e: Event) {
		e.preventDefault();
		busy = true; error = null; sent = null;
		try {
			const r = await api.post<{ sent_to: string }>('/auth/verify/request/', { email });
			sent = r.sent_to;
			await auth.init();
		} catch (err) { error = err instanceof ApiError ? err.message : String(err); }
		busy = false;
	}
</script>


<Breadcrumb trail={[{ label: 'Twoje konto' }]} />

<h1>Twoje konto</h1>
{#if auth.user}
	<div class="box">
		<h2 class="box__title">{auth.user.username}</h2>
		<div class="box__body">
			<table class="meta">
				<tbody>
					<tr><th>E-mail konta</th><td>{auth.user.email || '—'}</td></tr>
					<tr><th>Rola</th><td>
						{#if auth.user.is_staff}<span class="pill pill--green">administracja / moderacja</span>{/if}
						{#if auth.user.is_trusted}<span class="pill pill--amber">zaufany (zweryfikowana afiliacja)</span>{:else if !auth.user.is_staff}<span class="pill">zwykły użytkownik</span>{/if}
					</td></tr>
					{#if auth.user.affiliation}
						<tr><th>Afiliacja</th><td>{auth.user.affiliation.institution} <span class="muted small">({auth.user.affiliation.email_masked})</span></td></tr>
					{/if}
				</tbody>
			</table>
			<p class="small">
				<a href="/moje">Moje wpisy</a>
				{#if auth.user.is_trusted}· <a href="/tablica">Tablica moderacji</a>{/if}
				{#if auth.user.is_staff}· <a href="/moderacja">Kolejka moderacji</a>{/if}
			</p>
		</div>
	</div>

	<div class="box">
		<h2 class="box__title">Weryfikacja afiliacji <small>wyższe uprawnienia dla ludzi z Wydziału i okolic</small></h2>
		<div class="box__body">
			<p>Potwierdź adres e-mail w domenie związanej z Wydziałem Fizyki (UW, studenci UW, CeNT, instytuty PAN), a dostaniesz
				status <strong>zaufanego</strong>: twoje wpisy publikują się od ręki, możesz jednym kliknięciem ukrywać treści
				(trafiają na <a href="/tablica">tablicę moderacji</a>, gdzie widzą je wszyscy zaufani) i — w ostateczności — użyć opcji
				nuklearnej dla treści nielegalnych lub obrzydliwie obraźliwych (wtedy widzi je już tylko administracja).</p>
			{#if auth.user.is_trusted && !auth.user.is_staff}
				<div class="ok">Masz już status zaufanego.</div>
			{:else if auth.user.pending_verification}
				<p class="help">Wysłaliśmy link na {auth.user.pending_verification}. Kliknij go, albo poproś o nowy poniżej.</p>
			{/if}
			<form onsubmit={request}>
				<label for="aff-email">Adres instytucjonalny</label>
				<input id="aff-email" type="email" bind:value={email} placeholder="imie.nazwisko@fuw.edu.pl" required />
				<p class="help">Adres służy tylko do weryfikacji — nie pokażemy go nikomu.</p>
				<button type="submit" class="btn" disabled={busy}>{busy ? 'Wysyłam…' : 'Wyślij link weryfikacyjny'}</button>
			</form>
			{#if sent}<div class="ok">Wysłano na {sent}. Sprawdź skrzynkę (link ważny 24 h).</div>{/if}
			{#if error}<div class="error">{error}</div>{/if}
			{#if domains.length}
				<p class="small muted">Akceptowane domeny: {domains.map((d) => `${d.domain} (${d.institution})`).join(', ')}.</p>
			{/if}
		</div>
	</div>
{:else}
	<p class="muted">Ładuję…</p>
{/if}
