/** Koło AI: the shapes the API sends (backend/kolo_ai/views.py) and the member singleton. */
import { api, ApiError, getKoloSession, setKoloSession } from './api';

/** Mirrors backend/kolo_ai/rules.py CONSENT_VERSION — change both, and the consent text. */
export const CONSENT_VERSION = '2026-11-03';

export interface KoloMember {
	id: number; name: string; status: string; status_label: string; role: 'czlonek' | 'sympatyk';
	affiliation: 'student' | 'doktorant' | 'inny'; funkcja: string; zarzad: boolean; can_manage: boolean;
	email?: string; created_at?: string; email_confirmed_at?: string | null; approved_at?: string | null;
	uw_email?: boolean; problem_czlonek?: string | null;
}
export interface StatusEntry { id: number; title: string; body: string; published_at: string; status: string }
export interface PollResult {
	counts: number[]; voters: number; eligible: number; quorum: boolean; passed: boolean; winner: string | null; note: string;
}
export interface Poll {
	id: number; organ: 'walne' | 'zarzad'; organ_label: string; kind: 'uchwala' | 'wybory'; title: string;
	mode: 'jawne' | 'tajne'; majority: string; majority_label: string; trial: boolean; status: string;
	phase: 'draft' | 'announced' | 'open' | 'closed' | 'cancelled' | 'moved';
	opens_at: string; closes_at: string; announced_at: string | null; options: string[];
	body?: string; has_voted?: boolean; can_vote?: boolean; eligible_count?: number | null; objections?: number;
	objected?: boolean; my_vote?: number | null; result?: PollResult | null;
	named_votes?: { name: string; option: number }[] | null;
}

export const PHASE_LABEL: Record<Poll['phase'], string> = {
	draft: 'projekt', announced: 'zawiadomione — przed głosowaniem', open: 'trwa głosowanie',
	closed: 'zakończone', cancelled: 'odwołane', moved: 'przeniesione na zebranie'
};
export const AFFILIATION_LABEL = { student: 'student UW', doktorant: 'doktorant UW', inny: 'inna osoba (sympatyk)' };

/** A path inside the Koło app: `/glosowania` on ai.fuw.lol, `/ai/glosowania` anywhere else
 * (development). src/hooks.ts maps the first onto the second. */
export function kp(path = ''): string {
	const onAiHost = typeof location !== 'undefined' && location.hostname.startsWith('ai.');
	return onAiHost ? path || '/' : `/ai${path}`;
}

export function when(iso: string | null | undefined): string {
	if (!iso) return '—';
	return new Date(iso).toLocaleString('pl-PL', { dateStyle: 'medium', timeStyle: 'short' });
}

let me = $state<KoloMember | null>(null);
let ready = $state(false);

export const kolo = {
	get me() { return me; },
	get ready() { return ready; },
	get isVoter() { return me?.status === 'member' && me?.role === 'czlonek'; },
	get isManager() { return !!me?.can_manage; },
	async init() {
		if (getKoloSession()) {
			try { me = await api.get<KoloMember>('/kolo/me/'); }
			catch (e) { if (e instanceof ApiError && e.status === 401) setKoloSession(null); }
		}
		ready = true;
	},
	async openLink(token: string) {
		const r = await api.post<{ session: string; member: KoloMember }>('/kolo/link/', { token });
		setKoloSession(r.session); me = r.member;
		return r.member;
	},
	async logout() {
		try { await api.post('/kolo/logout/'); } catch { /* already gone */ }
		setKoloSession(null); me = null;
	}
};
