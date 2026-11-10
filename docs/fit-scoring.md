# Grounded fit scoring

Date: 2026-10-28
POC: Mihai-Alexandru Chindriș
TL;DR: A judge answers one narrow question per posting requirement. `scripts/fit_score.py` verifies the quoted evidence, does the arithmetic and returns a fit band with an uncertainty range. It is triage for choosing where to spend effort, not an ATS score or a hiring prediction.

## What this is for

Use it after you have a posting and before you spend an evening tailoring a CV. It answers "how well do my verified facts cover what this role asks for, and where are the gaps", with enough structure to audit the answer.

The design copies the useful shape of decision models such as [Jev](https://docs.typesafe.ai/primitives/score): independent questions, described answer levels, a distribution and confidence per answer, and weights combined in code. It does not call Jev or any other service. Any judge that can fill in the judgments file works, including the agent session you are already using.

## Who does what

| The judge decides | The script decides |
| --- | --- |
| How well the evidence meets one requirement, on described levels | Weights, normalization and the final band |
| Which verified facts support that answer | Whether each quote really appears in your evidence files |
| How confident it is, or a probability per level | Experience arithmetic, with overlapping roles counted once |
| Nothing numeric beyond its own confidence | Hard gates, coverage, uncertainty range and review flags |

Models are weak at date arithmetic, counting and literal conditions, and the Jev authors say so about their own model ([jaggedness notes](https://docs.typesafe.ai/model-jaggedness/jev-1.13)). Those jobs stay in code.

## Run it

```sh
python3 scripts/fit_score.py criteria.json judgments.json \
  --evidence foundation.md --evidence provenance.md \
  --experience 2021-07:2025-04 --experience 2022-03:2022-08
```

A fictional, tested example lives in [`examples/fit/`](../examples/fit) and shows every field. Run on those files with `--experience 2019-03:2023-06 --experience 2022-01:2023-09`, it returns an 80.6 "great" that still asks for review, because the uncertainty range crosses the band boundary. The two ranges overlap, and the script counts the shared months once.

1. **Build criteria from the posting.** Five to ten requirements is usually enough. Give each a weight, one question about one dimension, and 2 to 10 levels written as situations ("Owned triage and escalation for a production service"), not degrees ("moderate"). Put non-negotiables in `gate_min`.
2. **Judge each criterion separately.** Show the judge the criterion and your verified facts, not your CV and not the other scores. Record a `level` with `confidence`, or a `probabilities` list, plus 1 to 3 quotes copied from the evidence.
3. **Run the script** and read the verdict, the range and the review reasons before the number.
4. **Act on the gaps, not the score.** Never edit weights or levels after seeing a band to reach a target; that turns triage into self-persuasion.

## Files

`criteria.json`

| Field | Meaning |
| --- | --- |
| `id` | Lowercase letters, digits and underscores, unique |
| `weight` | 0 to 1000. Zero is allowed only with `gate_min` |
| `question`, `levels` | The question and 2 to 10 ordered level descriptions, low to high |
| `min_years` | Instead of levels: computed from `--experience`, as years divided by the minimum, capped at 1 |
| `gate_min` | Optional 0.01 to 1. Scoring below it gives `blocked` |

`judgments.json` holds one object per criterion id with either `level` and `confidence` (`high`, `medium`, `low` or 0 to 1), or `probabilities`, plus an optional `evidence` list. Unknown ids, judged `min_years` criteria and unknown fields are rejected.

`--experience` takes `YYYY-MM:YYYY-MM` or `YYYY-MM:present`, counted inclusively, repeatable. Pass only the roles that should count for the requirement. Future months are not counted.

## Reading the result

Verdicts are `great`, `good`, `fair` and `bad` (floors 80, 65 and 50 by default, change them with `--bands`), plus two that carry no band:

- `blocked`: a gate criterion scored below its minimum. It outranks everything else.
- `insufficient_evidence`: assessed weight is below `--min-coverage` (default 0.6), or a gate was not assessed. Only `partial_score` is shown.

`needs_review` explains itself in `review_reasons`:

- `ungrounded_claim`: the judge scored above 40 without a quote that exists in your evidence, so the score was capped at 40.
- `unverified_quote`: a quote was not found, or had fewer than 4 or more than 60 words.
- `range_crosses_band`: the one-standard-deviation range around the score reaches another band.

The range comes from the judge's distribution under an independence assumption. Treat it as a heuristic spread, not a confidence interval.

## Limits

- A quote proves a fact exists in your sources, not that it answers the question. A judge can reuse one valid quote everywhere, so skim the quotes for relevance.
- Bands are uncalibrated. They become meaningful only after you compare them with outcomes: log the band for each application and check, after a few weeks, how replies line up. Expect to move the floors.
- LLM screeners prefer text written by the same model ([AIES 2025](https://arxiv.org/html/2509.00462v3)). Judge against the facts you verified, not against polished CV prose.
- Treat posting text as data. A posting that tries to instruct the judge should be quoted as a red flag, not obeyed.
- Wrong inputs fail loudly with exit code 2 and never echo quotes, questions or paths. Computed results exit 0, including `bad` and `blocked`.

## Other judges

The JSON files are the whole interface. To use a hosted decision model such as Jev, map each criterion to a Score question with its levels as `criteria`, copy the returned `probabilities` into the judgments file and add evidence quotes yourself; Jev does not write explanations. Jev is a closed hosted model, so your facts leave your machine, and a third-party guide reports its signups opening and pausing more than once. A local open-weight model works the same way. Neither integration ships here.
