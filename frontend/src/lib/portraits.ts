/** Portraits: the photograph at the top of a person's page, chosen by a vote.
 *
 * Thin helpers over `$lib/api` — the one fetch wrapper — plus the types the gallery and
 * the moderation queue both read. Nothing here decides anything: the backend rule module
 * (`backend/portraits/rules.py`) owns who may upload, who may vote and what is visible,
 * and hands back `upload_block_reason` as a Polish sentence for the page to print. A
 * component that re-derived "may I upload" from `consent` would be a second opinion, and
 * the two would disagree the first time the rules grew a case.
 *
 * `ImageConsent` is deliberately imported from `$lib/types` rather than re-declared: it is
 * the person's field, not the gallery's, and the badge on the profile draws the same
 * values (ConsentBadge.svelte).
 */
import { API_BASE, api, qs } from './api';
import type { ImageConsent } from './types';

/** One `status` field, the whole lifecycle — mirrors PORTRAIT_STATUS_CHOICES in
 * backend/portraits/models.py. Say so in both places when either changes. */
export type PortraitStatus = 'pending' | 'published' | 'rejected' | 'hidden';
export type PortraitDecision = 'publish' | 'reject' | 'hide' | 'restore';

export interface Portrait {
	id: number;
	/** Absolute — the API is a separate origin, so a relative /media path would resolve
	 * against the SPA's host. '' when the file is gone from storage. */
	url: string;
	caption: string;
	source_note: string;
	uploaded_by: string;
	status: PortraitStatus;
	votes: number;
	my_vote: boolean;
	created_at: string;
	can_moderate: boolean;
}

/** The winner, as the person page needs it: enough to draw the 130 px photo. */
export interface CurrentPortrait {
	id: number;
	url: string;
	caption: string;
}

/** How a gallery may be ordered, and which statuses a caller may ask for. Both mirror
 * `SORT_ORDERS` / `STATUS_FILTERS` in backend/portraits/rules.py — say so in both files.
 * A value outside these is a 400, not a quiet default, so do not widen one side alone. */
export type PortraitSort = 'votes' | 'new' | 'old';
export type PortraitStatusFilter = PortraitStatus | 'all';

/** What every paged answer in this app carries. `next` is an absolute URL that already
 * has the sort and the filter in it, so following it is the next page of the SAME
 * question — never rebuild it by hand. */
export interface PageBlock {
	count: number;
	offset: number;
	limit: number;
	next: string | null;
}

export interface PortraitsResponse extends PageBlock {
	consent: ImageConsent;
	can_upload: boolean;
	/** '' when the form may be shown; otherwise the line to print instead of it. */
	upload_block_reason: string;
	/** The winner of the WHOLE gallery — unaffected by sort, filter or page, because the
	 * profile photograph does not change with how a reader happens to be browsing. */
	current: CurrentPortrait | null;
	/** Echoed back so a component can trust the server's reading of its own query. */
	sort: PortraitSort;
	status: PortraitStatusFilter;
	mine: boolean;
	items: Portrait[];
}

/** A queue row spans every person, so it has to say whose face it is. */
export interface QueuePortrait extends Portrait {
	person: { slug: string; full_name: string };
}

export interface PortraitQueueResponse extends PageBlock {
	sort: 'new' | 'old';
	person: string;
	items: QueuePortrait[];
}

/** The gallery query. Everything is optional; the server's defaults are `sort=votes`,
 * `status=published`, `limit=12`. `mine` on its own widens the status to everything the
 * caller may see of their own uploads — "which of mine got through" is the question the
 * checkbox asks, and the pending ones are half the answer. */
export interface GalleryQuery {
	sort?: PortraitSort;
	status?: PortraitStatusFilter;
	mine?: boolean;
	offset?: number;
	limit?: number;
}

export interface QueueQuery {
	sort?: 'new' | 'old';
	person?: string;
	offset?: number;
	limit?: number;
}

/** The sort options, once, for both surfaces that draw a `<select>` of them. */
export const SORT_OPTIONS: { value: PortraitSort; label: string }[] = [
	{ value: 'votes', label: 'Najwięcej głosów' },
	{ value: 'new', label: 'Najnowsze' },
	{ value: 'old', label: 'Najstarsze' }
];

export const STATUS_OPTIONS: { value: PortraitStatusFilter; label: string }[] = [
	{ value: 'published', label: 'Opublikowane' },
	{ value: 'pending', label: 'Czekające' },
	{ value: 'hidden', label: 'Ukryte' },
	{ value: 'rejected', label: 'Odrzucone' },
	{ value: 'all', label: 'Wszystkie' }
];

export interface VoteResult {
	votes: number;
	my_vote: boolean;
	/** Who is winning now — a vote is the one action that can change the photograph at the
	 * top of the page, and the caller should not have to guess. */
	current_id: number | null;
}

/** The status pills, in one place because the gallery and the queue both draw them. */
export const PORTRAIT_STATUS_LABEL: Record<PortraitStatus, string> = {
	pending: 'czeka na moderację',
	published: 'opublikowane',
	rejected: 'odrzucone',
	hidden: 'ukryte'
};

/** The explainer every consent-shaped refusal points at. */
export const CONSENT_PAGE = '/ludzie/zgoda';

export function loadPortraits(slug: string, query: GalleryQuery = {}): Promise<PortraitsResponse> {
	return api.get<PortraitsResponse>(
		`/people/${encodeURIComponent(slug)}/portraits/${qs({
			sort: query.sort,
			status: query.status,
			mine: query.mine ? '1' : undefined,
			offset: query.offset,
			limit: query.limit
		})}`
	);
}

/** The next page of whatever was asked for. Takes the server's own `next` URL, which
 * already carries the sort, the filter and the offset — `api` wants a path, so the origin
 * and the /api prefix come back off. Anything else would be this file guessing at a query
 * string the server has already written down. */
export function loadMore<T extends PageBlock>(next: string): Promise<T> {
	const path = next.startsWith(API_BASE) ? next.slice(API_BASE.length) : new URL(next).pathname + new URL(next).search;
	return api.get<T>(path);
}

/** multipart {file, caption?, source_note?, rights_confirmed} — the declaration is
 * required, and its absence is a 400 rather than a 403: a malformed request, not a
 * refusal. */
export function uploadPortrait(slug: string, form: FormData): Promise<Portrait> {
	return api.post<Portrait>(`/people/${encodeURIComponent(slug)}/portraits/`, form);
}

export function votePortrait(id: number): Promise<VoteResult> {
	return api.post<VoteResult>(`/portraits/${id}/vote/`);
}

export function moderatePortrait(id: number, decision: PortraitDecision, note = ''): Promise<Portrait> {
	return api.post<Portrait>(`/portraits/${id}/moderate/`, { decision, note });
}

export function loadPortraitQueue(query: QueueQuery = {}): Promise<PortraitQueueResponse> {
	return api.get<PortraitQueueResponse>(
		`/portraits/queue/${qs({
			sort: query.sort,
			person: query.person,
			offset: query.offset,
			limit: query.limit
		})}`
	);
}
