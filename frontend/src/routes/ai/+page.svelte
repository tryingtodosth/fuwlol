<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api';
	import { kolo, kp, when, CONSENT_VERSION, FOUNDER_CONSENT_VERSION, type Founder, type StatusEntry } from '$lib/kolo.svelte';

	let statuses = $state<StatusEntry[]>([]);
	let members = $state<number | null>(null);
	let notice = $state('');

	// the list: name, address, declaration, consent
	let name = $state('');
	let email = $state('');
	let affiliation = $state<'student' | 'doktorant' | 'inny'>('student');
	let consent = $state(false);
	let joined = $state<string | null>(null);
	let joinError = $state<string | null>(null);
	let busy = $state(false);


	// founder data for the printed BOK list (only once logged in)
	let founder = $state<Founder | null>(null);
	let fConsent = $state(false);
	let fSaved = $state<string | null>(null);
	let fError = $state<string | null>(null);
	$effect(() => {
		if (kolo.me && founder === null) {
			api.get<Founder>('/kolo/me/founder/').then((f) => { founder = f; fConsent = !!f.nr_albumu; }).catch(() => {});
		}
	});
	async function saveFounder(e: Event) {
		e.preventDefault();
		if (!founder) return;
		fError = null; fSaved = null;
		try {
			const { phone, kierunek, etap, nr_albumu } = founder;
			founder = { ...(await api.put<Founder>('/kolo/me/founder/', {
				phone, kierunek, etap, nr_albumu, agreed_text_version: fConsent ? FOUNDER_CONSENT_VERSION : ''
			})), problem: null };
			fSaved = 'Zapisano. Dane trafią na wydruk listy założycieli — podpiszesz ją na zebraniu.';
		} catch (err) { fError = err instanceof ApiError ? err.message : String(err); }
	}

	onMount(() => {
		document.title = 'Koło AI — Wydział Fizyki UW';
		api.get<StatusEntry[]>('/kolo/status/').then((s) => (statuses = s)).catch(() => {});
		api.get<{ members: number; texts: { founders_notice: string } }>('/kolo/info/')
			.then((i) => { members = i.members; notice = i.texts.founders_notice; }).catch(() => {});
	});

	async function join(e: Event) {
		e.preventDefault();
		busy = true; joinError = null; joined = null;
		try {
			const r = await api.post<{ detail: string }>('/kolo/join/', {
				email, name, affiliation, agreed_text_version: consent ? CONSENT_VERSION : ''
			});
			joined = r.detail;
		} catch (err) { joinError = err instanceof ApiError ? err.message : String(err); }
		busy = false;
	}

</script>

<h1>Koło AI</h1>
<p>
	Studencka organizacja przy Wydziale Fizyki UW dla osób, które chcą sztuczną inteligencję <strong>rozumieć,
	budować i badać</strong>: od sieci neuronowych do analizy danych z eksperymentów, przez otwarte modele, po
	pytanie, dlaczego tyle osób AI nie ufa.
</p>

