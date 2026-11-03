<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { api, ApiError } from '$lib/api';
	import { kolo, kp, when, AFFILIATION_LABEL, type KoloMember, type Poll, type StatusEntry } from '$lib/kolo.svelte';
	import { dialog } from '$lib/dialog.svelte';

	let members = $state<KoloMember[]>([]);
	let error = $state<string | null>(null);
	let info = $state<string | null>(null);
	const pending = $derived(members.filter((m) => m.status === 'pending_approval'));
	const register = $derived(members.filter((m) => m.status === 'member'));
	const other = $derived(members.filter((m) => !['pending_approval', 'member'].includes(m.status)));

	function fail(e: unknown) { error = e instanceof ApiError ? e.message : String(e); info = null; }
	async function load() {
		try { members = await api.get<KoloMember[]>('/kolo/members/'); } catch (e) { fail(e); }
	}
	$effect(() => { if (kolo.ready && !kolo.isManager) goto(kp()); });
	onMount(() => { document.title = 'Koło AI — Zarząd'; load(); });

	async function decide(m: KoloMember, decision: 'admit' | 'reject' | 'leave', role?: string) {
		const texts = {
			admit: [`Wpisać ${m.name} do ewidencji jako ${role === 'czlonek' ? 'członka z prawem głosu' : 'sympatyka'}?`, 'optional'],
			reject: [`Odmowa wpisu wymaga uchwały Zarządu z uzasadnieniem (§ 5 ust. 5). Wpisz uzasadnienie i numer uchwały.`, 'required'],
			leave: [`Ustanie członkostwa ${m.name} (§ 6) — podaj przyczynę.`, 'required']
		} as const;
		const reason = await dialog.ask({ title: m.name, text: texts[decision][0], reason: texts[decision][1], danger: decision !== 'admit' });
		if (reason === null) return;
		error = null;
		try { await api.post(`/kolo/members/${m.id}/decide/`, { decision, role, reason }); info = 'Zapisano.'; await load(); }
		catch (e) { fail(e); }
	}

	// invitation
	let iEmail = $state(''), iName = $state(''), iAff = $state<'student' | 'doktorant' | 'inny'>('student'), iRole = $state('czlonek');
	async function invite(e: Event) {
		e.preventDefault(); error = null;
		try {
			await api.post('/kolo/invite/', { email: iEmail, name: iName, affiliation: iAff, role: iRole });
			info = `Wysłano zaproszenie na ${iEmail}.`; iEmail = ''; iName = ''; await load();
		} catch (err) { fail(err); }
	}

	// a new vote (draft)
	let pTitle = $state(''), pBody = $state(''), pOrgan = $state('walne'), pKind = $state('uchwala'), pMode = $state('jawne');
	let pMajority = $state('zwykla'), pCands = $state(''), pOpens = $state(''), pCloses = $state(''), pTrial = $state(false);
	async function createPoll(e: Event) {
		e.preventDefault(); error = null;
		try {
			const p = await api.post<Poll>('/kolo/polls/', {
				title: pTitle, body: pBody, organ: pOrgan, kind: pKind, mode: pMode, majority: pMajority, trial: pTrial,
				candidates: pCands.split('\n').map((s) => s.trim()).filter(Boolean),
				opens_at: new Date(pOpens).toISOString(), closes_at: new Date(pCloses).toISOString()
			});
			goto(kp(`/glosowania/${p.id}`));
		} catch (err) { fail(err); }
	}

	// the founders' notice on the front page (rules.SETTINGS)
	let notice = $state('');
	onMount(() => { api.get<{ texts: { founders_notice: string } }>('/kolo/info/').then((i) => (notice = i.texts.founders_notice)).catch(() => {}); });
	async function saveNotice(e: Event) {
		e.preventDefault(); error = null;
		try { await api.put('/kolo/settings/founders_notice/', { value: notice }); info = 'Komunikat zapisany.'; }
		catch (err) { fail(err); }
	}

	// status
	let sTitle = $state(''), sBody = $state('');
	async function postStatus(e: Event) {
		e.preventDefault(); error = null;
		try { await api.post<StatusEntry>('/kolo/status/', { title: sTitle, body: sBody }); info = 'Opublikowano.'; sTitle = ''; sBody = ''; }
		catch (err) { fail(err); }
	}
</script>

