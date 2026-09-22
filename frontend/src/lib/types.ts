export type Format = 'text' | 'latex';
/** The lock badge, shown wherever a post is listed. One constant, four call sites. */
export const LOCK_PILL = '🔒 Dla zweryfikowanych';
export type Status = 'pending' | 'published' | 'rejected' | 'hidden' | 'nuked';
export type ReactionKind = 'lol' | 'classic' | 'wow' | 'cringe';

export interface Affiliation { institution: string; domain: string; email_masked: string; verified_at: string }
export interface User {
	id: number; username: string; email: string; is_staff: boolean; is_superuser?: boolean; date_joined: string;
	reputation?: number; is_trusted?: boolean; affiliation?: Affiliation | null; pending_verification?: string | null;
}
export type ModerationState = 'visible' | 'hidden' | 'nuked';
export interface ModerationBlock { actor: string; reason: string; at: string | null; action?: string }
export interface Category { slug: string; name: string; description: string; emoji: string; post_count: number }
export type Sex = 'm' | 'f' | '';
/** What the person THEMSELF said about their image — see ConsentBadge.svelte and /ludzie/zgoda. */
export type ImageConsent = 'unknown' | 'granted' | 'refused' | 'opted_out';
/** A nickname: an ordinary tag that makes a tagged post the person's post (archive/people.py). */
export interface PersonAlias { slug: string; name: string }
export interface Person {
	slug: string; name: string; full_name: string; degree: string; surname: string; letter: string;
	role: string; unit: string; bio: string; sex: Sex; image_consent: ImageConsent; aliases: PersonAlias[];
	// from the directory/profile endpoints only — absent when a Person is embedded in a post
	post_count?: number; year_min?: number | null; year_max?: number | null;
	/** Moderation queue only (ModerationPostSerializer): this post's submitter named them,
	 * and nothing published mentions them yet — so publishing is also what puts them in
	 * /ludzie. Absent everywhere else. */
	is_new?: boolean;
}
export interface Tag { slug: string; name: string; post_count: number }
/** A university subject (*przedmiot*) — the third filing axis, next to tags and people.
 * Mirrors archive/models.py::Subject and archive/serializers.py::SubjectSerializer; say so
 * in both places if either moves. `post_count` is present on /subjects/ and absent when the
 * subject is embedded in a post, exactly like a Person's. */
export interface Subject { slug: string; name: string; short: string; post_count?: number }
export interface Attachment { id: number; url: string; original_name: string; kind: 'image' | 'pdf' | 'audio' | 'video' | 'other'; caption?: string; order: number }
export interface PostSummary {
	id: number; slug: string; catalog_no: string; title: string; summary: string; category: string; category_name: string;
	format: Format; year: number | null; year_precision: 'exact' | 'approx' | 'decade' | 'unknown'; date_note: string;
	people: Person[]; subjects?: Subject[]; tags: Tag[]; submitted_by: string; status: Status; featured: boolean; views: number;
	cover: string | null; reaction_counts: Record<ReactionKind, number>; comment_count: number;
	published_at: string | null; created_at: string;
	/** „Kontrowersyjne" — mirrors archive/models.py::Post.trusted_only. Public: the badge
	 * says so on every card, to everybody. */
	trusted_only: boolean;
	/** Derived by the server per caller (archive/moderation.can_read_body): THIS reader may
	 * not see body, summary, cover, files, filing or comments. **Never re-derive it from
	 * `trusted_only` here** — the author's own exception lives in that rule and nowhere
	 * else, and a second definition would drift from it. */
	locked: boolean;
}
export interface Post extends PostSummary {
	body: string; source_note: string; source_url: string; attachments: Attachment[];
	my_reaction: ReactionKind | null; can_edit: boolean; review_note: string;
	can_moderate?: boolean; moderation_notice?: string | null; moderation?: ModerationBlock | null;
	/** The Polish sentence to show in place of the body, written by archive/moderation.py
	 * (LOCKED_NOTICE) and displayed verbatim; null when the reader may read the post. */
	lock_notice?: string | null;
	reports?: { id: number; reason: string; note: string; contact_email: string; created_at: string; formal?: boolean }[];
}
export interface Comment {
	id: number; author: string; author_id: number; parent: number | null; format: Format; body: string;
	attachments: Attachment[]; is_removed: boolean; moderation?: ModerationState; created_at: string;
}
export interface Page<T> { count: number; next: string | null; previous: string | null; results: T[] }

export const REACTIONS: { kind: ReactionKind; emoji: string; label: string }[] = [
	{ kind: 'lol', emoji: '😂', label: 'lol' },
	{ kind: 'classic', emoji: '🏛️', label: 'klasyk' },
	{ kind: 'wow', emoji: '😮', label: 'wow' },
	{ kind: 'cringe', emoji: '😬', label: 'cringe' }
];

export function yearLabel(p: { year: number | null; year_precision: string }): string {
	if (p.year == null) return 'rok nieznany';
	switch (p.year_precision) {
		case 'exact': return String(p.year);
		case 'approx': return `ok. ${p.year}`;
		case 'decade': return `lata ${Math.floor(p.year / 10) * 10}.`;
		default: return `${p.year}?`;
	}
}
export function fmtDate(iso: string | null): string {
	if (!iso) return '';
	return new Date(iso).toLocaleDateString('pl-PL', { year: 'numeric', month: 'long', day: 'numeric' });
}

/** escalation app — head-admin only (is_superuser). See backend/escalation/. */
export type EscalationStatus = 'pending' | 'approved' | 'declined';
export interface EvidenceFile { name: string; stored_as: string; sha256: string }
export interface EvidenceManifest {
	kind: 'Post' | 'Comment' | 'Message'; pk: number; captured_at: string; created_at: string; files: EvidenceFile[];
	title?: string; body?: string; format?: Format; status?: string; catalog_no?: string; nick?: string; post_id?: number; ip_hash?: string;
	submitted_by?: { id: number; username: string; email: string; date_joined: string } | null;
	author?: { id: number; username: string; email: string; date_joined: string } | null;
}
export interface Escalation {
	id: number; kind: 'post' | 'comment' | 'message'; object_id: number; requested_by: string | null; reason: string;
	status: EscalationStatus; decided_by: string | null; decision_note: string; evidence_ref: string;
	created_at: string; decided_at: string | null; evidence?: EvidenceManifest | null;
}
