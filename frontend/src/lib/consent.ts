/** „Jesteś tą osobą?” — the person a post is about registers their own wish.
 *
 * Everything the four consent screens know about the API lives here: the shapes, the
 * calls, and — because copy that exists twice drifts — the three wishes with the one-line
 * explanation each of them carries. `WISHES` is imported by the claim box, the settings
 * page and the staff queue, so the label a person ticks is literally the same string the
 * moderator later reads.
 *
 * Backend: backend/consent/ (rules.py is where every one of these decisions is made).
 * The Polish labels mirror `consent.rules.WISH_LABELS`; keep the two in step — that pair
 * is the usual place for a mirror like this to drift.
 */
import { api, qs } from '$lib/api';

export type Wish = 'images_ok' | 'no_images' | 'no_mention';
/** One `status` field, the way the backend keeps it: `sent` → `verified` → a decision. */
export type ClaimStatus = 'sent' | 'verified' | 'approved' | 'rejected' | 'superseded' | 'withdrawn';

export interface PersonRef {
	slug: string;
	full_name: string;
}

/** Plausibility signals for the staff queue — facts, not a score. Each has an obvious
 * failure mode (an address rarely matches a nickname), so the page prints them as they
 * are and lets a human weigh them. */
export interface ClaimSignals {
	domain_trusted: boolean;
	institution: string | null;
	name_tokens_in_local_part: boolean;
	account: string | null;
	earlier_claims: number;
}

export interface ClaimRow {
	id: number;
	person: PersonRef;
	email: string;
	wish: Wish;
	wish_label: string;
	note: string;
	status: ClaimStatus;
	created_at: string;
	verified_at: string | null;
	/** Null until the wish has actually been written onto the person and their posts —
	 * one nullable timestamp rather than a boolean, so "applied" cannot disagree with
	 * "when". */
	applied_at: string | null;
	decided_by: string | null;
	decided_at: string | null;
	decision_note: string;
	consent_text_version: string;
	signals: ClaimSignals;
}

export interface ConfirmResult {
	ok: boolean;
	wish: Wish;
	wish_label: string;
	/** Whether the wish took effect at once (a tightening wish from an institutional
	 * mailbox) or is waiting for a human. The page says which, in those words. */
	applied: boolean;
	person: PersonRef;
	message: string;
}

export interface ManageState {
	person: PersonRef;
	current_wish: Wish;
	current_wish_label: string;
	email_masked: string;
	consent_text_version: string;
}

export interface ClaimRequest {
	email: string;
	wish: Wish;
	note?: string;
	agree: true;
	/** The honeypot. Empty from every human; the server answers 202 either way. */
	website?: string;
}

export const WISHES: { value: Wish; label: string; hint: string }[] = [
	{
		value: 'images_ok',
		label: 'Zdjęcia ze mną mogą tu być',
		hint: 'Na Twojej stronie pojawi się odznaka „✓ zgoda na wizerunek”, a czytelnicy będą mogli zgłaszać do niej zdjęcia. Każdy wpis nadal można zgłosić osobno.'
	},
	{
		value: 'no_images',
		label: 'Wzmianki tak, zdjęć nie',
		hint: 'Wpisy z Twoim zdjęciem znikną ze strony i trafią do moderatora. Cytaty, anegdoty i wzmianki zostają.'
	},
	{
		value: 'no_mention',
		label: 'Nie chcę być w archiwum',
		hint: 'Ukryjemy wpisy z Twoim nazwiskiem i moderator przejrzy je po kolei; strona zniknie ze spisu.'
	}
];

export function wishLabel(wish: Wish): string {
	return WISHES.find((w) => w.value === wish)?.label ?? wish;
}

/** 202 with a masked address whatever happened behind it — sent, capped or a bot. The
 * page says "check your mail" and nothing else, because every other answer would be a way
 * to ask questions about somebody else's mailbox. */
export const requestClaim = (slug: string, body: ClaimRequest) =>
	api.post<{ sent_to: string }>(`/people/${slug}/claims/`, body);

export const confirmClaim = (token: string) => api.post<ConfirmResult>('/claims/confirm/', { token });

export const requestManageLink = (slug: string, email: string) =>
	api.post<{ sent_to: string }>(`/people/${slug}/claims/manage-link/`, { email });

export const loadManage = (token: string) => api.get<ManageState>(`/claims/manage/${qs({ token })}`);

/** Applies at once: the mailbox has already been checked by a human once, and RODO
 * art. 7 ust. 3 does not let a withdrawal be harder than the consent was. */
export const changeWish = (token: string, wish: Wish) =>
	api.post<{ ok: boolean; wish: Wish; wish_label: string; message: string }>('/claims/manage/', { token, wish });

export const withdrawClaim = (token: string) =>
	api.post<{ ok: boolean; message: string }>('/claims/manage/withdraw/', { token });

/** Staff only (`is_staff`) — deliberately not the trusted tier: confirming that a stranger
 * really is dr Kwant Niepewny is a different power from "hide this fast". */
export const loadClaimQueue = (status?: string) => api.get<ClaimRow[]>(`/claims/queue/${qs({ status })}`);

export const decideClaim = (id: number, decision: 'approve' | 'reject', note: string) =>
	api.post<ClaimRow>(`/claims/${id}/decide/`, { decision, note });
