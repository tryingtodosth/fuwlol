<script lang="ts">
	/** Plain text with `$…$` maths typeset — for summaries and other one-liners. The text is
	 * escaped (never HTML), then KaTeX auto-render runs over it. */
	import { typeset } from '$lib/render/markdown';
	let { text }: { text: string } = $props();
	let el = $state<HTMLElement | null>(null);
	$effect(() => {
		const t = text;
		if (!el) return;
		el.textContent = t;
		if (/\$|\\\(|\\\[/.test(t)) typeset(el);
	});
</script>

<span class="mathtext" bind:this={el}></span>
