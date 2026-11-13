
"""Criterion-agnostic LLM judge.

Recipe:
1. Select contrastive examples from labelled development data.
2. Interpret the supplied criterion dynamically.
3. Match relevant reply claims to policy evidence.
4. Evaluate only differences relevant to the criterion.
5. Use adaptive majority voting (maximum 3 LLM calls).

No criterion-specific rules or policy values are hardcoded.
"""

from __future__ import annotations

import os
import random
import re
import sys
import threading
import time
import urllib.error

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import baseline_judge as bj


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

def _load_env() -> None:
    """Load missing settings from .env; environment variables win."""
    paths = (
        os.path.join(_HERE, "..", ".env"),
        os.path.join(_HERE, ".env"),
    )

    for path in paths:
        if not os.path.exists(path):
            continue

        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                value = value.strip().strip('"').strip("'")

                if value:
                    os.environ.setdefault(key.strip(), value)


_load_env()

VOTES = max(1, min(3, int(os.environ.get("JUDGE_VOTES", "3"))))
TEMPERATURE = float(os.environ.get("JUDGE_TEMPERATURE", "0"))
MAX_TOKENS = int(os.environ.get("JUDGE_MAX_TOKENS", "1600"))
MAX_EXAMPLES = max(0, int(os.environ.get("JUDGE_MAX_EXAMPLES", "10")))
DEBUG = os.environ.get("JUDGE_DEBUG", "0") == "1"

EXAMPLES_TEXT = ""
unparsed = 0
split_votes = 0

_lock = threading.Lock()


# ---------------------------------------------------------
# Development example selection
# ---------------------------------------------------------

def _label(case: dict) -> str:
    return str(case.get("edited_label", "")).strip().lower()


def _format_examples(cases: list[dict]) -> str:
    if not cases:
        return ""

    parts = [
        "# Labelled examples",
        (
            "These examples illustrate how the supplied criterion "
            "applies to different replies. Infer the relevant "
            "distinctions; do not memorize their specific facts."
        ),
    ]

    for i, case in enumerate(cases, 1):
        note = case.get("edit_note", "")

        section = [
            f"## Example {i}",
            (
                "Customer question: "
                f"{case.get('question_original') or case.get('question', '')}"
            ),
            f"Reply A: {case['original']}",
            (
                "Verdict for A: "
                f"{str(case.get('original_label', 'pass')).upper()}"
            ),
            f"Reply B: {case['edited']}",
        ]

        if note:
            section.append(f"Description of change: {note}")

        section.append(f"Verdict for B: {_label(case).upper()}")
        parts.append("\n".join(section))

    return "\n\n".join(parts)


def prepare(
    criterion: str,
    policy: str,
    dev_pairs: list[dict],
) -> None:
    """Select diverse, contrastive labelled examples.

    Uses metadata supplied with the development cases.
    Does not contain criterion-specific logic.
    """
    global EXAMPLES_TEXT

    groups: dict[str, list[dict]] = {}

    for case in dev_pairs:
        if not case.get("original") or not case.get("edited"):
            continue

        if _label(case) not in ("pass", "fail"):
            continue

        group_key = str(
            case.get("edit_type")
            or case.get("edited_label")
        )

        groups.setdefault(group_key, []).append(case)

    def rank(case: dict) -> tuple:
        same_language = (
            case.get("lang") == case.get("orig_lang")
        )

        return (
            case.get("lang") != "en",
            not same_language,
            len(case["original"]) + len(case["edited"]),
            str(case.get("case_id", "")),
        )

    selected = []
    used_sources = set()

    for _, cases in sorted(groups.items()):
        cases = sorted(cases, key=rank)

        fresh = [
            case for case in cases
            if case.get("source_id") not in used_sources
        ]

        choice = (fresh or cases)[0]

        selected.append(choice)
        used_sources.add(choice.get("source_id"))

    fails = [c for c in selected if _label(c) == "fail"]
    passes = [c for c in selected if _label(c) == "pass"]

    chosen = []

    while (fails or passes) and len(chosen) < MAX_EXAMPLES:
        for bucket in (fails, passes):
            if bucket and len(chosen) < MAX_EXAMPLES:
                chosen.append(bucket.pop(0))

    EXAMPLES_TEXT = _format_examples(chosen)


# ---------------------------------------------------------
# Optional deterministic rules
# ---------------------------------------------------------

def rules(
    question: str,
    reply: str,
    lang: str,
    policy: str,
) -> str | None:
    """No fixed rules: all criteria are evaluated dynamically."""
    return None


# ---------------------------------------------------------
# Criterion-agnostic evaluation prompt
# ---------------------------------------------------------

