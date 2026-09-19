<script lang="ts">
	/** "Zaproponuj poprawkę" — and, for the post's author or staff, the queue of what
	 * other people have proposed.
	 *
	 * Both halves live in one component on purpose: they are the two ends of the same
	 * conversation, and the person deciding usually wants to see the current text right
	 * next to what somebody wants it to say.
	 *
	 * Only CHANGED fields are sent. The form starts as a copy of the post, so a suggester
	 * edits rather than retypes — but submitting the untouched copy would produce a diff
	 * of everything against itself, and the server would (rightly) refuse it as no change
	 * at all. */
	import { api, ApiError } from '$lib/api';
	import { auth } from '$lib/auth.svelte';

	let { post, canDecide = false, onChanged }: {
		post: Record<string, any>; canDecide?: boolean; onChanged: () => void;
	} = $props();

	const FIELDS = [
		{ key: 'title', label: 'Tytuł', kind: 'text' },
		{ key: 'body', label: 'Treść', kind: 'area' },
		{ key: 'year', label: 'Rok', kind: 'number' },
		{ key: 'date_note', label: 'Uwaga o dacie', kind: 'text' },
		{ key: 'source_note', label: 'Skąd to jest', kind: 'text' },
		{ key: 'source_url', label: 'Link do źródła', kind: 'text' }
	] as const;

	let open = $state(false);
	let draft = $state<Record<string, string>>({});
	let rationale = $state('');
	let busy = $state(false);
	let error = $state<string | null>(null);
	let ok = $state<string | null>(null);
	let list = $state<any[]>([]);
	let loaded = $state(false);

	function startEditing() {
		draft = Object.fromEntries(FIELDS.map((f) => [f.key, post[f.key] ?? '']));
		rationale = '';
		error = null;
		ok = null;
		open = true;
	}

	/** Only what the person actually touched. '' and null are the same absence here, so a
	 * field left empty in both the post and the form is not reported as a change. */
	function diff(): Record<string, unknown> {
		const out: Record<string, unknown> = {};
		for (const f of FIELDS) {
			const now = post[f.key] ?? '';
			let next: unknown = draft[f.key] ?? '';
			if (f.kind === 'number') next = String(next).trim() === '' ? null : Number(next);
			if (String(next ?? '') !== String(now ?? '')) out[f.key] = next;
		}
		return out;
	}

	async function submit() {
		const changes = diff();
		if (!Object.keys(changes).length) { error = 'Nie zmieniono niczego.'; return; }
		if (!rationale.trim()) { error = 'Napisz, dlaczego tak jest lepiej.'; return; }
		busy = true; error = null;
		try {
			await api.post(`/posts/${post.slug}/suggestions/`, { changes, rationale });
			open = false;
			ok = 'Dziękujemy — poprawka czeka na decyzję autora wpisu albo administracji.';
			await load();
		} catch (e) { error = e instanceof ApiError ? e.message : String(e); }
		busy = false;
	}

	async function load() {
		if (!auth.user) return;
		try {
			list = await api.get<any[]>(`/posts/${post.slug}/suggestions/`);
		} catch { list = []; }
		loaded = true;
	}

	async function decide(s: any, decision: 'accept' | 'reject') {
		busy = true; error = null;
		try {
			await api.post(`/suggestions/${s.id}/decide/`, { decision });
			await load();
			if (decision === 'accept') onChanged();
		} catch (e) { error = e instanceof ApiError ? e.message : String(e); }
		busy = false;
	}

	async function withdraw(s: any) {
		busy = true; error = null;
		try { await api.post(`/suggestions/${s.id}/withdraw/`, {}); await load(); }
		catch (e) { error = e instanceof ApiError ? e.message : String(e); }
		busy = false;
	}

	const label = (k: string) => FIELDS.find((f) => f.key === k)?.label ?? k;
	const pending = $derived(list.filter((s: any) => s.status === 'pending'));
	$effect(() => { if (auth.user && !loaded) load(); });
