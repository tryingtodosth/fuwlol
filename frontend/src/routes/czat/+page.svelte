<script lang="ts">
	import Breadcrumb from '$lib/components/Breadcrumb.svelte';
	import { onMount } from 'svelte';
	import ChatBoard from '$lib/components/board/ChatBoard.svelte';
	onMount(() => {
		document.title = 'Czat — fuw.lol';
		const id = location.hash;
		if (id.startsWith('#m')) setTimeout(() => document.querySelector(id)?.scrollIntoView(), 800);
	});
</script>


<Breadcrumb trail={[{ label: 'Czat' }]} />

<h1>Czat</h1>
<ChatBoard />
