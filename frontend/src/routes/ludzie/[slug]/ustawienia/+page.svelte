<script lang="ts">
	/** The settings behind the magic link: what this mailbox asked for, and the two ways to
	 * change it.
	 *
	 * No account, no password, no second review — on purpose. RODO art. 7 ust. 3 says
	 * withdrawing consent must be as easy as giving it, and giving it was one form and one
	 * click in a mailbox. A queue in front of the withdrawal would make the taking-back
	 * harder than the giving, which is the one thing that article names outright. The
	 * change therefore applies the moment it is clicked, and the page says so before it is. */
	import Breadcrumb from '$lib/components/Breadcrumb.svelte';
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { ApiError } from '$lib/api';
	import { dialog } from '$lib/dialog.svelte';
	import { changeWish, loadManage, withdrawClaim, WISHES, type ManageState, type Wish } from '$lib/consent';

	const slug = $derived(page.params.slug ?? '');

	let token = $state('');
	let state_ = $state<ManageState | null>(null);
	let loading = $state(true);
	let error = $state('');
	let notice = $state('');
	let busy = $state(false);
	let done = $state(false); // withdrawn: nothing left to manage

	onMount(async () => {
		document.title = 'Twoje ustawienia — fuw.lol';
		token = page.url.searchParams.get('token') ?? '';
		if (!token) {
			error = 'Brak tokenu w linku.';
			loading = false;
			return;
		}
		await load();
	});

	async function load() {
		loading = true;
		try {
			state_ = await loadManage(token);
			error = '';
		} catch (e) {
			error = e instanceof ApiError ? e.message : String(e);
		} finally {
			loading = false;
		}
	}

	async function pick(wish: Wish) {
		if (busy || !state_ || wish === state_.current_wish) return;
		const label = WISHES.find((w) => w.value === wish)?.label ?? wish;
		const ok = await dialog.ask({
			title: 'Zmienić wybór?',
			text: `Nowy wybór: „${label}”.\n\nZadziała od razu — nikt tego już nie zatwierdza, bo ten adres został sprawdzony raz i to wystarczy. Poprzedni wybór zostaje w naszym archiwum jako zapis tego, co i kiedy ustaliliśmy.`,
			confirm: 'Zmień'
		});
		if (ok === null) return;
		busy = true;
		try {
			const r = await changeWish(token, wish);
			notice = r.message;
			await load();
		} catch (e) {
			error = e instanceof ApiError ? e.message : String(e);
		} finally {
			busy = false;
		}
	}

	async function withdraw() {
		if (busy) return;
		const ok = await dialog.ask({
			title: 'To jednak nie ja',
			text: 'Wycofamy Twój wybór: odznaka zniknie, a wpisy ukryte na Twój wniosek wrócą tam, gdzie były. Zapis samego wniosku zostaje — musimy umieć powiedzieć, kto i kiedy o co prosił.',
			confirm: 'Wycofaj',
			danger: true
		});
		if (ok === null) return;
		busy = true;
		try {
			const r = await withdrawClaim(token);
			notice = r.message;
			state_ = null;
			done = true;
		} catch (e) {
			error = e instanceof ApiError ? e.message : String(e);
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>Twoje ustawienia — fuw.lol</title></svelte:head>

<Breadcrumb trail={[{ label: 'Osoby', href: '/ludzie' }, { label: state_ ? state_.person.full_name : 'Osoba', href: `/ludzie/${page.params.slug}` }, { label: 'Twoje ustawienia' }]} />


<div class="box">
	<h1 class="box__title">
		Twoje ustawienia
		{#if state_}<small>{state_.person.full_name}</small>{/if}
	</h1>
	<div class="box__body">
		{#if loading}
			<p class="muted">Wczytuję…</p>
		{:else if done}
			<div class="ok">{notice}</div>
			<p><a href="/ludzie">Spis osób</a> · <a href="/ludzie/zgoda">Jak to działa</a></p>
		{:else if error && !state_}
			<div class="error">{error}</div>
			<p class="small">
				Link do ustawień działa 24 godziny. Po nowy wróć na <a href="/ludzie/{slug}">stronę osoby</a>
				i użyj „Wyślij link do ustawień” — przyjdzie na ten sam adres co poprzednio.
			</p>
		{:else if state_}
			{#if notice}<div class="ok">{notice}</div>{/if}
			{#if error}<div class="error">{error}</div>{/if}
			<table class="meta">
				<tbody>
					<tr><th>Strona</th><td><a href="/ludzie/{state_.person.slug}">{state_.person.full_name}</a></td></tr>
					<tr><th>Twój adres</th><td>{state_.email_masked}</td></tr>
					<tr><th>Obecny wybór</th><td><strong>{state_.current_wish_label}</strong></td></tr>
					<tr><th>Wersja zgody</th><td class="muted">{state_.consent_text_version}</td></tr>
				</tbody>
			</table>

			<h2>Zmień wybór</h2>
			<p class="small muted">Działa od razu, bez kolejki i bez konta.</p>
			<ul class="wishes">
				{#each WISHES as w (w.value)}
					<li class="wish" class:wish--current={w.value === state_.current_wish}>
						<div class="wish__text">
							<strong>{w.label}</strong>
							<span class="wish__hint">{w.hint}</span>
						</div>
						{#if w.value === state_.current_wish}
							<span class="pill pill--green">tak jest teraz</span>
						{:else}
							<button type="button" class="btn btn--sm" disabled={busy} onclick={() => pick(w.value)}>
								Wybierz
							</button>
						{/if}
					</li>
				{/each}
			</ul>

			<h2>To jednak nie ja</h2>
			<p class="small">
				Jeśli wpis został złożony przez pomyłkę — albo to wcale nie Twoja strona — wycofaj go.
				Wszystko, co się na jego podstawie zmieniło, wróci do stanu sprzed.
			</p>
			<button type="button" class="btn btn--warn btn--sm" disabled={busy} onclick={withdraw}>
				Wycofaj mój wpis
			</button>
		{/if}
	</div>
</div>

<style>
	h2 {
		font-size: 14px;
		margin: 14px 0 4px;
	}
	.wishes {
		list-style: none;
		margin: 0 0 8px;
		padding: 0;
		border: 1px solid var(--line);
	}
	.wish {
		display: flex;
		gap: 10px;
		align-items: center;
		justify-content: space-between;
		padding: 8px 10px;
		border-bottom: 1px solid #e6e6e6;
	}
	.wish:last-child {
		border-bottom: 0;
	}
	.wish--current {
		background: var(--box);
	}
	.wish__hint {
		display: block;
		color: var(--muted);
		font-size: 11px;
	}
</style>
