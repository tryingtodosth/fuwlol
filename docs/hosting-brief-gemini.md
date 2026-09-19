# Research brief for Gemini — where should fuw.lol be hosted? (September 2026)

**What we are choosing hosting for.** fuw.lol is an unofficial, community-run archive of the
folklore of the Faculty of Physics, University of Warsaw — memes, quotes, legendary exam problems,
scans, photos, old web pages. It is a hobby project run by one person, non-commercial, no revenue,
with an almost entirely Polish audience.

**The stack, exactly as it is today:**
- Django 5 + DRF behind gunicorn (3 workers), PostgreSQL 16, and an nginx container serving a
  prebuilt SvelteKit SPA and proxying `/api`, `/admin`, `/static` to the app. Three containers, one
  `docker-compose.yml`, everything on one domain (no CORS).
- Currently deployed as **one Hetzner Cloud CX23 + Coolify + Cloudflare (free plan)**, Germany.
  This is the baseline to beat — a candidate, not a constraint.
- Uploads: up to 6 files × 25 MB per post (image/PDF/audio/video) on a local Docker volume. A
  separate `evidence` volume holds SHA-256-verified evidence packages and quarantined files
  produced by the legal escalation path (DSA notice-and-action, NASK / Dyżurnet.pl reports).
- Per-IP and per-user rate limits (registration, e-mail verification, guest chat, reports) live in
  a **file-based cache on local disk**.
- E-mail drives the trust model: a user with a confirmed `@fuw.edu.pl` / UW / PAN address becomes
  "trusted" and publishes without moderation. Verification mail landing in spam breaks that tier.

**Requirements to research against:**
1. **A load balancer** in front of the application.
2. **A couple of real mailboxes** on `fuw.lol` (e.g. `archiwum@`, `kontakt@`, `abuse@`) — 2–3
   boxes, IMAP/SMTP, aliases, read by a human.
3. **Traffic is small**: normally dozens of visitors; the realistic worst case is ~500 simultaneous
   visitors, and that will be rare (a post going around a student group).
4. **Polish audience — not necessarily Polish servers.** Latency to Poland, Polish-language
   support, PLN/VAT invoicing and EU data residency all matter; the physical location does not have
   to be Poland. Any EU (or EU-adequate) provider is in scope, and where a non-Polish one clearly
   wins, say so and say why.
5. One maintainer, limited time. Ops burden is a first-class cost, not a footnote.

**Budget is not fixed.** Give options in three tiers — under 100 PLN/month, 100–300 PLN/month, and
above 300 PLN/month — and say what each tier actually buys.

Answer each item with **dated sources** (provider pricing pages over blog posts; flag any source
older than 12 months, and say whether a price is net or gross of VAT).

1. **Sizing sanity check.** What does "500 simultaneous visitors" mean in requests/second and
   concurrent connections for a read-heavy Django SPA backend, and what is the real bottleneck for
   this stack — gunicorn workers, Postgres connections, or nginx serving 25 MB media? Find
   benchmarks. How small a VPS genuinely survives that peak, and how much headroom does a
   2 vCPU / 4 GB box have?

2. **Does the load balancer earn its keep here?** At this scale an LB buys availability and
   zero-downtime deploys, not capacity. Price the real options — Hetzner Cloud Load Balancer,
   OVHcloud Load Balancer, Cloudflare Load Balancing (paid add-on), a managed LB in Azure Poland
   Central / GCP europe-central2 (Warsaw) or any EU region — versus simply running Traefik, nginx
   or HAProxy on the box itself. Cost per month, health-checking behaviour, and what each does
   *not* protect against (single VPS, single database, single region).

3. **What true HA would actually require for this stack**, and what it costs. Two app instances
   behind an LB means the file-based rate-limit cache must become shared (Redis/Valkey, managed or
   self-hosted — priced), the local media volume must become S3-compatible object storage (priced:
   Cloudflare R2, Hetzner Object Storage, OVH Object Storage, Backblaze B2, a Polish provider), and
   Postgres becomes the remaining single point of failure. Give the monthly total for "properly
   redundant" versus "one well-backed-up box", and say plainly which a project this size should pick.

4. **The provider matrix.** Compare with current prices: EU providers with good Polish latency —
   Hetzner (Falkenstein/Nuremberg), netcup, Contabo, Scaleway, UpCloud — alongside Polish ones —
   OVHcloud (Warsaw WAW), Atman, Beyond.pl / e24cloud (Poznań), home.pl, nazwa.pl, cyber_Folks,
   Zenbox, dhosting, MyDevil, Mikrus, LiveNet, Polcom — and the Poland-region hyperscalers (Azure
   Poland Central, Google Cloud europe-central2, any AWS Warsaw presence). For each: specs at our
   price points, Docker Compose support, snapshot/backup pricing, bandwidth limits and overage,
   IPv6, support hours and language, measured or documented latency to Warsaw, and any uptime SLA
   that is real rather than decorative.

