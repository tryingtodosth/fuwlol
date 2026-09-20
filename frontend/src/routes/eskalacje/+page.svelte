<script lang="ts">
	/** Head-admin only (is_superuser): the escalations to NASK. What is reviewed here is the
	 * FROZEN evidence package, never the live content — the whole point of the package is
	 * that it outlives whatever happens to the post/comment/message afterwards. */
	import Breadcrumb from '$lib/components/Breadcrumb.svelte';
	import { api, ApiError, downloadBlob } from '$lib/api';
	import { auth } from '$lib/auth.svelte';
	import { dialog } from '$lib/dialog.svelte';
	import { fmtDate, type Escalation, type EscalationStatus } from '$lib/types';
	import PostBody from '$lib/components/PostBody.svelte';

	const TABS: { value: EscalationStatus; label: string }[] = [
		{ value: 'pending', label: 'Czekają na decyzję' },
		{ value: 'approved', label: 'Zatwierdzone (zgłoszone)' },
		{ value: 'declined', label: 'Odrzucone' }
	];
	const KIND: Record<Escalation['kind'], string> = { post: 'wpis', comment: 'komentarz', message: 'wiadomość na czacie' };

	let tab = $state<EscalationStatus>('pending');
	let rows = $state<Escalation[]>([]);
	let detail = $state<Record<number, Escalation>>({});
	let open = $state<Set<number>>(new Set());
	let loading = $state(true);
	let error = $state('');
	let busy = $state<number | null>(null);
	let loadedFor = '';

	$effect(() => {
		if (!auth.ready || !auth.isHeadAdmin) return;
		if (loadedFor === tab) return;
		loadedFor = tab;
		load();
	});

	async function load() {
		loading = true; error = '';
		try { rows = await api.get<Escalation[]>(`/moderation/escalations/?status=${tab}`); }
		catch (e) { error = e instanceof ApiError ? e.message : String(e); }
		finally { loading = false; }
	}

	async function toggle(id: number) {
		const s = new Set(open);
		if (s.has(id)) { s.delete(id); open = s; return; }
		s.add(id); open = s;
		if (!detail[id]) {
			try { detail = { ...detail, [id]: await api.get<Escalation>(`/moderation/escalations/${id}/`) }; }
			catch (e) { error = e instanceof ApiError ? e.message : String(e); }
		}
	}

	async function decide(e: Escalation, decision: 'approve' | 'decline') {
		const note = await dialog.ask(decision === 'approve' ? {
			title: 'Zatwierdź zgłoszenie do NASK', danger: true,
			text: 'Zatwierdzenie oznacza: pakiet dowodowy jest kompletny i Ty — osobiście — przekazujesz go przez formularz Dyżurnet.pl (dyzurnet.pl/zglos). Treść pozostaje niewidoczna dla wszystkich na stałe. Aplikacja NIE wysyła niczego sama.',
			confirm: 'Zatwierdź i zgłaszam do NASK', reason: 'optional', placeholder: 'np. numer zgłoszenia z Dyżurnet.pl, uwagi'
		} : {
			title: 'Odrzuć zgłoszenie',
			text: 'To nie jest sprawa dla NASK. Treść wraca pod zwykłą moderację (ukrycie / opcja nuklearna / przywrócenie działają znowu) i znowu widzą ją ci, którzy widzieli ją przedtem.',
			confirm: 'Odrzuć', reason: 'optional', placeholder: 'dlaczego — trafia do rejestru'
		});
		if (note === null) return;
		busy = e.id; error = '';
		try {
			await api.post(`/moderation/escalations/${e.id}/decide/`, { decision, note });
			rows = rows.filter((x) => x.id !== e.id);
		} catch (err) { error = err instanceof ApiError ? err.message : String(err); }
		busy = null;
	}

	async function download(e: Escalation, name: string) {
		try {
			const blob = await downloadBlob(`/moderation/escalations/${e.id}/evidence/${encodeURIComponent(name)}`);
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url; a.download = name; a.click();
			setTimeout(() => URL.revokeObjectURL(url), 5000);
		} catch (err) { error = err instanceof ApiError ? err.message : String(err); }
	}

	function who(m: Escalation['evidence']) {
		const u = m?.submitted_by ?? m?.author;
		if (!u) return m?.nick ? `${m.nick} (gość)` : '—';
		return `${u.username} · ${u.email} · konto od ${fmtDate(u.date_joined)}`;
	}
</script>

<svelte:head><title>Zgłoszenia do NASK — fuw.lol</title></svelte:head>

<Breadcrumb trail={[{ label: 'Zgłoszenia do NASK' }]} />


