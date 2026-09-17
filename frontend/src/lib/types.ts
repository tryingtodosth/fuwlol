export type Format = 'text' | 'latex';
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
export interface Person { slug: string; name: string; role: string; bio: string; post_count: number }
export interface Tag { slug: string; name: string; post_count: number }
export interface Attachment { id: number; url: string; original_name: string; kind: 'image' | 'pdf' | 'audio' | 'video' | 'other'; caption?: string; order: number }
export interface PostSummary {
	id: number; slug: string; catalog_no: string; title: string; summary: string; category: string; category_name: string;
	format: Format; year: number | null; year_precision: 'exact' | 'approx' | 'decade' | 'unknown'; date_note: string;
	people: Person[]; tags: Tag[]; submitted_by: string; status: Status; featured: boolean; views: number;
	cover: string | null; reaction_counts: Record<ReactionKind, number>; comment_count: number;
	published_at: string | null; created_at: string;
}
export interface Post extends PostSummary {
	body: string; source_note: string; source_url: string; attachments: Attachment[];
	my_reaction: ReactionKind | null; can_edit: boolean; review_note: string;
	can_moderate?: boolean; moderation_notice?: string | null; moderation?: ModerationBlock | null;
	reports?: { id: number; reason: string; note: string; contact_email: string; created_at: string }[];
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
