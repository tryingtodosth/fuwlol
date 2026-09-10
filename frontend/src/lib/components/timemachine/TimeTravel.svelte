<!-- The controller. Turns `?czas=` into an era, plays the Big Bang for everything that
     is not our own archive, and keeps a way back on screen the whole time. -->
<script lang="ts">
	import { goto } from '$app/navigation';
	import BigBang from './BigBang.svelte';
	import EraCopernicus from './EraCopernicus.svelte';
	import EraNow from './EraNow.svelte';
	import EraPaper from './EraPaper.svelte';
	import EraPrehistoric from './EraPrehistoric.svelte';
	import EraWayback from './EraWayback.svelte';
	import {
		eraFor,
		eraLabel,
		eraOpensWithBigBang,
		formatTravel,
		parseTravel,
		toRoman,
		travelLabel
	} from './eras';

	let { date }: { date: string } = $props();

	const travel = $derived(parseTravel(date));
	const era = $derived(travel ? eraFor(travel) : null);

	/** Which destination the animation has already been played for. When the visitor
	 *  jumps again the prop changes, this no longer matches, and it plays again — no
	 *  effect and no reset flag needed. */
	let playedFor = $state<string | null>(null);
	const showBang = $derived(era !== null && eraOpensWithBigBang(era) && playedFor !== date);

	const when = $derived(
		travel
			? era === 'copernicus'
				? `Anno Domini ${toRoman(travel.year)}`
				: travelLabel(travel)
			: ''
	);

	let jump = $state('');
	function go(e: SubmitEvent) {
		e.preventDefault();
		const d = parseTravel(jump);
		if (!d) return;
		jump = '';
		goto('/?czas=' + formatTravel(d));
	}
</script>

{#if !date.trim()}
	<p class="error">Nie podano daty w adresie (<code>?czas=</code>).</p>
	<p><a href="/">← Wróć do teraźniejszości</a></p>
{:else if !travel || era === null}
	<p class="error">
		Nie rozumiem daty „{date}”. Podaj rok (np. <code>2003</code>), rok z miesiącem
		(<code>2003-06</code>), pełną datę (<code>2003-06-14</code>) albo rok ujemny
		(<code>-66000000</code>).
	</p>
	<p><a href="/">← Wróć do teraźniejszości</a></p>
{:else}
	{#if showBang}
		<BigBang reverse={era === 'void'} onDone={() => (playedFor = date)} />
	{/if}

	<div class="strip">
		<div class="strip__inner">
			<span class="strip__what"><b>Wehikuł czasu</b> — {when}</span>
			<span class="strip__era">{eraLabel(era)}</span>
			<form class="strip__jump" onsubmit={go}>
				<label class="visually-hidden" for="tt-jump">Skocz do innej daty</label>
				<input
					id="tt-jump"
					type="text"
					inputmode="numeric"
					placeholder="np. 2003"
					bind:value={jump}
					size="9"
				/>
				<button type="submit" class="btn btn--sm">Jedź</button>
			</form>
			<a class="strip__back" href="/">Wróć do teraźniejszości</a>
		</div>
	</div>

	<!-- Rendered underneath the (opaque, fixed) overlay rather than after it, so the
	     slow parts of an era — the Internet Archive iframe above all — spend the two
	     seconds of the animation loading instead of waiting for it. -->
	<div class="era" inert={showBang}>
		{#if era === 'now'}
			<EraNow date={travel} />
		{:else if era === 'wayback'}
			<EraWayback date={travel} />
		{:else if era === 'paper_pl'}
			<EraPaper lang="pl" date={travel} />
		{:else if era === 'paper_de'}
			<EraPaper lang="de" date={travel} />
		{:else if era === 'copernicus'}
			<EraCopernicus date={travel} />
		{:else if era === 'prehistoric'}
			<EraPrehistoric variant="cave" />
		{:else if era === 'dinosaurs'}
			<EraPrehistoric variant="dinosaurs" />
		{:else}
			<EraPrehistoric variant="void" />
		{/if}
	</div>
{/if}

<style>
	/* The immersive eras break out of the 900 px column with `calc(50% - 50vw)`, which
	   overshoots by the width of the scrollbar. This clips that back — and because
	   Svelte removes a component's stylesheet with the component, it applies only while
	   the time machine is on screen. */
	:global(body) {
		overflow-x: hidden;
	}

	.strip {
		position: sticky;
		top: 0;
		z-index: 40;
		margin: 0 calc(50% - 50vw) 14px;
		width: 100vw;
		background: var(--green);
		color: #fff;
		border-bottom: 1px solid var(--green-dark);
	}
	.strip__inner {
		width: 92%;
		max-width: 900px;
		margin: 0 auto;
		padding: 6px 0;
		display: flex;
		align-items: center;
		gap: 12px;
		flex-wrap: wrap;
		font-size: 12px;
	}
	.strip__what {
		white-space: nowrap;
	}
	.strip__era {
		color: #cfe6df;
		font-style: italic;
	}
	.strip__jump {
		display: flex;
		gap: 4px;
		margin-left: auto;
	}
	.strip__jump input {
		width: 92px;
		padding: 2px 5px;
		font-size: 11px;
		border-color: var(--green-dark);
	}
	.strip__jump .btn {
		background: #fff;
		color: var(--green);
		border-color: var(--green-dark);
	}
	.strip__jump .btn:hover {
		background: var(--amber);
		color: #222;
	}
	.strip__back {
		color: #fff;
		text-decoration: underline;
		white-space: nowrap;
	}
	.strip__back:hover {
		color: var(--amber);
	}
	.era {
		min-height: 40vh;
	}
	@media (max-width: 560px) {
		.strip__jump {
			margin-left: 0;
		}
	}
</style>
