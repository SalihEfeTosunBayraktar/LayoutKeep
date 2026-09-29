"""Sample a document, ask the local model what it is, and write a preamble plus a glossary draft.

WHY THIS EXISTS: no segment knows what its document is about - measured on a 2184-segment book, half
of them carry under 200 characters of neighbouring context - so names and terminology settle in
differently on page 3 and page 300. The idea of sending the whole book to the model cannot work on an
8192-token local window (a 517k-character book is ~130k tokens), so this samples instead: the opening
of every part the reader found, in one request.

The output is deliberately two files, and neither is used automatically. Terms go to a glossary, where
`providers/glossary.py` checks each one actually appears translated in the segments that carry it -
verifiable; subject, genre and style go to a prose preamble - not verifiable, so a person reads it
first. A 4B model's terminology can be wrong, and a wrong term injected into every segment is worse
than no preamble at all.

Usage: python tools/audit/document_preamble.py <run-or-lkproj> [--out DIR] [--per-part N]
       [--base-url URL] [--model NAME]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from layoutkeep.core.docir import load_project
from layoutkeep.providers.openai_compat import OpenAICompatProvider

INSTRUCTIONS = """You are preparing to translate a document. Below are opening excerpts from each part of it.

Answer with ONLY a JSON object, no prose and no markdown fences, with these keys:
  "subject"      - one sentence: what this document is about
  "genre"        - e.g. academic paper, novel, legal form, technical manual
  "style"        - e.g. formal, literary, conversational, bureaucratic
  "audience"     - who it is written for
  "proper_nouns" - names, places and titles that must stay recognisable, as a list of strings
  "terms"        - recurring terms and their translations, as an object of source -> translation

