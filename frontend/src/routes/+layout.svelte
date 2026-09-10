<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';
	import Header from '$lib/components/Header.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import { auth } from '$lib/auth.svelte';

	let { children } = $props();

	onMount(() => {
		auth.init();
	});
</script>

<Header />
<main class="container page">
	{@render children()}
</main>
<Footer />