{#if !auth.ready}
	<div class="box"><div class="box__body"><p class="muted">Chwileczkę…</p></div></div>
{:else if !auth.isHeadAdmin}
	<div class="box">
		<h1 class="box__title">Zgłoszenia do NASK</h1>
		<div class="box__body"><p>Tylko dla head-admina (konto z uprawnieniem superużytkownika). Moderatorzy i zaufani nie widzą tej strony — to celowe: treść zgłoszona do NASK nie jest widoczna dla nikogo poza jedną osobą.</p></div>
	</div>
{:else}
	<h1>Zgłoszenia do NASK (Dyżurnet.pl)</h1>
	<div class="box box--grey">
		<div class="box__body small">
			<p>Zaufany użytkownik lub moderator zgłasza treść nielegalną. Od tej chwili widzisz ją tylko Ty; kopia (treść, autor, pliki) jest zamrożona jako pakiet dowodowy z sumą SHA-256. <strong>Zatwierdzenie</strong> = pakiet jest kompletny, przekazujesz go ręcznie przez <a href="https://dyzurnet.pl/zglos" rel="noopener nofollow" target="_blank">dyzurnet.pl/zglos</a>; treść zostaje niewidoczna na stałe. <strong>Odrzucenie</strong> = to nie sprawa dla NASK, treść wraca pod zwykłą moderację. Każda decyzja trafia do rejestru (baza + dziennik serwera).</p>
			<div class="tabs" role="tablist">
				{#each TABS as t (t.value)}
					<button type="button" role="tab" aria-selected={tab === t.value} class="btn btn--sm" class:btn--ghost={tab !== t.value} onclick={() => (tab = t.value)}>{t.label}</button>
				{/each}
			</div>
		</div>
	</div>
	{#if error}<div class="error">{error}</div>{/if}
	<div class="box">
		<h2 class="box__title">{TABS.find((t) => t.value === tab)?.label} <small>{loading ? 'wczytuję…' : `${rows.length} pozycji`}</small></h2>
		{#if loading}
			<div class="box__body"><p class="muted">Wczytuję…</p></div>
		{:else if rows.length === 0}
			<div class="box__body"><p class="muted">{tab === 'pending' ? 'Nic nie czeka. Dobrze.' : 'Pusto.'}</p></div>
		{:else}
			{#each rows as e (e.id)}
				<div class="item">
					<h3 class="item__title">
						#{e.id} — {KIND[e.kind]} nr {e.object_id}
						<span class="pill" class:pill--amber={e.status === 'pending'} class:pill--green={e.status === 'approved'} class:pill--grey={e.status === 'declined'}>
							{e.status === 'pending' ? 'czeka' : e.status === 'approved' ? 'zgłoszone do NASK' : 'odrzucone'}
						</span>
					</h3>
					<p class="small muted">zgłosił/a <strong>{e.requested_by ?? '—'}</strong> {fmtDate(e.created_at)}
						{#if e.decided_by} · decyzja: <strong>{e.decided_by}</strong> {fmtDate(e.decided_at)}{#if e.decision_note} — {e.decision_note}{/if}{/if}
					</p>
					<blockquote class="reason"><strong>Powód zgłoszenia:</strong> {e.reason}</blockquote>
					<p class="small mono muted">SHA-256 pakietu: {e.evidence_ref || '—'}</p>
					<p><button type="button" class="btn btn--sm btn--ghost" onclick={() => toggle(e.id)}>{open.has(e.id) ? 'Zwiń materiał dowodowy' : 'Pokaż materiał dowodowy'}</button></p>
					{#if open.has(e.id)}
						{@const m = detail[e.id]?.evidence}
						{#if !detail[e.id]}
							<p class="muted small">Wczytuję pakiet…</p>
						{:else if !m}
							<div class="error">Brak manifestu na dysku — pakiet nie został zachowany (sprawdź FUWLOL_EVIDENCE_ROOT i wolumen).</div>
						{:else}
							<div class="evidence">
								<table class="meta">
									<tbody>
										<tr><th>Zamrożono</th><td>{m.captured_at}</td></tr>
										<tr><th>Rodzaj</th><td>{m.kind} #{m.pk}{#if m.catalog_no} · {m.catalog_no}{/if}{#if m.post_id} · pod wpisem #{m.post_id}{/if}</td></tr>
										<tr><th>Autor</th><td>{who(m)}</td></tr>
										{#if m.ip_hash}<tr><th>Hash IP</th><td class="mono">{m.ip_hash}</td></tr>{/if}
										{#if m.title}<tr><th>Tytuł</th><td>{m.title}</td></tr>{/if}
										<tr><th>Pliki</th><td>
											{#if m.files.length === 0}brak{:else}
												{#each m.files as f (f.stored_as)}
													<div><button type="button" class="linky" onclick={() => download(e, f.stored_as)}>⬇ {f.name}</button> <span class="mono small muted">{f.sha256.slice(0, 16)}…</span></div>
												{/each}
											{/if}
										</td></tr>
									</tbody>
								</table>
								<div class="preview">
									<PostBody format={m.format ?? 'text'} body={m.body ?? ''} attachments={[]} />
								</div>
							</div>
						{/if}
					{/if}
					{#if e.status === 'pending'}
						<div class="acts">
							<button type="button" class="btn btn--warn" disabled={busy === e.id} onclick={() => decide(e, 'approve')}>Zatwierdź — zgłaszam do NASK</button>
							<button type="button" class="btn btn--ghost" disabled={busy === e.id} onclick={() => decide(e, 'decline')}>Odrzuć — to nie sprawa dla NASK</button>
						</div>
					{/if}
				</div>
			{/each}
		{/if}
	</div>
{/if}

<style>
	.tabs { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
	.reason { margin: 6px 0; }
	.evidence { border: 1px dashed var(--line); background: var(--box); padding: 8px 10px; margin: 6px 0; }
	.preview { background: #fff; border: 1px solid var(--line); padding: 8px; margin-top: 8px; max-height: 480px; overflow: auto; }
	.acts { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
	.linky { background: none; border: 0; padding: 0; color: var(--rust); cursor: pointer; font-family: inherit; font-size: 12px; }
	.linky:hover { background: none; text-decoration: underline; }
</style>
