<script lang="ts">
	import { onMount } from 'svelte';
	import ChatBoard from '$lib/components/board/ChatBoard.svelte';
	onMount(() => {
		document.title = 'Czat — fuw.lol';
		const id = location.hash;
		if (id.startsWith('#m')) setTimeout(() => document.querySelector(id)?.scrollIntoView(), 800);
	});
</script>

<h1>Czat</h1>
<ChatBoard />
