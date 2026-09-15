export interface BoardMessage {
	id: number; nick: string; is_guest: boolean; author_id: number | null; format: 'text' | 'latex';
	body: string; created_at: string; is_hidden: boolean; can_hide: boolean;
	open_reports: number | null; // null unless the caller may moderate (server-side hidden otherwise)
}
export interface BoardPage { count: number; latest_id: number; results: BoardMessage[] }

export const REPORT_REASONS: { value: string; label: string }[] = [
	{ value: 'spam', label: 'Spam' },
	{ value: 'offensive', label: 'Obraźliwe' },
	{ value: 'illegal', label: 'Niezgodne z prawem' },
	{ value: 'privacy', label: 'Dotyczy mnie' },
	{ value: 'other', label: 'Inne' }
];
export const MAX_LEN = 2048; // 2^11
export const PREVIEW_CHARS = 100;

/** The first 100 characters of a message, never cut inside an unclosed `$…$`. */
export function excerpt(body: string): { head: string; rest: boolean } {
	const chars = Array.from(body);
	if (chars.length <= PREVIEW_CHARS) return { head: body, rest: false };
	let cut = PREVIEW_CHARS;
	const before = chars.slice(0, cut).join('');
	const dollars = (before.match(/\$/g) || []).length;
	if (dollars % 2 === 1) cut = before.lastIndexOf('$');
	if (cut <= 0) cut = PREVIEW_CHARS;
	return { head: chars.slice(0, cut).join(''), rest: true };
}

export function stamp(iso: string): string {
	const d = new Date(iso);
	const p = (n: number) => String(n).padStart(2, '0');
	return `${p(d.getDate())}.${p(d.getMonth() + 1)} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
