# Candidate-side rules from the late career-ops audit (2026-11-24)

Private reference for `cv-witness`. These are candidate-protection rules, not
claims that we implemented every upstream feature. Where no script exists,
the workflow must apply the rule by hand and say so plainly.

## Hard workflow rules

1. **Never run employer-side or recruiter code.** Read public upstream source
   only to understand candidate risk. Do not execute recruiting agents,
   candidate-screeners, ranking pipelines or portal/CRM code against the user,
   their CV or anyone else's data.
2. **Two-pass job importance.** First extract only explicit posting requirements
   (must-have, nice-to-have, responsibilities, reporting line, success measures)
   into a candidate-owned list. Only in a second pass compare that list with
   the user's approved evidence. Never let an inferred skill appear as a
   posting requirement.
3. **No verdict, no research.** If a job, offer or message lacks a clear
   decision or a specific question, do not invent a next step. Ask the user for
   the missing decision or stop.
4. **User actions only.** All submissions, messages, profile changes, offer
   acceptances and withdrawals are performed by the user. We may prepare text
   but never press send.
5. **Do-not-apply signal.** If a posting triggers a knockout, expired deadline,
   unexplained unpaid work, candidate-paid fee, work-rights contradiction or
   material integrity red flag, report a clear `do not apply` recommendation
   with reasons. Do not silently downgrade it to "maybe".
6. **Opt-in cross-channel dedupe.** Compare a role across sources only with
   candidate consent and using candidate-held data. Never scrape or merge
   private recruiter pipelines to decide whether the user may apply.
7. **Skipped is never dropped.** A skipped or deferred application must stay in
   the user's own visible list with a reason and a review date. No silent
   removal from the record.
8. **Fewer, better applications.** Reject volume metrics as success criteria.
   Track applications by decision quality and evidence, not count alone.
9. **Desired salary only when asked.** Never publish or volunteer a salary
   expectation in a CV, cover letter or message unless the user explicitly
   asks for it or the form requires the field.

## Risk and evidence rules

- **Fees and work rights:** a candidate asked to pay for training, equipment,
  visa processing or placement is a high-risk signal. Verify through official
  sources; do not treat a recruiter's reassurance as proof.
- **Gambit honesty:** a resume is evidence for a human decision, not a way to
  beat an ATS. No score, ranking, guaranteed parse or guaranteed interview.
- **ATS "own words" rule:** the user's own words must remain the source of
  truth. We may tighten structure and vocabulary only where the evidence
  supports it; never copy posting sentences into the CV or letter.
- **Retracted claims:** if a source is corrected or a claim is withdrawn, all
  downstream CVs, letters and stories must be re-checked. A retracted figure
  is treated as unverified until replaced with trusted evidence.
- **No fabricated interview material:** interview questions, interviewer
  names, panel structure, follow-ups and offer terms must come from the user,
  the posting or a cited source. If unknown, say unknown.
- **Red flags from real sessions only:** do not invent candidate anecdotes,
  interview warnings or employer behaviour. Use cited public reports or the
  user's own experience, clearly labelled.
- **Calibration floors:** confidence reflects the weakest untested link, not
  the number of passing checks. Never round up, never claim 100% where human
  decisions, vendor parsers or future upstream drift remain.

## Fit, channel and voice rules

- **Fit weights:** when fit weights are not explicitly specified by the
  posting or user, say `estimate`; an estimate may not drive a `great` band.
  Vocabulary, structure and evidence are not interchangeable.
- **Adjacent title evidence:** a related title counts only when the duties and
  dates defend it. Do not relabel a role to match the posting.
- **Channel yield ≠ discrimination:** a channel with fewer replies is not
  proof of bias or bad fit. Report it as a signal to review, not a verdict.
- **Voice tiers:** separate the user's factual voice, the user's preferred
  style and our advisory suggestions. Suggestions never become facts.
- **Data portability:** the user owns the fields, sources, stories and
  decision log. Keep them in plain files; export on request; no lock-in.

## Scripts added or tightened in the 0.9.4 pass

- `check_posting_liveness.py`: transient HTTP statuses are suspicious, never
  dead; question-form "applications closed?" and completed forms are not
  closure phrases; "job/role has been filled" is.
- `cover_letter_check.py`: flags em/en dashes, curly quotes and stock openers.
- `role_clarity.py`: supervisor must name a department; success measure and
  horizon must share a sentence; quotes capped at 240 chars; empty posting
  keeps the six-point shape without asking fabricated questions.
- `story_provenance.py`: same number + same unit + shared metric tokens are
  required to call a figure existing; story-level provenance markers mask all
  figures in that story block; Unicode tokens are preserved.
- `ats_validate.py`: standard headings accept common EU/global aliases; an
  unrecognized language is reported as such, not silently treated as English.
- `jd_coverage.py`: optional `--fields` adds advisory reverse coverage,
  listing CV skills not named by the supplied JD terms.

Everything in this file is candidate-side. Nothing here authorizes running
employer/recruiter tooling or making a submission on the user's behalf.
