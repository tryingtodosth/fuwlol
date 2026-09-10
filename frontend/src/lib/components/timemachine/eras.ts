/** The time machine's arithmetic, and nothing else: parsing a date the user typed,
 * putting it on the timeline, and naming what they will see. Kept free of Svelte and
 * of `fetch` so the boundaries can be unit-tested by calling `eraFor` directly.
 *
 * A travelled date is deliberately NOT a `Date`: the picker must reach years like
 * -13 800 000 000, which no calendar type handles. It is a year plus optional month
 * and day, and a missing part means "the whole period", so a date is compared at the
 * END of what it names — "2003" is the last moment of 2003, not its first. That is
 * what makes "show me the site in 2003" mean "as it stood when 2003 finished".
 */

export interface TravelDate {
	/** Negative = BC / years before the present. May be enormous (-13.8e9). */
	year: number;
	/** 1-12, or undefined for "the whole year". */
	month?: number;
	/** 1-31, or undefined for "the whole month". */
	day?: number;
}

export type Era =
	| 'now' // our own archive, as it stood on that day
	| 'wayback' // fuw.edu.pl in the Internet Archive
	| 'paper_pl' // a printed Polish newspaper
	| 'paper_de' // the same paper, in German (Warsaw under Prussia)
	| 'copernicus' // Latin, as handwritten notes
	| 'prehistoric' // cave painting
	| 'dinosaurs' // a comet, and something looking up at it
	| 'void'; // before the Big Bang

/** fuw.lol went live. Anything from this day on is OUR archive. */
export const SITE_LAUNCH: TravelDate = { year: 2026, month: 9, day: 10 };
/** The Internet Archive's first capture of fuw.edu.pl (matches EARLIEST in backend/archive/wayback.py). */
export const WAYBACK_EARLIEST: TravelDate = { year: 1998, month: 1, day: 20 };
/** The University of Warsaw is founded — before this there is no faculty to report on. */
export const UW_FOUNDED: TravelDate = { year: 1816, month: 1, day: 1 };
/** The third partition: Warsaw passes to Prussia, so the local press prints in German. */
export const PRUSSIAN_WARSAW: TravelDate = { year: 1795, month: 1, day: 1 };
/** Far enough back that a printed newspaper is an anachronism and a manuscript is not. */
export const COPERNICUS_FROM: TravelDate = { year: 1400, month: 1, day: 1 };
/** Roughly when the cave paintings we are imitating start. */
export const HUMANS_FROM: TravelDate = { year: -100000, month: 1, day: 1 };
/** t = 0. At or before it there is no "when" to travel to. */
export const BIG_BANG_YEAR = -13_800_000_000;

type Ymd = readonly [number, number, number];

