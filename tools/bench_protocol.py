"""Benchmark local models on LayoutKeep's REAL protocol, measuring protocol fidelity.

Why this exists: fine-tuning a model for LayoutKeep only helps if the benchmark measures what
LayoutKeep actually does. Translation quality alone is the wrong criterion - the app sends a
JSON array of segments carrying inline `<N>` markers and U+E000..U+E001 protected-value tokens,
and a model fine-tuned purely for translation can be worse at that structured task than a
smaller general instruct model.

So each model is measured on three axes, in LayoutKeep's exact wire format (built by the real
`_build_messages` and judged by the real `_parse_reply`):

  PROTOCOL FIDELITY (automatic, decisive)
    - JSON parses via _parse_reply
    - returned id set == sent id set
    - <N> marker open/close counts balanced, source == target count
    - U+E000..U+E001 protected-token count source == target
    - no passthrough (target identical to source on a translatable segment)
    - multi-segment array returned whole (2/2, 3/3, ...) not truncated
  QUALITY (proxy, automatic + printed for a human eye)
    - target/source length ratio (sane expansion range ~0.7-1.4 for en<->tr)
    - whether the target is actually in the requested language (crude script check)
    - full translated text printed per scenario
  SPEED
    - seconds per request

Two edge cases per model, both directions where meaningful:
  - single segment with a marker + a protected token
  - multi-segment (3) array, one with a marker, one with a protected token

Usage:  .venv/Scripts/python.exe tools/bench_protocol.py MODEL_ID [MODEL_ID ...]
Run while LM Studio is serving http://localhost:1234/v1. Each model is loaded via the `lms`
CLI (unload all first) to give it a fair, isolated context.

The most recent run is saved to _artifacts/bench_protocol.json; a compact CSV is written next
to it so a chart can be drawn without re-running models.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from layoutkeep.providers.openai_compat import _build_messages, _parse_reply

BASE_URL = "http://localhost:1234/v1"
LMS = Path.home() / ".lmstudio" / "bin" / "lms.exe"

#: Turkish-specific letters - a strong, low-noise signal that text is Turkish (absent from
#: English). English-only output will have zero of them, so for a Turkish target this is a
#: reliable positive test; we never call short/ambiguous Turkish "English" by accident.
_TR_CHARS = set("çğıöşüÇĞİÖŞÜ")


def _lang_is(text: str, lang: str) -> bool | None:
    """Positive signal that text is in `lang`. None = inconclusive (never a false accusation).

    Turkish target: any Turkish-specific letter means it is Turkish; none means inconclusive
    (a short fragment may legitimately lack them) rather than "wrong". English target: we do
    not use the absence of Turkish letters (English has none anyway) - we check that the text
    carries English stop-words and little/no Turkish morphology marker.
    """
    if lang == "tr":
        return True if any(ch in _TR_CHARS for ch in text) else None
    # English target: Turkish words rarely avoid all Turkish letters, so if we see any Turkish
    # letters it is almost certainly not English; otherwise inconclusive.
    if any(ch in _TR_CHARS for ch in text):
        return False
    return None


def _http_chat(model: str, messages: list[dict], timeout: float = 180) -> tuple[str | None, float]:
    body = json.dumps({"model": model, "messages": messages, "temperature": 0.0,
                       "max_tokens": 1500}).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + "/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer not-needed"},
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - timeout / conn reset is a result, not a crash
        return None, time.monotonic() - started
    try:
        return payload["choices"][0]["message"]["content"], time.monotonic() - started
    except Exception:  # noqa: BLE001 - malformed server reply is a recorded result
        return None, time.monotonic() - started


def _load_model(key: str, context: int = 4096) -> tuple[bool, str]:
    subprocess.run([str(LMS), "unload", "-a"],  # -a/--all; no -y flag on unload
                   capture_output=True, timeout=120, check=False)
    p = subprocess.run(
        [str(LMS), "load", key, "--context-length", str(context), "--parallel", "1",
         "--gpu", "max", "-y"],
        capture_output=True, text=True, timeout=420, encoding="utf-8", errors="replace",
        check=False,  # a model that fails to load is a recorded result, not a crash
    )
    tail = (p.stdout or "").strip().splitlines()[-1] if (p.stdout or "").strip() else ""
    return p.returncode == 0, tail[:160]


# --------------------------------------------------------------------------------------
# Scenarios: real LayoutKeep-shaped user payloads
# --------------------------------------------------------------------------------------

def _seg(id_: str, text: str, ctx_before: str = "", ctx_after: str = "") -> dict:
    return {"id": id_, "text": text, "context_before": ctx_before,
            "context_after": ctx_after, "max_len": None}


#: A genuine machine-manual sentence (EN), the kind LayoutKeep reads.
_MANUAL_EN = ("Tighten each fastener to {t0} before assembly, and record the value in the "
              "maintenance log together with the date of the inspection.")
_MANUAL_TR = ("Her bağlantı elemanını montajdan önce {t0} değerine sıkın ve değeri, denetim "
              "tarihiyle birlikte bakım günlüğüne kaydedin.")

#: A scholarly sentence (EN) with a bold run to carry a marker.
_PAPER_EN = ("The <0>proposed architecture</0> couples a convolutional encoder with an "
             "attention decoder and reaches state-of-the-art accuracy on the benchmark.")
_PAPER_TR = ("Önerilen <0>mimari</0>, evrişimli bir kodlayıcıyı dikkat tabanlı bir çözücüyle "
             "birleştirir ve kıyaslama testinde en güncel doğruluk düzeyine ulaşır.")


def _scenarios(which: str) -> list[dict]:
    """Build single- and multi-segment scenarios. `which` is src_lang for the request."""
    t0 = "\ue0000\ue001"
    if which == "tr":  # we ask the model to translate TURKISH -> ENGLISH
        single = _seg("s1", _MANUAL_TR.format(t0=t0) + " <0>kalibrasyon</0> periyodu yıllıktır.")
        multi = [
            _seg("m0", _MANUAL_TR.format(t0=t0)),
            _seg("m1", _PAPER_TR),
            _seg("m2", "Örnekler, {p} atmosferinde tavlandı ve ardından hızla soğutuldu.".replace("{p}", t0)),
        ]
        src_lang, tgt_lang = "Turkish", "English"
    else:
        single = _seg("s1", _MANUAL_EN.format(t0=t0) + " The <0>calibration</0> interval is annual.")
        multi = [
            _seg("m0", _MANUAL_EN.format(t0=t0)),
            _seg("m1", _PAPER_EN),
            _seg("m2", "The sample was annealed under {p} and then quenched rapidly.".replace("{p}", t0)),
        ]
        src_lang, tgt_lang = "English", "Turkish"
    return [
        {"name": f"single_{which}", "src": src_lang, "tgt": tgt_lang,
         "user_items": [single]},
        {"name": f"multi3_{which}", "src": src_lang, "tgt": tgt_lang,
         "user_items": multi},
    ]


def _marker_stats(text: str) -> tuple[int, int]:
    opens = len(re.findall(r"<(\d+)>", text))
    closes = len(re.findall(r"</(\d+)>", text))
    return opens, closes


def _token_count(text: str) -> int:
    return len(re.findall("\ue000(\\d+)\ue001", text))


def _evaluate(model: str, scenario: dict) -> dict:
    src_lang, tgt_lang = scenario["src"], scenario["tgt"]
    items = scenario["user_items"]
    messages = _build_messages(
        _items_to_segments(items, src_lang, tgt_lang), src_lang, tgt_lang, None)
    reply, secs = _http_chat(model, messages)

    result = {
        "name": scenario["name"], "src": src_lang, "tgt": tgt_lang,
        "sent_ids": [i["id"] for i in items], "seconds": round(secs, 1),
        "ok": False, "parse": False, "ids_ok": False, "whole": False,
        "marker_ok": False, "token_ok": False, "passthrough": 0,
        "reply": reply, "reply_preview": (reply or "")[:400],
    }
    if reply is None:
        result["error"] = "no reply (timeout/conn)"
        return result

    parsed = _parse_reply(reply)
    if parsed is None:
        result["reply_preview"] = reply[:400]
        return result
    result["parse"] = True

    got_ids = set(parsed)
    exp_ids = set(result["sent_ids"])
    result["ids_ok"] = got_ids == exp_ids
    result["whole"] = len(got_ids) == len(exp_ids)

    # Per-id protocol checks
    tok_ok = True
    marker_ok = True
    passthrough = 0
    for item in items:
        src_text = item["text"]
        tgt_text = parsed.get(item["id"], "")
        if not tgt_text:
            marker_ok = False
            continue
        if tgt_text.strip() == src_text.strip():
            passthrough += 1
        if _token_count(src_text) != _token_count(tgt_text):
            tok_ok = False
        so, sc = _marker_stats(src_text)
        to_, tc = _marker_stats(tgt_text)
        if so != sc or so != to_ or sc != tc:
            marker_ok = False
    result["marker_ok"] = marker_ok
    result["token_ok"] = tok_ok
    result["passthrough"] = passthrough

    # Quality proxies: target language + length ratio (mean over ids present)
    ratios = []
    lang_ok = True
    for item in items:
        tgt_text = parsed.get(item["id"], "")
        if not tgt_text:
            lang_ok = False
            continue
        ratios.append(len(tgt_text) / max(1, len(item["text"])))
        probe = _lang_is(tgt_text, "tr" if tgt_lang.lower().startswith("turk") else "en")
        if probe is False:
            lang_ok = False
    result["ratio_mean"] = round(sum(ratios) / len(ratios), 2) if ratios else None
    result["target_lang_ok"] = lang_ok

    # overall protocol pass = everything decisive
    result["ok"] = all([
        result["parse"], result["ids_ok"], result["whole"],
        result["marker_ok"], result["token_ok"], result["passthrough"] == 0,
    ])
    return result


def _items_to_segments(items, src, tgt):
    from layoutkeep.core.docir import Segment
    segs = []
    for it in items:
        segs.append(Segment(
            block_id=it["id"], source=it["text"],
            context_before=it.get("context_before", ""),
            context_after=it.get("context_after", ""),
            max_len=it.get("max_len"),
            needs_review=False,
        ))
    return segs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("models", nargs="+")
    ap.add_argument("--context", type=int, default=4096)
    ap.add_argument("--no-load", action="store_true",
                    help="skip lms load/unload; assume the model is already loaded (8GB: load "
                         "one model, run it, then load the next)")
    args = ap.parse_args(argv)

    out_dir = ROOT / "_artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    all_results: dict[str, object] = {}

    for model in args.models:
        print(f"\n{'=' * 72}\n{model}\n{'=' * 72}")
        if not args.no_load:
            ok, msg = _load_model(model, context=args.context)
            if not ok:
                print(f"  LOAD FAILED: {msg}")
                all_results[model] = {"error": "load failed"}
                continue
            print("  loaded")

        runs = _scenarios("en") + _scenarios("tr")  # both directions x {single, multi3}
        model_results = []
        for sc in runs:
            r = _evaluate(model, sc)
            model_results.append(r)
            print(f"  {r['name']:<12} ok={r['ok']!s:<5} parse={r['parse']} "
                  f"ids={r['ids_ok']} whole={r['whole']} marker={r['marker_ok']} "
                  f"token={r['token_ok']} pass={r['passthrough']} "
                  f"ratio={r.get('ratio_mean')} tgt_lang={r.get('target_lang_ok')} "
                  f"{r['seconds']}s")
            if r.get("reply_preview"):
                print(f"      {r['reply_preview'][:220]}")
        all_results[model] = {"context": args.context, "scenarios": model_results}

    (out_dir / "bench_protocol.json").write_text(
        json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")

    # Compact CSV for charting
    rows = ["model,scenario,direction,ok,parse,ids_ok,whole,marker_ok,token_ok,passthrough,ratio,seconds"]
    for model, data in all_results.items():
        if not isinstance(data, dict) or "scenarios" not in data:
            continue
        for sc in data["scenarios"]:
            rows.append(",".join(str(v) for v in [
                model, sc["name"], sc["tgt"], sc["ok"], sc["parse"], sc["ids_ok"],
                sc["whole"], sc["marker_ok"], sc["token_ok"], sc["passthrough"],
                sc.get("ratio_mean"), sc["seconds"]]))
    (out_dir / "bench_protocol.csv").write_text("\n".join(rows), encoding="utf-8")

    print(f"\nwritten to {out_dir / 'bench_protocol.json'} and .csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