For "terms", include only terms that really recur and whose translation matters. Leave both lists
empty rather than inventing plausible-looking entries: a wrong term will be applied to every page."""


def sample(doc, per_part: int) -> tuple[str, int]:
    """The opening blocks of every part, in order, and how many parts there were."""
    chunks: list[str] = []
    parts = list(doc.pages)
    for page in parts:
        taken = 0
        for block in page.blocks:
            text = (block.source_text or block.text or "").strip()
            if len(text) < 40:
                continue
            chunks.append(text[:600])
            taken += 1
            if taken >= per_part:
                break
    return "\n\n---\n\n".join(chunks), len(parts)


def spread_sample(doc, count: int, seed: int) -> tuple[str, int]:
    """Blocks picked at random across the whole document, with a fixed seed.

    WHY: the opening of each part of a novel sets a scene rather than representing the part, so a
    global picture built only from openings is biased. Random blocks spread the same small sample
    over the whole narrative at the same cost, and the seed is fixed so two runs describe the same
    sample and their preambles can be compared.
    """
    rng = random.Random(seed)
    pool = [
        (block.source_text or block.text or "").strip()
        for page in doc.pages
        for block in page.blocks
    ]
    pool = [t for t in pool if len(t) >= 200]
    picked = rng.sample(pool, min(count, len(pool))) if pool else []
    return "\n\n---\n\n".join(t[:600] for t in picked), len(doc.pages)


def keyword_map(provider: OpenAICompatProvider, doc, batch_chars: int, per_batch: int) -> list[dict]:
    """Ask the model for a few keywords per stretch of text, one request per stretch.

    WHY: a novel's opening, middle and end are about different things, so one global preamble cannot
    describe the whole book. Per page would be right in spirit and ruinous in cost: at the measured
    request time, one request per page on a 400-page book is about 2.8 hours against a 1.7-hour run.
    Stretches of about `batch_chars` characters keep the narrative-local signal and cost ~10 minutes.
    """
    blocks = [
        ((block.source_text or block.text or "").strip(), block.id)
        for page in doc.pages
        for block in page.blocks
    ]
    blocks = [(t, i) for t, i in blocks if len(t) >= 40]
    stretches: list[tuple[str, list[str]]] = []
    current: list[str] = []
    ids: list[str] = []
    size = 0
    for text, block_id in blocks:
        current.append(text)
        ids.append(block_id)
        size += len(text)
        if size >= batch_chars:
            stretches.append(("\n".join(current), ids))
            current, ids, size = [], [], 0
    if current:
        stretches.append(("\n".join(current), ids))

    out: list[dict] = []
    for i, (text, block_ids) in enumerate(stretches):
        ask = (
            f"Here is part {i + 1} of {len(stretches)} of a document.\n\n{text[:batch_chars * 2]}\n\n"
            f"Reply with ONLY a JSON array of at most {per_batch} short keywords or key phrases naming "
            "what THIS part is about: the subjects, the people and the terms a translator must keep in "
            "mind here. No prose, no markdown fences. An empty array is better than invented words."
        )
        try:
            reply = str(provider._chat([
                {"role": "system", "content": "You name what a passage is about. Reply with only a JSON array."},
                {"role": "user", "content": ask},
            ])).strip()
        except Exception as e:  # noqa: BLE001 - keep going, record the gap
            print(f"   [{i + 1}/{len(stretches)}] ÇAĞRI BAŞARISIZ {type(e).__name__}: {e}")
            out.append({"index": i, "block_ids": block_ids, "keywords": []})
            continue
        words: list[str] = []
        try:
            start, end = reply.index("["), reply.rindex("]") + 1
            words = [str(w) for w in json.loads(reply[start:end])][:per_batch]
        except (ValueError, json.JSONDecodeError):
            print(f"   [{i + 1}/{len(stretches)}] JSON değil: {reply[:60]!r}")
        out.append({"index": i, "chars": len(text), "block_ids": block_ids, "keywords": words})
        print(f"   [{i + 1}/{len(stretches)}] {len(words)} anahtar kelime: {', '.join(words[:6])}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="a run directory or an .lkproj file")
    ap.add_argument("--out", default=None, help="where to write (default: beside the project)")
    ap.add_argument("--per-part", type=int, default=2)
    ap.add_argument("--sample", choices=("parts", "random"), default="parts",
                    help="parts: the opening of every part; random: N blocks spread over the document")
    ap.add_argument("--sample-blocks", type=int, default=14, help="blocks to sample in random mode")
    ap.add_argument("--seed", type=int, default=20260921, help="random-mode seed, so runs compare")
    ap.add_argument("--map", action="store_true", help="write a keyword map, one request per stretch")
    ap.add_argument("--batch-chars", type=int, default=8000, help="characters per keyword stretch")
    ap.add_argument("--per-batch", type=int, default=8, help="keywords asked for per stretch")
    ap.add_argument("--base-url", default="http://127.0.0.1:1234/v1")
    ap.add_argument("--model", default="gemma-4-e4b")
    ap.add_argument("--timeout", type=float, default=900.0)
    args = ap.parse_args()

    target = Path(args.target)
    project = target if target.suffix == ".lkproj" else next(target.glob("*.lkproj"), None)
    if project is None or not project.exists():
        print(f"no .lkproj found for {target}")
        return 2

    doc = load_project(project)
    if args.sample == "random":
        excerpts, parts = spread_sample(doc, args.sample_blocks, args.seed)
    else:
        excerpts, parts = sample(doc, args.per_part)
    out_dir = Path(args.out) if args.out else project.parent
    print(f"{project.name}: {parts} bölüm, {len(doc.pages)} sayfa, örneklem {len(excerpts)} karakter")

    provider = OpenAICompatProvider(base_url=args.base_url, model=args.model, timeout=args.timeout)
    if args.map:
        mapping = keyword_map(provider, doc, args.batch_chars, args.per_batch)
        path = out_dir / "keyword_map.json"
        path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        filled = sum(1 for m in mapping if m.get("keywords"))
        total_words = sum(len(m.get("keywords") or []) for m in mapping)
        print(f"harita: {len(mapping)} blok, {filled} blokta anahtar kelime, toplam {total_words} kelime")
        print(f"yazıldı: {path}")
        print("Bu harita henüz hiçbir çeviriye enjekte edilmiyor: önce konu takibini iyileştirip "
              "iyileştirmediği ölçülmeli.")
        return 0

    # Asked through a plain chat call, NOT through translate(): that path carries the translator's
    # system prompt (reply with a JSON array of {id, text}), which hijacks a question about the
    # document - the first version of this tool got an empty reply for exactly that reason.
    messages = [
        {
            "role": "system",
            "content": "You answer questions about documents. Reply with ONLY the JSON object asked for.",
        },
        {"role": "user", "content": f"{INSTRUCTIONS}\n\n---\n\n{excerpts}"},
    ]
    try:
        reply = str(provider._chat(messages)).strip()
    except Exception as e:  # noqa: BLE001 - report, never invent a summary
        print(f"ÇAĞRI BAŞARISIZ {type(e).__name__}: {e}")
        return 1
    print(f"model yanıtı: {len(reply)} karakter")
    if not reply:
        print("model boş yanıt verdi")
        return 1

    text = reply
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    try:
        data = json.loads(text[text.index("{") : text.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError) as e:
        (out_dir / "preamble_raw.txt").write_text(reply, encoding="utf-8")
        print(f"model JSON vermedi ({e}); ham yanıt preamble_raw.txt'e yazıldı")
        return 1

    preamble = (
        f"Subject: {data.get('subject', '')}\n"
        f"Genre: {data.get('genre', '')}\n"
        f"Style: {data.get('style', '')}\n"
        f"Audience: {data.get('audience', '')}"
    )
    nouns = data.get("proper_nouns") or []
    if nouns:
        preamble += "\nProper nouns (keep recognisable, do not translate literally): " + ", ".join(map(str, nouns))
    terms = data.get("terms") or {}

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "preamble.txt").write_text(preamble, encoding="utf-8")
    (out_dir / "glossary_draft.json").write_text(
        json.dumps(terms, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"yazıldı: {out_dir / 'preamble.txt'}  ve  {out_dir / 'glossary_draft.json'}")
    print(f"terim sayısı: {len(terms)} | özel ad: {len(nouns)}")
    print("--- ön bilgi (okuyup onaylayın) ---")
    print(preamble)
    if terms:
        print("--- terim taslağı (ilk 15) ---")
        for k, v in list(terms.items())[:15]:
            print(f"   {k} -> {v}")
    print("\nHiçbiri otomatik kullanılmaz: ön bilgiyi ayarlardaki 'Belge ön bilgisi' alanına, "
           "terimleri gözden geçirdikten sonra 'Terim sözlüğü dosyası' alanına verin.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
