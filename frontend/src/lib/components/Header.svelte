<script lang="ts">
	/** The banner and the green bar, copied from fuw.edu.pl on purpose: an amber strip 1000px
	 * wide with the mark at its left edge and plain dark icons at its right, the navigation as a
	 * second 1000px bar directly under it, and on a phone the grey hamburger square inside the
	 * banner instead of the old full-width "Menu" bar. */
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import { auth } from '$lib/auth.svelte';
	import type { Category } from '$lib/types';

	let categories = $state<Category[]>([]);
	let pending = $state(0);
	let escalations = $state(0);
	let dropOpen = $state(false);
	let mobileOpen = $state(false);

	onMount(async () => {
		try {
			categories = await api.get<Category[]>('/categories/');
		} catch {
			/* the rest of the navigation still works without the category list */
		}
	});

	// plain `let`, not $state: only a guard, never read by the template
	let askedForStats = false;
	$effect(() => {
		if (!auth.isStaff || askedForStats) return;
		askedForStats = true;
		api.get<{ pending: number }>('/posts/stats/')
			.then((s) => (pending = s.pending))
			.catch(() => {});
	});
	let askedForEscalations = false;
	$effect(() => {
		if (!auth.isHeadAdmin || askedForEscalations) return;
		askedForEscalations = true;
		api.get<unknown[]>('/moderation/escalations/?status=pending')
			.then((rows) => (escalations = rows.length))
			.catch(() => {});
	});

	// any navigation closes whatever the reader left open
	$effect(() => {
		void page.url.pathname;
		void page.url.search;
		dropOpen = false;
		mobileOpen = false;
	});

	async function logout() {
		await auth.logout();
		goto('/');
	}

	function onKey(e: KeyboardEvent) {
		if (e.key === 'Escape') dropOpen = false;
	}
</script>

<svelte:window onkeydown={onKey} />

