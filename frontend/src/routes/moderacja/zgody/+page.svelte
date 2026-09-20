<script lang="ts">
	/** The staff queue for „Jesteś tą osobą?”.
	 *
	 * Staff (`is_staff`), not the trusted tier — and the server enforces it, this page only
	 * draws it. A confirmed fuw.edu.pl address says somebody is around the Faculty; it does
	 * not qualify them to decide whether a stranger really is dr Kwant Niepewny, and that
	 * decision publishes a consent under somebody's name.
	 *
	 * The address is shown in full here, unmasked, because judging it IS the job. The
	 * signals next to it are facts with known failure modes, not a score: an address rarely
	 * matches a nickname, so „nazwisko w adresie” missing means nothing at all, while its
	 * presence means something. Nothing on this page adds them up for you. */
	import Breadcrumb from '$lib/components/Breadcrumb.svelte';
	import { ApiError } from '$lib/api';
	import { auth } from '$lib/auth.svelte';
	import { dialog } from '$lib/dialog.svelte';
	import { decideClaim, loadClaimQueue, type ClaimRow } from '$lib/consent';
	import { fmtDate } from '$lib/types';

	/** Polish, like every other status in this interface — the raw value is a database
	 * word and only means something to whoever wrote the model. */
	const STATUS_LABEL: Record<string, string> = {
		sent: 'link wysłany, nie potwierdzony',
		verified: 'skrzynka potwierdzona',
		approved: 'zatwierdzony',
		rejected: 'odrzucony',
		superseded: 'zastąpiony nowszym',
		withdrawn: 'wycofany przez osobę'
	};

	const FILTERS: { value: string; label: string }[] = [
		{ value: 'verified', label: 'Do decyzji' },
		{ value: 'approved', label: 'Zatwierdzone' },
		{ value: 'rejected', label: 'Odrzucone' },
		{ value: 'sent', label: 'Niepotwierdzone' },
		{ value: 'all', label: 'Wszystkie' }
	];

	let filter = $state('verified');
	let rows = $state<ClaimRow[]>([]);
	let loading = $state(true);
	let error = $state('');
	let busyId = $state(0);

	let loadedFor = ''; // plain let: guards the fetch so the effect cannot loop
	$effect(() => {
		if (!auth.ready || !auth.isStaff) return;
		const key = filter;
		if (key === loadedFor) return;
		loadedFor = key;
		load(key);
	});

	async function load(status: string) {
		loading = true;
		error = '';
		try {
			rows = await loadClaimQueue(status);
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Nie udało się wczytać kolejki.';
		} finally {
			loading = false;
		}
	}

	async function decide(row: ClaimRow, decision: 'approve' | 'reject') {
		if (busyId) return;
		const approve = decision === 'approve';
		const note = await dialog.ask({
			title: approve ? 'Zatwierdzić wniosek?' : 'Odrzucić wniosek?',
			danger: !approve,
			text: approve
				? `Wybór „${row.wish_label}” zacznie obowiązywać na stronie ${row.person.full_name}, a wnioskodawca dostanie mailem link do ustawień — od tej chwili zmienia i cofa sam, bez nas.`
				: `Wszystko, co ten wniosek zdążył zmienić, wróci do stanu sprzed (ukryte wpisy wrócą tam, gdzie były). Powód pójdzie mailem do wnioskodawcy — napisz go tak, żeby dało się go przeczytać.`,
			confirm: approve ? 'Zatwierdź' : 'Odrzuć',
			reason: approve ? 'optional' : 'required',
			placeholder: approve
				? 'notatka do wnioskodawcy (nieobowiązkowa)'
				: 'dlaczego — ten tekst dostanie wnioskodawca'
		});
		if (note === null || (!approve && !note)) return;
		busyId = row.id;
		error = '';
		try {
			const updated = await decideClaim(row.id, decision, note);
			rows =
				filter === 'all' || filter === updated.status
					? rows.map((r) => (r.id === updated.id ? updated : r))
					: rows.filter((r) => r.id !== updated.id);
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Decyzja nie przeszła.';
		} finally {
			busyId = 0;
		}
	}
</script>

<svelte:head><title>Zgody osób — fuw.lol</title></svelte:head>

<Breadcrumb trail={[{ label: 'Moderacja', href: '/moderacja' }, { label: 'Zgody osób' }]} />


