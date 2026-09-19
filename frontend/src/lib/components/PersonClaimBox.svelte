<script lang="ts">
	/** „Jesteś tą osobą?” — the box on a profile through which the person the folklore is
	 * about says what they want, without an account, because a lecturer who finds their
	 * name in a meme archive is not going to register first.
	 *
	 * Collapsed to one sentence until somebody says "that's me": on a page about somebody
	 * else it is noise, and the profile is mostly read by people who are not the subject.
	 * Once an entry has been claimed (`granted` / `refused`) the form goes away entirely
	 * and only the settings path stays — the wish is already recorded, and what the person
	 * needs then is the way to change it, not a second copy of the same form.
	 *
	 * The honeypot, the 202-whatever-happened answer and the fact that the note never
	 * leaves the database in an e-mail all live on the server (backend/consent/rules.py);
	 * this file's job is to ask the questions in the order a person can answer them. */
	import { ApiError } from '$lib/api';
	import { requestClaim, requestManageLink, WISHES, type Wish } from '$lib/consent';
	import type { ImageConsent } from '$lib/types';

	let { slug, personName, consent }: { slug: string; personName: string; consent: ImageConsent } =
		$props();

	const claimed = $derived(consent === 'granted' || consent === 'refused');

	let open = $state(false);
	let email = $state('');
	// Nothing is pre-selected, and that is a legal point rather than a style one: RODO
	// motyw 32 says a pre-ticked box is not consent. The person picks, or nothing is sent.
	let wish = $state<Wish | ''>('');
	let note = $state('');
	let agree = $state(false);
	let website = $state(''); // honeypot: empty from every human
	let busy = $state(false);
	let error = $state('');
	let sent = $state(false);

	let manageEmail = $state('');
	let manageBusy = $state(false);
	let manageError = $state('');
	let manageSent = $state(false);

	async function submit(e: Event) {
		e.preventDefault();
		if (busy || !wish) return;
		busy = true;
		error = '';
		try {
			await requestClaim(slug, { email, wish, note, agree: true, website });
			sent = true;
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Nie udało się wysłać. Spróbuj za chwilę.';
		} finally {
			busy = false;
		}
	}

	async function sendManage(e: Event) {
		e.preventDefault();
		if (manageBusy) return;
		manageBusy = true;
		manageError = '';
		try {
			await requestManageLink(slug, manageEmail);
			manageSent = true;
		} catch (err) {
			manageError = err instanceof ApiError ? err.message : 'Nie udało się wysłać. Spróbuj za chwilę.';
		} finally {
			manageBusy = false;
		}
	}
</script>