<h1>Zarząd</h1>
{#if error}<div class="error">{error}</div>{/if}
{#if info}<div class="ok">{info}</div>{/if}

<p><a class="btn btn--ghost" href={kp('/zarzad/zalozyciele')}>Lista założycieli do druku →</a></p>

<h2>Komunikat przy liście założycieli</h2>
<form class="card" onsubmit={saveNotice}>
	<p class="small muted">Widać go na stronie głównej przy zapisie i przy danych założyciela (np. kiedy i gdzie podpisujemy listę).</p>
	<textarea rows="3" maxlength="1000" bind:value={notice} required></textarea>
	<button class="btn" type="submit">Zapisz komunikat</button>
</form>

<h2>Czekają na zatwierdzenie ({pending.length})</h2>
{#if pending.length}
	<table class="kt">
		<tbody>
			{#each pending as m (m.id)}
				<tr>
					<td><strong>{m.name}</strong><br /><span class="muted small">{m.email} · {AFFILIATION_LABEL[m.affiliation]} · zgłoszenie {when(m.created_at)}</span>
						{#if m.problem_czlonek}<br /><span class="small">Członek: nie — {m.problem_czlonek}</span>{/if}</td>
					<td class="actions">
						<button class="btn btn--sm" disabled={!!m.problem_czlonek} onclick={() => decide(m, 'admit', 'czlonek')}>członek</button>
						<button class="btn btn--ghost btn--sm" onclick={() => decide(m, 'admit', 'sympatyk')}>sympatyk</button>
						<button class="btn btn--ghost btn--sm" onclick={() => decide(m, 'reject')}>odmowa</button>
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
{:else}
	<p class="muted">Nikt nie czeka.</p>
{/if}

<h2>Zaproś</h2>
<form class="card" onsubmit={invite}>
	<p class="small muted">Zaproszenie to zatwierdzenie: kto otworzy link, zostaje wpisany do ewidencji z wybraną rolą.</p>
	<div class="grid2">
		<div><label for="i-name">Imię i nazwisko</label><input id="i-name" type="text" bind:value={iName} required /></div>
		<div><label for="i-email">E-mail</label><input id="i-email" type="email" bind:value={iEmail} required /></div>
		<div><label for="i-aff">Status</label>
			<select id="i-aff" bind:value={iAff}><option value="student">student UW</option><option value="doktorant">doktorant UW</option><option value="inny">inna osoba</option></select></div>
		<div><label for="i-role">Rola</label>
			<select id="i-role" bind:value={iRole}><option value="czlonek">członek (głos)</option><option value="sympatyk">sympatyk</option></select></div>
	</div>
	<button class="btn" type="submit">Wyślij zaproszenie</button>
</form>

<h2>Nowe głosowanie</h2>
<form class="card" onsubmit={createPoll}>
	<label for="p-title">W sprawie</label><input id="p-title" type="text" bind:value={pTitle} required maxlength="200" />
	<label for="p-body">Projekt uchwały</label><textarea id="p-body" rows="6" bind:value={pBody} required></textarea>
	<div class="grid2">
		<div><label for="p-organ">Organ</label><select id="p-organ" bind:value={pOrgan}><option value="walne">Walne Zebranie</option><option value="zarzad">Zarząd</option></select></div>
		<div><label for="p-kind">Rodzaj</label><select id="p-kind" bind:value={pKind}><option value="uchwala">uchwała (za/przeciw/wstrzymuję się)</option><option value="wybory">wybory</option></select></div>
		<div><label for="p-mode">Tryb</label><select id="p-mode" bind:value={pMode}><option value="jawne">jawne</option><option value="tajne">tajne</option></select></div>
		<div><label for="p-maj">Większość</label>
			<select id="p-maj" bind:value={pMajority} disabled={pKind === 'wybory'}>
				<option value="zwykla">zwykła (§ 10 ust. 5)</option><option value="bezwzgledna">bezwzględna</option>
				<option value="3/5">3/5 (zmiana opiekuna)</option><option value="2/3">2/3 (regulamin, odwołanie, rozwiązanie)</option>
			</select></div>
		<div><label for="p-open">Początek</label><input id="p-open" type="datetime-local" bind:value={pOpens} required /></div>
		<div><label for="p-close">Koniec (min. 48 h)</label><input id="p-close" type="datetime-local" bind:value={pCloses} required /></div>
	</div>
	{#if pKind === 'wybory'}
		<label for="p-cands">Kandydaci (po jednym w linii)</label><textarea id="p-cands" rows="3" bind:value={pCands}></textarea>
		<p class="small muted">Wybory: bezwzględna większość ważnie oddanych głosów (§ 12 ust. 4); przy jednym kandydacie dochodzi „przeciw”.</p>
	{/if}
	<label class="inline"><input type="checkbox" bind:checked={pTrial} /> Próba (bez skutków prawnych, bez terminu zawiadomienia)</label>
	<p class="small muted">Zawiadomienie musi wyjść 7 dni przed początkiem (Walne) albo 2 dni (Zarząd). Projekt zapisuje się bez wysyłki; zawiadamiasz z jego strony.</p>
	<button class="btn" type="submit">Zapisz projekt</button>
</form>

<h2>Status na stronie</h2>
<form class="card" onsubmit={postStatus}>
	<label for="s-title">Tytuł</label><input id="s-title" type="text" bind:value={sTitle} required maxlength="200" />
	<label for="s-body">Treść</label><textarea id="s-body" rows="3" bind:value={sBody}></textarea>
	<button class="btn" type="submit">Opublikuj</button>
</form>

<h2>Ewidencja członków ({register.length})</h2>
<table class="kt">
	<tbody>
		{#each register as m (m.id)}
			<tr>
				<td>{m.name}{m.funkcja ? ` — ${m.funkcja}` : ''}<br /><span class="muted small">{m.email} · {m.role === 'czlonek' ? 'członek' : 'sympatyk'} · {AFFILIATION_LABEL[m.affiliation]} · od {when(m.approved_at)}</span></td>
				<td class="actions"><button class="btn btn--ghost btn--sm" onclick={() => decide(m, 'leave')}>ustanie członkostwa</button></td>
			</tr>
		{/each}
	</tbody>
</table>
{#if other.length}
	<h2>Pozostałe</h2>
	<table class="kt"><tbody>
		{#each other as m (m.id)}<tr><td>{m.name} <span class="muted small">{m.email}</span></td><td>{m.status_label}</td></tr>{/each}
	</tbody></table>
{/if}

<style>
	.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 0 14px; }
	@media (max-width: 600px) { .grid2 { grid-template-columns: 1fr; } }
	.actions { white-space: nowrap; text-align: right; }
	.inline { font-weight: normal; display: flex; gap: 8px; align-items: center; }
	form .btn { margin-top: 10px; }
</style>
