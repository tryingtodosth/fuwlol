<!-- The transition into every era but our own: a flash, a fireball, a shockwave and a
     few hundred particles, on one requestAnimationFrame clock. `reverse` runs the same
     clock backwards, which is how the `void` era arrives — everything falls back in.
     No libraries; the particles are a canvas, the fireball and the ring are CSS radial
     gradients whose transform is driven by the same progress value. -->
<script lang="ts">
	import { onMount } from 'svelte';

	let { onDone, reverse = false }: { onDone: () => void; reverse?: boolean } = $props();

	const DURATION = 2200;
	const FADE_OUT = 190;

	let canvas = $state<HTMLCanvasElement | null>(null);
	/** 0 -> 1 along the animation, already flipped when `reverse`. */
	let p = $state(0);
	let overlayOut = $state(false);
	let reduced = $state(false);

	let finished = false;
	let raf = 0;
	let timer: ReturnType<typeof setTimeout> | undefined;

	function finish() {
		if (finished) return;
		finished = true;
		cancelAnimationFrame(raf);
		onDone();
	}

	/** Skip: stop the clock, fade the black out, then hand over. */
	function skip() {
		if (finished || overlayOut) return;
		cancelAnimationFrame(raf);
		overlayOut = true;
		timer = setTimeout(finish, FADE_OUT + 10);
	}

	function onKey(e: KeyboardEvent) {
		if (e.key === 'Escape') skip();
	}

	const easeOut = (t: number) => 1 - Math.pow(1 - t, 3);

	interface Particle {
		a: number; // direction, radians
		v: number; // how far out it gets, as a fraction of the screen
		hue: number;
		size: number;
	}

	onMount(() => {
		reduced =
			typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

		// The era is already mounted behind this opaque overlay; stop the wheel from
		// scrolling it out of sight while nobody can see what they are doing.
		const scrollWas = document.body.style.overflow;
		document.body.style.overflow = 'hidden';
		const unlock = () => {
			document.body.style.overflow = scrollWas;
		};

		if (reduced) {
			// Nothing moves: a plain 300 ms curtain, then on with it.
			timer = setTimeout(finish, 300);
			return () => {
				clearTimeout(timer);
				unlock();
				finished = true;
			};
		}

		const el = canvas;
		const ctx = el?.getContext('2d') ?? null;
		let w = 0;
		let h = 0;
		let dpr = 1;

		function size() {
			if (!el || !ctx) return;
			dpr = Math.min(window.devicePixelRatio || 1, 2);
			w = window.innerWidth;
			h = window.innerHeight;
			el.width = Math.round(w * dpr);
			el.height = Math.round(h * dpr);
			ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
			ctx.fillStyle = '#000';
			ctx.fillRect(0, 0, w, h);
		}
		size();

		const count = w < 560 ? 150 : 260;
		const parts: Particle[] = Array.from({ length: count }, () => ({
			a: Math.random() * Math.PI * 2,
			v: 0.12 + Math.random() * Math.random() * 0.95,
			hue: 20 + Math.random() * 45, // white-hot through amber, the site's own palette
			size: 0.7 + Math.random() * 2.4
		}));

		const started = performance.now();

		function frame(now: number) {
			const t = Math.min(1, (now - started) / DURATION);
			p = reverse ? 1 - t : t;

			if (ctx) {
				// A translucent wipe instead of a clear: that leftover is the afterglow.
				ctx.globalCompositeOperation = 'source-over';
				ctx.fillStyle = 'rgba(0, 0, 0, 0.2)';
				ctx.fillRect(0, 0, w, h);
				ctx.globalCompositeOperation = 'lighter';

				const cx = w / 2;
				const cy = h / 2;
				const reach = Math.hypot(w, h) * 0.55;
				const spread = easeOut(p);
				for (const q of parts) {
					const d = q.v * spread * reach;
					const x = cx + Math.cos(q.a) * d;
					const y = cy + Math.sin(q.a) * d;
					const alpha = Math.max(0, 1 - p * 0.95) * (0.35 + q.v * 0.65);
					const light = 60 + (1 - p) * 40;
					ctx.beginPath();
					ctx.arc(x, y, q.size * (1 + spread * 0.8), 0, Math.PI * 2);
					ctx.fillStyle = `hsla(${q.hue}, 100%, ${light}%, ${alpha})`;
					ctx.fill();
				}
				ctx.globalCompositeOperation = 'source-over';
			}

			if (t >= 1) {
				overlayOut = true;
				timer = setTimeout(finish, FADE_OUT + 10);
				return;
			}
			raf = requestAnimationFrame(frame);
		}
		raf = requestAnimationFrame(frame);
		window.addEventListener('resize', size);

		return () => {
			cancelAnimationFrame(raf);
			clearTimeout(timer);
			window.removeEventListener('resize', size);
			unlock();
			finished = true; // never call back after the parent has thrown us away
		};
	});

	// Flash: a hard white peak right at the start, gone almost at once.
	const flash = $derived(Math.max(0, 1 - Math.pow(p * 9, 1.6)));
	const ballScale = $derived(0.05 + easeOut(Math.min(1, p * 1.5)) * 2.9);
	const ballAlpha = $derived(p < 0.45 ? 1 : Math.max(0, 1 - (p - 0.45) / 0.5));
	const ringScale = $derived(easeOut(p) * 3.6);
	const ringAlpha = $derived(p < 0.08 ? p / 0.08 : Math.max(0, 1 - (p - 0.08) / 0.78));
