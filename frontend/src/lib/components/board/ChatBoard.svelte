<script lang="ts">
	import { onMount } from 'svelte';
	import { api, API_BASE, ApiError } from '$lib/api';
	import { auth } from '$lib/auth.svelte';
	import MessageBody from './MessageBody.svelte';
	import { excerpt, stamp, MAX_LEN, REPORT_REASONS, type BoardMessage, type BoardPage } from './types';

	let messages = $state<BoardMessage[]>([]);
	let count = $state(0);
	let latestId = $state(0);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let sendError = $state<string | null>(null);
	let sending = $state(false);
	let exhausted = $state(false);
	let showHidden = $state(false);
	let expanded = $state<Set<number>>(new Set()); // messages shown in full, in place of their excerpt
	let reporting = $state<number | null>(null); // message whose report-reason picker is open
	let reportReason = $state('offensive');
	let reportError = $state<string | null>(null);

	let nick = $state('');
	let body = $state('');
	let format = $state<'text' | 'latex'>('text');
	let preview = $state(false);
	let website = $state(''); // honeypot

	const length = $derived(Array.from(body).length);
	const over = $derived(length > MAX_LEN);
	const canModerate = $derived(auth.isStaff || !!auth.user?.is_trusted);

	function q(extra: Record<string, string | number> = {}) {
		const u = new URLSearchParams();
		if (showHidden && canModerate) u.set('include_hidden', '1');
		for (const [k, v] of Object.entries(extra)) u.set(k, String(v));
		const s = u.toString();
		return s ? `?${s}` : '';
	}

	async function load() {
		loading = true; error = null;
		try {
			const p = await api.get<BoardPage>(`/board/${q()}`);
			messages = p.results; count = p.count; latestId = p.latest_id;
			exhausted = p.results.length >= p.count;
		} catch (e) { error = (e as Error).message; }
		loading = false;
	}

	async function older() {
		const oldest = messages[messages.length - 1];
		if (!oldest) return;
		try {
			const p = await api.get<BoardPage>(`/board/${q({ before: oldest.id })}`);
			messages = [...messages, ...p.results]; count = p.count;
			exhausted = p.results.length === 0 || messages.length >= p.count;
		} catch (e) { error = (e as Error).message; }
	}

	async function poll() {
		if (document.visibilityState !== 'visible') return;
		try {
			const p = await api.get<BoardPage>(`/board/${q({ since: latestId })}`);
			if (p.results.length) {
				const known = new Set(messages.map((m) => m.id));
				messages = [...p.results.filter((m) => !known.has(m.id)), ...messages];
			}
			count = p.count; latestId = Math.max(latestId, p.latest_id);
		} catch { /* a poll may fail quietly */ }
	}

	async function send(e: Event) {
		e.preventDefault();
		if (!body.trim() || over || sending) return;
		sending = true; sendError = null;
		try {
			const m = await api.post<BoardMessage>('/board/', { nick, body, format, website });
			messages = [m, ...messages]; count += 1; latestId = Math.max(latestId, m.id);
			body = ''; preview = false;
			try { localStorage.setItem('fuwlol.nick', nick); } catch { /* ignore */ }
		} catch (err) { sendError = err instanceof ApiError ? err.message : String(err); }
		sending = false;
	}

	async function toggleHide(m: BoardMessage) {
		try {
			const r = await api.post<BoardMessage>(`/board/${m.id}/${m.is_hidden ? 'restore' : 'hide'}/`);
			messages = messages.map((x) => (x.id === m.id ? r : x)).filter((x) => showHidden || !x.is_hidden);
		} catch (err) { error = (err as Error).message; }
	}

	async function sendReport(m: BoardMessage) {
		reportError = null;
		try {
			const r = await api.post<BoardMessage>(`/board/${m.id}/report/`, { reason: reportReason });
			messages = messages.map((x) => (x.id === m.id ? r : x));
			reporting = null;
		} catch (err) { reportError = err instanceof ApiError ? err.message : String(err); }
	}

	async function escalate(m: BoardMessage) {
		const reason = prompt('ZGŁOSZENIE DO NASK — treść nielegalna (np. materiały przedstawiające '
			+ 'wykorzystywanie dzieci). Od tej chwili wiadomość jest niewidoczna dla wszystkich oprócz '
			+ 'administracji najwyższego szczebla. Podaj powód (wymagany):') ?? '';
		if (!reason.trim()) return;
		try {
			await api.post(`/board/${m.id}/escalate/`, { reason });
			messages = messages.filter((x) => x.id !== m.id);
		} catch (err) { error = err instanceof ApiError ? err.message : String(err); }
	}

	onMount(() => {
		try { nick = localStorage.getItem('fuwlol.nick') || ''; } catch { /* ignore */ }
		load();
		const t = setInterval(poll, 30000);
		return () => clearInterval(t);
	});
