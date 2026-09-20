<script lang="ts">
	/** The faculty's footer is one bare line at the bottom left („Stopka redakcyjna”, a rust
	 * link, 10px in from the edge). Ours says what the site is not, and where the code is. */
</script>

<footer class="foot">
	<p>
		fuw.lol — nieoficjalne archiwum Wydziału Fizyki UW; ta strona nie jest stroną Wydziału.
		Zgłoś błąd albo poproś o usunięcie przy każdym wpisie.
	</p>
	<p class="foot__links">
		<a href="/o-archiwum">O archiwum</a>
		<!-- An unofficial archive that moderates other people's content owes readers a way
		     to check what it actually does with it; the source is that answer. -->
		<a href="https://github.com/tryingtodosth/fuwlol" target="_blank" rel="noopener noreferrer">
			Kod źródłowy (GitHub)
		</a>
	</p>
</footer>

<style>
	.foot {
		margin-top: 20px;
		padding: 0 10px 10px;
	}
	.foot p {
		margin: 0;
		font-size: 12px;
		color: var(--text);
	}
	.foot__links {
		display: flex;
		gap: 12px;
		flex-wrap: wrap;
	}
	.foot :global(a) {
		color: var(--rust);
	}
</style>
