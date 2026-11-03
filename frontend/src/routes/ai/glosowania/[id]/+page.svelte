<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { api, ApiError } from '$lib/api';
	import { kolo, kp, when, PHASE_LABEL, type Poll } from '$lib/kolo.svelte';
	import { dialog } from '$lib/dialog.svelte';

	interface Comment { id: number; name: string; body: string; created_at: string }

	const id = $derived(page.params.id);
	let poll = $state<Poll | null>(null);
	let comments = $state<Comment[]>([]);
	let choice = $state<number | null>(null);
	let note = $state('');
	let error = $state<string | null>(null);
	let info = $state<string | null>(null);
	let protocol = $state<string | null>(null);

	async function load() {
		try {
			poll = await api.get<Poll>(`/kolo/polls/${id}/`);
			comments = await api.get<Comment[]>(`/kolo/polls/${id}/comments/`);
			document.title = `${poll.title} — Koło AI`;
		} catch (e) { error = e instanceof ApiError ? e.message : String(e); }
	}
	onMount(load);

	function fail(e: unknown) { error = e instanceof ApiError ? e.message : String(e); }

	async function vote() {
		if (choice === null || !poll) return;
		const ok = await dialog.ask({
			title: 'Oddać głos?',
			text: `Twój głos: „${poll.options[choice]}”. Głosu nie można zmienić.` +
				(poll.mode === 'tajne' ? ' Głosowanie tajne: system zapisze tylko, że głosowałeś, nie jak.' : ''),
			confirm: 'Głosuję'
		});
		if (ok === null) return;
		error = null;
		try { poll = await api.post<Poll>(`/kolo/polls/${id}/vote/`, { option: choice }); info = 'Głos oddany.'; }
		catch (e) { fail(e); }
	}

	async function object() {
		const ok = await dialog.ask({
			title: 'Żądanie rozpatrzenia na zebraniu',
			text: 'Jeśli co najmniej 1/5 członków tego zażąda przed rozpoczęciem głosowania, sprawa trafi na zebranie (§ 10a ust. 7).',
			confirm: 'Żądam'
		});
		if (ok === null) return;
		try { poll = await api.post<Poll>(`/kolo/polls/${id}/object/`); } catch (e) { fail(e); }
	}

	async function comment(e: Event) {
		e.preventDefault();
		try {
			const c = await api.post<Comment>(`/kolo/polls/${id}/comments/`, { body: note });
			comments = [...comments, c]; note = '';
		} catch (err) { fail(err); }
	}

	async function hide(c: Comment) {
		try { await api.post(`/kolo/comments/${c.id}/hide/`); comments = comments.filter((x) => x.id !== c.id); }
		catch (e) { fail(e); }
	}

	async function manage(action: 'announce' | 'cancel') {
		const ok = await dialog.ask({
			title: action === 'announce' ? 'Zawiadomić członków?' : 'Odwołać głosowanie?',
			text: action === 'announce'
				? 'Wszyscy uprawnieni dostaną maila z projektem uchwały i terminem. Potem projektu nie można już zmienić.'
				: 'Głosowanie zostanie odwołane przed rozpoczęciem.',
			confirm: action === 'announce' ? 'Zawiadom' : 'Odwołaj'
		});
		if (ok === null) return;
		try {
			const r = await api.post<Poll & { mail_failed?: number }>(`/kolo/polls/${id}/${action}/`);
			poll = r;
			if (r.mail_failed) info = `Nie doszło ${r.mail_failed} maili — roześlij zawiadomienie ręcznie.`;
		} catch (e) { fail(e); }
	}

	async function loadProtocol() {
		try { protocol = (await api.get<{ markdown: string }>(`/kolo/polls/${id}/protocol/`)).markdown; } catch (e) { fail(e); }
	}
</script>

