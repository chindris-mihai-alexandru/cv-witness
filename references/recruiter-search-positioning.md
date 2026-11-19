# Position yourself for recruiter search (the reverse-recruit view)

The Treg `recruit` skill is the *employer's* sourcing workflow: a job post in, a ranked
candidate shortlist out. Read it backwards and it tells you exactly how you will be found,
ranked and contacted as a candidate. This note turns that into positioning rules for the
job seeker. It complements `treg-jobs-sourcing.md` (which finds roles); this one makes you
findable and rankable for them.

Source: the upstream `recruit` skill (`skills/recruit` in superdesigndev/treg) and the
Treg Recruiter page. The mechanics below are how the sourcing agent actually behaves, not
speculation.

## How a recruiter's agent finds you, and what to do about it

1. **Title variants.** The agent searches the posted title *plus two to four aliases the
   same job goes by* (one routed people search per variant). If your headline only carries
   one exact title, you miss the searches that use the others.
   → Carry the common variants of your target role in your LinkedIn headline and CV
   headline (e.g. "Technical Support Engineer · Application Support · Cloud Support").
   Keep them truthful and within the same job family.

2. **Must-have skills are search keywords.** The search passes `keywords:[…]` drawn from
   the post's must-haves. A skill buried in a bullet is weaker than one in the headline or
   skills line.
   → Surface the exact terms recruiters search for your target role (the tools, clouds and
   methods named in real postings) in your headline and skills section, not only deep in
   experience. Use the posting's own vocabulary.

3. **Hard filters drop people silently.** The agent drops, with a reason: wrong location,
   seniority too far off, a title from another job family, no profile URL to contact from,
   or already at the hiring company.
   → Make location and remote-openness explicit; state seniority clearly; keep your title
   in the right job family; and always have a public, contactable profile URL. A missing
   URL is an automatic drop.

4. **Ranking is one line on why you fit.** The agent ranks only survivors it can write a
   single specific line for ("8 yrs Go at a payments scale-up, led a Kafka migration"). No
   line, no rank.
   → Make that line easy to write about you: quantified, specific, role-relevant
   achievements near the top (scale, uptime, users, tests, latency). Vague duty lists give
   the agent nothing to rank.

## Evidence re-scoring: your public footprint moves you up or down

For the shortlist, the agent gathers *cited* facts and re-scores: a claim the evidence backs
moves a candidate up, one it contradicts moves them down. It checks:

- **Recent LinkedIn posts** — only your own posts from the last six months (it filters by
  author handle). → Post recently about the domain you want to be hired in; stale or
  off-topic posts give no lift.
- **GitHub** — languages, stars and repos that match the job's skills. → Keep public repos
  aligned to your target skills, with real activity; pin the relevant ones.
- **Talks and writing** — YouTube / Google Scholar results that actually name you. → A talk
  or article on the target topic is citable evidence; generic results are ignored.
- **Open to move** — job-change detection, tenure, and company news (layoffs, funding gap).
  A recent move reads as "less likely to move again"; long tenure plus company trouble reads
  as movable. → Understand these timing signals; they shape whether recruiters pursue you.

Two rules follow for your CV and profile:
- **Every claim should be backed by something citable.** A metric or project on your CV
  that a public repo, post or write-up corroborates ranks higher. Keep your `foundation.md`
  facts and your public footprint consistent.
- **Contradictions cost you.** If your CV says "led X" but your public footprint shows
  nothing of it, the evidence step can move you down. Do not claim what you cannot evidence.

## How the people-search bench grades you (LessieAI People Search Bench)

The open People Search Bench (119 queries, EMNLP 2026) scores people-search agents by
decomposing each query into **checkable criteria** and verifying every returned person
against them via **live web search — not the model's memory**. A person matching 2 of 3
criteria scores 0.67. Three dimensions, reverse-engineered for the candidate:

- **Relevance Precision** (padded nDCG@10): the fraction of the role's criteria you
  verifiably satisfy, ranked. → Make every must-have criterion (skill, years, location,
  seniority) factually true about you *online*, not only claimed on the CV.
- **Effective Coverage** (qualified yield, grade ≥ 0.5): you count only if you match at
  least half the criteria strongly. → Don't apply broadly into roles where you meet few of
  the must-haves; concentrate where you genuinely clear the bar.
- **Information Utility** (completeness + evidence quality + actionability): a complete
  profile, corroborated by cited evidence, with a clear way to act. → Full work history and
  skills, public repos/posts/talks that back the claims, and a contactable, consistent
  identity.

The lesson that ties it together: **agents grade on web-verifiable facts, not prose.** A
criterion the web confirms scores; a vague or contradicted claim does not. This is the same
rule as the evidence re-scoring above, measured. (The bench is maintained by LessieAI, itself
an evaluated platform — read its leaderboard with that disclosed interest in mind.)

Recruiters' agents build these lists as a *waterfall* — find → enrich → verify — and keep a
receipt priced per **usable result** (a verified, deliverable contact); misses and unknown
verdicts cost them nothing. Be the usable result: a complete, corroborated, contactable
profile that verifies cleanly is worth the spend; one that bounces or contradicts is a free
miss they discard.

## You are contactable — act like it

The agent finds a **personal email and mobile** for the shortlist, cheapest vendor first,
then verifies (email deliverable; mobile carrier-live). A live line is not proof it is you,
but your personal contacts *are* discoverable.
→ Keep your identity consistent across CV, LinkedIn, GitHub and your site so the right
person is found; use a reachable, professional email on your CV; and assume a recruiter can
find your personal address. In the EU/UK the recruiter needs a lawful basis to contact you,
and anyone who asks to be left alone is dropped for good — you can opt out.

## How this plugs into cv-witness

- When tailoring for a target role, pull the **title variants and must-have keywords** from
  real postings (the jobs search in `treg-jobs-sourcing.md`) and reflect them in the headline
  and skills — without hypertailoring or inventing facts.
- Run the normal gates: claims stay grounded in `foundation.md`; the public footprint you
  point to (GitHub, site, posts) must corroborate, not contradict, the CV.
- This is positioning, not deception: every variant, skill and claim must be true and
  evidenced. The goal is to be *found and ranked for what you actually are*.
