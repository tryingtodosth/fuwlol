/** A body references its files by ORIGINAL name (`![](zdjecie.jpg)`, `\includegraphics{zdjecie.jpg}`).
 * The editor previews unsaved files through object URLs; a saved post maps names to stored URLs. */
export interface MediaRef { name: string; url: string; kind: string }

export function resolver(refs: MediaRef[]): (name: string) => string | undefined {
	const map = new Map(refs.map((r) => [r.name.toLowerCase(), r.url]));
	return (name: string) => {
		const n = name.trim().replace(/^\.\//, '').toLowerCase();
		if (map.has(n)) return map.get(n);
		// a name written without its extension (LaTeX habit) still resolves
		for (const [k, v] of map) if (k.replace(/\.[a-z0-9]+$/, '') === n) return v;
		return undefined;
	};
}