PROMPT = """You are a precise, evidence-grounded evaluator.

Your task is to decide whether ONE customer-service reply
PASSES or FAILS the supplied evaluation criterion.

The criterion determines what matters.
The company policy provides the authoritative factual context.
Do not introduce additional evaluation requirements.

# EVALUATION CRITERION

{criterion}

# COMPANY POLICY

{policy}

{examples}

# CUSTOMER QUESTION

Language: {lang}
{question}

# REPLY TO EVALUATE

{reply}

# EVALUATION PROCEDURE

STEP 1 — INTERPRET THE CRITERION

Determine from the criterion itself:

- What exactly constitutes a failure?
- What evidence is necessary to establish a failure?
- Which differences, omissions or behaviors are irrelevant?
- Does the criterion require a directional comparison,
  an exact constraint, a semantic property, or something else?

Do not assume that every criterion concerns factual accuracy,
customer benefit, completeness, or over-promising.

STEP 2 — IDENTIFY RELEVANT EVIDENCE

Read the customer question and the entire reply.

Identify only statements, implications, omissions or behaviors
that could affect the active criterion.

When policy evidence is needed, identify the applicable
policy passage using the customer's question and context.

A condition or qualifier may appear anywhere in the reply.
Do not treat it as absent merely because it appears in
another sentence.

Do not compare unrelated policy rules.

STEP 3 — VERIFY

For each potentially decisive issue:

- State what the reply communicates.
- Identify supporting or conflicting evidence from the
  policy, criterion, or question, as applicable.
- Determine whether there is a meaningful difference.
- Determine whether that difference violates the criterion.

Consider quantities, conditions, scope, certainty,
implications, omissions, and other properties ONLY when
they are relevant to the criterion.

Do not assume that larger or smaller numbers are inherently
better or worse. For every quantity in the reply that differs
from the policy, write out its practical effect BEFORE judging it:
who pays, receives, waits for or has to do the thing measured,
and whether under the reply the customer ends up with more or
less (money, time, rights, obligations) than under the policy.
An amount charged to the customer that is smaller, or a time
allowed to the customer that is longer, is MORE favourable to
the customer than the policy, not less.

An omitted policy detail is not automatically a violation.
Determine whether the detail is relevant, whether the
reply implies it elsewhere, and whether the criterion
requires it.

Do not fail a reply for an unrelated defect.

Do not invent policy requirements or infer unsupported facts.

STEP 4 — DECIDE

Return FAIL only when the evidence establishes a violation
of the supplied criterion.

Otherwise return PASS.

Harmless paraphrasing, sentence reordering, translation,
formatting, and conversational filler must not change the
verdict unless the criterion explicitly makes them relevant.

Apply the criterion consistently. Do not become stricter
or more lenient than its actual requirements.

# RESPONSE FORMAT

Give a concise analysis using:

CRITERION: What is being evaluated.
EVIDENCE: The decisive evidence, if any.
ASSESSMENT: Why that evidence does or does not violate
the criterion.

End with exactly one final line:

VERDICT: PASS

or

VERDICT: FAIL
"""


def build_prompt(
    question: str,
    reply: str,
    lang: str,
    criterion: str,
    policy: str,
) -> str:
    return PROMPT.format(
        criterion=criterion.strip(),
        policy=policy.strip(),
        examples=EXAMPLES_TEXT,
        lang=lang,
        question=question,
        reply=reply,
    )


# ---------------------------------------------------------
# Verdict parsing
# ---------------------------------------------------------

_VERDICT = re.compile(
    r"^\s*\**VERDICT\**\s*:\s*\**(PASS|FAIL)\**\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def parse_verdict(answer: str) -> str | None:
    matches = _VERDICT.findall(answer or "")
    return matches[-1].lower() if matches else None


# ---------------------------------------------------------
# LLM API call
# ---------------------------------------------------------

def _call(prompt: str) -> str:
    base, key, model, timeout, _ = bj._config()

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
    }

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    max_retries = max(
        bj.MAX_RETRIES,
        int(os.environ.get("JUDGE_MAX_RETRIES", "15")),
    )

    for attempt in range(max_retries + 1):
        try:
            response = bj._post(
                f"{base}/chat/completions",
                payload,
                headers,
                timeout,
            )

            return (
                response["choices"][0]["message"]["content"]
                or ""
            )

        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise bj.LLMError(
                    f"LLM authentication failed: HTTP {exc.code}"
                ) from exc

            if (
                exc.code not in bj._RETRY_STATUS
                or attempt == max_retries
            ):
                raise bj.LLMError(
                    f"LLM request failed: HTTP {exc.code}"
                ) from exc

            retry_after = (
                exc.headers.get("Retry-After")
                if exc.headers
                else None
            )

            delay = bj._wait(attempt, retry_after)
            time.sleep(delay + random.random() * 5)

        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == max_retries:
                raise bj.LLMError(
                    f"LLM request failed: {exc}"
                ) from exc

            time.sleep(bj._wait(attempt, None))

    raise bj.LLMError("LLM retry loop exhausted")


# ---------------------------------------------------------
# Main judge
# ---------------------------------------------------------

def judge(
    question: str,
    reply: str,
    lang: str,
    criterion: str,
    policy: str,
) -> str:
    global unparsed, split_votes

    deterministic = rules(
        question,
        reply,
        lang,
        policy,
    )

    if deterministic is not None:
        return deterministic

    prompt = build_prompt(
        question,
        reply,
        lang,
        criterion,
        policy,
    )

    votes: list[str] = []

    for attempt in range(VOTES):
        answer = _call(prompt)
        verdict = parse_verdict(answer)

        if DEBUG:
            with _lock:
                print(
                    f"\n--- Judge call {attempt + 1} ---\n"
                    f"{answer}\n"
                    f"Parsed verdict: {verdict}\n",
                    file=sys.stderr,
                    flush=True,
                )

        if verdict is None:
            with _lock:
                unparsed += 1
            continue

        votes.append(verdict)

        # Two matching votes already establish a majority.
        if len(votes) == 2 and votes[0] == votes[1]:
            break

    if not votes:
        return "fail"

    if len(set(votes)) > 1:
        with _lock:
            split_votes += 1

    # Conservative fallback for a tied vote.
    return (
        "pass"
        if votes.count("pass") > votes.count("fail")
        else "fail"
    )