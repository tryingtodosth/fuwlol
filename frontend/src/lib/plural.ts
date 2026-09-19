/** Polish plural forms: plural(1, 'wpis', 'wpisy', 'wpisów') → 'wpis'; 2–4 → 'wpisy' (but 12–14
 * → 'wpisów', like every teen); everything else → 'wpisów'. The earlier `n === 1 ? … : …`
 * printed „3 wpisów”, which no Pole has ever said.
 * Mirrored in backend/share/previews.py (`plural`), which conjugates the same nouns for the
 * link previews a scraper reads — change one, change the other, or a shared link says
 * „3 wpisów” while the page it opens says „3 wpisy”. */
export function plural(n: number, one: string, few: string, many: string): string {
	const m10 = n % 10;
	const m100 = n % 100;
	if (n === 1) return one;
	if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
	return many;
}