{#if kolo.me}
	<div class="card card--accent">
		<strong>{kolo.me.name}</strong> — {kolo.me.status_label}{kolo.me.status === 'member' ? (kolo.me.role === 'czlonek' ? ', z prawem głosu' : ', sympatyk') : ''}.
		{#if kolo.me.status === 'pending_approval'}
			<p>Oczekujesz na zatwierdzenie. Zarząd wpisuje do ewidencji członków studentów i doktorantów UW (§ 5 regulaminu); dostaniesz maila.</p>
		{:else if kolo.isVoter}
			<p><a href={kp('/glosowania')}>Głosowania i obrady →</a></p>
		{/if}
	</div>
{/if}

{#if kolo.me && founder}
	<h2 id="zalozyciel">Dane do listy założycieli</h2>
	<div class="card">
		{#if founder.problem}
			<p class="muted">{founder.problem}</p>
		{:else}
			{#if notice}<div class="notice pre">{notice}</div>{/if}
			<p class="small">Lista założycieli jest załącznikiem do Powiadomienia Rektora UW o powstaniu Koła (zarządzenie nr 170).
				Imię, nazwisko i adres UW już mamy: <strong>{founder.name}</strong>, {founder.email}. Uzupełnij resztę — na zebraniu tylko podpiszesz wydruk.</p>
			<form onsubmit={saveFounder}>
				<div class="grid2">
					<div><label for="f-phone">Numer telefonu</label><input id="f-phone" type="text" inputmode="tel" bind:value={founder.phone} required /></div>
					<div><label for="f-album">Numer albumu</label><input id="f-album" type="text" inputmode="numeric" bind:value={founder.nr_albumu} required /></div>
					<div><label for="f-kier">Kierunek albo szkoła doktorska</label><input id="f-kier" type="text" bind:value={founder.kierunek} required maxlength="120" placeholder="Fizyka" /></div>
					<div><label for="f-etap">Rok studiów albo etap kształcenia</label><input id="f-etap" type="text" bind:value={founder.etap} required maxlength="40" placeholder="2. rok I stopnia" /></div>
				</div>
				<label class="consent">
					<input type="checkbox" bind:checked={fConsent} required />
					<span>Jestem założycielem Koła AI i zgadzam się na umieszczenie powyższych danych na liście założycieli, która z
						Powiadomieniem trafia do Rektora UW (Biuro ds. Obsługi Kształcenia). Do tego czasu dane widzą tylko osoby prowadzące listę założycieli; po rejestracji usuwamy je z serwisu (zostają na papierowej liście). Administrator: Piotr Putyło,
						<a href="mailto:admin@fuw.lol">admin@fuw.lol</a>.</span>
				</label>
				<button type="submit" class="btn" disabled={!fConsent}>Zapisz dane założyciela</button>
			</form>
			{#if fSaved}<div class="ok">{fSaved}</div>{/if}
			{#if fError}<div class="error">{fError}</div>{/if}
		{/if}
	</div>
{/if}

<h2>Co robimy</h2>
<ul>
	<li><strong>AI w edukacji</strong> — narzędzia i sposoby uczenia (się) z AI, także na naszym Wydziale.</li>
	<li><strong>AI w badaniach naukowych</strong> — projekty dla grup badawczych: analiza obrazów i danych z eksperymentów, otwarte modele.</li>
	<li><strong>Badania nad AI i postawami wobec AI</strong> — w tym poważne potraktowanie sceptyków i przeciwników.</li>
</ul>
<p class="muted">Spotkania, warsztaty, wystąpienia gości, wspólne projekty i — w miarę możliwości — dostęp do mocy obliczeniowej.
	Każda inicjatywa Koła trafia do jawnego dla członków rejestru i kończy się raportem.</p>

<h2>Status</h2>
{#if statuses.length}
	{#each statuses as s (s.id)}
		<div class="status-item">
			<time>{when(s.published_at)}</time>
			<div><strong>{s.title}</strong></div>
			{#if s.body}<div class="pre">{s.body}</div>{/if}
		</div>
	{/each}
{:else}
	<p class="muted">Zebranie założycielskie: wtorek 3 listopada 2026, 11:00, sala 0.03, Pasteura 5. Kolejne wieści pojawią się tutaj.</p>
{/if}

{#if !kolo.me}
	<h2 id="lista">Zapisz się na listę</h2>
	<div class="card">
		<p>Wpis na listę to deklaracja członkowska (§ 5 ust. 4 regulaminu). Członkiem z prawem głosu może być
			<strong>student lub doktorant UW</strong>; pozostali są mile widziani jako <strong>sympatycy</strong> (§ 7).
			{#if members !== null && members > 0}W Kole jest już {members} {members === 1 ? 'członek' : 'członków'}.{/if}</p>
		{#if notice}<div class="notice pre">{notice}</div>{/if}
		{#if joined}
			<div class="ok"><strong>{joined}</strong></div>
		{:else}
			<form onsubmit={join}>
				<label for="j-name">Imię i nazwisko</label>
				<input id="j-name" type="text" bind:value={name} required minlength="3" maxlength="120" autocomplete="name" />
				<label for="j-email">Adres e-mail</label>
				<input id="j-email" type="email" bind:value={email} required placeholder="imie.nazwisko@student.uw.edu.pl" autocomplete="email" />
				<p class="help">Członkostwo wymaga adresu UW (np. @student.uw.edu.pl) — przez niego głosujesz zdalnie (§ 10a).</p>
				<label for="j-aff">Jestem</label>
				<select id="j-aff" bind:value={affiliation}>
					<option value="student">studentem / studentką UW</option>
					<option value="doktorant">doktorantem / doktorantką UW</option>
					<option value="inny">kimś innym — chcę być sympatykiem</option>
				</select>
				<label class="consent">
					<input type="checkbox" bind:checked={consent} required />
					<span>Zgadzam się na przetwarzanie mojego imienia, nazwiska i adresu e-mail w celu prowadzenia ewidencji członków
					i listy sympatyków Koła AI, wysyłania zawiadomień i przeprowadzania głosowań. Administrator: Piotr Putyło,
					<a href="mailto:admin@fuw.lol">admin@fuw.lol</a>. Mogę w każdej chwili zażądać wglądu, poprawienia lub usunięcia
					danych i wycofać zgodę, pisząc na ten adres; dane członków są przechowywane do ustania członkostwa, a dane
					zgłoszeń niepotwierdzonych w ciągu 30 dni — usuwane.</span>
				</label>
				<button type="submit" class="btn" disabled={busy || !consent}>{busy ? 'Wysyłam…' : 'Zapisz mnie na listę'}</button>
			</form>
		{/if}
		{#if joinError}<div class="error">{joinError}</div>{/if}
	</div>

	<p class="muted small">
		Już jesteś na liście?
		<a href={kp('/zaloguj')}>Zaloguj się linkiem z maila</a>
	</p>
{/if}

<h2>Jak działamy</h2>
<p>
	Najwyższą władzą jest <strong>Walne Zebranie</strong> członków; bieżącą działalnością kieruje <strong>Zarząd</strong>
	(Prezes, do trzech Wiceprezesów, Sekretarz, Skarbnik), a <strong>Komisja Rewizyjna</strong> kontroluje go po fakcie.
	Uchwały mogą zapadać <strong>zdalnie, tutaj</strong>: głosowanie trwa co najmniej 48 godzin, zawiadomienie wychodzi
	7 dni wcześniej, głosowanie tajne nie łączy głosu z osobą, a 1/5 członków może przenieść sprawę na zwykłe zebranie (§ 10a).
</p>

<style>
	/* .card label.consent outranks the layout's `.kolo label` (bold) */
	:global(.card) label.consent { font-weight: normal; font-size: 13px; display: flex; gap: 8px; align-items: flex-start; margin: 14px 0; }
	.consent input { margin-top: 3px; flex: none; }
	form .btn { margin-top: 8px; }
	.notice { border-left: 4px solid #c98f1e; background: #fff8e8; padding: 8px 12px; margin: 6px 0 10px; }
	.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 0 14px; }
	@media (max-width: 600px) { .grid2 { grid-template-columns: 1fr; } }
</style>