</script>

<svelte:window onkeydown={onKey} />

<div class="bb" class:is-out={overlayOut}>
	{#if !reduced}
		<canvas bind:this={canvas} aria-hidden="true"></canvas>
		<div class="bb__ball" aria-hidden="true" style="opacity:{ballAlpha}; transform: translate(-50%,-50%) scale({ballScale})"></div>
		<div class="bb__ring" aria-hidden="true" style="opacity:{ringAlpha}; transform: translate(-50%,-50%) scale({ringScale})"></div>
		<div class="bb__flash" aria-hidden="true" style="opacity:{flash}"></div>
	{/if}
	<button type="button" class="bb__skip" onclick={skip}>Pomiń</button>
	<p class="bb__cap" aria-live="polite">
		{reverse ? 'Cofamy Wielki Wybuch…' : 'Wielki Wybuch…'}
	</p>
</div>

<style>
	.bb {
		position: fixed;
		inset: 0;
		z-index: 9000;
		background: #000;
		overflow: hidden;
		opacity: 1;
		transition: opacity 190ms linear;
	}
	.bb.is-out {
		opacity: 0;
		pointer-events: none;
	}
	canvas {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		display: block;
	}
	.bb__ball,
	.bb__ring {
		position: absolute;
		left: 50%;
		top: 50%;
		width: 180px;
		height: 180px;
		border-radius: 50%;
		will-change: transform, opacity;
	}
	.bb__ball {
		background: radial-gradient(
			circle,
			#fff 0%,
			#fff6d8 14%,
			#fdba45 34%,
			#ff8c00 52%,
			rgba(168, 66, 4, 0.55) 70%,
			rgba(168, 66, 4, 0) 78%
		);
		filter: blur(1px);
	}
	.bb__ring {
		border: 2px solid rgba(255, 246, 216, 0.85);
		box-shadow: 0 0 26px rgba(253, 186, 69, 0.65);
	}
	.bb__flash {
		position: absolute;
		inset: 0;
		background: #fff;
	}
	.bb__skip {
		position: absolute;
		top: 14px;
		right: 14px;
		background: transparent;
		border: 1px solid rgba(255, 255, 255, 0.6);
		color: #fff;
		font-size: 12px;
		padding: 4px 12px;
	}
	.bb__skip:hover {
		background: rgba(255, 255, 255, 0.14);
	}
	.bb__skip:focus-visible {
		outline: 2px solid var(--amber);
		outline-offset: 2px;
	}
	.bb__cap {
		position: absolute;
		left: 0;
		right: 0;
		bottom: 26px;
		margin: 0;
		text-align: center;
		color: rgba(255, 255, 255, 0.72);
		font-size: 11px;
		letter-spacing: 3px;
		text-transform: uppercase;
	}
	@media (prefers-reduced-motion: reduce) {
		.bb {
			transition: opacity 300ms linear;
		}
	}
</style>
