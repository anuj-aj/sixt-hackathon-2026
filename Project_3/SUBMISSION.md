# Submission: Project 3, Judge the Judge — <team name>

## Authors
**Team name:** <team name>

**Project:** Project 3: Judge the Judge — a recipe for building LLM judges you can trust

## Problem and approach
An LLM judge decides whether a customer-service reply meets a criterion, given the company policy. The starting
judge accepts harmless rewording, which is right, but misses small edits that change the meaning: it catches only
7% of dropped conditions. It also fails 14% of good replies. The task is a recipe that fixes both and still works on
a criterion it has never seen.

The main idea is one prompt that makes the model **interpret the criterion first, look only for decisive evidence,
and pass by default**. The judge is `starter_pack/final_judge.py`:

1. **Interpret the criterion** before reading the reply: what counts as a failure, what is irrelevant.
2. **Collect only decisive evidence** from the reply and the matching policy rule. A qualifier anywhere in the reply
   counts, and an omitted detail is not automatically a violation.
3. **Spell out what a different quantity means** (who pays or waits, and whether the customer ends up with more or
   less) before judging it.
4. **Fail only when the evidence establishes a violation.** Paraphrase, reordering, translation and filler must not
   change the verdict.
5. **Contrastive examples chosen by code** from the `--dev` file: one pair per edit type, from different source
   replies.
6. **Temperature 0**, so two runs of the same code give the same verdicts.

Why this and not something more elaborate: I built four stricter designs that make the model list every difference
from the policy or audit against a compiled rubric. Each looked best on one held-out split and collapsed on a second
one, because it failed honest paraphrases on topics it had not seen. The simple pass-by-default prompt is the only
design that held on both.

Assumptions: the criterion, the policy and the examples arrive as inputs and nothing about them is in the code;
the judge sees one reply at a time and keeps no state; at most 3 model calls per reply (it normally uses 2).

The full recipe, step by step, is in [`starter_pack/RECIPE.md`](starter_pack/RECIPE.md).

## Models and why
The model is fixed for this project, so no other model was tried.

| Model | Open-weight or closed | Where it runs | Main metric(s) | Cost and time per item | Chosen? |
| --- | --- | --- | --- | --- | --- |
| `claude-haiku-4.5` | closed | API (OpenAI-compatible endpoint provided by SIXT) | combined 0.923 on dev (criterion 1), 0.901 on the surprise dev set | 2 calls per reply, prompt of about 13,000 characters; about 12–20 minutes for 235 replies with 4 workers; cost not measured | yes, required |

Settings: temperature 0, at most 1600 output tokens, up to 10 examples, up to 3 calls per reply.

## Results
All numbers come from `score.py`. "Combined" is the harmonic mean of macro catch and macro keep.

**Criterion 1 (over-promising), full dev set, 226 cases**

| | combined | catch | keep | kappa |
|---|---|---|---|---|
| Starting judge | 0.697 | 0.592 | 0.847 | 0.531 |
| Ours | 0.923 | 0.902 | 0.946 | 0.877 |

Consistency: two runs gave the same verdict on all 235 replies (1.000).

**Criterion 1, held out by source reply.** The full-dev score is flattering, because the prompt's examples come from
the same source replies that are scored. Splitting by source gives the honest estimate:

| Held-out set | Starting judge | Ours |
|---|---|---|
| Split A: 149 cases, 6 unseen sources | 0.797 | 0.913 |
| Split B: 43 cases, 3 other unseen sources | 0.294 | 0.679 |

**Criterion 2 (surprise: is the policy stated correctly?), 73 cases, code unchanged**

| | combined | catch | keep | kappa |
|---|---|---|---|---|
| Starting judge | 0.632 | 0.567 | 0.715 | 0.393 |
| Ours, with the surprise examples | 0.901 | 0.833 | 0.980 | 0.877 |
| Ours, no examples at all | 0.851 | 0.867 | 0.835 | 0.739 |

**Hidden test cases:** the four result files are in `submission/` (`criterion1_run1.csv`, `criterion1_run2.csv`,
`criterion2_run1.csv`, `criterion2_run2.csv`). They carry no labels, so there is no score to report here.

**What did not work and what the limits are**

- Four checklist-style designs scored 0.90–0.94 on split A and 0.12–0.33 on split B, below the starting judge.
- Voting at temperature 0.3 did not stabilise the judge: 6.4% of verdicts changed between runs, and the score moved
  between 0.886 and 0.932.
- Dropped conditions remain the weakest catch: 0.800 on criterion 1 and 0.600 on criterion 2.
- On new topics (split B) the judge still fails about a quarter of good replies.
- The quantity instruction is a partial fix: some lowered fees still pass (`wrong_number` catch 0.857).
- The two split scores were measured at temperature 0.3, before the switch to 0.
- Unseen edit types could not be tested, since the dev data has none.

## How to run
Python 3.11 or newer (tested on 3.12). Standard library only, nothing to install.

Environment variables (names only), in the shell or in `Project_3/.env`:
`JUDGE_LLM_BASE_URL`, `JUDGE_LLM_API_KEY`, `JUDGE_LLM_MODEL` (set to `claude-haiku-4.5`).

From a fresh clone:

```bash
cd Project_3/starter_pack

# Criterion 1 on the dev set, twice, then score with consistency
python3 run_judge.py --judge final_judge.py --pairs dev_pairs.jsonl --criterion JUDGE1_CRITERION.md \
    --policy policy.md --dev dev_pairs.jsonl --out dev_run1.csv
python3 run_judge.py --judge final_judge.py --pairs dev_pairs.jsonl --criterion JUDGE1_CRITERION.md \
    --policy policy.md --dev dev_pairs.jsonl --out dev_run2.csv
python3 score.py dev_run1.csv dev_pairs.jsonl --baseline baseline_dev_verdicts.csv --repeat dev_run2.csv

# Criterion 2 (surprise), same code, only the inputs change
python3 run_judge.py --judge final_judge.py --pairs surprise/dev_pairs.jsonl --criterion surprise/CRITERION.md \
    --policy policy.md --dev surprise/dev_pairs.jsonl --out surprise_dev.csv
python3 score.py surprise_dev.csv surprise/dev_pairs.jsonl
```

The hidden test sets are run the same way, with `--pairs` pointing at the hidden cases and `--dev` at the matching
dev file (`dev_pairs.jsonl` for criterion 1, `surprise/dev_pairs.jsonl` for criterion 2).

`final_judge.py` imports `baseline_judge.py` for its HTTP helpers, so both must stay in `starter_pack/`.

## Demo
<`submission/demo.mp4` or `submission/slides.pdf`>

## Next steps
- **Dropped conditions.** This is the weakest catch on both criteria. The open problem is catching a removed
  condition without failing honest paraphrases; every stricter check I tried lost more than it gained.
- **Validate on several source splits.** Two splits were enough to expose four designs that one split would have
  chosen. Grouped cross-validation over all nine sources would make each decision firmer.
- **One call per reply.** At temperature 0 the second call repeats the first, so a single call should give the same
  verdicts at half the cost. This needs a check before use.
- **Test the judge against edit types it has never seen,** and against a reversed criterion, to confirm it follows
  the criterion text and not habit.
- **Use at SIXT:** the same file can gate chatbot changes for any written criterion. Supply the criterion, the
  policy and a handful of labelled pairs, then check the judge on source replies it was not shown before trusting it.
