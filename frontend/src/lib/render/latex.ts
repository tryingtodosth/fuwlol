/** LaTeX → HTML in the browser with LaTeX.js (a real subset of LaTeX: document structure,
 * sectioning, lists, text macros, KaTeX math). There is no TeX engine on the server, so this
 * IS the compiler — the editor's "Recompile" runs it, and a post page runs it on read.
 *
 * `\includegraphics` is handled here, not by LaTeX.js: each occurrence becomes a marker
 * word that survives parsing as plain text, and is swapped for an <img> afterwards — which
 * also lets `width=0.5\textwidth` become a percentage the browser understands. */
import DOMPurify from 'dompurify';
import { hookSanitizer, trackingResolver, withAllowedImages } from './markdown';

export interface LatexResult { html: string; error: string | null; line?: number }

let lib: Promise<typeof import('latex.js')> | null = null;
function load() {
	lib ??= Promise.all([
		import('latex.js'),
		import('katex/dist/katex.min.css'),
		import('./latexjs.scoped.css') // LaTeX.js's own stylesheet, scoped — see scripts/scope-latexjs-css.mjs
	]).then(([m]) => m);
	return lib;
}

const MARK = 'FUWIMGMARK';

function graphicsWidth(opts: string): string | null {
	const m = /width\s*=\s*([0-9.]+)\s*\\(text|line|column)width/.exec(opts);
	if (m) return `${Math.round(parseFloat(m[1]) * 100)}%`;
	const cm = /width\s*=\s*([0-9.]+)\s*(cm|mm|in|pt|px)/.exec(opts);
	if (cm) return `${cm[1]}${cm[2] === 'pt' ? 'pt' : cm[2]}`;
	const sc = /scale\s*=\s*([0-9.]+)/.exec(opts);
	if (sc) return `${Math.round(parseFloat(sc[1]) * 100)}%`;
	return null;
}

export async function renderLatex(src: string, resolve: (name: string) => string | undefined,
	options: { images?: boolean } = {}): Promise<LatexResult> {
	const { parse, HtmlGenerator } = await load();
	if (options.images === false) {
		src = src.replace(/\\includegraphics\s*(\[[^\]]*\])?\s*\{[^}]*\}/g, '');
	}
	hookSanitizer();
	const seen = new Set<string>();
	const track = trackingResolver(resolve, seen);
	const images: { url?: string; name: string; width: string | null }[] = [];
	let body = src.replace(/\\includegraphics\s*(\[[^\]]*\])?\s*\{([^}]*)\}/g, (_m, opts, name) => {
		images.push({ url: track(name), name, width: graphicsWidth(opts || '') });
		return ` ${MARK}${images.length - 1}X `;
	});
	// LaTeX.js needs a document; a fragment pasted into a comment gets one wrapped around it.
	if (!/\\begin\{document\}/.test(body)) {
		body = `\\documentclass{article}\n\\begin{document}\n${body}\n\\end{document}`;
	}
	// packages LaTeX.js does not ship are dropped rather than fatal — amsmath etc. are what people type
	body = body.replace(/\\usepackage(\[[^\]]*\])?\{([^}]*)\}/g, (m, _o, pkgs: string) =>
		pkgs.split(',').every((p) => ['graphicx', 'hyperref', 'multicol', 'textcomp', 'stix', 'xcolor', 'echo'].includes(p.trim())) ? m : '');
	try {
		const gen = new HtmlGenerator({ hyphenate: false });
		parse(body, { generator: gen });
		const frag = gen.domFragment();
		const holder = document.createElement('div');
		holder.appendChild(frag);
		let html = holder.innerHTML;
		html = html.replace(new RegExp(`${MARK}(\\d+)X`, 'g'), (_m, i) => {
			const img = images[Number(i)];
			if (!img) return '';
			if (!img.url) return `<span class="latex-missing">(brak pliku: ${escapeHtml(img.name)})</span>`;
			const style = img.width ? ` style="width:${img.width}"` : '';
			return `<img class="latex-img" src="${img.url}" alt="${escapeHtml(img.name)}"${style}>`;
		});
		// LaTeX.js output is classed spans/divs with inline sizes (its scoped stylesheet reads
		// them) and KaTeX MathML, so the tag list stays DOMPurify's default minus anything
		// that is a page element rather than content; images follow the same allow-list as
		// Markdown (withAllowedImages), links get the same rel/target hook.
		html = withAllowedImages(options.images === false ? [] : seen, () => DOMPurify.sanitize(html, {
			ADD_ATTR: ['style'], FORBID_TAGS: ['style', 'form', 'input', 'button', 'textarea', 'select', 'iframe', 'object', 'embed'],
			FORBID_ATTR: ['srcset'], ALLOWED_URI_REGEXP: /^(?:https?:|mailto:|blob:|\/)/i
		}));
		return { html, error: null };
	} catch (e: unknown) {
		const err = e as { message?: string; location?: { start?: { line?: number } } };
		return { html: '', error: err.message || String(e), line: err.location?.start?.line };
	}
}

function escapeHtml(s: string) {
	return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] as string);
}
