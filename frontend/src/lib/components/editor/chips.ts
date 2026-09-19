/** What a picker holds, and how a chip turns back into something the API understands.
 *
 * A chip is either somebody/something that already exists (it has a `slug`) or a name the
 * writer just typed (`isNew`, no slug yet). That distinction is the whole feature: the old
 * editor could only tick people who were already in the database, the help text said „Brak
 * osoby? Wpisz ją w tagach", and nothing ever promoted such a tag to a person — so /ludzie
 * stood still from launch day.
 *
 * The folding here mirrors `normalize_text` in backend/archive/search.py (lowercase, no
 * diacritics, ł → l, everything else to spaces). It is used ONLY to stop the same name being
 * added to one post twice before it is sent; the authoritative de-duplication is the
 * backend's `name_key`, which is what decides whether a typed name is a new person or an old
 * one. Say so in both files if either fold changes.
 */
import type { Person, Subject, Tag } from '$lib/types';

export interface Chip {
	slug?: string;
	name: string;
	isNew?: boolean;
	degree?: string;
	role?: string;
	consent?: string;
	/** A person's nicknames, joined for display. Shown in the picker's option row because
	 * half the archive knows a lecturer only by one — „Hamiltonianka” is how you recognise
	 * prof. Hamiltonian, and a list that hid that would have you typing her in again. */
	aliases?: string;
}

export function fold(s: string): string {
	return s
		.toLocaleLowerCase('pl')
		.replace(/ł/g, 'l')
		.normalize('NFD')
		.replace(/[̀-ͯ]/g, '')
		.replace(/[^0-9a-z]+/g, ' ')
		.trim();
}

/** What makes two chips the same chip in one picker. */
export function chipKey(c: Chip): string {
	return c.slug ? 's:' + c.slug : 'n:' + fold(c.name);
}

export function hasChip(chips: Chip[], c: Chip): boolean {
	const k = chipKey(c);
	return chips.some((x) => chipKey(x) === k);
}

export function personChip(p: Person): Chip {
	return {
		slug: p.slug,
		name: p.full_name || p.name,
		role: p.role,
		consent: p.image_consent,
		aliases: (p.aliases ?? []).map((a) => a.name).join(', ')
	};
}
export function subjectChip(s: Subject): Chip {
	return { slug: s.slug, name: s.name, role: s.short };
}
export function tagChip(t: Tag): Chip {
	return { slug: t.slug, name: t.name };
}

/** `people` on the wire: a slug for somebody who exists, an object for somebody who does
 * not. `archive/people.resolve_people` reads exactly this and decides which is which — a
 * typed name that matches an existing person is reused there, not here, because only the
 * database knows who is already in it. */
export function peoplePayload(chips: Chip[]): (string | { name: string; degree: string; role: string })[] {
	return chips.map((c) =>
		c.slug ? c.slug : { name: c.name, degree: c.degree ?? '', role: c.role ?? '' }
	);
}

/** `subjects` and `tags` on the wire: plain names. A slug folds to itself on the backend
 * (`subjects.subject_slug`), so sending the visible name works for both halves of a chip. */
export function namePayload(chips: Chip[]): string[] {
	return chips.map((c) => c.name);
}