</script>

{#if auth.user}
	<section class="sug">
		<h3 class="sug__h">Poprawki</h3>

		{#if ok}<p class="ok small">{ok}</p>{/if}

		{#if !open}
			<button type="button" class="btn btn--sm" onclick={startEditing}>✏️ Zaproponuj poprawkę</button>
			<p class="small muted">
				Zauważyłeś błędny rok, przekręcone nazwisko albo literówkę? Zaproponuj zmianę —
				decyduje autor wpisu albo administracja, a poprzednia wersja zostaje w historii.
			</p>
		{:else}
			<div class="form">
				{#each FIELDS as f (f.key)}
					<label class="fld">
						<span class="small">{f.label}</span>
						{#if f.kind === 'area'}
							<textarea rows="6" bind:value={draft[f.key]}></textarea>
						{:else}
							<input type={f.kind === 'number' ? 'number' : 'text'} bind:value={draft[f.key]} />
						{/if}
					</label>
				{/each}
				<label class="fld">
					<span class="small">Dlaczego? <em>(wymagane)</em></span>
					<textarea rows="2" bind:value={rationale}
						placeholder="np. byłem na tym egzaminie, to był rok 2011"></textarea>
				</label>
				<div class="acts">
					<button type="button" class="btn btn--sm" disabled={busy} onclick={submit}>Wyślij poprawkę</button>
					<button type="button" class="btn btn--sm btn--ghost" disabled={busy} onclick={() => (open = false)}>Anuluj</button>
				</div>
			</div>
		{/if}

		{#if error}<p class="err small">{error}</p>{/if}

		{#if pending.length}
			<ul class="list">
				{#each pending as s (s.id)}
					<li class="item">
						<p class="small">
							<strong>{s.suggested_by ?? 'konto usunięte'}</strong> proponuje:
						</p>
						<ul class="diff small">
							{#each Object.entries(s.changes) as [k, v] (k)}
								<li>
									<span class="k">{label(k)}:</span>
									<del>{s.base?.[k] || '—'}</del> → <ins>{v || '—'}</ins>
								</li>
							{/each}
						</ul>
						<p class="small why">„{s.rationale}”</p>
						{#if canDecide}
							<div class="acts">
								<button type="button" class="btn btn--sm" disabled={busy} onclick={() => decide(s, 'accept')}>Przyjmij</button>
								<button type="button" class="btn btn--sm btn--ghost" disabled={busy} onclick={() => decide(s, 'reject')}>Odrzuć</button>
							</div>
						{:else if s.suggested_by === auth.user?.username}
							<button type="button" class="btn btn--sm btn--ghost" disabled={busy} onclick={() => withdraw(s)}>Wycofaj</button>
						{/if}
					</li>
				{/each}
			</ul>
		{/if}
	</section>
{/if}

<style>
	.sug { border-top: 1px solid var(--line); margin-top: 16px; padding-top: 12px; }
	.sug__h { font-size: 14px; margin: 0 0 6px; }
	.form { display: grid; gap: 8px; max-width: 620px; }
	.fld { display: grid; gap: 2px; }
	.fld input, .fld textarea { width: 100%; font: inherit; padding: 4px 6px; border: 1px solid var(--line); }
	.acts { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; }
	.list { list-style: none; padding: 0; margin: 10px 0 0; display: grid; gap: 10px; }
	.item { border: 1px solid var(--line); padding: 8px; background: var(--box); }
	.diff { list-style: none; padding: 0; margin: 4px 0; }
	.diff .k { color: var(--muted); }
	.diff del { color: #b00020; text-decoration: line-through; }
	.diff ins { color: #0a6b2f; text-decoration: none; }
	.why { font-style: italic; }
	.muted { color: var(--muted); }
	.err { color: #b00020; }
	.ok { color: #0a6b2f; }
</style>
