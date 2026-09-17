# Research brief for Gemini — fuw.lol market research (Sept 2026)

Context for the model: **fuw.lol** is an unofficial, community-run archive of the *funny* side of the
Faculty of Physics, University of Warsaw — memes, quotes, legendary exam problems, photos, scans,
folklore, old web pages. Posts are Markdown+KaTeX or LaTeX (compiled in the browser), with up to 6
files (image/PDF/audio/video, 25 MB). Everything from a non-trusted account waits for a moderator;
users with a confirmed FUW/UW/PAN e-mail are "trusted" (publish at once, can hide content). There is
an old-school shoutbox chat, a time machine (Internet Archive snapshots of fuw.edu.pl back to 1998),
and a legal escalation path to NASK/Dyżurnet.pl. Stack: Django + SvelteKit, Hetzner + Coolify +
Cloudflare. The look deliberately copies fuw.edu.pl.

Answer each item with dated sources; end with a **ranked list of the five improvements with the
strongest evidence** and the one assumption of ours you think is most likely wrong.

1. **Comparable projects.** Which university/faculty humour or folklore archives exist — Poland first
   (Spotted pages, „memy z wydziału” groups, student-council wikis, Wykop tags), then MIT/Caltech/
   Oxford-style lore sites, subreddit wikis, Fandom wikis? For each: what they collect, how they
   moderate, what killed the dead ones, what the living ones added in their first two years.
2. **Where the content lives today** for FUW UW students: Facebook groups, Discord, Messenger,
   Instagram. What makes somebody move a meme from a group chat into an archive, and what stops them
   (effort, fear of being identified, "it's ours, not public")?
3. **Legal risk map (Poland/EU)**: photos of identifiable people without consent (RODO, art. 81 pr.
   aut.), quotes attributed to named lecturers (art. 212 KK, dobra osobiste), scans of exam sheets
   (university copyright), and DSA obligations for a small hosting service (notice-and-action,
   statement of reasons, contact point). What must a takedown/report flow contain to be compliant?
4. **NASK / Dyżurnet.pl**: the current reporting form and process, what evidence they want, whether a
   SHA-256-verified frozen evidence package is useful to them, and any data-preservation duties after
   a report.
5. **Trust tiers in small communities**: evidence on quorum-based auto-hide (we hide a chat message
   after 3 distinct trusted reports) and on reporter-reputation systems; thresholds that work at a
   few hundred users; known abuse patterns (brigading by a trusted clique).
6. **Editor expectations**: do physics students want a LaTeX editor for posts, or is Markdown with
   `$…$` enough? Documented limits people hit with LaTeX.js/KaTeX (TikZ, tables, packages) and how
   other sites handle "paste a whole .tex".
7. **Browsing patterns for archives**: are year timelines and "person" indexes used, or do people
   only search and hit "random"? Any analytics or UX studies from meme/lore archives.
8. **Brand-confusion risk** of copying the faculty site's look: precedents of universities objecting
   to parody/unofficial sites (Poland and abroad) and how they were resolved; what a disclaimer needs.
9. **Hosting sanity check**: Hetzner CX23 + Coolify + Cloudflare (free) vs Mikrus / OVH / a Polish VPS
   for a site with 25 MB uploads and light traffic; what breaks at Cloudflare's 100 MB request cap;
   backup practices for a one-box deployment.
10. **Growth channels** that worked for comparable student projects (student council mailing,
    orientation week, alumni groups, lecturer buy-in) and the typical failure mode of
    "launched, forty posts, silence" — what the survivors did differently in months 2–6.
