<script lang="ts">
	/** Every year the archive knows about, tallest bar wins. */
	import Breadcrumb from '$lib/components/Breadcrumb.svelte';
	import { api, ApiError } from '$lib/api';

	interface Timeline {
		years: { year: number; count: number }[];
		undated: number;
	}

	let data = $state<Timeline | null>(null);
	let loading = $state(true);
	let error = $state('');

	let asked = false; // plain let: fetched once
	$effect(() => {
		if (asked) return;
		asked = true;
		load();
	});

	async function load() {
		loading = true;
		error = '';
		try {
			data = await api.get<Timeline>('/posts/timeline/');
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Nie udało się wczytać osi czasu.';
		} finally {
			loading = false;
		}
	}

	const max = $derived(Math.max(1, ...(data?.years ?? []).map((y) => y.count)));
	const decades = $derived.by(() => {
		const out: { decade: number; years: { year: number; count: number }[] }[] = [];
		for (const y of data?.years ?? []) {
			const d = Math.floor(y.year / 10) * 10;
			const last = out[out.length - 1];
			if (last && last.decade === d) last.years.push(y);
			else out.push({ decade: d, years: [y] });
		}
		return out;
	});
	const total = $derived((data?.years ?? []).reduce((a, y) => a + y.count, 0));
</script>

<svelte:head><title>Oś czasu — fuw.lol</title></svelte:head>

<Breadcrumb trail={[{ label: 'Oś czasu' }]} />


<div class="box">
	<h1 class="box__title">
		Oś czasu
		<small>{loading ? 'wczytuję…' : `${total} datowanych wpisów`}</small>
	</h1>
	<div class="box__body">
		{#if loading}
			<p class="muted">Wczytuję oś czasu…</p>
		{:else if error}
			<div class="error">{error}</div>
		{:else if data}
			{#if decades.length === 0}
				<p class="muted">Nic jeszcze nie ma daty.</p>
			{:else}
				{#each decades as d (d.decade)}
					<h2 class="dec">lata {d.decade}.</h2>
					<ul class="years">
						{#each d.years as y (y.year)}
							<li>
								<a class="yr" href="/przegladaj?year={y.year}">{y.year}</a>
								<span class="bar" style="width: {Math.round((y.count / max) * 100)}%"></span>
								<span class="cnt small muted">{y.count}</span>
							</li>
						{/each}
					</ul>
				{/each}
			{/if}

			{#if data.undated}
				<hr />
				<p class="small">
					bez daty: <a href="/przegladaj?sort=new">{data.undated}</a>
				</p>
			{/if}
		{/if}
	</div>
</div>

<style>
	.dec {
		font-size: 14px;
		margin: 14px 0 6px;
		color: var(--green);
		border-bottom: 1px solid var(--line);
		padding-bottom: 3px;
	}
	.years {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.years li {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 2px 0;
	}
	.yr {
		flex: 0 0 46px;
		font-family: 'DejaVu Sans Mono', Consolas, monospace;
		font-size: 12px;
	}
	.bar {
		height: 11px;
		background: var(--green);
		min-width: 2px;
		max-width: calc(100% - 100px);
		display: block;
	}
	.cnt {
		flex: 0 0 auto;
	}
</style>
