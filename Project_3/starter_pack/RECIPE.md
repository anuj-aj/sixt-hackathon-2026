# Our recipe for building an LLM judge

The judge is `final_judge.py`. Numbers come from `score.py`, with `claude-haiku-4.5`.

## Step 1. Diagnose
I scored the baseline per edit type and per language on the 226 dev cases, then read the replies it got wrong.

- **Dropped conditions pass unnoticed:** `condition_removal` catch 0.067.
- **Removed hedges are missed half the time:** `hedge_removal` catch 0.500 ("usually" → "always").
- **Good replies get failed:** 14% of original replies fail; `sentence_reorder` keep 0.733.
- **Languages:** French (0.603) and German (0.635) are weakest.
- **Example miss:** a fee lowered from 20 EUR to 8 EUR was judged "less generous" and passed.

## Step 2. Split: rules vs. LLM
- **Code does:** pick the examples from the `--dev` file, read the final `VERDICT:` line, and cap the calls at 3 per
  reply.
- **The LLM does:** every pass or fail decision.
- **Why no code rule decides a verdict:** the same difference can be a failure under one criterion and acceptable
  under another. A rule fixed in code would fit one criterion and break on the next.

- Check: there is no rule, so no rule can fail a harmless edit.

## Step 3. Improve the LLM part
The judge constructs a realistic scenario from the edited reply, compares it against the company policy, and
evaluates the consequences.

For example, if early pickup is promised without an availability condition, the judge considers what happens when
no car is available.

Key idea: Identify whether the edit creates an unsupported customer benefit, company obligation, or potential loss,
then determine whether it violates the criterion.

This is scenario-based reasoning, not an actual simulation.

The prompt also changes the baseline in these ways:

1. **Reason first, verdict last.** A short analysis, then a final `VERDICT:` line.
2. **Interpret the criterion first.** The model states what counts as a failure under this criterion and what is
   irrelevant, without assuming what the criterion is about.
3. **Decisive evidence only, pass by default.** Fail only when the evidence establishes a violation. Paraphrase,
   reordering, translation and filler must not change the verdict. This is what stops good replies being failed.
4. **Contrastive examples chosen by code** from the `--dev` file: one pair per edit type, from different source
   replies, at most 10.

Up to 3 calls per reply: a second call confirms the first, a third only if they disagree.

- Check: catch rose from 0.592 to 0.902 and keep rose from 0.847 to 0.946.

## Step 4. Verify
Full dev set, 226 cases. Two runs gave identical verdicts (consistency 1.000).

| | combined | catch | keep |
|---|---|---|---|
| Baseline | 0.697 | 0.592 | 0.847 |
| Ours | 0.923 | 0.902 | 0.946 |

| Language | Baseline | Ours |
|---|---|---|
| de | 0.635 | 0.829 |
| en | 0.737 | 0.869 |
| es | 0.724 | 0.957 |
| fr | 0.603 | 0.934 |
| it | 0.739 | 0.934 |

The full-dev score is flattering, because the prompt's examples come from the same source replies that are scored.
Held out by source reply (`python3 make_split.py dev_pairs.jsonl --n-example-sources 3 --seed 0`; full commands
in `SUBMISSION.md`), ours scores 0.913 on one split (baseline 0.797) and 0.679 on another
(baseline 0.294). Both were measured at temperature 0.3, before the switch to 0.

- Check: the gain holds on source replies I did not tune on. Unseen edit types could not be tested.

## Surprise criterion
Nothing changed in the code. Only `--criterion` and `--dev` pointed at the new files.

| | combined | catch | keep |
|---|---|---|---|
| Baseline | 0.632 | 0.567 | 0.715 |
| Ours, recipe unchanged | 0.901 | 0.833 | 0.980 |

Without any examples in the prompt, the same code scores 0.851.

## What did not work
- **Voting at temperature 0.3.** It did not stabilise verdicts: 6.4% changed between two runs of the same code.
  Temperature 0 fixed it.
- **Dropped conditions are still the weakest catch** (0.800, and 0.600 on the surprise criterion).
