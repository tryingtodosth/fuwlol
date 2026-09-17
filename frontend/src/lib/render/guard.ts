/** The browser-side twin of backend/archive/latexguard.py: the editor refuses a macro bomb
 * before the upload does, and the READER refuses to compile one that somehow got stored
 * (an old row, the Django admin). LaTeX.js runs on the main thread and cannot be
 * interrupted, so `\def\x{\x\x}\x` would freeze the tab of everybody who opens the post.
 * The rules must stay identical on both sides; the server's copy is the one that counts. */
export const MAX_POST_CHARS = 60_000;
export const MAX_COMMENT_CHARS = 10_000;
const MAX_ENVIRONMENTS = 400;
const FORBIDDEN = /\\(def|edef|gdef|xdef|let|futurelet|csname|expandafter|loop|catcode|noexpand|afterassignment|aftergroup|input|include|write|openout)\b/;
const NEWCOMMAND = /\\(?:re)?newcommand\*?\s*\{?\\([A-Za-z@]+)\}?/g;
const NEWENV = /\\(?:re)?newenvironment\*?\s*\{([A-Za-z@*]+)\}/g;

function definitionBody(src: string, start: number): string {
	let i = start;
	while (i < src.length && /\s/.test(src[i])) i++;
	while (i < src.length && src[i] === '[') {
		const j = src.indexOf(']', i);
		if (j === -1) return '';
		i = j + 1;
		while (i < src.length && /\s/.test(src[i])) i++;
	}
	if (i >= src.length || src[i] !== '{') return '';
	let depth = 0;
	for (let j = i; j < src.length; j++) {
		if (src[j] === '{' && src[j - 1] !== '\\') depth++;
		else if (src[j] === '}' && src[j - 1] !== '\\') { depth--; if (depth === 0) return src.slice(i + 1, j); }
	}
	return '';
}

/** null when fine, otherwise the message to show. */
export function checkSource(src: string, maxChars = MAX_POST_CHARS): string | null {
	if (src.length > maxChars) return `Za długa treść (limit ${maxChars} znaków).`;
	const bad = FORBIDDEN.exec(src);
	if (bad) return `Makra \\${bad[1]} nie są tu obsługiwane — ze względów bezpieczeństwa treść nie może definiować własnych poleceń TeX-a.`;
	for (const m of src.matchAll(NEWCOMMAND)) {
		const name = m[1];
		const body = definitionBody(src, m.index + m[0].length);
		if (new RegExp('\\\\' + name + '(?![A-Za-z@])').test(body)) return `Polecenie \\${name} odwołuje się do samego siebie — takie makro zawiesiłoby przeglądarkę czytelnika.`;
	}
	for (const m of src.matchAll(NEWENV)) {
		const name = m[1];
		if (src.slice(m.index + m[0].length, m.index + m[0].length + 2000).includes(`\\begin{${name}}`)) return `Środowisko ${name} odwołuje się do samego siebie.`;
	}
	if ((src.match(/\\begin\{/g) || []).length > MAX_ENVIRONMENTS) return `Za dużo środowisk \\begin{…} (limit ${MAX_ENVIRONMENTS}).`;
	return null;
}