<p class="small"><a href={kp('/glosowania')}>← Głosowania</a></p>
{#if error}<div class="error">{error}</div>{/if}
{#if info}<div class="ok">{info}</div>{/if}

{#if poll}
	<h1>{poll.title}</h1>
	<p class="muted">
		{poll.organ_label} · {poll.kind === 'wybory' ? 'wybory' : 'uchwała'} · głosowanie {poll.mode} · {poll.majority_label}<br />
		{when(poll.opens_at)} – {when(poll.closes_at)} · <strong>{PHASE_LABEL[poll.phase]}</strong>
		{#if poll.trial}<br /><strong>Próba — bez skutków prawnych.</strong>{/if}
	</p>

	<div class="card pre">{poll.body}</div>

	{#if poll.phase === 'open'}
		<h2>Głos</h2>
		{#if poll.has_voted}
			<div class="ok">Głos oddany{poll.my_vote !== null && poll.my_vote !== undefined ? `: „${poll.options[poll.my_vote]}”` : ''}. Wyniki po zakończeniu głosowania.</div>
		{:else if poll.can_vote}
			<div class="card">
				{#each poll.options as o, i (i)}
					<label class="opt"><input type="radio" name="opt" value={i} bind:group={choice} /> {o}</label>
				{/each}
				<button class="btn" disabled={choice === null} onclick={vote}>Oddaj głos</button>
			</div>
		{:else}
			<p class="muted">Nie jesteś uprawniony do głosowania w tej sprawie (uprawnieni są członkowie wpisani do ewidencji w chwili rozpoczęcia, § 10a ust. 2).</p>
		{/if}
	{:else if poll.phase === 'announced'}
		<p>Głosowanie rozpocznie się {when(poll.opens_at)}. Do tego czasu trwają obrady.</p>
		{#if kolo.isVoter}
			<p class="small">
				Żądania rozpatrzenia na zebraniu: {poll.objections}.
				{#if poll.objected}Twoje żądanie jest zapisane.{:else}<button class="btn btn--ghost btn--sm" onclick={object}>Żądam rozpatrzenia na zebraniu</button>{/if}
			</p>
		{/if}
	{/if}

	{#if poll.result}
		<h2>Wynik</h2>
		<div class="card card--accent">
			<table class="kt">
				<tbody>
					{#each poll.options as o, i (i)}<tr><td>{o}</td><td><strong>{poll.result.counts[i]}</strong></td></tr>{/each}
				</tbody>
			</table>
			<p>Uprawnionych {poll.result.eligible}, głosowało {poll.result.voters} — kworum {poll.result.quorum ? 'jest' : 'nie ma'}.</p>
			<p><strong>{poll.result.note}</strong></p>
		</div>
		{#if poll.named_votes}
			<h2>Głosy imienne</h2>
			<table class="kt"><tbody>
				{#each poll.named_votes as v (v.name)}<tr><td>{v.name}</td><td>{poll.options[v.option]}</td></tr>{/each}
			</tbody></table>
		{/if}
	{/if}

	<h2>Obrady</h2>
	{#each comments as c (c.id)}
		<div class="status-item">
			<time>{c.name}, {when(c.created_at)}</time>
			<div class="pre">{c.body}</div>
			{#if kolo.isManager}<button class="btn btn--ghost btn--sm" onclick={() => hide(c)}>ukryj</button>{/if}
		</div>
	{:else}
		<p class="muted">Nikt jeszcze nie zabrał głosu.</p>
	{/each}
	{#if poll.phase === 'announced' || poll.phase === 'open'}
		<form onsubmit={comment}>
			<label for="note">Twój głos w dyskusji</label>
			<textarea id="note" rows="3" maxlength="4000" bind:value={note} required></textarea>
			<button class="btn btn--ghost" type="submit">Dodaj</button>
		</form>
	{/if}

	{#if kolo.isManager}
		<h2>Zarządzanie</h2>
		<p>
			{#if poll.phase === 'draft'}<button class="btn" onclick={() => manage('announce')}>Zawiadom członków</button>{/if}
			{#if poll.phase === 'draft' || poll.phase === 'announced'}<button class="btn btn--ghost" onclick={() => manage('cancel')}>Odwołaj</button>{/if}
			{#if poll.phase === 'closed'}<button class="btn btn--ghost" onclick={loadProtocol}>Protokół (§ 10a ust. 8)</button>{/if}
		</p>
		{#if protocol}<textarea rows="16" readonly>{protocol}</textarea>{/if}
	{/if}
{:else if !error}
	<p class="muted">Ładuję…</p>
{/if}

<style>
	.opt { font-weight: normal; display: flex; gap: 8px; align-items: center; margin: 6px 0; }
	textarea[readonly] { font-family: ui-monospace, monospace; font-size: 12px; }
</style>
