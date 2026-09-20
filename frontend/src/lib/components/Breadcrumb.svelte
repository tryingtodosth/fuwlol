<script lang="ts">
	/** The faculty's `.mod_breadcrumb`: „fuw.lol > Dział > Tu jesteś” in 12px, the trail in
	 * blue-grey and the current page in the body colour. Every subpage of fuw.edu.pl starts with
	 * one, so every subpage here does too; the front page, like theirs, has none. The last crumb
	 * is always the page itself and never a link, whatever `href` it carries. */
	let { trail }: { trail: { label: string; href?: string; title?: string }[] } = $props();
</script>

<!-- `{' > '}` rather than a typed „&gt;”: Svelte trims the whitespace at a block's edge, so the
     space between a link crumb and the next separator would otherwise vanish („Przedmioty> Analiza”). -->
<div class="mod_breadcrumb">
	<a href="/" title="fuw.lol — archiwum folkloru Wydziału Fizyki UW">fuw.lol</a>{#each trail as c, i (i)}{' > '}{#if i < trail.length - 1 && c.href}<a href={c.href} title={c.title}>{c.label}</a>{:else}<span class="active">{c.label}</span>{/if}{/each}
</div>
