<script lang="ts">
	/** One exhibit: the stamp, the metadata table, the body, reactions, the report form and
	 * the discussion underneath. */
	import { page } from '$app/state';
	import { api, ApiError } from '$lib/api';
	import { auth } from '$lib/auth.svelte';
	import { fmtDate, yearLabel, type Post } from '$lib/types';
	import PostBody from '$lib/components/PostBody.svelte';
	import Reactions from '$lib/components/Reactions.svelte';
	import ModTools from '$lib/components/ModTools.svelte';
	import MathText from '$lib/components/MathText.svelte';
	import Comments from '$lib/components/Comments.svelte';

	const REASONS: { value: string; label: string }[] = [
		{ value: 'privacy', label: 'Dotyczy mnie i chcę usunięcia' },
		{ value: 'wrong', label: 'Nieprawda / błąd' },
		{ value: 'offensive', label: 'Obraźliwe' },
		{ value: 'copyright', label: 'Prawa autorskie' },
		{ value: 'other', label: 'Inne' }
	];

	const slug = $derived(page.params.slug ?? '');

	let post = $state<Post | null>(null);
	let loading = $state(true);
	let error = $state('');
	let notFound = $state(false);

	let reportOpen = $state(false);
	let reason = $state('privacy');
	let note = $state('');
	let contact = $state('');
	let sending = $state(false);
	let reportError = $state('');
	let reportDone = $state(false);

	let loadedFor = ''; // plain let: guards the fetch so the effect cannot loop
	$effect(() => {
		const s = slug;
		if (!s || s === loadedFor) return;
		loadedFor = s;
		reportOpen = false;
		reportDone = false;
		reportError = '';
		note = '';
		load(s);
	});

	async function load(s: string) {
		loading = true;
		error = '';
		notFound = false;
		post = null;
		try {
			post = await api.get<Post>(`/posts/${s}/`);
		} catch (e) {
			if (e instanceof ApiError && e.status === 404) notFound = true;
			else error = e instanceof ApiError ? e.message : 'Nie udało się wczytać wpisu.';
		} finally {
			loading = false;
		}
	}

	async function sendReport(e: SubmitEvent) {
		e.preventDefault();
		if (sending || !post) return;
		sending = true;
		reportError = '';
		try {
			await api.post('/reports/', {
				post: post.slug,
				reason,
				note,
				contact_email: contact
			});
			reportDone = true;
			reportOpen = false;
		} catch (err) {
			reportError = err instanceof ApiError ? err.message : 'Nie udało się wysłać zgłoszenia.';
		} finally {
			sending = false;
		}
	}

	const formatLabel = $derived(post?.format === 'latex' ? 'LaTeX' : 'Tekst / Markdown');
	const statusNote = $derived.by(() => {
		if (!post || post.status === 'published') return '';
		if (post.status === 'pending') return 'Ten wpis czeka na moderację — widzisz go, bo go dodałeś/aś (albo moderujesz).';
		if (post.status === 'rejected') return 'Ten wpis został odrzucony przez moderatora.';
		return 'Ten wpis został ukryty przez moderatora.';
	});
</script>

<svelte:head>
	<title>{post ? `${post.title} — fuw.lol` : 'fuw.lol'}</title>
</svelte:head>

