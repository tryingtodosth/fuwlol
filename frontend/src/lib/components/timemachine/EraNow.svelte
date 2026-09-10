<!-- Era 1: our own archive, as it stood on the chosen day. The look is NOT decided
     here — versions.ts owns that, so a date from before a future redesign mounts the
     component the site actually used then. -->
<script lang="ts">
	import type { TravelDate } from './eras';
	import { versionFor } from './versions';

	let { date }: { date: TravelDate } = $props();

	const version = $derived(versionFor(date));
	const Look = $derived(version.component);
</script>

<Look {date} />

<p class="stamp-line small muted">
	Wygląd strony: {version.label}
</p>

<style>
	.stamp-line {
		margin-top: 14px;
		padding-top: 8px;
		border-top: 1px dotted var(--line);
	}
</style>
