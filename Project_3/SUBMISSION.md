# Submission: Project 3, Judge the Judge — OBSIDIAN

## Authors
**Team name:** OBSIDIAN

**Project:** Project 3: Judge the Judge — a recipe for building LLM judges you can trust

## Problem and approach
The starting judge misses small edits that change a reply's meaning (it catches 7% of dropped conditions) and fails
14% of good replies. The task is a recipe that fixes both and still works on a criterion it has never seen.

The main idea is one prompt that makes the model **interpret the criterion first, look only for decisive evidence,
and pass by default**, with examples picked by code and temperature 0. The judge is `starter_pack/final_judge.py`;
the step-by-step recipe is in [`starter_pack/RECIPE.md`](starter_pack/RECIPE.md).

I chose it because the stricter designs I built (listing every difference from the policy, auditing against a
rubric) looked best on one held-out split and collapsed on a second one.

Assumptions: the criterion, the policy and the examples are inputs and nothing about them is in the code; the judge
sees one reply at a time, keeps no state, and makes at most 3 model calls per reply.

## Models and why
The model is fixed for this project, so no other model was tried.

| Model | Open-weight or closed | Where it runs | Main metric(s) | Cost and time per item | Chosen? |
| --- | --- | --- | --- | --- | --- |
| `claude-haiku-4.5` | closed | API (endpoint provided by SIXT) | combined 0.923 (criterion 1), 0.901 (criterion 2) | 2 calls per reply; 12–20 minutes for 235 replies; cost not measured | yes, required |

Settings: temperature 0, up to 10 examples, up to 3 calls per reply.

## Results
"Combined" is the `score.py` score: the harmonic mean of macro catch and macro keep.

| | Starting judge | Ours |
|---|---|---|
| Criterion 1, full dev set (226 cases) | 0.697 | 0.923 |
| Criterion 1, kappa | 0.531 | 0.877 |
| Criterion 1, consistency over two runs | – | 1.000 |
| Criterion 1, held out by source reply, split A (149 cases) | 0.797 | 0.913 |
| Criterion 1, held out by source reply, split B (43 cases) | 0.294 | 0.679 |
| Criterion 2 (surprise), 73 cases, code unchanged | 0.632 | 0.901 |
| Criterion 2, no examples in the prompt | 0.632 | 0.851 |

The full-dev and criterion 2 scores are flattering, because the prompt's examples come from the same source replies
that are scored. The held-out and no-examples rows are the honest estimates.

Hidden test cases: the result files are in `submission/` (`criterion1_run1.csv`, `criterion1_run2.csv`,
`criterion2_run1.csv`, `criterion2_run2.csv`).

What did not work, and the limits:

- Four stricter designs scored 0.90–0.94 on split A and 0.12–0.33 on split B, below the starting judge.
- Dropped conditions remain the weakest catch: 0.800 on criterion 1, 0.600 on criterion 2.
- On new topics (split B) the judge still fails about a quarter of good replies.
- Unseen edit types could not be tested.

## How to run
Python 3.11 or newer, standard library only. Environment variables (names only), in the shell or in
`Project_3/.env`: `JUDGE_LLM_BASE_URL`, `JUDGE_LLM_API_KEY`, `JUDGE_LLM_MODEL` (set to `claude-haiku-4.5`).

```bash
cd Project_3/starter_pack

# Criterion 1
python3 run_judge.py --judge final_judge.py --pairs dev_pairs.jsonl --criterion JUDGE1_CRITERION.md \
    --policy policy.md --dev dev_pairs.jsonl --out dev_run1.csv
python3 score.py dev_run1.csv dev_pairs.jsonl --baseline baseline_dev_verdicts.csv

# Criterion 2 (surprise): same code, only the inputs change
python3 run_judge.py --judge final_judge.py --pairs surprise/dev_pairs.jsonl --criterion surprise/CRITERION.md \
    --policy policy.md --dev surprise/dev_pairs.jsonl --out surprise_dev.csv
python3 score.py surprise_dev.csv surprise/dev_pairs.jsonl
```

For consistency, run a command twice and add `--repeat <second file>` to `score.py`.

## Demo
<`submission/demo.mp4` or `submission/slides.pdf`>

## Next steps
- **Dropped conditions:** catch a removed condition without failing honest paraphrases.
- **Firmer validation:** grouped cross-validation over all source replies, and tests on unseen edit types.
- **Use at SIXT:** the same file can gate chatbot changes for any written criterion. Supply the criterion, the
  policy and a few labelled pairs, then check the judge on replies it was not shown before trusting it.
