<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import Header from '$lib/components/Header.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
	import { auth } from '$lib/auth.svelte';

	let { children } = $props();
	// Koło AI (routes/ai/, ai.fuw.lol) is not the archive and does not wear its look: its own
	// layout draws the page, and the archive's header, footer and session stay out of it.
	const kolo = $derived(page.route.id?.startsWith('/ai') ?? false);

	onMount(() => {
		if (!kolo) auth.init();
	});
</script>

{#if kolo}
	{@render children()}
{:else}
	<Header />
	<main class="container page">
		{@render children()}
	</main>
	<Footer />
{/if}
<ConfirmDialog />