5. **Managed Postgres or a container?** Price managed PostgreSQL in the EU (OVH, Azure Poland
   Central, GCP Warsaw, Aiven, Neon, Supabase — whichever have a suitable region) against running
   `postgres:16-alpine` next to the app. Include backup/PITR guarantees and what a restore actually
   involves for each.

6. **Mailboxes on a custom domain for 2–3 people.** Compare Polish providers (home.pl,
   cyber_Folks, nazwa.pl, Zenbox, seohost, dhosting) with EU/other options (Migadu, Mailbox.org,
   Fastmail, Google Workspace, Microsoft 365, Purelymail, Proton). Price per mailbox per year,
   storage, aliases and catch-all, IMAP/SMTP, 2FA, spam-filter quality, whether a RODO-compliant
   DPA is offered, and where the data physically sits. Note which also let us send application mail
   through the same account, and at what sending limits.

7. **Transactional e-mail that actually reaches university inboxes.** Verification mail must land
   in `@fuw.edu.pl`, `@uw.edu.pl` and `@student.uw.edu.pl` inboxes, not spam. Compare Polish relays
   (EmailLabs/Vercom, GetResponse, FreshMail, Redlink) with EU-hosted international ones (Brevo,
   Mailgun EU, Amazon SES eu-central-1, Postmark, MailerSend, Resend): cheapest/free tier and its
   volume, EU data residency, DPA availability, deliverability evidence, SPF/DKIM/DMARC setup.
   Separately: what SPF, DKIM and DMARC records a domain like ours needs in 2026 to avoid spam
   classification at Google- and Microsoft-hosted university mail, and whether Polish universities
   apply extra filtering (greylisting, strict DMARC) that catches small senders. Confirm which
   candidate hosts block outbound port 25 (Hetzner does) and whether that matters behind a relay on
   587/465.

8. **Abuse policy and takedown behaviour — this is a user-generated-content site.** fuw.lol hosts
   uploads from strangers and has a legal escalation path (DSA notice-and-action, NASK/Dyżurnet.pl,
   quarantined files kept as evidence). For each candidate: what the abuse process looks like in
   practice for a UGC host, whether one complaint can suspend a server without warning, what notice
   period is given, and any documented cases of Polish or German providers nulling hobby projects.
   Also: does hosting in Poland rather than elsewhere in the EU change our obligations or exposure
   under the DSA and the Polish *ustawa o świadczeniu usług drogą elektroniczną*, and does storing
   evidence packages (potentially including illegal material, quarantined) create contract problems
   we should raise before signing?

9. **Cloudflare in front, or not.** We use the free plan, proxied. Confirm the current free-plan
   limits that bite: the 100 MB request-body cap against our 6 × 25 MB uploads, cache rules, and
   whether proxying interferes with large uploads or with recovering the real client IP (we rely on
   `CF-Connecting-IP` for per-IP throttles). Price Cloudflare Load Balancing and R2 for our media,
   and compare against a Polish CDN or no CDN at all given an almost entirely Polish audience. Is
   free still right, and what would push us to Pro?

10. **Backups and disaster recovery for a one-box deployment.** Snapshot pricing and retention at
    each candidate, off-site EU backup destinations, cost of nightly `pg_dump` plus media sync, and
    the part usually skipped — what a full restore takes in wall-clock time. What is a realistic
    RPO/RTO for a hobby project, and what does improving it cost?

11. **Deployment and ops model.** Compare self-hosted Coolify (what we use) against Dokploy,
    CapRover, plain `docker compose` + Caddy, and managed PaaS with a nearby region (Fly.io `waw`,
    others). For each: maintenance burden for one maintainer, upgrade and security-patch story,
    lock-in, and the migration path if we outgrow or dislike it.

12. **Discounts we may be eligible for.** Nonprofit, student, academic or open-source hosting
    credits open to a non-commercial project run by a Polish university student — GitHub Student
    Developer Pack, provider nonprofit programmes, Polish academic infrastructure (PIONIER/PSNC),
    cloud credit programmes. State eligibility conditions honestly, including any that would require
    formal registration as an association or foundation.

**Finish with:**
- **A ranked recommendation**: one primary, one cheaper fallback, one "if it unexpectedly gets
  popular" — each with a concrete monthly total in PLN, itemised (compute + load balancer +
  database + object storage + mailboxes + transactional mail + backups + domain).
- **A one-page migration plan** from the current Hetzner + Coolify + Cloudflare setup to your
  primary recommendation: DNS, mail, data movement, estimated downtime.
- **The single assumption in this brief most likely to be wrong**, and what evidence changed your mind.