/** Days in a month, without going through `Date` — which cannot represent year 1543. */
export function daysInMonth(year: number, month: number): number {
	if (month === 2) return (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0 ? 29 : 28;
	return [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1] ?? 31;
}

/** The last moment the date names: "1998" ends on 1998-12-31, "1998-01" on 1998-01-31. */
function endOf(d: TravelDate): Ymd {
	const month = d.month ?? 12;
	return [d.year, month, d.day ?? daysInMonth(d.year, month)];
}

/** A boundary constant, which always spells out all three parts. */
function at(d: TravelDate): Ymd {
	return [d.year, d.month ?? 1, d.day ?? 1];
}

function cmp(a: Ymd, b: Ymd): number {
	return a[0] - b[0] || a[1] - b[1] || a[2] - b[2];
}

/**
 * The one place a date becomes an era. Boundaries, inclusive on the left:
 *
 *   void        year <= -13 800 000 000
 *   dinosaurs   -13 800 000 000 <  date <  -100000
 *   prehistoric -100000         <= date <  1400-01-01
 *   copernicus  1400-01-01      <= date <  1795-01-01
 *   paper_de    1795-01-01      <= date <  1816-01-01
 *   paper_pl    1816-01-01      <= date <  1998-01-20
 *   wayback     1998-01-20      <= date <  2026-09-10
 *   now         2026-09-10      <= date
 */
export function eraFor(date: TravelDate): Era {
	// Checked on the year alone: at this scale a month is noise, and it keeps the Big Bang
	// itself on the "nothing" side of the line, as `void`'s own copy claims.
	if (date.year <= BIG_BANG_YEAR) return 'void';
	const t = endOf(date);
	if (cmp(t, at(SITE_LAUNCH)) >= 0) return 'now';
	if (cmp(t, at(WAYBACK_EARLIEST)) >= 0) return 'wayback';
	if (cmp(t, at(UW_FOUNDED)) >= 0) return 'paper_pl';
	if (cmp(t, at(PRUSSIAN_WARSAW)) >= 0) return 'paper_de';
	if (cmp(t, at(COPERNICUS_FROM)) >= 0) return 'copernicus';
	if (cmp(t, at(HUMANS_FROM)) >= 0) return 'prehistoric';
	return 'dinosaurs';
}

/** True when the era's first act is the Big Bang animation. Everything but our own archive. */
export function eraOpensWithBigBang(era: Era): boolean {
	return era !== 'now';
}

const TRAVEL_RE = /^(-?\d{1,15})(?:-(\d{1,2})(?:-(\d{1,2}))?)?$/;

/**
 * Accepts `YYYY-MM-DD`, `YYYY-MM`, `YYYY` and the same three with a leading `-` for BC.
 * Returns null for anything else, including an impossible month or day — a URL somebody
 * typed by hand is untrusted input like any other.
 */
export function parseTravel(s: string): TravelDate | null {
	const m = TRAVEL_RE.exec((s ?? '').trim());
	if (!m) return null;
	const year = Number(m[1]);
	if (!Number.isFinite(year)) return null;
	if (m[2] === undefined) return { year };
	const month = Number(m[2]);
	if (month < 1 || month > 12) return null;
	if (m[3] === undefined) return { year, month };
	const day = Number(m[3]);
	if (day < 1 || day > daysInMonth(year, month)) return null;
	return { year, month, day };
}

/** The inverse of `parseTravel`, and what goes in `?czas=`. */
export function formatTravel(d: TravelDate): string {
	const year = d.year < 0 ? String(d.year) : String(d.year).padStart(4, '0');
	if (d.month === undefined) return year;
	const month = String(d.month).padStart(2, '0');
	if (d.day === undefined) return `${year}-${month}`;
	return `${year}-${month}-${String(d.day).padStart(2, '0')}`;
}

/**
 * A real calendar day for the APIs that need one (`/posts/?before=`, `/wayback/?date=`),
 * taken at the END of the period so "2003" asks for the site as 2003 finished. Only
 * meaningful for years 1-9999, which is every era that talks to a server.
 */
export function toISODate(d: TravelDate): string {
	const month = d.month ?? 12;
	const day = Math.min(d.day ?? 31, daysInMonth(d.year, month));
	return `${String(d.year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

const ROMAN: [number, string][] = [
	[1000, 'M'], [900, 'CM'], [500, 'D'], [400, 'CD'], [100, 'C'], [90, 'XC'],
	[50, 'L'], [40, 'XL'], [10, 'X'], [9, 'IX'], [5, 'V'], [4, 'IV'], [1, 'I']
];

/** Roman numerals for the manuscript's date line. Years above 3999 simply repeat M. */
export function toRoman(year: number): string {
	let n = Math.floor(Math.abs(year));
	if (n === 0) return 'N'; // nulla, the medieval word for it
	let out = '';
	for (const [value, sign] of ROMAN) {
		while (n >= value) {
			out += sign;
			n -= value;
		}
	}
	return out;
}

function plNumber(n: number): string {
	return n.toLocaleString('pl-PL', { maximumFractionDigits: 1 });
}

/** How the chosen date reads in the green strip: a date, or a distance backwards. */
export function travelLabel(d: TravelDate): string {
	if (d.year < 0) {
		// Read back exactly as it was typed, so the strip and the URL never disagree.
		const ago = -d.year;
		if (ago >= 1e9) return `${plNumber(ago / 1e9)} mld lat temu`;
		if (ago >= 1e6) return `${plNumber(ago / 1e6)} mln lat temu`;
		return `${ago.toLocaleString('pl-PL')} p.n.e.`;
	}
	const year = String(d.year);
	if (d.month === undefined) return `rok ${year}`;
	const month = String(d.month).padStart(2, '0');
	if (d.day === undefined) return `${month}.${year}`;
	return `${String(d.day).padStart(2, '0')}.${month}.${year}`;
}

const ERA_LABELS: Record<Era, string> = {
	now: 'nasze archiwum',
	wayback: 'fuw.edu.pl w Internet Archive',
	paper_pl: 'gazeta drukowana',
	paper_de: 'gazeta drukowana (po niemiecku)',
	copernicus: 'rękopis łaciński',
	prehistoric: 'malowidło naskalne',
	dinosaurs: 'era dinozaurów',
	void: 'przed Wielkim Wybuchem'
};

export function eraLabel(era: Era): string {
	return ERA_LABELS[era];
}
