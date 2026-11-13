"""Honest validation: split labelled pairs by source reply, so the examples the judge sees in prepare() never share a
source reply (or its translation) with the cases it is scored on. Mirrors the unseen test set, which is split by source.

    python make_split.py dev_pairs.jsonl --n-example-sources 3 --seed 0
    -> split_examples.jsonl (pass to --dev), split_holdout.jsonl (pass to --pairs and score.py)
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pairs")
    ap.add_argument("--n-example-sources", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--prefix", default="split")
    a = ap.parse_args()
    cases = [json.loads(line) for line in open(a.pairs, encoding="utf-8") if line.strip()]
    sources = sorted({c["source_id"] for c in cases})
    random.Random(a.seed).shuffle(sources)
    ex_src = set(sources[: a.n_example_sources])
    ex = [c for c in cases if c["source_id"] in ex_src]
    ho = [c for c in cases if c["source_id"] not in ex_src]
    for name, part in (("examples", ex), ("holdout", ho)):
        with open(f"{a.prefix}_{name}.jsonl", "w", encoding="utf-8") as f:
            for c in part:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        print(f"{a.prefix}_{name}.jsonl: {len(part)} cases, intents {sorted({c['intent'] for c in part})}")
        print("   edit types:", dict(Counter(c["edit_type"] for c in part)))


if __name__ == "__main__":
    main()
