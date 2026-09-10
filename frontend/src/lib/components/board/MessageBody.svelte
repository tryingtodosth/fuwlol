<script lang="ts">
	import { renderMarkdown, typeset } from '$lib/render/markdown';
	import { renderLatex } from '$lib/render/latex';

	let { body, format }: { body: string; format: 'text' | 'latex' } = $props();
	let el = $state<HTMLElement | null>(null);
	let html = $state('');
	let error = $state<string | null>(null);
	const none = () => undefined;

	$effect(() => {
		const src = body, fmt = format;
		let live = true;
		if (fmt === 'latex') {
			renderLatex(src, none, { images: false }).then((r) => {
				if (!live) return;
				html = r.html; error = r.error;
			});
		} else {
			html = renderMarkdown(src, none, { images: false }); error = null;
			queueMicrotask(() => { if (live && el) typeset(el); });
		}
		return () => { live = false; };
	});
</script>

{#if error}
	<div class="err">Błąd LaTeX-a: {error}</div>
	<pre>{body}</pre>
{:else}
	<div class="msg-body" class:latex-doc={format === 'latex'} bind:this={el}>{@html html}</div>
{/if}

<style>
	.msg-body :global(p:last-child) { margin-bottom: 0; }
	.msg-body :global(.body) { max-width: none; margin: 0; padding: 0; }
	.err { color: #b00020; font-size: 11px; }
	pre { margin: 0; white-space: pre-wrap; }
</style>
