# Our recipe for building an LLM judge

The judge is `final_judge.py`. It takes the criterion text, the policy text and the labelled example pairs as inputs;
nothing about a specific criterion or policy is written into the code. All numbers below come from `score.py` with
`claude-haiku-4.5`.

## Step 1. Diagnose
I scored the baseline's shipped verdicts per edit type and per language, then read the replies it got wrong.

- **Dropped conditions pass unnoticed:** `condition_removal` catch is 0.067 (2 of 30).
- **Removed hedges are missed half the time:** `hedge_removal` catch is 0.500 ("usually" → "always").
- **Good replies get failed:** 14% of the original replies fail, and `sentence_reorder` keep is only 0.733. A failed
  original costs twice, because every case built on it then counts as neither a catch nor a keep.
- **Languages:** French (0.603) and German (0.635) are weakest; English, Spanish and Italian are 0.72–0.74.

Reading the misses showed one more pattern that the totals hide: a fee lowered from 20 EUR to 8 EUR was judged
"less generous" and passed, although a lower fee favours the customer.

- Check before moving on: the three costly failure types are dropped conditions, removed hedges, and good replies
  failed after a harmless change.

## Step 2. Split: rules vs. LLM
We use no code rules for the verdict; `rules()` returns nothing.

- **Why no rule:** whether a different number, a missing condition or a stronger word is a failure depends on the
  criterion. A fixed rule would encode one criterion and break on the next.
- **What we tried:** a code check that looks up every number of the reply in the policy text and hands the result to
  the model as evidence. It was part of a two-call pipeline that scored 0.631, below the baseline, so we dropped it.
- **What code does do:** it picks the examples (Step 3), reads the final verdict line, and enforces the 3-call limit.

- Check: there is no rule, so no rule can fail a harmless edit.

## Step 3. Improve the LLM part
One prompt per reply, with these changes from the baseline:

1. **Reason first, verdict last.** The baseline asks for one word. Ours asks for a short analysis (criterion,
   decisive evidence, assessment) and reads the last `VERDICT:` line.
2. **Interpret the criterion before judging.** The model first states what counts as a failure under this criterion
   and what is irrelevant. It is told not to assume the criterion is about accuracy, completeness or over-promising.
3. **Ask only for decisive evidence, and pass by default.** Fail only when the evidence establishes a violation. An
   omitted detail is not automatically a violation. Paraphrase, reordering, translation and filler must not change
   the verdict.
4. **Spell out what a different quantity means.** Before judging a number that differs from the policy, the model
   writes who pays or waits and whether the customer ends up with more or less. This targets the lowered-fee error.
5. **Contrastive examples chosen by code.** From the `--dev` file: one pair per edit type, English first, shortest,
   each from a different source reply, alternating fail and pass, at most 10.
6. **Temperature 0.** At 0.3, 6.4% of verdicts changed between two runs of the same code and the score moved between
   0.886 and 0.932. At 0, two runs gave identical verdicts.

Up to 3 calls per reply: a second call confirms the first, and a third is used only if they disagree.

- Check: on the full dev set catch rose from 0.592 to 0.902 and keep rose from 0.847 to 0.946.

## Step 4. Verify
Full dev set, 226 cases, two runs with identical verdicts (consistency 1.000).

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

| Edit type | Baseline | Ours |
|---|---|---|
| condition_removal (catch) | 0.067 | 0.800 |
| hedge_removal (catch) | 0.500 | 0.950 |
| wrong_number (catch) | 0.800 | 0.857 |
| wrong_policy_detail (catch) | 1.000 | 1.000 |
| sentence_reorder (keep) | 0.733 | 0.933 |
| translation (keep) | 0.833 | 0.861 |
| polite_opener (keep) | 0.867 | 0.933 |
| filler_padding (keep) | 0.800 | 1.000 |
| padding_removal (keep) | 1.000 | 1.000 |

The full-dev number is flattering, because the prompt's examples come from the same nine source replies that are
scored. So we also split dev by source reply (`make_split.py`): examples from three sources, scoring on the others.

| Held-out set | Baseline | Ours |
|---|---|---|
| Split A: 149 cases, 6 unseen sources | 0.797 | 0.913 |
| Split B: 43 cases, 3 other unseen sources | 0.294 | 0.679 |

These two were measured at temperature 0.3, before the switch to 0. Split B is our honest estimate for new topics:
the judge still fails about a quarter of good replies there.

- Check: the gain holds on source replies we did not tune on, on both splits. We could not test unseen edit types.

## Surprise criterion
New criterion: "does the reply state the policy correctly?" (errors count in both directions). We changed nothing
in the code: only `--criterion` and `--dev` pointed at the new files, as in the task's own command. We also ran it
once with no `--dev` at all, so that the prompt held no example of the new criterion.

| | combined | catch | keep |
|---|---|---|---|
| Baseline | 0.632 | 0.567 | 0.715 |
| Ours, recipe unchanged, with the surprise examples | 0.901 | 0.833 | 0.980 |
| Ours, recipe unchanged, no examples | 0.851 | 0.867 | 0.835 |

The with-examples score is flattering, because the examples in the prompt come from the same 73 cases that are
scored. The no-examples score is the honest one: the judge had seen neither these cases nor this criterion. The
examples mainly help the keep side (`filler_padding` keep 0.500 without, 1.000 with). `condition_removal` is the
weakest type either way (catch 0.600 with, 0.700 without); `wrong_policy_detail` is 1.000 and `wrong_number` 0.900
in both.

## What did not work
- **Checklist-style auditing.** Four designs told the model to list every difference from the policy, or to audit
  the reply against a compiled rubric. All scored well on split A (0.90–0.94) and collapsed on split B (0.12–0.33),
  below the baseline, because they fail honest paraphrases on topics they have not seen. One of them, a
  find-then-verify pipeline, scored 0.631 on the full dev set.
- **Trusting one split.** Every one of those designs would have been chosen on split A alone. A second split with
  different source replies is what exposed them.
- **Voting at temperature 0.3.** It did not stabilise verdicts; 6.4% still changed between runs.
- **Turning examples off.** No measurable difference (0.778 against 0.769 on split A with an earlier prompt).
- **The quantity instruction is only a partial fix.** It caught five more wrong numbers on the held-out splits, but
  on the full dev set `wrong_number` catch is 0.857 and some lowered fees still pass.
