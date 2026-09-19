<script lang="ts">
	/** The post editor. Metadata, one shared file tray, and two ways of writing: Markdown with a
	 * live preview, or LaTeX compiled in the browser by LaTeX.js in an Overleaf-shaped split
	 * (project files | source | compiled page).
	 *
	 * The body refers to its files by NAME, so the tray's "Wstaw" button is the only thing a
	 * writer has to learn — and it is why names are normalised on the way in: a space in a file
	 * name silently breaks `![](a b.jpg)`, and two files called `zdjecie.jpg` make the reference
	 * ambiguous. Both are fixed when the file is picked, and the tray always shows the name the
	 * body should use. */
	import { onDestroy, onMount, tick, untrack } from 'svelte';
	import { api, ApiError } from '$lib/api';
	import type { Attachment, Category, Format, Post } from '$lib/types';
	import { renderMarkdown, typeset } from '$lib/render/markdown';
	import { renderLatex } from '$lib/render/latex';
	import { resolver, type MediaRef } from '$lib/render/media';
	import TagPicker from './TagPicker.svelte';
	import { type Chip, namePayload, peoplePayload, personChip, subjectChip, tagChip } from './chips';

	let { initial = null, onSaved }: { initial?: Post | null; onSaved: (post: Post) => void } = $props();

	/** The post being edited, snapshotted once: the editor owns the form from here on, and a
	 * later prop change must not throw away what somebody has typed. */
	const seed: Post | null = untrack(() => initial);

	const MAX_FILES = 6;
	const MAX_BYTES = 25 * 1024 * 1024;
	const ALLOWED_EXT = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'pdf', 'mp3', 'ogg', 'm4a', 'wav', 'mp4', 'webm', 'txt', 'tex'];
	const ACCEPT = ALLOWED_EXT.map((e) => '.' + e).join(',');
	const LINE_H = 18;
	const DRAFT_KEY = 'fuwlol.draft';
	const TEMPLATE =
		'\\documentclass{article}\n\\usepackage{amsmath}\n\\usepackage{graphicx}\n\\begin{document}\n\\section*{Tytuł}\nTreść…\n\\end{document}\n';

	interface NewFile { id: number; file: File; name: string; caption: string; kind: Attachment['kind']; url: string }
	/** The draft kept in localStorage. `ppl`/`sub`/`tg` are chip lists now; drafts written
	 * before the pickers existed hold `ppl` as a list of slugs and `tg` as one comma-separated
	 * string, and `chipsFrom` reads both so an unsaved post survives the upgrade. */
	interface Draft { t: string; c: string; f: Format; b: string; s: string; y: string; yp: string; dn: string; sn: string; su: string; ppl: Chip[]; sub: Chip[]; tg: Chip[]; at: number }

	/* ---------- form state ---------- */
	let title = $state(seed?.title ?? '');
	let category = $state(seed?.category ?? '');
	let format = $state<Format>(seed?.format ?? 'text');
	let body = $state(seed?.body ?? '');
	let summary = $state(seed?.summary ?? '');
	let yearText = $state(seed?.year != null ? String(seed.year) : '');
	let yearPrec = $state<string>(seed?.year_precision ?? 'approx');
	let dateNote = $state(seed?.date_note ?? '');
	let sourceNote = $state(seed?.source_note ?? '');
	let sourceUrl = $state(seed?.source_url ?? '');
	let rightsOk = $state(!!seed); // an edit does not re-ask; a new post must declare
	let peopleChips = $state<Chip[]>(seed?.people.map(personChip) ?? []);
	let subjectChips = $state<Chip[]>(seed?.subjects?.map(subjectChip) ?? []);
	let tagChips = $state<Chip[]>(seed?.tags.map(tagChip) ?? []);

	let categories = $state<Category[]>([]);
	let metaError = $state<string | null>(null);

	let savedAtt = $state<Attachment[]>(seed ? [...seed.attachments] : []);
	let removeIds = $state<number[]>([]);
	let newFiles = $state<NewFile[]>([]);
	let fileSeq = 0;
	let fileError = $state<string | null>(null);

	let saving = $state(false);
	let error = $state<string | null>(null);
	let formatNotice = $state('');
	let formatWarned = false;
	let draftOffer = $state<Draft | null>(null);

	/* ---------- editor plumbing ---------- */
	let taText = $state<HTMLTextAreaElement | null>(null);
	let taTex = $state<HTMLTextAreaElement | null>(null);
	let gutterEl = $state<HTMLDivElement | null>(null);
	let previewEl = $state<HTMLDivElement | null>(null);
	let tabEscapes = $state(false);
	// an unfocused textarea still reports caret 0, so "Wstaw" would prepend to an existing
	// post instead of appending; until somebody puts the caret somewhere, the end is the
	// honest guess
	let caretTouched = false;

	let previewHtml = $state('');
	let mdTimer: ReturnType<typeof setTimeout> | undefined;

	let latexHtml = $state('');
	let latexError = $state<string | null>(null);
	let latexLine = $state<number | null>(null);
	let compiling = $state(false);
	let autoCompile = $state(true);
	let logOpen = $state(true);
	let texTimer: ReturnType<typeof setTimeout> | undefined;
	let texRun = 0;

	/* ---------- derived ---------- */
	// two textareas, two refs: one shared `bind:this` can be nulled by the outgoing branch
	const taEl = $derived(format === 'latex' ? taTex : taText);
	const keptSaved = $derived(savedAtt.filter((a) => !removeIds.includes(a.id)));
	const fileCount = $derived(keptSaved.length + newFiles.length);
	const mediaRefs = $derived<MediaRef[]>([
		...keptSaved.map((a) => ({ name: a.original_name, url: a.url, kind: a.kind })),
		...newFiles.map((f) => ({ name: f.name, url: f.url, kind: f.kind }))
	]);
	const lineNumbers = $derived(Array.from({ length: body.split('\n').length }, (_, i) => i + 1));
	const extras = $derived(mediaRefs.filter((r) => r.kind !== 'image').map((r) => r.name));
	const texStatus = $derived(compiling ? 'busy' : latexError ? 'err' : latexHtml ? 'ok' : 'idle');
	const draftJson = $derived(
		JSON.stringify({ t: title, c: category, f: format, b: body, s: summary, y: yearText, yp: yearPrec, dn: dateNote, sn: sourceNote, su: sourceUrl, ppl: peopleChips, sub: subjectChips, tg: tagChips })
	);

	/* ---------- helpers ---------- */
	function extOf(name: string): string {
		return name.includes('.') ? (name.split('.').pop() ?? '').toLowerCase() : '';
	}
	function kindOf(name: string): Attachment['kind'] {
		const e = extOf(name);
		if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(e)) return 'image';
		if (e === 'pdf') return 'pdf';
		if (['mp3', 'ogg', 'm4a', 'wav'].includes(e)) return 'audio';
		if (['mp4', 'webm'].includes(e)) return 'video';
		return 'other';
	}
	function iconFor(kind: string): string {
		return kind === 'image' ? '🖼' : kind === 'pdf' ? '📄' : kind === 'audio' ? '🎧' : kind === 'video' ? '🎬' : '📃';
	}
	function fmtSize(b: number): string {
		return b < 1024 * 1024 ? `${Math.max(1, Math.round(b / 1024))} kB` : `${(b / (1024 * 1024)).toFixed(1)} MB`;
	}
	/** A name the body can actually reference: no whitespace, no brackets or percent signs. */
	function cleanName(raw: string): string {
		const base = (raw.split(/[\\/]/).pop() ?? raw).trim();
		const dot = base.lastIndexOf('.');
		const ext = dot > 0 ? base.slice(dot).toLowerCase() : '';
		const stem = (dot > 0 ? base.slice(0, dot) : base)
			.replace(/\s+/g, '-')
			.replace(/[()[\]{}<>"'`%#|?*:;,$~^&=+!@]/g, '')
			.replace(/-+/g, '-')
			.replace(/^-|-$/g, '')
			.slice(0, 100);
		return (stem || 'plik') + ext;
	}
	function uniqueName(name: string): string {
		const taken = new Set(mediaRefs.map((r) => r.name.toLowerCase()));
		if (!taken.has(name.toLowerCase())) return name;
		const dot = name.lastIndexOf('.');
		const stem = dot > 0 ? name.slice(0, dot) : name;
		const ext = dot > 0 ? name.slice(dot) : '';
		for (let i = 2; i < 200; i++) if (!taken.has(`${stem}-${i}${ext}`.toLowerCase())) return `${stem}-${i}${ext}`;
		return `${stem}-${Date.now()}${ext}`;
	}
	/** Body → rough plain text, for the auto-filled summary. */
	function plainText(src: string, fmt: Format): string {
		// maths stays (summaries are typeset by MathText); display maths becomes inline, and
		// formulas are protected from the syntax stripping below
		const maths: string[] = [];
		let s = src
			.replace(/\$\$([\s\S]*?)\$\$|\\\[([\s\S]*?)\\\]|\\\(([\s\S]*?)\\\)/g, (_m, a, b, c) => ` $${(a ?? b ?? c ?? '').trim()}$ `)
			.replace(/\$[^$\n]+\$/g, (m) => { maths.push(m); return ` \u0000${maths.length - 1}\u0000 `; });
		if (fmt === 'latex') {
			s = s.replace(/(^|[^\\])%.*$/gm, '$1');
			s = s.replace(/\\(begin|end)\s*\{[^}]*\}/g, ' ');
			s = s.replace(/\\(documentclass|usepackage|includegraphics|label|ref|cite|input)\s*(\[[^\]]*\])?\s*\{[^}]*\}/g, ' ');
			s = s.replace(/\\[a-zA-Z@]+\*?\s*(\[[^\]]*\])?/g, ' ');
			s = s.replace(/[{}$&~^_\\]/g, ' ');
		} else {
			s = s.replace(/!\[[^\]]*\]\([^)]*\)/g, ' ');
			s = s.replace(/\[([^\]]*)\]\([^)]*\)/g, '$1');
			s = s.replace(/^\s{0,3}#{1,6}\s+/gm, '');
			s = s.replace(/^\s{0,3}>\s?/gm, '');
			s = s.replace(/^\s{0,3}[-*+]\s+/gm, '');
			s = s.replace(/`{1,3}/g, '');
			s = s.replace(/(\*\*|__|\*|_)/g, '');
		}
		s = s.replace(/\u0000(\d+)\u0000/g, (_m, i) => maths[Number(i)] ?? '');
		return s.replace(/\s+/g, ' ').replace(/\s+([.,;:!?)])/g, '$1').trim();
	}
	function clip(s: string, n: number): string {
		if (s.length <= n) return s;
		const cut = s.slice(0, n);
		const sp = cut.lastIndexOf(' ');
		return (sp > n * 0.6 ? cut.slice(0, sp) : cut).trimEnd() + '…';
	}

	/* ---------- textarea editing ---------- */
	function replaceRange(start: number, end: number, text: string, selStart?: number, selEnd?: number) {
		body = body.slice(0, start) + text + body.slice(end);
		const s = selStart ?? start + text.length;
		const e = selEnd ?? s;
		tick().then(() => {
			taEl?.focus();
			taEl?.setSelectionRange(s, e);
		});
	}
	function sel(): { start: number; end: number } {
		if (!taEl || !caretTouched) return { start: body.length, end: body.length };
		return { start: taEl.selectionStart, end: taEl.selectionEnd };
	}
	function wrapSel(before: string, after: string, placeholder: string) {
		const { start, end } = sel();
		if (end > start) {
			replaceRange(start, end, before + body.slice(start, end) + after, start + before.length, end + before.length);
		} else {
			replaceRange(start, start, before + placeholder + after, start + before.length, start + before.length + placeholder.length);
		}
	}
	function prefixLines(prefix: string) {
		const { start, end } = sel();
		const from = body.lastIndexOf('\n', start - 1) + 1;
		const toRaw = body.indexOf('\n', end);
		const to = toRaw === -1 ? body.length : toRaw;
		const block = body.slice(from, to).split('\n').map((l) => prefix + l).join('\n');
		replaceRange(from, to, block, from, from + block.length);
	}
	function insertBlock(text: string) {
		const { start, end } = sel();
		const atLineStart = start === 0 || body[start - 1] === '\n';
		const snippet = (atLineStart ? '' : '\n') + text + '\n';
		replaceRange(start, end, snippet);
	}
	function insertFile(name: string, caption = '') {
		if (format === 'latex') {
			insertBlock(`\\includegraphics[width=0.6\\textwidth]{${name}}`);
		} else {
			const alt = caption.trim() || 'opis';
			const { start, end } = sel();
			const snippet = `![${alt}](${name})`;
			replaceRange(start, end, snippet, start + 2, start + 2 + alt.length);
		}
	}
	function gotoLine(line: number) {
		if (!taEl) return;
		const lines = body.split('\n');
		const idx = Math.min(Math.max(line, 1), lines.length) - 1;
		let pos = 0;
		for (let i = 0; i < idx; i++) pos += lines[i].length + 1;
		taEl.focus();
		taEl.setSelectionRange(pos, pos + lines[idx].length);
		taEl.scrollTop = Math.max(0, (idx - 3) * LINE_H);
		if (gutterEl) gutterEl.scrollTop = taEl.scrollTop;
	}
	function onKey(e: KeyboardEvent) {
		const meta = e.ctrlKey || e.metaKey;
		if (meta && e.key === 'Enter') {
			e.preventDefault();
			if (format === 'latex') compileNow();
			else renderMd();
			return;
		}
		if (meta && (e.key === 'b' || e.key === 'B')) {
			e.preventDefault();
			if (format === 'latex') wrapSel('\\textbf{', '}', 'pogrubienie');
			else wrapSel('**', '**', 'pogrubienie');
			return;
		}
		if (meta && (e.key === 'i' || e.key === 'I')) {
			e.preventDefault();
			if (format === 'latex') wrapSel('\\emph{', '}', 'kursywa');
			else wrapSel('*', '*', 'kursywa');
			return;
		}
		if (e.key === 'Escape') {
			tabEscapes = true; // next Tab leaves the editor — no keyboard trap
			return;
		}
		if (e.key === 'Tab') {
			if (tabEscapes) {
				tabEscapes = false;
				return; // let the browser move focus
			}
			e.preventDefault();
			const { start, end } = sel();
			if (body.slice(start, end).includes('\n')) {
				const from = body.lastIndexOf('\n', start - 1) + 1;
				const toRaw = body.indexOf('\n', end);
				const to = toRaw === -1 ? body.length : toRaw;
				const lines = body.slice(from, to).split('\n');
				const block = lines.map((l) => (e.shiftKey ? l.replace(/^ {1,2}/, '') : '  ' + l)).join('\n');
				replaceRange(from, to, block, from, from + block.length);
			} else if (e.shiftKey) {
				const from = body.lastIndexOf('\n', start - 1) + 1;
				const line = body.slice(from, from + 2);
				const drop = line.startsWith('  ') ? 2 : line.startsWith(' ') ? 1 : 0;
				if (drop) replaceRange(from, from + drop, '', Math.max(from, start - drop));
			} else {
				replaceRange(start, end, '  ');
			}
			return;
		}
		if (tabEscapes) tabEscapes = false;
	}
	function syncGutter() {
		if (gutterEl && taEl) gutterEl.scrollTop = taEl.scrollTop;
	}

	/* ---------- previews ---------- */
	async function renderMd(src: string = body, refs: MediaRef[] = mediaRefs) {
		previewHtml = renderMarkdown(src, resolver([...refs]));
		await tick();
		if (previewEl) typeset(previewEl).catch(() => {});
	}
	async function compileNow(src: string = body, refs: MediaRef[] = mediaRefs) {
		const run = ++texRun;
		compiling = true;
		try {
			const r = await renderLatex(src, resolver([...refs]));
			if (run !== texRun) return;
			latexHtml = r.html;
			latexError = r.error;
			latexLine = r.line ?? null;
			if (r.error) logOpen = true;
		} catch (e) {
			if (run !== texRun) return;
			latexHtml = '';
			latexError = e instanceof Error ? e.message : String(e);
			latexLine = null;
			logOpen = true;
		} finally {
			if (run === texRun) compiling = false;
		}
	}

	$effect(() => {
		const src = body;
		const refs = mediaRefs;
		if (format !== 'text') return;
		clearTimeout(mdTimer);
		mdTimer = setTimeout(() => renderMd(src, refs), 300);
		return () => clearTimeout(mdTimer);
	});

	$effect(() => {
		const src = body;
		const refs = mediaRefs;
		if (format !== 'latex' || !autoCompile) return;
		clearTimeout(texTimer);
		texTimer = setTimeout(() => compileNow(src, refs), 700);
		return () => clearTimeout(texTimer);
	});

	/* ---------- draft ---------- */
	$effect(() => {
		const snap = draftJson;
		if (seed || draftOffer !== null) return;
		const d = JSON.parse(snap) as Draft;
		if (!d.t.trim() && !d.b.trim() && !d.s.trim() && !d.tg.length && !d.ppl.length && !d.sub.length) return;
		const timer = setTimeout(() => {
			try {
				localStorage.setItem(DRAFT_KEY, JSON.stringify({ ...d, at: Date.now() }));
			} catch {
				/* private mode — a lost draft is not worth an error message */
			}
		}, 2000);
		return () => clearTimeout(timer);
	});

	/** A draft field that may be chips (current), a list of slugs (`ppl`, pre-pickers) or one
	 * comma-separated string (`tg`, pre-pickers). A bare string in `ppl` was a SLUG, so it
	 * becomes a chip that still carries the slug — the name shown is the slug until it is
	 * saved, which is ugly for one draft and correct, where inventing a person called
	 * „kwant-niepewny” would be neither. */
	function chipsFrom(v: unknown, asSlug = false): Chip[] {
		if (typeof v === 'string') {
			return v.split(',').map((x) => x.trim()).filter(Boolean).map((name) => ({ name }));
		}
		if (!Array.isArray(v)) return [];
		return v
			.map((x) => (typeof x === 'string' ? (asSlug ? { slug: x, name: x } : { name: x }) : (x as Chip)))
			.filter((c) => c && typeof c.name === 'string' && c.name.trim().length > 0);
	}
	function restoreDraft() {
		const d = draftOffer;
		if (!d) return;
		title = d.t; category = d.c; format = d.f; body = d.b; summary = d.s;
		yearText = d.y; yearPrec = d.yp; dateNote = d.dn; sourceNote = d.sn; sourceUrl = d.su;
		peopleChips = chipsFrom(d.ppl, true); subjectChips = chipsFrom(d.sub); tagChips = chipsFrom(d.tg);
		draftOffer = null;
	}
	function discardDraft() {
		clearDraft();
		draftOffer = null;
	}
	function clearDraft() {
		try {
			localStorage.removeItem(DRAFT_KEY);
		} catch {
			/* nothing to clear */
		}
	}

	/* ---------- files ---------- */
	function onPick(e: Event) {
		const input = e.currentTarget as HTMLInputElement;
		const picked = Array.from(input.files ?? []);
		input.value = ''; // so the same file can be picked again after a removal
		const bad: string[] = [];
		for (const file of picked) {
			if (fileCount >= MAX_FILES) {
				bad.push(`${file.name}: przekroczony limit ${MAX_FILES} plików`);
				continue;
			}
			const ext = extOf(file.name);
			if (!ALLOWED_EXT.includes(ext)) {
				bad.push(`${file.name}: niedozwolony typ .${ext || '?'}`);
				continue;
			}
			if (file.size > MAX_BYTES) {
				bad.push(`${file.name}: za duży (${fmtSize(file.size)}, limit 25 MB)`);
				continue;
			}
			const name = uniqueName(cleanName(file.name));
			newFiles.push({ id: ++fileSeq, file, name, caption: '', kind: kindOf(name), url: URL.createObjectURL(file) });
		}
		fileError = bad.length ? bad.join('\n') : null;
	}
	function dropNew(id: number) {
		const i = newFiles.findIndex((f) => f.id === id);
		if (i < 0) return;
		URL.revokeObjectURL(newFiles[i].url);
		newFiles.splice(i, 1);
	}
	function toggleSaved(id: number) {
		removeIds = removeIds.includes(id) ? removeIds.filter((x) => x !== id) : [...removeIds, id];
	}
	function setFormat(f: Format) {
		if (f === format) return;
		format = f;
		caretTouched = false; // the other mode's textarea has its own caret
		if (body.trim() && !formatWarned) {
			formatWarned = true;
			formatNotice = 'Treść została zachowana, ale drugi format renderuje ją inaczej — sprawdź podgląd.';
		} else {
			formatNotice = '';
		}
	}
	function useTemplate() {
		body = TEMPLATE;
		tick().then(() => taEl?.focus());
	}

	/* ---------- save ---------- */
	function normalizedUrl(): string {
		const u = sourceUrl.trim();
		if (!u) return '';
		return /^[a-z][a-z0-9+.-]*:\/\//i.test(u) ? u : 'https://' + u;
	}
	function validate(): string | null {
		const problems: string[] = [];
		if (!title.trim()) problems.push('Podaj tytuł.');
		if (title.trim().length > 200) problems.push('Tytuł jest dłuższy niż 200 znaków.');
		if (!category) problems.push('Wybierz kategorię.');
		if (!body.trim() && fileCount === 0) problems.push('Wpis musi mieć treść albo przynajmniej jeden plik.');
		if (fileCount > MAX_FILES) problems.push(`Najwyżej ${MAX_FILES} plików (jest ${fileCount}).`);
		const y = yearText.trim();
		if (y && !/^\d{4}$/.test(y)) problems.push('Rok wpisz jako cztery cyfry, np. 2009.');
		else if (y && (Number(y) < 1900 || Number(y) > 2100)) problems.push('Rok musi być z zakresu 1900–2100.');
		for (const f of newFiles) {
			if (!ALLOWED_EXT.includes(extOf(f.name))) problems.push(`Plik ${f.name}: niedozwolony typ.`);
			if (f.file.size > MAX_BYTES) problems.push(`Plik ${f.name}: za duży (limit 25 MB).`);
		}
		const link = normalizedUrl();
		if (link) {
			try {
				const parsed = new URL(link);
				if (!parsed.hostname.includes('.')) problems.push('Link źródła wygląda na niepełny.');
			} catch {
				problems.push('Link źródła jest nieprawidłowy.');
			}
		}
		if (!seed && !rightsOk) problems.push('Potwierdź, że masz prawo opublikować tę treść (pole nad przyciskiem „Zapisz wpis”).');
		return problems.length ? problems.join('\n') : null;
	}
	function buildForm(): FormData {
		const fd = new FormData();
		fd.set('title', title.trim());
		fd.set('category', category);
		fd.set('format', format);
		fd.set('body', body);
		const auto = summary.trim() || clip(plainText(body, format), 200);
		fd.set('summary', auto.slice(0, 300));
		const y = yearText.trim();
		fd.set('year', y);
		fd.set('year_precision', y ? yearPrec : 'unknown');
		fd.set('date_note', dateNote.trim());
		fd.set('source_note', sourceNote.trim());
		fd.set('source_url', normalizedUrl());
		// JSON, not a comma-separated list: `people` may carry an object for somebody who does
		// not exist yet, and a comma is a legal character in a tag. archive/serializers.py
		// `_items` reads both shapes, so an older client keeps working.
		fd.set('people', JSON.stringify(peoplePayload(peopleChips)));
		fd.set('subjects', JSON.stringify(namePayload(subjectChips)));
		fd.set('tags', JSON.stringify(namePayload(tagChips)));
		fd.set('rights_confirmed', rightsOk ? 'true' : 'false');
		for (const f of newFiles) fd.append('files', f.file, f.name);
		fd.set('captions', JSON.stringify(newFiles.map((f) => f.caption.trim().slice(0, 200))));
		for (const id of removeIds) fd.append('remove_attachments', String(id));
		return fd;
	}
	async function save() {
		error = null;
		const bad = validate();
		if (bad) {
			error = bad;
			return;
		}
		saving = true;
		try {
			const fd = buildForm();
			const post = seed
				? await api.patch<Post>(`/posts/${seed.slug}/`, fd)
				: await api.post<Post>('/posts/', fd);
			if (!seed) clearDraft();
			onSaved(post);
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Nie udało się zapisać — sprawdź połączenie i spróbuj jeszcze raz.';
		} finally {
			saving = false;
		}
	}

	/* ---------- load ---------- */
	onMount(() => {
		if (!seed) {
			try {
				const raw = localStorage.getItem(DRAFT_KEY);
				if (raw) {
					const d = JSON.parse(raw) as Draft;
					if (d && (d.t?.trim() || d.b?.trim())) draftOffer = d;
				}
			} catch {
				/* unreadable draft — ignore it */
			}
		}
		// Only the categories are fetched up front now. People, subjects and tags are typed
		// at, not scrolled through: the pickers ask the API per keystroke, which is also the
		// only way a person the directory means to hide stays hidden — a full download
		// filtered in the browser would suggest her anyway.
		(async () => {
			try {
				categories = await api.get<Category[]>('/categories/');
			} catch (e) {
				metaError = e instanceof ApiError ? e.message : 'Nie udało się wczytać kategorii.';
			}
		})();
	});

	onDestroy(() => {
		clearTimeout(mdTimer);
		clearTimeout(texTimer);
		for (const f of newFiles) URL.revokeObjectURL(f.url);
	});
</script>

<div class="ed">
	{#if draftOffer}
		<div class="draft">
			<span>
				Masz niezapisany szkic z {new Date(draftOffer.at).toLocaleString('pl-PL')}:
				<strong>{draftOffer.t.trim() || '(bez tytułu)'}</strong>
			</span>
			<span class="draft__acts">
				<button type="button" class="btn btn--sm" onclick={restoreDraft}>Przywróć szkic</button>
				<button type="button" class="btn btn--sm btn--ghost" onclick={discardDraft}>Odrzuć</button>
			</span>
		</div>
	{/if}

	{#if metaError}<div class="error">{metaError}</div>{/if}

	<!-- ---------------- metadata ---------------- -->
	<div class="box">
		<h2 class="box__title">Dane wpisu</h2>
		<div class="box__body">
			<label for="ed-title">Tytuł *</label>
			<input id="ed-title" type="text" maxlength="200" bind:value={title} placeholder="np. Kartka na drzwiach dziekanatu, 2009" />

			<div class="row">
				<div>
					<label for="ed-cat">Kategoria *</label>
					<select id="ed-cat" bind:value={category}>
						<option value="">— wybierz —</option>
						{#each categories as c (c.slug)}
							<option value={c.slug}>{c.emoji ? c.emoji + ' ' : ''}{c.name}</option>
						{/each}
					</select>
				</div>
				<div>
					<label for="ed-year">Rok</label>
					<input id="ed-year" type="text" inputmode="numeric" maxlength="4" bind:value={yearText} placeholder="np. 2009" />
				</div>
				<div>
					<label for="ed-prec">Dokładność daty</label>
					<select id="ed-prec" bind:value={yearPrec} disabled={!yearText.trim()}>
						<option value="exact">dokładnie</option>
						<option value="approx">około</option>
						<option value="decade">dekada</option>
						<option value="unknown">nieznany</option>
					</select>
				</div>
			</div>
			{#if !yearText.trim()}<p class="help">Bez roku wpis trafi do „rok nieznany”.</p>{/if}

			<label for="ed-datenote">Notatka o dacie</label>
			<input id="ed-datenote" type="text" maxlength="120" bind:value={dateNote} placeholder="np. semestr zimowy 2009, kolokwium II" />

			<label for="ed-people">Osoby</label>
			<TagPicker
				kind="people"
				id="ed-people"
				allowCreate
				selected={peopleChips}
				onchange={(c) => (peopleChips = c)}
				placeholder="zacznij pisać nazwisko…"
			/>
			<p class="help">
				Osoby z <span class="okmark">✓</span> potwierdziły zgodę na publikację zdjęć; w pozostałych przypadkach
				potrzebujesz zgody (art. 81 pr. aut.) — <a href="/ludzie/zgoda" target="_blank">jak to działa</a>.
				Kogoś brakuje? Wpisz i dodaj — pojawi się w spisie, gdy wpis zostanie opublikowany.
			</p>

			<label for="ed-subjects">Przedmioty</label>
			<TagPicker
				kind="subjects"
				id="ed-subjects"
				allowCreate
				selected={subjectChips}
				onchange={(c) => (subjectChips = c)}
				placeholder="np. Mechanika klasyczna, II Pracownia fizyczna…"
			/>
			<p class="help">Zajęcia, na których to się stało. Lista jest z programu studiów — brakującego przedmiotu po prostu dopisz.</p>

			<label for="ed-tags">Tagi</label>
			<TagPicker
				kind="tags"
				id="ed-tags"
				allowCreate
				selected={tagChips}
				onchange={(c) => (tagChips = c)}
				placeholder="np. kolokwium, kreda, dziekanat…"
			/>
			<p class="help">Wszystko inne: miejsce, rekwizyt, pora roku. Ksywka wykładowcy też — wpis otagowany ksywką trafia na stronę tej osoby.</p>

			<div class="row">
				<div>
					<label for="ed-src">Źródło</label>
					<input id="ed-src" type="text" maxlength="300" bind:value={sourceNote} placeholder="np. zdjęcie od autora, archiwum SKFiz" />
				</div>
				<div>
					<label for="ed-srcurl">Link źródła</label>
					<input id="ed-srcurl" type="text" inputmode="url" bind:value={sourceUrl} placeholder="np. fuw.edu.pl/aktualnosci" />
				</div>
			</div>

			<label for="ed-sum">Streszczenie</label>
			<textarea id="ed-sum" rows="2" maxlength="300" bind:value={summary}></textarea>
			<p class="help">Puste — wypełnimy je początkiem treści. {summary.length}/300</p>
		</div>
	</div>

	<!-- ---------------- files ---------------- -->
	<div class="box">
		<h2 class="box__title">Pliki <small>{fileCount}/{MAX_FILES} plików</small></h2>
		<div class="box__body">
			<label for="ed-files">Dodaj pliki</label>
			<input
				id="ed-files"
				type="file"
				multiple
				accept={ACCEPT}
				onchange={onPick}
				disabled={fileCount >= MAX_FILES}
			/>
			<p class="help">
				Obrazy, PDF, audio, wideo, .txt, .tex — do 25 MB każdy. Spacje w nazwach zamieniamy na myślniki,
				bo wpis odwołuje się do plików po nazwie.
			</p>

			{#if fileError}<div class="error">{fileError}</div>{/if}

			{#if keptSaved.length || removeIds.length}
				<div class="lbl">W tym wpisie</div>
				<ul class="tray">
					{#each savedAtt as a (a.id)}
						{@const gone = removeIds.includes(a.id)}
						<li class="tray__row" class:tray__row--gone={gone}>
							<span class="tray__ico" aria-hidden="true">{iconFor(a.kind)}</span>
							{#if a.kind === 'image'}<img class="tray__thumb" src={a.url} alt="" />{/if}
							<span class="tray__name mono">{a.original_name}</span>
							<span class="tray__cap muted small">{a.caption || '—'}</span>
							{#if !gone && a.kind === 'image'}
								<button type="button" class="btn btn--sm btn--ghost" onclick={() => insertFile(a.original_name, a.caption ?? '')}>Wstaw</button>
							{/if}
							<button type="button" class="btn btn--sm" class:btn--warn={!gone} class:btn--ghost={gone} onclick={() => toggleSaved(a.id)}>
								{gone ? 'Przywróć' : 'Usuń'}
							</button>
						</li>
					{/each}
				</ul>
				<p class="help">Podpisów zapisanych plików nie da się już zmienić — usuń plik i dodaj go jeszcze raz.</p>
			{/if}

			{#if newFiles.length}
				<div class="lbl">Nowe pliki</div>
				<ul class="tray">
					{#each newFiles as f (f.id)}
						<li class="tray__row">
							<span class="tray__ico" aria-hidden="true">{iconFor(f.kind)}</span>
							{#if f.kind === 'image'}<img class="tray__thumb" src={f.url} alt="" />{/if}
							<span class="tray__name mono">{f.name}</span>
							<span class="tray__size muted small">{fmtSize(f.file.size)}</span>
							<input class="tray__capin" type="text" maxlength="200" bind:value={f.caption} placeholder="podpis (opcjonalny)" aria-label="Podpis do {f.name}" />
							{#if f.kind === 'image'}
								<button type="button" class="btn btn--sm btn--ghost" onclick={() => insertFile(f.name, f.caption)}>Wstaw</button>
							{:else}
								<span class="muted small tray__note">pod wpisem</span>
							{/if}
							<button type="button" class="btn btn--sm btn--warn" onclick={() => dropNew(f.id)} aria-label="Usuń {f.name}">×</button>
						</li>
					{/each}
				</ul>
			{/if}

			{#if fileCount === 0}<p class="muted small">Na razie bez plików.</p>{/if}
		</div>
	</div>

	<!-- ---------------- body ---------------- -->
	<div class="box">
		<h2 class="box__title">Treść wpisu</h2>
		<div class="box__body">
			<div class="fmt" role="group" aria-label="Format wpisu">
				<button type="button" class="btn fmt__btn" class:is-active={format === 'text'} aria-pressed={format === 'text'} onclick={() => setFormat('text')}>
					Tekst + obrazy
				</button>
				<button type="button" class="btn fmt__btn" class:is-active={format === 'latex'} aria-pressed={format === 'latex'} onclick={() => setFormat('latex')}>
					LaTeX (jak Overleaf)
				</button>
			</div>
			{#if formatNotice}<p class="help fmt__note">{formatNotice}</p>{/if}

			{#if format === 'text'}
				<div class="tools">
					<button type="button" class="btn btn--sm btn--ghost" onclick={() => wrapSel('**', '**', 'pogrubienie')} title="Ctrl+B"><b>B</b></button>
					<button type="button" class="btn btn--sm btn--ghost" onclick={() => wrapSel('*', '*', 'kursywa')} title="Ctrl+I"><i>I</i></button>
					<button type="button" class="btn btn--sm btn--ghost" onclick={() => prefixLines('## ')}>nagłówek</button>
					<button type="button" class="btn btn--sm btn--ghost" onclick={() => prefixLines('- ')}>lista</button>
					<button type="button" class="btn btn--sm btn--ghost" onclick={() => prefixLines('> ')}>cytat</button>
					<button type="button" class="btn btn--sm btn--ghost" onclick={() => wrapSel('$', '$', 'E=mc^2')}>$ $ wzór</button>
				</div>
				<div class="split">
					<div class="pane">
						<label class="visually-hidden" for="ed-body">Treść wpisu</label>
						<textarea id="ed-body" class="src__area src__area--plain" bind:this={taText} bind:value={body} onkeydown={onKey} onfocus={() => (caretTouched = true)} spellcheck="true" placeholder="Napisz, co się stało…"></textarea>
						<p class="help">
							Markdown + wzory w <code>$…$</code>. Obrazy: <code>![opis](nazwa-pliku.jpg)</code> — użyj Wstaw.
							Ctrl+Enter odświeża podgląd, Esc a potem Tab wychodzi z pola.
						</p>
					</div>
					<div class="pane">
						<div class="pane__bar"><span class="lbl lbl--bar">Podgląd</span></div>
						<div class="paper paper--md">
							<div class="prose" bind:this={previewEl}>{@html previewHtml}</div>
							{#if !body.trim()}<p class="muted small">Podgląd pojawi się, gdy zaczniesz pisać.</p>{/if}
						</div>
						{#if extras.length}<p class="help">Pod wpisem pokażą się też: {extras.join(', ')}.</p>{/if}
					</div>
				</div>
			{:else}
				<div class="split split--tex">
					<div class="pane pane--files">
						<div class="lbl">Pliki projektu</div>
						<ul class="proj">
							<li><span class="proj__it proj__it--main">📄 main.tex</span></li>
							{#each mediaRefs as r (r.name)}
								<li>
									{#if r.kind === 'image'}
										<button type="button" class="proj__it proj__it--btn" onclick={() => insertFile(r.name)} title="Wstaw w miejscu kursora">
											🖼 {r.name}
										</button>
									{:else}
										<span class="proj__it proj__it--dim">{iconFor(r.kind)} {r.name}</span>
									{/if}
								</li>
							{/each}
						</ul>
						<p class="help">Kliknij obraz, żeby wstawić go do dokumentu.</p>
					</div>

					<div class="pane pane--src">
						<div class="pane__bar">
							<button type="button" class="btn btn--sm btn--ghost" onclick={() => wrapSel('\\textbf{', '}', 'pogrubienie')} title="Ctrl+B"><b>B</b></button>
							<button type="button" class="btn btn--sm btn--ghost" onclick={() => wrapSel('\\emph{', '}', 'kursywa')} title="Ctrl+I"><i>I</i></button>
							<button type="button" class="btn btn--sm btn--ghost" onclick={() => insertBlock('\\section*{Tytuł sekcji}')}>sekcja</button>
							<button type="button" class="btn btn--sm btn--ghost" onclick={() => wrapSel('$', '$', 'E=mc^2')}>$ $ wzór</button>
							<button type="button" class="btn btn--sm btn--ghost" onclick={useTemplate} disabled={!!body.trim()} title="Wstawia szkielet dokumentu, gdy pole jest puste">Szablon</button>
						</div>
						<div class="src">
							<div class="src__gutter" bind:this={gutterEl} aria-hidden="true">
								{#each lineNumbers as n (n)}<div>{n}</div>{/each}
							</div>
							<label class="visually-hidden" for="ed-body-tex">Źródło LaTeX</label>
							<textarea
								id="ed-body-tex"
								class="src__area"
								bind:this={taTex}
								bind:value={body}
								onkeydown={onKey}
								onfocus={() => (caretTouched = true)}
								onscroll={syncGutter}
								wrap="off"
								spellcheck="false"
								placeholder={'\\documentclass{article}\n\\begin{document}\n…\n\\end{document}'}
							></textarea>
						</div>
						<p class="help">
							Kompilacja w przeglądarce (LaTeX.js): sekcje, listy, <code>\textbf</code>, <code>\emph</code>,
							wzory (KaTeX), <code>\includegraphics</code>. Bez TikZ i pakietów spoza listy.
							Tab = dwie spacje, Ctrl+Enter kompiluje, Esc a potem Tab wychodzi z pola.
						</p>

						{#if latexError}
							<div class="log">
								<button type="button" class="log__head" onclick={() => (logOpen = !logOpen)} aria-expanded={logOpen}>
									<span aria-hidden="true">{logOpen ? '▾' : '▸'}</span>
									Błąd kompilacji{latexLine ? ` — linia ${latexLine}` : ''}
								</button>
								{#if logOpen}
									<div class="log__body">
										<pre class="log__msg">{latexError}</pre>
										{#if latexLine}
											<button type="button" class="btn btn--sm btn--ghost" onclick={() => gotoLine(latexLine ?? 1)}>
												Przejdź do linii {latexLine}
											</button>
										{/if}
									</div>
								{/if}
							</div>
						{/if}
					</div>

					<div class="pane pane--preview">
						<div class="pane__bar">
							<button type="button" class="btn btn--sm" onclick={() => compileNow()} disabled={compiling}>Rekompiluj</button>
							<label class="auto"><input type="checkbox" bind:checked={autoCompile} /> auto</label>
							<span class="pill" class:pill--amber={texStatus === 'busy'} class:pill--green={texStatus === 'ok'} class:pill--err={texStatus === 'err'}>
								{texStatus === 'busy' ? 'Kompiluję…' : texStatus === 'err' ? 'Błąd' : texStatus === 'ok' ? 'OK' : 'brak podglądu'}
							</span>
						</div>
						<div class="paper">
							<div class="latex-doc">{@html latexHtml}</div>
							{#if !latexHtml && !compiling}
								<p class="muted small hint">Podgląd pojawi się po kompilacji — napisz coś albo naciśnij „Rekompiluj”.</p>
							{/if}
						</div>
						{#if extras.length}<p class="help">Pod wpisem pokażą się też: {extras.join(', ')}.</p>{/if}
					</div>
				</div>
			{/if}
		</div>
	</div>

	{#if !seed}
		<label class="rights">
			<input type="checkbox" bind:checked={rightsOk} />
			<span>Mam prawo opublikować tę treść: jest moja albo mieści się w granicach parodii/pastiszu (art. 29¹ pr. aut.), a każda rozpoznawalna osoba na zdjęciu zgodziła się na publikację (art. 81) — wykładowca nie jest „osobą powszechnie znaną”. Nie ma tu cudzych materiałów z zajęć w całości ani danych studentów (ocen, numerów indeksu). Szczegóły: <a href="/o-archiwum" target="_blank">regulamin</a>.</span>
		</label>
	{/if}

	{#if error}<div class="error">{error}</div>{/if}

	<div class="savebar">
		<button type="button" class="btn" onclick={save} disabled={saving}>
			{saving ? 'Zapisywanie…' : seed ? 'Zapisz zmiany' : 'Zapisz wpis'}
		</button>
		{#if saving}<span class="muted small">Wysyłam pliki i treść…</span>{/if}
	</div>
</div>

<style>
	.ed { margin: 0; }
	.rights { display: flex; gap: 8px; align-items: flex-start; font-size: 12px; margin: 12px 0 4px; }
	.rights input { width: auto; margin-top: 3px; }

	.draft { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: space-between;
		border: 1px solid #c98f1e; background: #fffbe8; padding: 6px 9px; margin: 0 0 12px; font-size: 12px; }
	.draft__acts { display: flex; gap: 6px; }

	.lbl { font-size: 12px; color: #333; margin: 10px 0 3px; font-weight: bold; }
	.lbl--bar { margin: 0; font-weight: bold; }

	/* the ✓ in the people help text, same green as the consent badge it explains */
	.okmark { color: #0b5a2a; font-weight: bold; }

	/* file tray */
	.tray { list-style: none; margin: 0; padding: 0; border: 1px solid var(--line); }
	.tray__row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; padding: 5px 7px; border-bottom: 1px solid #e6e6e6; }
	.tray__row:last-child { border-bottom: 0; }
	.tray__row--gone { background: #fff0f0; }
	.tray__row--gone .tray__name { text-decoration: line-through; color: var(--muted); }
	.tray__ico { font-size: 14px; }
	.tray__thumb { width: 34px; height: 26px; object-fit: cover; border: 1px solid var(--line); background: var(--box); display: block; }
	.tray__name { flex: 1 1 140px; min-width: 0; overflow-wrap: anywhere; font-size: 12px; }
	.tray__size, .tray__note { flex: 0 0 auto; }
	.tray__cap { flex: 1 1 100px; min-width: 0; overflow-wrap: anywhere; }
	.tray__capin { flex: 1 1 130px; width: auto; min-width: 0; font-size: 12px; padding: 2px 5px; }

	/* format switch */
	.fmt { display: flex; gap: 8px; flex-wrap: wrap; }
	.fmt__btn { flex: 1 1 180px; padding: 9px 12px; font-size: 13px; }
	.fmt__note { color: #8a5a00; }

	.tools { display: flex; flex-wrap: wrap; gap: 4px; margin: 10px 0 5px; }

	/* split panes */
	.split { display: grid; gap: 10px; grid-template-columns: minmax(0, 1fr); margin-top: 8px; }
	.pane { min-width: 0; }
	.pane__bar { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; padding: 4px 6px;
		border: 1px solid var(--line); border-bottom: 0; background: var(--box); }
	.auto { display: inline-flex; align-items: center; gap: 4px; margin: 0; font-size: 11px; color: #333; cursor: pointer; }
	.auto input { margin: 0; }
	.pill--err { background: #fff0f0; color: #b00020; border-color: #f2b8b8; }

	/* source */
	.src { display: flex; border: 1px solid #aaa; background: #fff; }
	.src__gutter { flex: 0 0 auto; width: 38px; overflow: hidden; background: #f0f0f0; border-right: 1px solid var(--line);
		font-family: "DejaVu Sans Mono", Consolas, monospace; font-size: 12px; line-height: 18px; color: #999;
		text-align: right; padding: 6px 5px 6px 0; user-select: none; }
	.src__gutter div { height: 18px; }
	.src__area { flex: 1 1 auto; width: 100%; min-width: 0; border: 0; padding: 6px 8px; resize: vertical;
		font-family: "DejaVu Sans Mono", Consolas, monospace; font-size: 12px; line-height: 18px; min-height: 320px; }
	.src__area--plain { border: 1px solid #aaa; font-family: inherit; font-size: 13px; line-height: 1.45; }
	.src__area:focus { outline: 2px solid var(--amber); outline-offset: -2px; }

	/* latex project files */
	.pane--files .proj { list-style: none; margin: 0; padding: 0; border: 1px solid var(--line); background: #fff; }
	.proj li { border-bottom: 1px solid #eee; }
	.proj li:last-child { border-bottom: 0; }
	.proj__it { display: block; width: 100%; text-align: left; font-size: 11px; padding: 4px 6px;
		overflow-wrap: anywhere; background: none; border: 0; color: var(--text); }
	.proj__it--btn { cursor: pointer; }
	.proj__it--btn:hover { background: var(--box); text-decoration: underline; }
	.proj__it--main { background: var(--box); font-weight: bold; }
	.proj__it--dim { color: var(--muted); }

	/* previews */
	.paper { background: #e9e9e9; border: 1px solid var(--line); padding: 10px; max-height: 520px; overflow: auto; }
	.paper--md { background: #fff; }
	.latex-doc { background: #fff; border: 1px solid #ddd; padding: 14px 16px; min-height: 180px; }
	.prose { overflow-wrap: anywhere; }
	.hint { margin: 6px 2px 0; }

	.latex-doc :global(.body) { max-width: none; margin: 0; padding: 0; }
	.latex-doc :global(.latex-img) { display: block; max-width: 100%; margin: 8px 0; }
	.prose :global(img) { max-width: 100%; border: 1px solid var(--line); }

	/* compile log */
	.log { border: 1px solid #f2b8b8; background: #fff0f0; margin-top: 8px; }
	.log__head { display: block; width: 100%; text-align: left; background: none; border: 0; color: #b00020;
		font-size: 12px; font-weight: bold; padding: 5px 8px; cursor: pointer; }
	.log__head:hover { background: #ffe6e6; }
	.log__body { padding: 0 8px 8px; }
	.log__msg { margin: 0 0 6px; background: #fff; border: 1px solid #f2b8b8; color: #b00020; max-height: 150px; }

	.savebar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: 4px 0 0; }

	@media (min-width: 720px) {
		.split { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
		.split--tex { grid-template-columns: 132px minmax(0, 1fr); }
		.split--tex .pane--preview { grid-column: 1 / -1; }
	}
	@media (min-width: 980px) {
		.split--tex { grid-template-columns: 128px minmax(0, 1fr) minmax(0, 1fr); }
		.split--tex .pane--preview { grid-column: auto; }
	}
</style>