{#if !auth.ready}
	<div class="box"><div class="box__body"><p class="muted">Chwileczkę…</p></div></div>
{:else if !auth.isStaff}
	<div class="box">
		<h1 class="box__title">Zgody osób</h1>
		<div class="box__body">
			<p>
				Tylko dla administracji. Potwierdzanie, że ktoś naprawdę jest tą osobą, to inna władza niż
				ukrywanie treści — dlatego nie wystarczy tu status zaufanego.
			</p>
		</div>
	</div>
{:else}
	<div class="box">
		<h1 class="box__title">
			Zgody osób <small>„Jesteś tą osobą?” · {loading ? 'wczytuję…' : `${rows.length}`}</small>
		</h1>
		<div class="box__body">
			<p class="small muted">
				Wniosek osoby, której dotyczą wpisy (art. 81 ust. 1 pr. aut.). Sprawdzasz jedno: czy ten
				adres wiarygodnie należy do tej osoby. Sygnały niżej są przesłankami, nie dowodem — adres
				rzadko pasuje do ksywki, a jego niedopasowanie nie znaczy nic. Jak to działa dla ludzi z
				drugiej strony: <a href="/ludzie/zgoda">odznaka „zgoda na wizerunek”</a>.
			</p>
			<p class="filters">
				{#each FILTERS as f (f.value)}
					<button
						type="button"
						class="btn btn--sm"
						class:btn--ghost={filter !== f.value}
						onclick={() => (filter = f.value)}>{f.label}</button
					>
				{/each}
			</p>
			{#if error}<div class="error">{error}</div>{/if}
		</div>

		{#if loading}
			<div class="box__body"><p class="muted">Wczytuję…</p></div>
		{:else if rows.length === 0}
			<div class="box__body">
				<p class="muted">Pusto. Nikt się nie upomina o swoją twarz.</p>
			</div>
		{:else}
			{#each rows as row (row.id)}
				<div class="c">
					<h3 class="c__title">
						<a href="/ludzie/{row.person.slug}">{row.person.full_name}</a>
						<span class="pill pill--amber">{row.wish_label}</span>
						{#if row.status !== 'verified'}<span class="pill pill--grey">{STATUS_LABEL[row.status] ?? row.status}</span>{/if}
						{#if row.applied_at}<span class="pill pill--green" title="wniosek już działa na stronie i wpisach">zastosowany</span>{/if}
					</h3>
					<div class="small muted">
						<span class="mono">{row.email}</span> · złożony {fmtDate(row.created_at)}
						{#if row.verified_at}· skrzynka potwierdzona {fmtDate(row.verified_at)}{/if}
						· tekst zgody {row.consent_text_version}
					</div>

					<p class="sig">
						{#if row.signals.domain_trusted}
							<span class="pill pill--green" title="adres w domenie uznawanej instytucji">
								domena instytucjonalna: {row.signals.institution}
							</span>
						{:else}
							<span class="pill pill--grey" title="zwykła skrzynka — to nie jest zarzut, tylko brak sygnału">
								domena prywatna
							</span>
						{/if}
						{#if row.signals.name_tokens_in_local_part}
							<span class="pill pill--green" title="fragment nazwiska lub imienia występuje przed @">
								nazwisko w adresie
							</span>
						{/if}
						{#if row.signals.account}
							<span class="pill pill--amber" title="konto w serwisie zarejestrowane na ten adres — kontekst, nie uprawnienie">
								konto: {row.signals.account}
							</span>
						{/if}
						{#if row.signals.earlier_claims}
							<span class="pill pill--grey" title="ile innych wniosków dotyczyło już tej strony">
								wcześniejsze zgłoszenia: {row.signals.earlier_claims}
							</span>
						{/if}
					</p>

					{#if row.note}
						<div class="note">
							<strong class="small">Wiadomość od wnioskodawcy:</strong>
							<p class="small">{row.note}</p>
						</div>
					{/if}

					{#if row.status === 'verified'}
						<div class="c__acts">
							<button type="button" disabled={busyId === row.id} onclick={() => decide(row, 'approve')}>
								Zatwierdź
							</button>
							<button
								type="button"
								class="btn btn--warn"
								disabled={busyId === row.id}
								onclick={() => decide(row, 'reject')}
							>
								Odrzuć
							</button>
						</div>
					{:else if row.decided_at}
						<p class="small muted">
							{row.status === 'approved' ? 'Zatwierdzone' : 'Rozstrzygnięte'}
							{#if row.decided_by}przez {row.decided_by}{/if} · {fmtDate(row.decided_at)}
							{#if row.decision_note}— „{row.decision_note}”{/if}
						</p>
					{/if}
				</div>
			{/each}
		{/if}
	</div>
{/if}

<style>
	.c {
		padding: 12px;
		border-bottom: 1px solid #e6e6e6;
	}
	.c:last-child {
		border-bottom: 0;
	}
	.c__title {
		font-size: 15px;
		font-weight: normal;
		margin: 0 0 4px;
	}
	.c__acts {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
		margin-top: 8px;
	}
	.sig {
		margin: 6px 0 0;
	}
	.note {
		border: 1px solid var(--line);
		background: var(--box);
		padding: 6px 9px;
		margin: 6px 0 0;
	}
	.note p {
		margin: 2px 0 0;
		white-space: pre-wrap;
	}
	.filters {
		display: flex;
		gap: 4px;
		flex-wrap: wrap;
		margin: 8px 0 0;
	}
</style>