{#if loading}
	<div class="box"><div class="box__body"><p class="muted">Wczytuję wpis…</p></div></div>
{:else if notFound}
	<div class="box">
		<h1 class="box__title">Nie ma takiego wpisu</h1>
		<div class="box__body">
			<p>Nie ma takiego wpisu (albo jeszcze nie został opublikowany).</p>
			<p><a href="/przegladaj">Przeglądaj archiwum</a> · <a href="/losowe">Losowy wpis</a></p>
		</div>
	</div>
{:else if error}
	<div class="box"><div class="box__body"><div class="error">{error}</div></div></div>
{:else if post}
	{#if statusNote}
		<div class="box box--grey">
			<div class="box__body">
				<p class="small"><strong>{statusNote}</strong></p>
				{#if post.review_note}
					<p class="small">Uwaga moderatora: {post.review_note}</p>
				{/if}
			</div>
		</div>
	{/if}

	<div class="box">
		<div class="box__body">
			<h1 class="title">
				{#if post.catalog_no}<span class="stamp">{post.catalog_no}</span>{/if}
				{post.title}
				{#if post.featured}<span class="pill pill--amber">Wyróżnione</span>{/if}
			</h1>
			{#if post.summary}<p class="lead"><MathText text={post.summary} /></p>{/if}

			<table class="meta">
				<tbody>
					<tr>
						<th scope="row">Kategoria</th>
						<td><a href="/przegladaj?category={post.category}">{post.category_name}</a></td>
					</tr>
					<tr>
						<th scope="row">Rok</th>
						<td>
							{#if post.year != null}
								<a href="/przegladaj?year={post.year}">{yearLabel(post)}</a>
							{:else}
								{yearLabel(post)}
							{/if}
						</td>
					</tr>
					{#if post.date_note}
						<tr><th scope="row">Kiedy</th><td>{post.date_note}</td></tr>
					{/if}
					{#if post.people.length}
						<tr>
							<th scope="row">Osoby</th>
							<td>
								{#each post.people as p, i (p.slug)}<a href="/ludzie/{p.slug}">{p.name}</a>{#if i < post.people.length - 1},
									{/if}{/each}
							</td>
						</tr>
					{/if}
					{#if post.tags.length}
						<tr>
							<th scope="row">Tagi</th>
							<td>
								{#each post.tags as t (t.slug)}
									<a class="pill" href="/przegladaj?tag={t.slug}">{t.name}</a>
								{/each}
							</td>
						</tr>
					{/if}
					{#if post.source_note || post.source_url}
						<tr>
							<th scope="row">Źródło</th>
							<td>
								{post.source_note}
								{#if post.source_url}
									{#if post.source_note}<br />{/if}
									<a href={post.source_url} target="_blank" rel="noopener nofollow">{post.source_url}</a>
								{/if}
							</td>
						</tr>
					{/if}
					<tr><th scope="row">Dodał/a</th><td>{post.submitted_by || '—'}</td></tr>
					<tr>
						<th scope="row">Opublikowano</th>
						<td>{post.published_at ? fmtDate(post.published_at) : 'jeszcze nie'}</td>
					</tr>
					<tr><th scope="row">Wyświetlenia</th><td>{post.views}</td></tr>
					<tr><th scope="row">Format</th><td>{formatLabel}</td></tr>
				</tbody>
			</table>

			<hr />

			<PostBody format={post.format} body={post.body} attachments={post.attachments} />

			<Reactions {post} />

			{#if post.can_moderate}
				<p class="acts small modrow">
					{#if post.moderation_notice}<span class="pill pill--amber">{post.moderation_notice}</span>{/if}
					{#if post.moderation?.actor}<span class="muted">({post.moderation.actor}: {post.moderation.reason || 'bez powodu'})</span>{/if}
					<ModTools kind="post" id={post.slug}
						status={post.status === 'hidden' ? 'hidden' : post.status === 'nuked' ? 'nuked' : 'visible'}
						onChanged={() => location.reload()} />
				</p>
			{/if}

			<p class="acts small">
				{#if post.can_edit}
					<a href="/edytuj/{post.slug}">Edytuj</a> ·
				{/if}
				<button type="button" class="linky" onclick={() => (reportOpen = !reportOpen)}>
					Zgłoś / poproś o usunięcie
				</button>
			</p>

			{#if reportDone}
				<div class="ok">Dziękujemy, zgłoszenie trafiło do moderacji.</div>
			{/if}

			{#if reportOpen}
				<form class="report" onsubmit={sendReport}>
					<p class="small muted">
						Jesteś na zdjęciu, coś tu jest nieprawdą albo naruszamy Twoje prawa? Napisz — moderator to
						przejrzy.
					</p>
					<label for="r-reason">Powód</label>
					<select id="r-reason" bind:value={reason}>
						{#each REASONS as r (r.value)}
							<option value={r.value}>{r.label}</option>
						{/each}
					</select>

					<label for="r-note">Szczegóły (opcjonalnie)</label>
					<textarea id="r-note" rows="4" bind:value={note}></textarea>

					<label for="r-mail">E-mail kontaktowy (opcjonalnie)</label>
					<input id="r-mail" type="email" bind:value={contact} placeholder="żebyśmy mogli odpisać" />

					{#if reportError}<div class="error">{reportError}</div>{/if}

					<div class="report__send">
						<button type="submit" disabled={sending}>{sending ? 'Wysyłam…' : 'Wyślij zgłoszenie'}</button>
						<button type="button" class="btn btn--ghost" onclick={() => (reportOpen = false)}>
							Anuluj
						</button>
					</div>
				</form>
			{/if}
		</div>
	</div>

	<Comments slug={post.slug} />
{/if}

<style>
	.title {
		font-size: 20px;
		line-height: 1.3;
		margin-bottom: 8px;
	}
	.title .stamp {
		margin-right: 6px;
		vertical-align: 3px;
	}
	.title .pill {
		vertical-align: 4px;
		font-weight: normal;
	}
	.lead {
		font-size: 13px;
		color: #333;
		font-style: italic;
	}
	.acts {
		margin-top: 10px;
		color: var(--muted);
	}
	.linky {
		background: none;
		border: 0;
		padding: 0;
		font-size: 11px;
		color: var(--rust);
		cursor: pointer;
		font-family: inherit;
	}
	.linky:hover {
		background: none;
		text-decoration: underline;
	}
	.report {
		border: 1px solid var(--line);
		background: var(--box);
		padding: 8px 10px 12px;
		margin-top: 8px;
	}
	.report__send {
		display: flex;
		gap: 8px;
		margin-top: 10px;
	}
	.meta a.pill {
		color: #333;
	}
</style>
