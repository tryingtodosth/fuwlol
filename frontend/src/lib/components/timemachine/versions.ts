/** Every look fuw.lol has ever had.
 *
 * This is what makes "check how the website used to work" more than a phrase: the time
 * machine does not restyle today's page for an old date, it MOUNTS THE COMPONENT that
 * was the site on that date. Today there is exactly one entry, so every date from the
 * launch onwards renders v1 — the registry earns its keep on the day of the first
 * redesign.
 *
 * Adding a version, in full:
 *   1. copy the current version component to a new file (VersionV2.svelte), change that;
 *   2. LEAVE VersionV1.svelte alone — it is a historical record now, not live code;
 *   3. append `{ id: 'v2', from: '<the day it went live>', label: '…', component: VersionV2 }`.
 * `versionFor` then picks the last entry whose `from` is on or before the travelled date.
 */
import type { Component } from 'svelte';
import { parseTravel, type TravelDate } from './eras';
import VersionV1 from './VersionV1.svelte';

export interface SiteVersion {
	id: string;
	/** The day this look went live, `YYYY-MM-DD`. */
	from: string;
	label: string;
	component: Component<{ date: TravelDate }>;
}

/** Oldest first. */
export const SITE_VERSIONS: SiteVersion[] = [
	{
		id: 'v1',
		from: '2026-09-10',
		label: 'Wersja 1 — w stylu fuw.edu.pl',
		component: VersionV1
	}
];

function rank(d: TravelDate): number {
	// Safe here and nowhere else: every version's `from` is a real modern date, so a
	// plain year*10000 key orders them without dragging in the full comparison.
	return d.year * 10000 + (d.month ?? 12) * 100 + (d.day ?? 31);
}

/** The look the site had on that date; the oldest version for anything earlier. */
export function versionFor(date: TravelDate): SiteVersion {
	const want = rank(date);
	let chosen = SITE_VERSIONS[0];
	for (const v of SITE_VERSIONS) {
		const from = parseTravel(v.from);
		if (from && rank(from) <= want) chosen = v;
	}
	return chosen;
}
