<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import { stamp, type BoardMessage, type BoardPage } from './types';

	let messages = $state<BoardMessage[]>([]);
	let failed = $state(false);
	const plain = (s: string) => {
		const t = s.replace(/!\[[^\]]*\]\([^)]*\)/g, '').replace(/[*_`>#\\]/g, '').replace(/\s+/g, ' ').trim();
		return t.length > 90 ? t.slice(0, 90) + '…' : t;
	};
	onMount(() => {
		api.get<BoardPage>('/board/?limit=5').then((p) => (messages = p.results)).catch(() => (failed = true));
	});
</script>

<div class="box">
	<h2 class="box__title">Czat <small>ostatnie wiadomości</small></h2>
	<div class="box__body">
		{#if failed}
			<p class="muted">Czat chwilowo niedostępny.</p>
		{:else if messages.length === 0}
			<p class="muted">Cisza. <a href="/czat">Napisz pierwszy →</a></p>
		{:else}
			<ul class="lines">
				{#each messages as m (m.id)}
					<li><span class="mono time">[{stamp(m.created_at)}]</span> <strong>{m.nick}</strong>: {plain(m.body) || '(wzór)'}</li>
				{/each}
			</ul>
		{/if}
		<p class="more-line"><a href="/czat" class="more">Wejdź na czat →</a></p>
	</div>
</div>

<style>
	.lines { list-style: none; margin: 0; padding: 0; }
	.lines li { padding: 2px 0; border-bottom: 1px dotted #e6e6e6; }
	.time { color: var(--muted); font-size: 11px; }
	.more-line { margin: 8px 0 0; text-align: right; }
</style>
