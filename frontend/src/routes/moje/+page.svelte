<script lang="ts">
	/** Everything you have sent in, in whatever state it is — including the things nobody
	 * else can see yet. */
	import { goto } from '$app/navigation';
	import { api, ApiError, qs } from '$lib/api';
	import { auth } from '$lib/auth.svelte';
	import { fmtDate, yearLabel, type Page as ApiPage, type PostSummary, type Status } from '$lib/types';

	/** `/posts/mine/` uses the list serializer, which does not carry `review_note` today —
	 * so it is optional here rather than assumed present. */
	type MyPost = PostSummary & { review_note?: string };

	const PER_PAGE = 20;
	const LABEL: Record<Status, string> = {
		published: 'Opublikowany',
		pending: 'Czeka na moderację',
		rejected: 'Odrzucony',
		hidden: 'Ukryty',
		nuked: '☢ Nuklearne'
	};
	const PILL: Record<Status, string> = {
		published: 'pill--green',
		pending: 'pill--amber',
		rejected: 'pill--grey',
		hidden: 'pill--grey',
		nuked: '☢ Nuklearne'
	};

	let items = $state<MyPost[]>([]);
	let count = $state(0);
	let pageNo = $state(1);
	let loading = $state(true);
	let error = $state('');

	const totalPages = $derived(Math.max(1, Math.ceil(count / PER_PAGE)));

	let loadedPage = 0; // plain let: guards the fetch so the effect cannot loop
	$effect(() => {
		if (!auth.ready) return;
		if (!auth.isAuthenticated) {
			goto('/logowanie?next=/moje', { replaceState: true });
			return;
		}
		if (pageNo === loadedPage) return;
		loadedPage = pageNo;
		load(pageNo);
	});

	async function load(n: number) {
		loading = true;
		error = '';
		try {
			const res = await api.get<ApiPage<MyPost>>(`/posts/mine/${qs({ page: n > 1 ? n : '' })}`);
			items = res.results;
			count = res.count;
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Nie udało się wczytać Twoich wpisów.';
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head><title>Moje wpisy — fuw.lol</title></svelte:head>

<div class="box">
	<h1 class="box__title">
		Moje wpisy
		<small>{loading ? 'wczytuję…' : `${count} ${count === 1 ? 'wpis' : 'wpisów'}`}</small>
	</h1>
	<div class="box__body">
		{#if !auth.ready}
			<p class="muted">Chwileczkę…</p>
		{:else if loading}
			<p class="muted">Wczytuję…</p>
		{:else if error}
			<div class="error">{error}</div>
		{:else if items.length === 0}
			<p class="muted">Nic tu jeszcze nie ma. <a href="/dodaj">Dodaj pierwszy wpis</a>.</p>
		{:else}
			<table class="mine">
				<tbody>
					{#each items as p (p.slug)}
						<tr>
							<td class="t">
								<a href="/wpis/{p.slug}">{p.title}</a>
								<div class="small muted">
									{#if p.catalog_no}{p.catalog_no} · {/if}{p.category_name} · {yearLabel(p)} ·
									dodano {fmtDate(p.created_at)}
								</div>
								{#if p.review_note}
									<div class="small note">Uwaga moderatora: {p.review_note}</div>
								{/if}
								{#if p.status === 'rejected' || p.status === 'hidden' || p.status === 'nuked'}
									<div class="small muted">Odwołanie: w ciągu 14 dni na adres z <a href="/o-archiwum">„O archiwum”</a>, z numerem {p.catalog_no || 'wpisu'}; rozpatruje człowiek, nie automat.</div>
								{/if}
							</td>
							<td class="s">
								<span class="pill {PILL[p.status]}">{LABEL[p.status]}</span>
							</td>
							<td class="e"><a class="small" href="/edytuj/{p.slug}">Edytuj</a></td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</div>
</div>

{#if !loading && totalPages > 1}
	<div class="pager">
		<button type="button" class="btn btn--ghost" disabled={pageNo <= 1} onclick={() => (pageNo -= 1)}>
			← Poprzednia
		</button>
		<span class="small muted">strona {pageNo} z {totalPages}</span>
		<button
			type="button"
			class="btn btn--ghost"
			disabled={pageNo >= totalPages}
			onclick={() => (pageNo += 1)}
		>
			Następna →
		</button>
	</div>
{/if}

<style>
	.mine {
		width: 100%;
	}
	.mine td {
		border-bottom: 1px solid #e6e6e6;
		padding: 7px 6px 7px 0;
		vertical-align: top;
	}
	.mine tr:last-child td {
		border-bottom: 0;
	}
	.t {
		width: 100%;
	}
	.s,
	.e {
		white-space: nowrap;
		text-align: right;
	}
	.note {
		color: var(--rust);
	}
	.pager {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 12px;
		margin: 4px 0 16px;
	}
</style>