<div class="box claim">
	<h2 class="box__title">
		Jesteś tą osobą?
		<small>{claimed ? 'strona podpisana przez osobę' : 'bez konta, wystarczy skrzynka'}</small>
	</h2>
	<div class="box__body">
		{#if claimed}
			<p>
				Tę stronę potwierdziła osoba, której dotyczy — {consent === 'granted'
					? 'zgodziła się na publikację swojego wizerunku'
					: 'poprosiła, żeby nie było tu jej zdjęć'}. Jeśli to Ty, możesz swój wybór zmienić albo
				cofnąć w każdej chwili: wyślemy link do ustawień na ten sam adres, z którego go potwierdzałaś
				lub potwierdzałeś.
			</p>
		{:else if !open}
			<p>
				Jeśli ta strona jest o Tobie — tak, o {personName} — to Ty decydujesz, co się z nią dzieje.
				Konto nie jest potrzebne; wystarczy skrzynka, do której masz dostęp. Wizerunek jest Twój
				(art. 81 ust. 1 pr. aut.), nie nasz i nie autora wpisu.
			</p>
			<button type="button" class="btn" onclick={() => (open = true)} aria-expanded={open}>
				To ja →
			</button>
			<p class="help">
				Co dokładnie zmienia każdy z wyborów: <a href="/ludzie/zgoda">odznaka „zgoda na wizerunek”</a>.
			</p>
		{/if}

		{#if open && !claimed}
			{#if sent}
				<div class="ok">Sprawdź pocztę — link działa 24 godziny.</div>
				<p class="help">
					Nic się nie stanie, dopóki go nie klikniesz. Jeśli wiadomość nie przyszła, zajrzyj do spamu
					— wysyłamy ją z adresu no-reply@fuw.lol.
				</p>
			{:else}
				<form onsubmit={submit}>
					<label for="claim-email">Twój adres e-mail</label>
					<input
						id="claim-email"
						type="email"
						bind:value={email}
						autocomplete="email"
						placeholder="imie.nazwisko@fuw.edu.pl"
						required
					/>
					<p class="help">
						Wyślemy na niego link potwierdzający. Nie pokazujemy adresu na stronie — widzi go tylko
						administracja, która sprawdza wniosek. Adres w domenie Wydziału albo uczelni przyspiesza
						sprawę: prośby o ukrycie z takiego adresu działają od razu.
					</p>

					<fieldset class="wishes">
						<legend>Czego chcesz?</legend>
						{#each WISHES as w (w.value)}
							<div class="wish">
								<input
									type="radio"
									id="wish-{w.value}"
									name="wish"
									value={w.value}
									bind:group={wish}
								/>
								<label for="wish-{w.value}">
									<span class="wish__label">{w.label}</span>
									<span class="wish__hint">{w.hint}</span>
								</label>
							</div>
						{/each}
					</fieldset>

					<label for="claim-note">Wiadomość do moderatora <span class="muted">(nieobowiązkowa)</span></label>
					<textarea id="claim-note" rows="3" maxlength="1000" bind:value={note}></textarea>
					<p class="help">
						Trafia wyłącznie do administracji archiwum. Nie wysyłamy jej nikomu mailem — nawet Tobie,
						bo formularz, który wysyła cudzy tekst na dowolny adres, jest spamownią z herbem.
					</p>

					<!-- Honeypot: no human sees this, scripts fill in everything. -->
					<div class="visually-hidden" aria-hidden="true">
						<label for="claim-website">Strona www</label>
						<input
							id="claim-website"
							type="text"
							name="website"
							bind:value={website}
							autocomplete="off"
							tabindex="-1"
						/>
					</div>

					<p class="agree">
						<input id="claim-agree" type="checkbox" bind:checked={agree} required />
						<label for="claim-agree">
							Rozumiem, że odznaka i wybór będą widoczne publicznie, a zgodę mogę w każdej chwili
							cofnąć.
						</label>
					</p>

					{#if error}<div class="error">{error}</div>{/if}
					<button type="submit" class="btn" disabled={busy || !agree || !wish}>
						{busy ? 'Wysyłam…' : 'Wyślij link potwierdzający'}
					</button>
					<button type="button" class="btn btn--ghost" onclick={() => (open = false)}>Nie, pomyłka</button>
					<p class="help">
						Chodzi Ci o jeden konkretny wpis, a nie o całą stronę? Szybsza jest ścieżka „Zgłoś /
						poproś o usunięcie” pod tym wpisem — działa też anonimowo. Szczegóły:
						<a href="/ludzie/zgoda">odznaka „zgoda na wizerunek”</a>.
					</p>
				</form>
			{/if}
		{/if}

		<div class="manage">
			{#if manageSent}
				<div class="ok">Sprawdź pocztę — link działa 24 godziny.</div>
			{:else}
				<form onsubmit={sendManage}>
					<p class="small muted">
						{claimed
							? 'Twój adres — ten, którym potwierdzałaś lub potwierdzałeś wpis:'
							: 'Masz już potwierdzony wpis? Wyślij sobie link do ustawień:'}
					</p>
					<div class="row">
						<input
							id="manage-email"
							type="email"
							bind:value={manageEmail}
							autocomplete="email"
							placeholder="twój adres"
							aria-label="Adres e-mail, na który mamy wysłać link do ustawień"
							required
						/>
						<button type="submit" class="btn btn--ghost btn--sm" disabled={manageBusy}>
							{manageBusy ? 'Wysyłam…' : 'Wyślij link do ustawień'}
						</button>
					</div>
					{#if manageError}<div class="error">{manageError}</div>{/if}
				</form>
			{/if}
			{#if claimed}
				<p class="help">
					To nie Ty, a strona jest podpisana? Napisz na
					<a href="mailto:admin@fuw.lol">admin@fuw.lol</a> — taki przypadek rozstrzyga człowiek, nie
					formularz.
				</p>
			{/if}
		</div>
	</div>
</div>

<style>
	.claim .box__body {
		font-size: 12px;
	}
	.wishes {
		border: 1px solid var(--line);
		margin: 10px 0 0;
		padding: 6px 10px 10px;
	}
	.wishes legend {
		font-size: 12px;
		color: #333;
		padding: 0 4px;
	}
	.wish {
		display: flex;
		gap: 6px;
		align-items: flex-start;
		margin: 6px 0 0;
	}
	.wish input {
		width: auto;
		margin: 2px 0 0;
		flex: 0 0 auto;
	}
	.wish label {
		margin: 0;
		cursor: pointer;
	}
	.wish__label {
		display: block;
		font-size: 13px;
		color: #222;
	}
	.wish__hint {
		display: block;
		color: var(--muted);
		font-size: 11px;
	}
	.agree {
		display: flex;
		gap: 6px;
		align-items: flex-start;
		margin: 10px 0;
	}
	.agree input {
		width: auto;
		margin: 2px 0 0;
		flex: 0 0 auto;
	}
	.agree label {
		margin: 0;
	}
	.manage {
		border-top: 1px solid #e6e6e6;
		margin: 12px 0 0;
		padding: 8px 0 0;
	}
	.manage .row > input {
		flex: 2 1 200px;
	}
	.manage .row > button {
		flex: 0 0 auto;
	}
</style>
