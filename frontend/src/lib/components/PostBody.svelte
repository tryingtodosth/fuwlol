<script lang="ts">
	/** The body of a post (or of a comment): Markdown+KaTeX, or LaTeX compiled in the
	 * browser, plus whatever files were attached but never named in the text. */
	import { renderMarkdown, typeset } from '$lib/render/markdown';
	import { renderLatex } from '$lib/render/latex';
	import { resolver } from '$lib/render/media';
	import type { Attachment, Format } from '$lib/types';

	let {
		format,
		body,
		attachments = [],
		article = false
	}: { format: Format; body: string; attachments?: Attachment[]; article?: boolean } = $props();

	const resolve = $derived(
		resolver(attachments.map((a) => ({ name: a.original_name, url: a.url, kind: a.kind })))
	);

	let el = $state<HTMLDivElement | null>(null);
	let html = $state('');
	let error = $state<string | null>(null);
	let errLine = $state<number | undefined>(undefined);
	let busy = $state(false);

	$effect(() => {
		const fmt = format;
		const src = body ?? '';
		const res = resolve;
		let dead = false;
		if (fmt === 'latex') {
			busy = true;
			renderLatex(src, res)
				.then((r) => {
					if (dead) return;
					html = r.html;
					error = r.error;
					errLine = r.line;
					busy = false;
				})
				.catch((e: unknown) => {
					if (dead) return;
					html = '';
					error = e instanceof Error ? e.message : String(e);
					busy = false;
				});
		} else {
			html = renderMarkdown(src, res);
			error = null;
			errLine = undefined;
			busy = false;
		}
		return () => {
			dead = true;
		};
	});

	// KaTeX only for Markdown — LaTeX.js has already typeset its own maths.
	$effect(() => {
		const ready = html;
		if (!el || !ready || format === 'latex') return;
		typeset(el).catch(() => {});
	});

	const named = $derived(
		new Set(
			attachments
				.filter((a) => (body ?? '').includes(a.original_name))
				.map((a) => a.id)
		)
	);
	const unnamed = $derived(attachments.filter((a) => a.kind === 'image' && !named.has(a.id)));
	// On a post page a Markdown body gets its first picture floated left at 315px, the way a
	// faculty news item does; a typeset LaTeX page and a comment keep the gallery underneath.
	const lead = $derived(article && format !== 'latex' ? unnamed[0] : undefined);
	const images = $derived(lead ? unnamed.slice(1) : unnamed);
	const others = $derived(attachments.filter((a) => a.kind !== 'image'));
</script>

{#if busy}
	<p class="muted small">Kompiluję LaTeX-a…</p>
{/if}

{#if error}
	<div class="lx-err">
		<p>
			<strong>Nie udało się skompilować tego LaTeX-a{errLine ? ` (linia ${errLine})` : ''}.</strong>
			Poniżej komunikat i źródło, tak jak zostało napisane.
		</p>
		<p class="mono lx-err__msg">{error}</p>
		<pre>{body}</pre>
	</div>
{:else}
	{#if lead}
		<div class="image_container">
			<a href={lead.url} target="_blank" rel="noopener">
				<img src={lead.url} alt={lead.caption || lead.original_name} />
			</a>
			{#if lead.caption}<div class="caption">{lead.caption}</div>{/if}
		</div>
	{/if}
	<div class="body-html" class:latex-doc={format === 'latex'} bind:this={el}>{@html html}</div>
	{#if lead}<div class="clear"></div>{/if}
{/if}

{#if images.length}
	<div class="gallery">
		{#each images as a (a.id)}
			<figure>
				<a href={a.url} target="_blank" rel="noopener">
					<img src={a.url} alt={a.caption || a.original_name} loading="lazy" />
				</a>
				<figcaption>{a.caption || a.original_name}</figcaption>
			</figure>
		{/each}
	</div>
{/if}

{#if others.length}
	<ul class="files">
		{#each others as a (a.id)}
			<li>
				{#if a.kind === 'audio'}
					<div>{a.caption || a.original_name}</div>
					<audio controls src={a.url}>
						<a href={a.url}>Pobierz nagranie</a>
					</audio>
				{:else if a.kind === 'video'}
					<div>{a.caption || a.original_name}</div>
					<!-- svelte-ignore a11y_media_has_caption -->
					<video controls src={a.url}>
						<a href={a.url}>Pobierz wideo</a>
					</video>
				{:else}
					<a href={a.url} target="_blank" rel="noopener">
						{a.kind === 'pdf' ? '📄' : '📎'}
						{a.caption || a.original_name}
					</a>
				{/if}
			</li>
		{/each}
	</ul>
{/if}

<style>
	.clear {
		clear: both;
	}
	.body-html :global(img) {
		max-width: 100%;
		height: auto;
	}
	.body-html :global(table) {
		border-collapse: collapse;
	}
	.body-html :global(table td),
	.body-html :global(table th) {
		border: 1px solid var(--line);
		padding: 3px 7px;
	}
	/* LaTeX.js styles a whole page; inside a box it should just be text */
	.latex-doc :global(.body) {
		max-width: none;
		margin: 0;
		padding: 0;
		text-align: left; /* a comment or a card is not a typeset page */
	}
	.latex-doc :global(.page) {
		padding: 0;
	}
	.body-html :global(.latex-img) {
		display: block;
		max-width: 100%;
		height: auto;
		margin: 8px 0;
	}
	.body-html :global(.latex-missing) {
		color: var(--muted);
		font-style: italic;
	}
	.lx-err {
		border: 1px solid var(--line);
		background: var(--box);
		padding: 9px 12px;
		margin: 0 0 10px;
	}
	.lx-err__msg {
		color: #b00020;
		white-space: pre-wrap;
	}
	.files {
		list-style: none;
		margin: 8px 0 0;
		padding: 0;
	}
	.files li {
		margin: 0 0 8px;
	}
	.files audio,
	.files video {
		max-width: 100%;
		display: block;
	}
</style>
