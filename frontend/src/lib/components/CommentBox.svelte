<script lang="ts">
	/** Write a comment: Markdown or LaTeX, up to three images, with a preview that runs the
	 * same renderer the posted comment will — the chosen files previewed through object URLs. */
	import { onDestroy } from 'svelte';
	import { api, ApiError } from '$lib/api';
	import { auth } from '$lib/auth.svelte';
	import type { Attachment, Comment, Format } from '$lib/types';
	import PostBody from './PostBody.svelte';

	let {
		slug,
		parent = null,
		onPosted,
		onCancel
	}: {
		slug: string;
		parent?: number | null;
		onPosted: (c: Comment) => void;
		onCancel?: () => void;
	} = $props();

	const MAX_FILES = 3;
	const MAX_BYTES = 25 * 1024 * 1024;

	interface Chosen {
		file: File;
		url: string;
	}

	let text = $state('');
	let format = $state<Format>('text');
	let chosen = $state<Chosen[]>([]);
	let preview = $state(false);
	let sending = $state(false);
	let error = $state('');
	let input = $state<HTMLInputElement | null>(null);

	onDestroy(() => {
		for (const c of chosen) URL.revokeObjectURL(c.url);
	});

	const previewFiles = $derived<Attachment[]>(
		chosen.map((c, i) => ({
			id: -1 - i,
			url: c.url,
			original_name: c.file.name,
			kind: 'image' as const,
			order: i
		}))
	);

	function pick(e: Event) {
		const list = (e.currentTarget as HTMLInputElement).files;
		if (!list) return;
		error = '';
		const next = [...chosen];
		for (const f of Array.from(list)) {
			if (next.length >= MAX_FILES) {
				error = `Najwyżej ${MAX_FILES} obrazy.`;
				break;
			}
			if (!f.type.startsWith('image/')) {
				error = `${f.name}: to nie jest obraz.`;
				continue;
			}
			if (f.size > MAX_BYTES) {
				error = `${f.name}: plik większy niż 25 MB.`;
				continue;
			}
			next.push({ file: f, url: URL.createObjectURL(f) });
		}
		chosen = next;
		if (input) input.value = '';
	}

	function drop(i: number) {
		const c = chosen[i];
		if (c) URL.revokeObjectURL(c.url);
		chosen = chosen.filter((_, j) => j !== i);
	}

	async function send() {
		if (sending) return;
		if (!text.trim() && chosen.length === 0) {
			error = 'Komentarz musi mieć treść albo obraz.';
			return;
		}
		sending = true;
		error = '';
		try {
			const fd = new FormData();
			fd.append('body', text);
			fd.append('format', format);
			if (parent != null) fd.append('parent', String(parent));
			for (const c of chosen) fd.append('files', c.file);
			const created = await api.post<Comment>(`/posts/${slug}/comments/`, fd);
			for (const c of chosen) URL.revokeObjectURL(c.url);
			chosen = [];
			text = '';
			preview = false;
			onPosted(created);
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Nie udało się wysłać komentarza.';
		} finally {
			sending = false;
		}
	}
</script>

{#if !auth.isAuthenticated}
	<p class="muted small">
		<a href="/logowanie?next=/wpis/{slug}">Zaloguj się</a>, żeby komentować.
	</p>
{:else}
	<div class="cbox">
		<label for="cbox-body-{parent ?? 'root'}">
			{parent ? 'Twoja odpowiedź' : 'Twój komentarz'}
		</label>
		<textarea
			id="cbox-body-{parent ?? 'root'}"
			rows={parent ? 3 : 5}
			bind:value={text}
			placeholder={format === 'latex'
				? 'LaTeX — np. \\textbf{no i} $E=mc^2$'
				: 'Markdown — np. **no i** $E=mc^2$, obraz przez ![](nazwa.jpg)'}
		></textarea>

		<div class="cbox__bar">
			<span class="small muted">Format:</span>
			<button
				type="button"
				class="btn btn--ghost btn--sm"
				class:is-active={format === 'text'}
				aria-pressed={format === 'text'}
				onclick={() => (format = 'text')}>Tekst</button
			>
			<button
				type="button"
				class="btn btn--ghost btn--sm"
				class:is-active={format === 'latex'}
				aria-pressed={format === 'latex'}
				onclick={() => (format = 'latex')}>LaTeX</button
			>

			<span class="sep"></span>

			<label class="filelabel" for="cbox-files-{parent ?? 'root'}">Obrazy (max 3)</label>
			<input
				id="cbox-files-{parent ?? 'root'}"
				class="file"
				type="file"
				accept="image/*"
				multiple
				bind:this={input}
				onchange={pick}
			/>

			<span class="sep"></span>

			<button
				type="button"
				class="btn btn--ghost btn--sm"
				class:is-active={preview}
				aria-pressed={preview}
				onclick={() => (preview = !preview)}>Podgląd</button
			>
		</div>

		{#if chosen.length}
			<ul class="chosen">
				{#each chosen as c, i (c.url)}
					<li>
						{c.file.name}
						<button type="button" class="x" title="Usuń plik" onclick={() => drop(i)}>×</button>
					</li>
				{/each}
			</ul>
		{/if}

		{#if preview}
			<div class="prev">
				<div class="prev__label small muted">Podgląd:</div>
				<PostBody {format} body={text} attachments={previewFiles} />
			</div>
		{/if}

		{#if error}<div class="error">{error}</div>{/if}

		<div class="cbox__send">
			<button type="button" onclick={send} disabled={sending}>
				{sending ? 'Wysyłam…' : 'Wyślij'}
			</button>
			{#if onCancel}
				<button type="button" class="btn btn--ghost" onclick={onCancel}>Anuluj</button>
			{/if}
		</div>
	</div>
{/if}

<style>
	.cbox {
		border: 1px solid var(--line);
		background: var(--box);
		padding: 8px 10px 10px;
		margin: 8px 0;
	}
	.cbox__bar {
		display: flex;
		align-items: center;
		gap: 6px;
		flex-wrap: wrap;
		margin: 6px 0;
	}
	.sep {
		width: 1px;
		height: 16px;
		background: var(--line);
	}
	.filelabel {
		display: inline;
		margin: 0;
		font-size: 11px;
		color: var(--muted);
	}
	.file {
		width: auto;
		font-size: 11px;
		border: 0;
		background: none;
		padding: 0;
	}
	.chosen {
		list-style: none;
		margin: 4px 0;
		padding: 0;
		font-size: 11px;
	}
	.chosen li {
		display: inline-block;
		border: 1px solid var(--line);
		background: #fff;
		padding: 1px 4px 1px 7px;
		margin: 0 4px 4px 0;
	}
	.x {
		background: none;
		border: 0;
		color: var(--rust);
		font-size: 13px;
		padding: 0 3px;
		cursor: pointer;
	}
	.x:hover {
		background: none;
		text-decoration: none;
	}
	.prev {
		border: 1px dashed var(--line);
		background: #fff;
		padding: 8px 10px;
		margin: 6px 0;
	}
	.prev__label {
		margin-bottom: 4px;
	}
	.prev :global(.gallery img) {
		max-height: 180px;
	}
	.cbox__send {
		display: flex;
		gap: 8px;
		margin-top: 6px;
	}
</style>
