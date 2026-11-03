<script lang="ts">
	import { onMount } from 'svelte';
	import { kolo, kp } from '$lib/kolo.svelte';

	let { children } = $props();
	onMount(() => { kolo.init(); });
</script>

<div class="kolo-bg"><div class="kolo">
	<header class="kolo__top">
		<a class="kolo__brand" href={kp()}>
			<img src="/kolo/logo.svg" alt="" width="44" height="44" />
			<span><strong>Koło AI</strong><small>Wydział Fizyki Uniwersytetu Warszawskiego</small></span>
		</a>
		<nav class="kolo__nav">
			<a href={kp()}>O Kole</a>
			{#if kolo.isVoter || kolo.isManager}<a href={kp('/glosowania')}>Głosowania</a>{/if}
			{#if kolo.isManager}<a href={kp('/zarzad')}>Zarząd</a>{/if}
			{#if kolo.me}
				<span class="kolo__who">{kolo.me.name}</span>
				<button class="kolo__link" onclick={() => kolo.logout()}>wyloguj</button>
			{/if}
		</nav>
	</header>
	<main class="kolo__main">
		{@render children()}
	</main>
	<footer class="kolo__foot">
		Koło AI — uczelniana organizacja studencka przy Wydziale Fizyki UW (w trakcie rejestracji).
		Administrator danych: Piotr Putyło, <a href="mailto:admin@fuw.lol">admin@fuw.lol</a>.
	</footer>
</div></div>

<style>
	/* the background on a wrapper, not on body: body belongs to the archive's app.css */
	.kolo-bg { background: #f4f4f2; min-height: 100vh; }
	.kolo :global(a) { color: #1d4f86; }
	.kolo .kolo__brand, .kolo .kolo__nav a { color: #222; }
	.kolo { max-width: 860px; margin: 0 auto; padding: 0 16px; font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; font-size: 15px; line-height: 1.55; color: #222; }
	.kolo__top { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; padding: 16px 0 12px; border-bottom: 2px solid #222; }
	.kolo__brand { display: flex; align-items: center; gap: 10px; color: inherit; text-decoration: none; }
	.kolo__brand strong { display: block; font-size: 20px; letter-spacing: .02em; }
	.kolo__brand small { display: block; color: #666; font-size: 12px; }
	.kolo__nav { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; font-size: 14px; }
	.kolo__nav a { color: #222; }
	.kolo__who { color: #666; }
	.kolo__link { background: none; border: none; color: #555; text-decoration: underline; padding: 0; font: inherit; cursor: pointer; }
	.kolo__main { padding: 18px 0 30px; }
	.kolo__foot { border-top: 1px solid #ccc; padding: 12px 0 24px; font-size: 12px; color: #666; }
	.kolo :global(h1) { font-size: 26px; font-weight: 650; margin: 8px 0 12px; }
	.kolo :global(h2) { font-size: 18px; font-weight: 650; margin: 22px 0 8px; }
	.kolo :global(.card) { background: #fff; border: 1px solid #d6d6d2; border-radius: 6px; padding: 14px 16px; margin: 12px 0; }
	.kolo :global(.card--accent) { border-left: 4px solid #222; }
	.kolo :global(label) { display: block; font-weight: 600; margin: 10px 0 3px; font-size: 14px; }
	.kolo :global(input[type='email']), .kolo :global(input[type='text']), .kolo :global(input[type='datetime-local']), .kolo :global(textarea), .kolo :global(select) { width: 100%; box-sizing: border-box; padding: 7px 9px; font: inherit; border: 1px solid #aaa; border-radius: 4px; background: #fff; }
	.kolo :global(.btn) { background: #222; border-color: #222; border-radius: 4px; padding: 7px 14px; font-size: 14px; }
	.kolo :global(.btn--ghost) { background: #fff; color: #222; }
	.kolo :global(.muted) { color: #666; }
	.kolo :global(.status-item) { border-left: 3px solid #999; padding: 2px 0 2px 12px; margin: 10px 0; }
	.kolo :global(.status-item time) { color: #666; font-size: 12px; }
	.kolo :global(.pre) { white-space: pre-wrap; }
	.kolo :global(table.kt) { border-collapse: collapse; width: 100%; font-size: 14px; }
	.kolo :global(table.kt td), .kolo :global(table.kt th) { border-bottom: 1px solid #e2e2de; padding: 6px 4px; text-align: left; vertical-align: top; }
</style>