</script>

<div class="box chat">
	<h2 class="box__title">Czat <small>stary dobry shoutbox — bez obrazków, z linkami i wzorami · Długie wiadomości zwijają się po 100 znakach</small></h2>
	<div class="box__body">
		<form class="composer" onsubmit={send}>
			{#if auth.isAuthenticated}
				<p class="small">Piszesz jako <strong>{auth.user?.username}</strong>. Nie musisz się logować, ale już jesteś. Bądź miły.</p>
			{:else}
				<p class="small">Nie musisz się logować. Bądź miły.</p>
				<label for="chat-nick">Nick</label>
				<input id="chat-nick" type="text" maxlength="30" bind:value={nick} placeholder="Anonim" />
			{/if}
			<div class="fmt" role="group" aria-label="Format wiadomości">
				<button type="button" class="btn btn--sm" class:is-active={format === 'text'} onclick={() => (format = 'text')}>Tekst</button>
				<button type="button" class="btn btn--sm" class:is-active={format === 'latex'} onclick={() => (format = 'latex')}>LaTeX</button>
				<button type="button" class="btn btn--sm btn--ghost" onclick={() => (preview = !preview)} aria-pressed={preview}>Podgląd</button>
			</div>
			<label for="chat-body" class="visually-hidden">Wiadomość</label>
			<textarea id="chat-body" rows="3" bind:value={body}
				placeholder={format === 'latex' ? 'Wzór: $E = mc^2$, \\textbf{pogrubienie}, \\begin{itemize}…' : 'Napisz coś. Linki i $wzory$ działają, obrazki nie.'}></textarea>
			<div class="visually-hidden" aria-hidden="true">
				<label for="chat-website">Strona www (nie wypełniaj)</label>
				<input id="chat-website" name="website" type="text" tabindex="-1" autocomplete="off" bind:value={website} />
			</div>
			<div class="composer__row">
				<span class="counter" class:over>{length} / {MAX_LEN}</span>
				<button type="submit" class="btn" disabled={over || !body.trim() || sending}>{sending ? 'Wysyłam…' : 'Wyślij'}</button>
				<button type="button" class="btn btn--ghost btn--sm" onclick={load}>Odśwież</button>
				{#if canModerate}
					<label class="inline"><input type="checkbox" bind:checked={showHidden} onchange={load} /> pokaż ukryte</label>
				{/if}
				<a class="small rss" href="{API_BASE}/board/rss/" target="_blank" rel="noopener">Kanał RSS</a>
			</div>
			{#if preview && body.trim()}
				<div class="preview"><MessageBody {body} {format} /></div>
			{/if}
			{#if sendError}<div class="error">{sendError}</div>{/if}
		</form>

		{#if loading}
			<p class="muted">Ładuję czat…</p>
		{:else if error}
			<div class="error">{error}</div>
		{:else if messages.length === 0}
			<p class="muted">Cisza. Napisz pierwszy.</p>
		{/if}
		<div class="list">
			{#each messages as m, i (m.id)}
				{@const ex = excerpt(m.body)}
				<div class="msg" class:alt={i % 2 === 1} class:hidden={m.is_hidden} id="m{m.id}">
					<span class="mono time">[{stamp(m.created_at)}]</span>
					<strong class="nick">{m.nick}</strong>{#if m.is_guest}<span class="muted small"> (gość)</span>{/if}
					{#if auth.user && m.author_id === auth.user.id}<span class="pill pill--amber">ty</span>{/if}
					{#if m.open_reports}<span class="pill pill--amber" title="otwarte zgłoszenia">⚑ {m.open_reports}</span>{/if}
					{#if m.can_hide}
						<button type="button" class="linky small" onclick={() => toggleHide(m)}>{m.is_hidden ? 'przywróć' : 'ukryj'}</button>
						<button type="button" class="linky small" onclick={() => escalate(m)}>zgłoś do NASK</button>
					{:else if !(auth.user && m.author_id === auth.user.id)}
						<button type="button" class="linky small" onclick={() => (reporting = reporting === m.id ? null : m.id)}>zgłoś</button>
					{/if}
					{#if reporting === m.id}
						<span class="report-picker">
							<select bind:value={reportReason} aria-label="Powód zgłoszenia">
								{#each REPORT_REASONS as r (r.value)}
									<option value={r.value}>{r.label}</option>
								{/each}
							</select>
							<button type="button" class="btn btn--sm" onclick={() => sendReport(m)}>Zgłoś</button>
							<button type="button" class="btn btn--sm btn--ghost" onclick={() => (reporting = null)}>Anuluj</button>
							{#if reportError}<span class="err">{reportError}</span>{/if}
						</span>
					{/if}
					<div class="text">
						{#if ex.rest && !expanded.has(m.id)}
							<MessageBody body={ex.head + '…'} format={m.format} />
							<button type="button" class="spoiler" onclick={() => (expanded = new Set([...expanded, m.id]))}>
								▸ pokaż całość ({Array.from(m.body).length} znaków)
							</button>
						{:else if ex.rest}
							<MessageBody body={m.body} format={m.format} />
							<button type="button" class="spoiler" onclick={() => { const s = new Set(expanded); s.delete(m.id); expanded = s; }}>▾ zwiń</button>
						{:else}
							<MessageBody body={m.body} format={m.format} />
						{/if}
					</div>
				</div>
			{/each}
		</div>
		{#if !loading && !exhausted}
			<p class="center"><button type="button" class="btn btn--ghost btn--sm" onclick={older}>Wczytaj starsze ({count - messages.length})</button></p>
		{/if}
	</div>
</div>

<style>
	.composer { border: 1px solid var(--line); background: var(--box); padding: 8px 10px; margin-bottom: 10px; }
	.composer textarea { margin-top: 4px; }
	.fmt { margin-top: 6px; display: flex; gap: 4px; }
	.composer__row { display: flex; gap: 8px; align-items: center; margin-top: 6px; flex-wrap: wrap; }
	.counter { font-family: monospace; font-size: 11px; color: var(--muted); }
	.counter.over { color: #b00020; font-weight: bold; }
	.inline { display: inline; margin: 0; font-size: 11px; }
	.rss { margin-left: auto; }
	.preview { border: 1px dashed var(--line); background: #fff; padding: 6px 8px; margin-top: 6px; }
	.list { border-top: 1px solid var(--line); }
	.msg { padding: 5px 8px; border-bottom: 1px solid #e6e6e6; }
	.msg.alt { background: var(--box); }
	.msg.hidden { opacity: .6; text-decoration: line-through; }
	.msg.hidden .text { text-decoration: none; }
	.time { color: var(--muted); font-size: 11px; margin-right: 6px; }
	.nick { color: #222; }
	.text { margin-top: 2px; }
	.spoiler { background: none; border: 0; padding: 0; cursor: pointer; color: var(--rust); font-size: 11px; }
	.spoiler:hover { background: none; text-decoration: underline; }
	.linky { background: none; border: 0; color: var(--rust); padding: 0 4px; cursor: pointer; }
	.linky:hover { text-decoration: underline; background: none; }
	.report-picker { display: inline-flex; gap: 4px; align-items: center; margin-left: 6px; }
	.report-picker .err { color: #b00020; font-size: 11px; }
</style>