<header class="banner">
	<a class="brand" href="/">
		<svg class="brand__mark" width="61" height="61" viewBox="0 0 46 46" aria-hidden="true">
			<rect width="46" height="46" fill="#175e4c" />
			<polygon points="23,6 42,17 4,17" fill="#fff" />
			<rect x="6" y="19" width="5" height="15" fill="#fff" />
			<rect x="14" y="19" width="5" height="15" fill="#fff" />
			<rect x="27" y="19" width="5" height="15" fill="#fff" />
			<rect x="35" y="19" width="5" height="15" fill="#fff" />
			<rect x="3" y="35" width="40" height="4" fill="#fff" />
		</svg>
		<span class="brand__txt">
			<span class="brand__name">fuw.lol</span>
			<span class="brand__sub">ARCHIWUM WYDZIAŁU FIZYKI UW</span>
			<!-- The faculty's banner has two lines; this third one is the whole disclaimer in
			     four words, in the one place nobody can miss it. `PRODUCT.md`: the site copies
			     fuw.edu.pl on purpose and must never be mistaken FOR it. -->
			<span class="brand__tag">100% legit nieoficjalne</span>
		</span>
	</a>

	<div class="banner__grow"></div>

	<div class="banner__icons">
		{#if auth.isAuthenticated}
			<a class="who" href="/konto">{auth.user?.username}</a>
			<button type="button" class="linky" onclick={logout}>Wyloguj</button>
		{:else if auth.ready}
			<a class="who" href="/logowanie">Zaloguj się</a>
		{/if}
		<a class="icon" href="/przegladaj" title="Szukaj w archiwum" aria-label="Szukaj w archiwum">
			<svg width="29" height="29" viewBox="0 0 24 24" aria-hidden="true">
				<circle cx="10" cy="10" r="6.5" fill="none" stroke="#222" stroke-width="2" />
				<line x1="15" y1="15" x2="21.5" y2="21.5" stroke="#222" stroke-width="2" stroke-linecap="round" />
			</svg>
		</a>
		<!-- the faculty's hamburger: a grey square at the right end of the banner, phones only -->
		<button
			type="button"
			class="toggleMenu"
			aria-expanded={mobileOpen}
			aria-controls="nav-main"
			aria-label="Menu"
			onclick={() => (mobileOpen = !mobileOpen)}
		>
			<svg width="29" height="29" viewBox="0 0 24 24" aria-hidden="true">
				<path d="M3 6h18M3 12h18M3 18h18" stroke="#fff" stroke-width="2" stroke-linecap="round" />
			</svg>
		</button>
	</div>
</header>

<nav class="nav" class:is-open={mobileOpen} id="nav-main" aria-label="Nawigacja główna">
	<ul class="nav__list">
		<li><a href="/">Strona główna</a></li>
		<li class="has-drop">
			<button
				type="button"
				aria-expanded={dropOpen}
				aria-haspopup="true"
				onclick={() => (dropOpen = !dropOpen)}
			>
				Przeglądaj
			</button>
			<ul class="drop" class:is-open={dropOpen}>
				<li><a href="/przegladaj">Wszystkie wpisy</a></li>
				{#each categories as c (c.slug)}
					<li>
						<a href="/przegladaj?category={c.slug}">
							{c.emoji} {c.name} <span class="cnt">({c.post_count})</span>
						</a>
					</li>
				{/each}
			</ul>
		</li>
		<li><a href="/ludzie">Ludzie</a></li>
		<li><a href="/przedmioty">Przedmioty</a></li>
		<li><a href="/os-czasu">Oś czasu</a></li>
		<li><a href="/losowe">Losowy wpis</a></li>
		<li><a href="/czat">Czat</a></li>
		<li><a href="/dodaj">Dodaj wpis</a></li>
		{#if auth.isAuthenticated}
			<li><a href="/moje">Moje wpisy</a></li>
		{/if}
		{#if auth.isTrusted}
			<li><a href="/tablica">Tablica</a></li>
		{/if}
		{#if auth.isStaff}
			<li>
				<a href="/moderacja">Moderacja{pending ? ` (${pending})` : ''}</a>
			</li>
		{/if}
		{#if auth.isHeadAdmin}
			<li>
				<a href="/eskalacje" class:nav__alert={escalations > 0}>NASK{escalations ? ` (${escalations})` : ''}</a>
			</li>
		{/if}
		<li><a href="/o-archiwum">O archiwum</a></li>
	</ul>
</nav>

<style>
	/* .responsive_baner: rgb(253,186,69), 1000px, 71px, flex; the logo sits flush left */
	.banner {
		max-width: 1000px;
		margin: 0 auto;
		min-height: 71px;
		background: var(--amber);
		display: flex;
		align-items: center;
	}
	.brand {
		display: flex;
		align-items: center;
		gap: 10px;
		color: #222;
		padding: 5px 0;
	}
	.brand:hover {
		text-decoration: none;
	}
	.brand__mark {
		display: block;
		flex: 0 0 auto;
	}
	.brand__txt {
		display: block;
		line-height: 1.2;
	}
	.brand__name {
		display: block;
		font-size: 22px;
		font-weight: bold;
		color: var(--green);
		letter-spacing: -0.5px;
	}
	.brand__sub {
		display: block;
		font-size: 10px;
		letter-spacing: 1px;
		color: #333;
	}
	.brand__tag {
		display: block;
		font-size: 10px;
		font-style: italic;
		color: var(--rust);
	}
	.banner__grow {
		flex: 1 1 auto;
	}
	.banner__icons {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 0 10px;
		font-size: 13px;
	}
	.banner__icons a {
		color: #222;
	}
	.icon {
		display: inline-flex;
		padding: 4px;
	}
	.who {
		max-width: 130px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.linky {
		background: none;
		border: 0;
		padding: 0;
		font-size: 13px;
		color: var(--rust);
		cursor: pointer;
		font-family: inherit;
	}
	.linky:hover {
		background: none;
		text-decoration: underline;
	}

	/* .toggleMenu: #666, padding 4px 4px 3px around a 29px icon — 37×36 */
	.toggleMenu {
		display: none;
		background: #666;
		border: 0;
		color: #fff;
		padding: 4px 4px 3px;
		line-height: 0;
		border-radius: 0;
	}
	.toggleMenu:hover {
		background: #555;
	}

	/* .nav: #175e4c, 1000px, links 13px white with 5px 15px padding, one 1px darker line on top */
	.nav {
		max-width: 1000px;
		margin: 0 auto;
		background: var(--green);
	}
	.nav__list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-wrap: wrap;
	}
	.nav__list > li {
		position: relative;
		border-top: 1px solid var(--green-dark);
	}
	.nav :global(a),
	.nav button {
		display: block;
		color: #fff;
		font-size: 13px;
		line-height: 1.5;
		padding: 5px 15px;
		background: none;
		border: 0;
		font-family: inherit;
		cursor: pointer;
		white-space: nowrap;
		border-radius: 0;
	}
	.nav :global(a:hover),
	.nav button:hover,
	.has-drop:hover > button,
	.has-drop:focus-within > button {
		background: var(--green-light);
		text-decoration: none;
	}
	/* the faculty's parent items carry a small grey arrow at their right edge */
	.has-drop > button {
		padding-right: 28px;
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='9' height='5'%3E%3Cpath d='M0 0h9L4.5 5z' fill='%23c2c2c2'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right 12px center;
	}
	.nav :global(a.nav__alert) {
		background: var(--rust);
	}
	/* .nav li ul: 20em wide, each item #1d7a62 with a 1px #175e4c line on top, no shadow */
	.drop {
		display: none;
		position: absolute;
		left: 0;
		top: 100%;
		z-index: 40;
		width: 20em;
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.has-drop:hover .drop,
	.has-drop:focus-within .drop,
	.drop.is-open {
		display: block;
	}
	.drop :global(a) {
		background: var(--green-light);
		border-top: 1px solid var(--green);
		white-space: normal;
	}
	.drop :global(a:hover) {
		background: var(--green);
	}
	.cnt {
		color: #b7ddd1;
		font-size: 11px;
	}

	@media (max-width: 850px) {
		.toggleMenu {
			display: inline-block;
		}
		.nav {
			display: none;
		}
		.nav.is-open {
			display: block;
		}
		.nav__list {
			display: block;
		}
		.nav :global(a),
		.nav button {
			padding: 6px 15px;
			white-space: normal;
		}
		.drop {
			position: static;
			width: auto;
		}
		.brand__name {
			font-size: 18px;
		}
		.brand__sub {
			font-size: 9px;
		}
		.banner__icons {
			gap: 6px;
			padding: 0 0 0 6px;
		}
	}
	/* the faculty's phone banner is logos and icons only; ours keeps the name and drops the line
	   under it, which otherwise wraps into the icons at 390px */
	@media (max-width: 480px) {
		.brand__sub {
			display: none;
		}
		.brand__name {
			font-size: 20px;
		}
		/* the disclaimer stays where the description goes: it is four words, and it is the
		   line a reader who landed here from a search result needs to see */
		.brand__tag {
			font-size: 9px;
		}
	}
</style>
