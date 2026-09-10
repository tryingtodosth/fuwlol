<!-- Eras 6, 7 and 8, which have one thing in common: there is no page to show, so the
     page is about that. A cave wall, then a sky with something falling out of it, then
     nothing at all. Everything is drawn inline — no images to load and no fonts either,
     because at this end of the timeline there is nothing left to set in type. -->
<script lang="ts">
	let { variant }: { variant: 'cave' | 'dinosaurs' | 'void' } = $props();

	/** Fixed, not random: the wall should look the same every time you come back to it. */
	const GLYPHS: number[][] = [
		[22, 9, 15, 30, 11, 19, 8, 26],
		[13, 24, 9, 17, 12, 33, 10],
		[28, 11, 20, 9, 14, 22, 9, 16, 12],
		[9, 18, 26, 10, 15, 9, 21]
	];
</script>

{#if variant === 'cave'}
	<div class="scene scene--cave">
		<div class="wall">
			<svg class="art" viewBox="0 0 800 340" role="img" aria-labelledby="cave-title">
				<title id="cave-title">
					Malowidło naskalne: odciski dłoni i postać rzucająca kamieniem po torze parabolicznym
				</title>
				<!-- hand stencils: ochre blown around the hand, so the hand itself is bare rock -->
				<g class="stencil">
					<ellipse class="halo" cx="96" cy="150" rx="62" ry="74" />
					<g class="hand" transform="translate(56 92) scale(0.66)">
						<rect x="30" y="52" width="40" height="46" rx="16" />
						<rect x="33" y="20" width="9" height="38" rx="4.5" />
						<rect x="45" y="14" width="9" height="44" rx="4.5" />
						<rect x="57" y="20" width="9" height="38" rx="4.5" />
						<rect x="68" y="30" width="8" height="30" rx="4" />
						<rect x="18" y="44" width="8" height="30" rx="4" transform="rotate(-28 22 59)" />
					</g>
				</g>
				<g class="stencil" transform="translate(78 26) rotate(9 96 150) scale(0.78)">
					<ellipse class="halo" cx="96" cy="150" rx="62" ry="74" />
					<g class="hand" transform="translate(56 92) scale(0.66)">
						<rect x="30" y="52" width="40" height="46" rx="16" />
						<rect x="33" y="20" width="9" height="38" rx="4.5" />
						<rect x="45" y="14" width="9" height="44" rx="4.5" />
						<rect x="57" y="20" width="9" height="38" rx="4.5" />
						<rect x="68" y="30" width="8" height="30" rx="4" />
						<rect x="18" y="44" width="8" height="30" rx="4" transform="rotate(-28 22 59)" />
					</g>
				</g>

				<!-- the thrower -->
				<g class="figure">
					<circle cx="330" cy="176" r="11" />
					<line x1="330" y1="187" x2="330" y2="232" />
					<line x1="330" y1="232" x2="316" y2="270" />
					<line x1="330" y1="232" x2="346" y2="270" />
					<line x1="330" y1="198" x2="306" y2="216" />
					<line x1="330" y1="198" x2="356" y2="172" />
				</g>
				<!-- the throw: a parabola, dotted, because somebody was already noticing -->
				<path class="traj" d="M 362 166 Q 500 78 646 208" />
				<circle class="rock" cx="366" cy="164" r="6" />
				<circle class="rock rock--landed" cx="648" cy="212" r="6" />

				<!-- the audience -->
				<g class="figure figure--small">
					<circle cx="700" cy="196" r="8" />
					<line x1="700" y1="204" x2="700" y2="238" />
					<line x1="700" y1="238" x2="690" y2="266" />
					<line x1="700" y1="238" x2="712" y2="266" />
					<line x1="700" y1="212" x2="682" y2="200" />
					<line x1="700" y1="212" x2="718" y2="200" />
				</g>
			</svg>

			<div class="glyphs" aria-hidden="true">
				{#each GLYPHS as row, r (r)}
					<div class="glyphs__row">
						{#each row as w, i (i)}
							<span class="glyph" style="width:{w}px"></span>
						{/each}
					</div>
				{/each}
			</div>
		</div>
		<p class="cap">Brak strony. Brak wydziału. Prawa fizyki: już obowiązują.</p>
	</div>
{:else if variant === 'dinosaurs'}
	<div class="scene scene--dino">
		<svg class="sky" viewBox="0 0 800 360" role="img" aria-labelledby="dino-title">
			<title id="dino-title">
				Sylwetka dinozaura patrzącego w niebo, po którym leci kometa
			</title>
			<g class="stars">
				<circle cx="70" cy="52" r="1.4" /><circle cx="150" cy="92" r="1" />
				<circle cx="236" cy="40" r="1.6" /><circle cx="318" cy="104" r="1.1" />
				<circle cx="404" cy="58" r="1.3" /><circle cx="486" cy="120" r="1" />
				<circle cx="566" cy="34" r="1.5" /><circle cx="640" cy="96" r="1.2" />
				<circle cx="722" cy="60" r="1" /><circle cx="762" cy="132" r="1.4" />
				<circle cx="112" cy="150" r="1" /><circle cx="392" cy="166" r="1.1" />
			</g>

			<!-- the comet, and where it has been -->
			<path class="traj" d="M 96 26 Q 330 96 556 196" />
			<g class="comet" transform="translate(556 196)">
				<path class="tail" d="M 0 0 L -74 -30 L -66 -8 L -84 6 L -58 10 Z" />
				<circle class="head" cx="0" cy="0" r="7.5" />
			</g>

			<!-- ground -->
			<path class="ground" d="M 0 330 C 140 312 260 322 380 316 C 520 309 660 322 800 312 L 800 360 L 0 360 Z" />

			<!-- sauropod, neck up, watching -->
			<path
				class="dino"
				d="M 40 318
				   C 110 300 168 292 214 286
				   C 268 279 300 254 318 210
				   C 332 176 348 140 380 116
				   C 400 100 424 92 446 92
				   C 462 92 470 100 466 110
				   C 462 120 448 122 436 128
				   C 412 141 396 166 388 196
				   C 380 226 374 254 370 276
				   L 380 318 L 356 318 L 348 282
				   C 326 292 300 298 274 302
				   L 268 318 L 244 318 L 240 304
				   C 176 314 106 320 40 318 Z"
			/>
			<circle class="eye" cx="452" cy="102" r="2.1" />
		</svg>
		<p class="cap cap--dark">
			Wydział Fizyki jeszcze nie istnieje. Cząstka o dużym pędzie: w drodze.
		</p>
	</div>
{:else}
	<div class="scene scene--void">
		<p class="void__line">t &lt; 0. Strona nie istnieje. „Przed” też nie.</p>
		<p class="void__back"><a href="/">← wróć do teraźniejszości</a></p>
	</div>
{/if}

<style>
	.scene {
		margin: 0 calc(50% - 50vw);
		width: 100vw;
		padding: 26px 0 34px;
	}

	/* ── cave ─────────────────────────────────────────────────────────────── */
	.scene--cave {
		background:
			radial-gradient(ellipse at 22% 18%, rgba(196, 118, 52, 0.34), transparent 58%),
			radial-gradient(ellipse at 78% 74%, rgba(140, 70, 28, 0.32), transparent 56%),
			radial-gradient(ellipse at 55% 46%, rgba(96, 58, 30, 0.5), transparent 70%),
			repeating-linear-gradient(
				104deg,
				rgba(0, 0, 0, 0.13) 0 3px,
				rgba(255, 255, 255, 0.035) 3px 7px
			),
			#3b2415;
	}
	.wall {
		width: 92%;
		max-width: 900px;
		margin: 0 auto;
	}
	.art {
		display: block;
		width: 100%;
		height: auto;
	}
	.halo {
		fill: #c2732c;
		opacity: 0.62;
		filter: blur(7px);
	}
	.hand rect {
		fill: #3b2415;
	}
	.figure line {
		stroke: #cf7c2f;
		stroke-width: 6;
		stroke-linecap: round;
	}
	.figure circle {
		fill: #cf7c2f;
	}
	.figure--small line {
		stroke-width: 4.5;
	}
	.traj {
		fill: none;
		stroke: #e2a765;
		stroke-width: 3;
		stroke-dasharray: 2 11;
		stroke-linecap: round;
		opacity: 0.85;
	}
	.rock {
		fill: #e8bb84;
	}
	.rock--landed {
		opacity: 0.5;
	}
	.glyphs {
		margin: 16px auto 0;
		max-width: 640px;
	}
	.glyphs__row {
		display: flex;
		gap: 8px;
		justify-content: center;
		margin-bottom: 9px;
	}
	.glyph {
		height: 7px;
		background: #c2732c;
		opacity: 0.75;
		border-radius: 3px;
		display: block;
	}
	.cap {
		width: 92%;
		max-width: 900px;
		margin: 20px auto 0;
		text-align: center;
		font-family: Tahoma, Verdana, Arial, sans-serif;
		font-size: 13px;
		color: #f0d6b4;
	}

	/* ── dinosaurs ────────────────────────────────────────────────────────── */
	.scene--dino {
		background:
			radial-gradient(ellipse at 70% 12%, rgba(70, 96, 140, 0.4), transparent 55%),
			radial-gradient(ellipse at 20% 90%, rgba(120, 60, 30, 0.3), transparent 60%),
			linear-gradient(180deg, #070b18 0%, #101a30 55%, #241a1c 100%);
	}
	.sky {
		display: block;
		width: 92%;
		max-width: 900px;
		height: auto;
		margin: 0 auto;
	}
	.stars circle {
		fill: #dfe6f5;
		opacity: 0.8;
	}
	.scene--dino .traj {
		stroke: #9fb4dd;
		stroke-width: 2;
		stroke-dasharray: 2 9;
		opacity: 0.7;
	}
	.comet .head {
		fill: #fff4d8;
	}
	.comet .tail {
		fill: #ffd489;
		opacity: 0.72;
	}
	.ground {
		fill: #14100f;
	}
	.dino {
		fill: #0d0b0c;
	}
	.eye {
		fill: #ffd489;
	}
	.cap--dark {
		color: #c9d3e8;
	}

	/* ── void ─────────────────────────────────────────────────────────────── */
	.scene--void {
		background: #000;
		min-height: 62vh;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 26px;
	}
	.void__line {
		margin: 0;
		color: #fff;
		font-family: 'DejaVu Sans Mono', Consolas, monospace;
		font-size: 15px;
		letter-spacing: 1px;
		text-align: center;
		padding: 0 16px;
	}
	.void__back {
		margin: 0;
		font-family: 'DejaVu Sans Mono', Consolas, monospace;
		font-size: 12px;
	}
	.void__back a {
		color: #6f6f6f;
	}
	.void__back a:hover {
		color: #fff;
	}
</style>
