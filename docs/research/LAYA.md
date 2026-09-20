# Laya — a non-autoregressive decision engine, and where it could fit here

*Research note, 2026-09-20. Asked by the project owner: what is
[`NandhaKishorM/laya`](https://github.com/NandhaKishorM/laya), and can it be integrated into our
local projects — LayoutKeep or generally?*

> **The fuller version of this note, with every number and its source, is the web report
> [`system-one-models.html`](system-one-models.html)** — measured accuracy, latency and cost for
> Laya, Jev and the open alternatives, plus the plan. This file is the short repo-native summary.

## What it is

Laya is a **multilingual, non-autoregressive "System 1" decision engine**: it does not generate
text at all. You hand it a *state* (an email, a ticket, a JSON document — any text) and a set of
**typed questions**, and it answers them in **a single forward pass**:

| question type | what it returns |
|---|---|
| `choice` | one of the options you listed (with a probability) |
| `score` | a position on an ordered rubric |
| `noul` | a calibrated yes/no probability |

No decoding means no broken JSON and nothing to parse, and because there is no free generation
there is nothing to hallucinate. Measured on a T4: **33 ms for one question, 7.2 ms per question
batched**. Three checkpoints ship with it — `laya` (ModernBERT-large, 421M, English),
`laya-multilingual` (mmBERT-base, 322M, 100+ languages, twice as fast) and `laya-typed-decisions` —
plus a `Router` that detects the script and language of the incoming state in sub-milliseconds and
picks the checkpoint for it. Installed with `pip install laya`; Apache-2.0.

The technique is not new hype dressed up: the author's earlier paper (arXiv:2503.23303, March 2025)
used reinforcement learning over conversion trajectories, and this model is trained with RLCD —
reinforcement learning against **strictly proper scoring rules**, which is what makes a probability
out of a classifier meaningful rather than decorative. The project itself is days old and the
surrounding discussion is loud in both directions; the *method* is the credible part.

Not to be confused with the other thing called Laya (a local-first "AI command center" that
intercepts notifications and drafts Action Cards — a Tauri/Svelte + FastAPI + n8n desktop app).
That is a different product by the same corner of the internet; the repository linked above is the
decision engine.

## Where it could fit

**It cannot replace the translator.** LayoutKeep's core is a generative task — text in, text out,
in the page's own boxes — and Laya never generates text. Any integration is therefore *around* the
pipeline, not inside it.

The honest fit is the part of the pipeline that is already a **typed decision**, and there are
three:

1. **Language and script detection (the strongest candidate).** Every run begins by deciding what
   language the document is in, and today that decision is heuristic. A 322M multilingual encoder
   answering "which language is this page?" in tens of milliseconds, locally, with a probability
   attached, is exactly the shape of the problem — and it is the one place where a wrong answer
   silently corrupts everything downstream.
2. **Document-type routing.** The pipeline already knows that a scanned form, a legal text and a
   journal article want different treatment (see the note on translation-quality factors). "Which
   of these profiles is this document?" is a `choice` question over the first page or two.
3. **Review-flag triage.** After a run, some blocks are flagged for human review. "Is this flag a
   real problem?" is a `noul` question over the block, its flags and its neighbours — and a local,
   33 ms, hallucination-free answer is worth more here than a generative one, because the output is
   a decision the UI can act on directly.

**What it costs.** A 421M encoder is small but not free: on this machine it would have to run
alongside the translation model, and the standing rule here is one model in the LM Studio server at
a time. On CPU a forward pass is seconds rather than milliseconds; on the GPU it competes for the
same 8 GB. It also needs *our* labelled examples to be trusted in any of the three roles above —
zero-shot quality on LayoutKeep's domain is unverified, and that is the experiment, not an
assumption.

**General answer.** For any local project of ours whose LLM call is really "pick one of these
options" — triage, routing, gating, form understanding, "does this message contain X" — a
non-autoregressive typed-decision model is a better tool than a chat model: faster, cheaper,
deterministic in shape, and impossible to hallucinate into a wrong format. For anything that has to
*write*, it is not a candidate.

## Verdict

Worth a **spike**, not a dependency. The cheapest useful experiment is (1): swap the heuristic
language detection for a `laya-multilingual` forward pass on a handful of held-out documents and
compare the answers against the languages we know are right. If that lands, the document-type
router is the natural second step. Until then it stays a research note — the pipeline does not gain
a new model on the strength of a repository that is two days old.

## Sources

- `github.com/NandhaKishorM/laya` — README, checkpoints, quickstart (Apache-2.0, 3k stars).
- `dev.to/nandakishor_m_6cc0adfde9f/i-built-non-autoregressive-decision-models-...` — the author on
  the architecture and the RLCD training.
- arXiv:2503.23303 — the earlier paper the model descends from.
- Hacker News discussion (items 49766884, 49753019) — the skeptical reading: claims of prior art,
  closed-source comparisons, and "vibecoded" counter-claims. Both sides are worth reading before
  betting anything on it.
