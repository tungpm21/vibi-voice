#!/usr/bin/env python3
"""Vibi voice CLI: text-to-speech through api.vibi.pro (ElevenLabs, MiniMax, CapCut).

Standard library only, Python 3.8+. Every command prints one JSON object.

Key lookup order: env VIBI_API_KEY, then a .env file in the current folder or a
parent, then ~/.config/vibi/.env (written by `set-key`).

  python vibi.py set-key                      # user runs this once; key is typed hidden
  python vibi.py credits
  python vibi.py voices --provider capcut --filter language=vi
  python vibi.py voices --provider elevenlabs --library shared --filter required_languages=vi
  python vibi.py speak --text "Xin chào" --out vo.mp3 --voice 8vYGUA5K6wBkIRqn7SLv --srt
  python vibi.py resume TASK_ID --out vo.mp3
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_BASE = "https://api.vibi.pro"
API_HOST = "api.vibi.pro"
USER_ENV = Path.home() / ".config" / "vibi" / ".env"

PROVIDERS = ("elevenlabs", "minimax", "capcut")
DEFAULT_MODELS = {
    "elevenlabs": "eleven_v4_turbo",
    "minimax": "speech-2.8-turbo",
    "capcut": "capcut",
}
DEFAULT_VOICES = {"elevenlabs": "21m00Tcm4TlvDq8ikWAM"}  # Rachel (premade)
VOICE_PATHS = {
    ("elevenlabs", "system"): "/v1/default-voices",
    ("elevenlabs", "shared"): "/v1/shared-voices",
    ("minimax", "system"): "/v1/minimax/system-voices",
    ("minimax", "cloned"): "/v1/minimax/voices",
    ("capcut", "system"): "/v1/capcut/system-voices",
}
SETTINGS = {
    "elevenlabs": ("stability", "similarity_boost", "style", "use_speaker_boost", "speed"),
    "minimax": ("speed", "pitch", "vol"),
    "capcut": ("speed", "pitch"),
}
SPEED_RANGE = {"elevenlabs": (0.7, 1.2), "minimax": (0.5, 2.0), "capcut": (0.5, 2.0)}
# Measured 2026-11-06: eleven_v4_turbo charged 44 credits for 87 characters,
# capcut 1 credit for 46 characters. Other models assume 1 credit per character.
CREDITS_PER_CHAR = {"eleven_v4_turbo": 0.5, "capcut": 0.025}


class VibiError(Exception):
    pass


# ---- key handling -------------------------------------------------------


def _read_env_file(path: Path) -> str | None:
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key.strip() == "VIBI_API_KEY":
                value = value.strip().strip("'\"")
                if value:
                    return value
    except OSError:
        pass
    return None


def find_key() -> str:
    if os.environ.get("VIBI_API_KEY"):
        return os.environ["VIBI_API_KEY"]
    here = Path.cwd().resolve()
    for folder in (here, *here.parents):
        value = _read_env_file(folder / ".env")
        if value:
            return value
    value = _read_env_file(USER_ENV)
    if value:
        return value
    raise VibiError(
        "No VIBI_API_KEY. Ask the user to run: python vibi.py set-key "
        "(or add VIBI_API_KEY=... to a .env file). Never ask them to paste the key in chat."
    )


def cmd_set_key(_args) -> dict:
    key = getpass.getpass("Vibi API key (hidden): ").strip()
    if not key:
        raise VibiError("Empty key, nothing saved")
    USER_ENV.parent.mkdir(parents=True, exist_ok=True)
    USER_ENV.write_text(f"VIBI_API_KEY={key}\n", encoding="utf-8")
    try:
        os.chmod(USER_ENV, 0o600)
    except OSError:
        pass
    os.environ["VIBI_API_KEY"] = key
    balance = request("GET", "/v1/auth/me").get("credit_balance")
    return {"saved_to": str(USER_ENV), "credit_balance": balance}


# ---- http ---------------------------------------------------------------


def request(method: str, path: str, *, params=None, body=None, timeout=30):
    key = find_key()
    url = API_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "xi-api-key": key,
            "Content-Type": "application/json",
            "User-Agent": "vibi-voice-skill/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise VibiError(f"HTTP {exc.code} on {path}: {detail}".replace(key, "[REDACTED]"))
    except urllib.error.URLError as exc:
        raise VibiError(f"Cannot reach {API_HOST}: {exc.reason}")
    return json.loads(raw.decode("utf-8")) if raw else {}


def download(url: str, out: Path) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise VibiError(f"Refusing non-https URL: {url}")
    headers = {"User-Agent": "vibi-voice-skill/1.0"}
    if parsed.netloc == API_HOST:  # never send the key to a CDN
        headers["xi-api-key"] = find_key()
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        content = resp.read()
    if not content:
        raise VibiError(f"Empty file from {url}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(content)


# ---- commands -----------------------------------------------------------


def cmd_credits(_args) -> dict:
    return {"credit_balance": request("GET", "/v1/auth/me").get("credit_balance")}


def cmd_models(args) -> dict:
    params = {} if args.provider == "elevenlabs" else {"provider": args.provider}
    models = request("GET", "/v1/models", params=params)
    return {"provider": args.provider, "models": [m.get("model_id") for m in models]}


def cmd_languages(args) -> dict:
    params = {} if args.provider == "elevenlabs" else {"provider": args.provider}
    return {"provider": args.provider, "languages": request("GET", "/v1/languages", params=params)}


def cmd_voices(args) -> dict:
    path = VOICE_PATHS.get((args.provider, args.library))
    if not path:
        raise VibiError(f"No '{args.library}' voice library for {args.provider}")
    params = {"page_size": args.page_size}
    if args.page is not None:
        params["page"] = args.page
    if args.search:
        params["search"] = args.search
    for item in args.filter or []:
        key, sep, value = item.partition("=")
        if not sep:
            raise VibiError(f"--filter needs key=value, got {item!r}")
        params[key] = value
    data = request("GET", path, params=params)
    voices = data.get("voices") or data.get("voice_list") or []
    slim = []
    for v in voices:
        slim.append(
            {
                "voice_id": v.get("voice_id"),
                "uniq_id": v.get("uniq_id"),
                "name": v.get("name") or v.get("voice_name"),
                "gender": v.get("gender"),
                "language": v.get("language"),
                "tags": v.get("tags") or v.get("tag_list"),
                "preview": v.get("preview_url") or v.get("sample_audio"),
                "description": (v.get("description") or "")[:160] or None,
            }
        )
    return {
        "provider": args.provider,
        "library": args.library,
        "has_more": data.get("has_more"),
        "total": data.get("total"),
        "voices": [{k: v for k, v in s.items() if v not in (None, "", [])} for s in slim],
    }


def _estimate_credits(text: str, model: str, srt: bool) -> float:
    credits = len(text) * CREDITS_PER_CHAR.get(model, 1.0)
    return round(credits * (1.15 if srt else 1.0), 1)


def _wait_and_save(task_id: str, out: Path, want_srt: bool, max_wait: int) -> dict:
    deadline = time.monotonic() + max_wait
    while True:
        task = request("GET", f"/v1/history/{task_id}", timeout=20)
        status = task.get("status")
        if status == "completed":
            break
        if status == "failed":
            detail = task.get("detail_error")
            raise VibiError(f"Task {task_id} failed: {task.get('error')}" + (f" ({detail})" if detail else ""))
        if time.monotonic() >= deadline:
            raise VibiError(f"Task {task_id} still {status}; run: vibi.py resume {task_id} --out {out}")
        time.sleep(2)
    result = task.get("result") or {}
    audio_url = result.get("audio_url")
    if not audio_url:
        raise VibiError(f"Task {task_id} completed without audio_url")
    download(audio_url, out)
    report = {
        "task_id": task_id,
        "output": str(out),
        "bytes": out.stat().st_size,
        "model": task.get("model_id"),
        "voice_id": task.get("voice_id"),
        "provider": task.get("provider"),
        "characters_used": task.get("characters_used"),
        "credits_deducted": task.get("credits_deducted"),
    }
    srt_url = result.get("srt_url")
    if srt_url:
        srt_path = out.with_suffix(".srt")
        download(srt_url, srt_path)
        report["srt"] = str(srt_path)
    elif want_srt:
        report["srt_note"] = "Task finished without an srt_url"
    return report


def cmd_speak(args) -> dict:
    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8").strip()
    else:
        text = (args.text or "").strip()
    if not text:
        raise VibiError("Give --text or --text-file")
    provider = args.provider
    voice = args.voice or DEFAULT_VOICES.get(provider)
    if not voice:
        raise VibiError(f"--voice is required for {provider}; find one with: vibi.py voices --provider {provider}")
    model = args.model or DEFAULT_MODELS[provider]

    settings = {}
    for field in SETTINGS[provider]:
        value = getattr(args, field, None)
        if value is not None:
            settings[field] = value
    if "speed" in settings:
        low, high = SPEED_RANGE[provider]
        if not low <= settings["speed"] <= high:
            raise VibiError(f"--speed for {provider} must be {low}-{high}")

    body = {"text": text, "model_id": model, "provider": provider, "language_code": args.lang}
    if settings:
        body["voice_settings"] = settings
    if args.srt:
        body["export_transcript"] = True

    estimate = _estimate_credits(text, model, args.srt)
    if args.dry_run:
        return {"dry_run": True, "request": body, "voice_id": voice, "estimated_credits": estimate}

    submitted = request("POST", f"/v1/text-to-speech/{urllib.parse.quote(voice, safe='')}", body=body)
    task_id = submitted.get("id")
    if not task_id:
        raise VibiError(f"No task id in response: {submitted}")
    report = _wait_and_save(task_id, Path(args.out), args.srt, args.max_wait)
    report["estimated_credits"] = estimate
    if args.word_srt:
        try:
            report["word_srt"] = word_timings(
                Path(args.out), text, args.lang, args.words_per_cue, args.max_wait
            )
        except VibiError as exc:  # audio is already paid for and saved; keep it
            report["word_srt_error"] = f"{exc} (retry with: vibi.py words {args.out} --text-file ...)"
    return report


def cmd_resume(args) -> dict:
    report = _wait_and_save(args.task_id, Path(args.out), args.srt, args.max_wait)
    if args.word_srt:
        script = Path(args.text_file).read_text(encoding="utf-8") if args.text_file else args.text
        report["word_srt"] = word_timings(
            Path(args.out), script, args.lang, args.words_per_cue, args.max_wait
        )
    return report


# ---- word-level timings (speech-to-text + script alignment) -------------

_ISO = {"vietnamese": "vi", "english": "en", "chinese": "zh", "japanese": "ja",
        "korean": "ko", "thai": "th", "indonesian": "id", "spanish": "es",
        "portuguese": "pt", "french": "fr", "german": "de"}


def _iso_lang(lang: str) -> str:
    return _ISO.get((lang or "").strip().lower(), lang)


def _post_multipart(path: str, fields: dict, file_path: Path, timeout=120) -> dict:
    key = find_key()
    boundary = "----vibi" + os.urandom(12).hex()
    parts = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    parts.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{file_path.name}"\r\nContent-Type: application/octet-stream\r\n\r\n'
        ).encode()
        + file_path.read_bytes()
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        API_BASE + path,
        data=b"".join(parts),
        method="POST",
        headers={
            "xi-api-key": key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "vibi-voice-skill/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise VibiError(f"HTTP {exc.code} on {path}: {detail}".replace(key, "[REDACTED]"))


def transcribe_words(audio: Path, lang: str, max_wait: int = 300) -> dict:
    """Run Vibi speech-to-text (Scribe v2) and return the finished task."""
    submitted = _post_multipart(
        "/v1/speech-to-text",
        {"language_code": _iso_lang(lang), "timestamps_granularity": "word",
         "tag_audio_events": "false"},
        audio,
    )
    task_id = submitted.get("task_id") or submitted.get("id")
    if not task_id:
        raise VibiError(f"No task id from speech-to-text: {submitted}")
    deadline = time.monotonic() + max_wait
    while True:
        task = request("GET", f"/v1/speech-to-text/{task_id}", timeout=20)
        if task.get("status") == "completed":
            return task
        if task.get("status") == "failed":
            raise VibiError(f"Speech-to-text failed: {task.get('detail_error')}")
        if time.monotonic() >= deadline:
            raise VibiError(f"Speech-to-text task {task_id} still running")
        time.sleep(2)


def _norm(token: str) -> str:
    import unicodedata

    token = unicodedata.normalize("NFC", token).lower()
    return "".join(ch for ch in token if ch.isalnum())


def _collapsed(heard: list) -> set:
    """Indexes of heard words stacked on one start time.

    Scribe sometimes squeezes the last words of a clip onto a single timestamp
    (seen 2026-11-06: three words all at 1.98-2.03 s in a 2.95 s clip). Their
    timings are useless, so they get re-spread like unmatched words.
    """
    bad = set()
    for i in range(1, len(heard)):
        if abs(float(heard[i]["start"]) - float(heard[i - 1]["start"])) < 0.01:
            bad.update((i - 1, i))
    return bad


def align_script(script_words: list, heard: list, total_end: float | None = None) -> list:
    """Put the script's own words on the heard timings.

    heard: [{"text", "start", "end"}] from speech-to-text. Words that match keep
    the heard timing; script words with no usable match share the time span
    between their timed neighbours (or the audio end), split by character length.
    """
    import difflib

    a = [_norm(w) for w in script_words]
    b = [_norm(h["text"]) for h in heard]
    bad = _collapsed(heard)
    timed = [None] * len(script_words)
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            if block.b + k in bad:
                continue
            h = heard[block.b + k]
            timed[block.a + k] = (float(h["start"]), float(h["end"]), "matched")

    last_heard = float(heard[-1]["end"]) if heard else 0.0
    if total_end is None or total_end < last_heard:
        total_end = last_heard
    i = 0
    while i < len(timed):
        if timed[i] is not None:
            i += 1
            continue
        j = i
        while j < len(timed) and timed[j] is None:
            j += 1
        left = timed[i - 1][1] if i > 0 else (float(heard[0]["start"]) if heard else 0.0)
        right = timed[j][0] if j < len(timed) else total_end
        if right < left:
            right = left
        weights = [max(len(script_words[k]), 1) for k in range(i, j)]
        span, cursor = right - left, left
        for k, weight in zip(range(i, j), weights):
            step = span * weight / sum(weights)
            timed[k] = (cursor, cursor + step, "interpolated")
            cursor += step
        i = j
    return [
        {"text": w, "start": round(s, 3), "end": round(max(e, s + 0.05), 3), "source": src}
        for w, (s, e, src) in zip(script_words, timed)
    ]


def _srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def words_to_srt(words: list, per_cue: int = 1) -> str:
    cues, current = [], []
    for word in words:
        current.append(word)
        ends_phrase = word["text"][-1:] in ".,!?;:…"
        if len(current) >= per_cue or ends_phrase:
            cues.append(current)
            current = []
    if current:
        cues.append(current)
    lines = []
    for n, cue in enumerate(cues, 1):
        lines += [str(n), f"{_srt_time(cue[0]['start'])} --> {_srt_time(cue[-1]['end'])}",
                  " ".join(w["text"] for w in cue), ""]
    return "\n".join(lines)


def word_timings(audio: Path, script: str | None, lang: str, per_cue: int, max_wait: int) -> dict:
    """Write <stem>.words.json and <stem>.words.srt next to the audio."""
    task = transcribe_words(audio, lang, max_wait)
    result = task.get("result") or task
    heard = [w for w in result.get("words", []) if w.get("type", "word") == "word"]
    if not heard:
        raise VibiError("Speech-to-text returned no words")
    heard_text = result.get("text") or " ".join(w["text"] for w in heard)
    duration = task.get("audio_duration_secs")
    script_words = script.split() if script else [w["text"] for w in heard]
    words = align_script(script_words, heard, float(duration) if duration else None)
    stem = audio.with_suffix("")
    json_path = Path(f"{stem}.words.json")
    srt_path = Path(f"{stem}.words.srt")
    json_path.write_text(json.dumps({"words": words, "heard_text": heard_text},
                                    ensure_ascii=False, indent=1), encoding="utf-8")
    srt_path.write_text(words_to_srt(words, per_cue), encoding="utf-8")
    matched = sum(1 for w in words if w["source"] == "matched")
    return {
        "words_srt": str(srt_path),
        "words_json": str(json_path),
        "word_count": len(words),
        "matched_ratio": round(matched / len(words), 3),
        "heard_text": heard_text,
        "stt_credits": task.get("credits_deducted"),
        "audio_seconds": task.get("audio_duration_secs"),
    }


def cmd_words(args) -> dict:
    audio = Path(args.audio)
    if not audio.is_file():
        raise VibiError(f"No audio file at {audio}")
    script = Path(args.text_file).read_text(encoding="utf-8") if args.text_file else args.text
    return word_timings(audio, script, args.lang, args.words_per_cue, args.max_wait)


# ---- cli ----------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vibi.py", description="Vibi text-to-speech CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("set-key", help="Save the API key to ~/.config/vibi/.env (run by the user)")
    sub.add_parser("credits", help="Credit balance (free)")

    for name in ("models", "languages"):
        p = sub.add_parser(name, help=f"List {name} (free)")
        p.add_argument("--provider", choices=PROVIDERS, default="elevenlabs")

    p = sub.add_parser("voices", help="Browse voice libraries (free)")
    p.add_argument("--provider", choices=PROVIDERS, default="elevenlabs")
    p.add_argument("--library", choices=("system", "shared", "cloned"), default="system")
    p.add_argument("--search")
    p.add_argument("--filter", action="append", help="key=value, repeatable (language=vi, gender=Female ...)")
    p.add_argument("--page", type=int)
    p.add_argument("--page-size", type=int, default=30)

    p = sub.add_parser("speak", help="Generate speech (spends credits)")
    p.add_argument("--text")
    p.add_argument("--text-file")
    p.add_argument("--out", required=True)
    p.add_argument("--provider", choices=PROVIDERS, default="elevenlabs")
    p.add_argument("--voice", help="voice_id (MiniMax also accepts uniq_id)")
    p.add_argument("--model", help="default: eleven_v4_turbo / speech-2.8-turbo / capcut")
    p.add_argument("--lang", default="vi", help="ISO code, or MiniMax language name")
    p.add_argument("--stability", type=float)
    p.add_argument("--similarity-boost", dest="similarity_boost", type=float)
    p.add_argument("--style", type=float)
    p.add_argument("--speaker-boost", dest="use_speaker_boost", action="store_true", default=None)
    p.add_argument("--speed", type=float)
    p.add_argument("--pitch", type=int)
    p.add_argument("--vol", type=float)
    p.add_argument("--srt", action="store_true", help="also save a sentence-level .srt (about +15%% credits)")
    p.add_argument("--max-wait", type=int, default=300)
    p.add_argument("--dry-run", action="store_true", help="show the request and credit estimate only")
    _word_args(p)

    p = sub.add_parser("resume", help="Finish a task that timed out (no new charge)")
    p.add_argument("task_id")
    p.add_argument("--out", required=True)
    p.add_argument("--srt", action="store_true")
    p.add_argument("--max-wait", type=int, default=300)
    p.add_argument("--lang", default="vi")
    p.add_argument("--text", help="script, for --word-srt")
    p.add_argument("--text-file", help="script file, for --word-srt")
    _word_args(p)

    p = sub.add_parser("words", help="Word-level .words.srt/.words.json for an existing audio file")
    p.add_argument("audio")
    p.add_argument("--text", help="the script that was read; its spelling is kept")
    p.add_argument("--text-file")
    p.add_argument("--lang", default="vi")
    p.add_argument("--words-per-cue", type=int, default=1)
    p.add_argument("--max-wait", type=int, default=300)
    return parser


def _word_args(p) -> None:
    p.add_argument("--word-srt", action="store_true",
                   help="also write <out>.words.srt and .words.json (speech-to-text, ~0.3 credit/s)")
    p.add_argument("--words-per-cue", type=int, default=1,
                   help="words per subtitle line in .words.srt; a cue also ends at punctuation")


COMMANDS = {
    "set-key": cmd_set_key,
    "credits": cmd_credits,
    "models": cmd_models,
    "languages": cmd_languages,
    "voices": cmd_voices,
    "speak": cmd_speak,
    "resume": cmd_resume,
    "words": cmd_words,
}


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    args = build_parser().parse_args(argv)
    try:
        result = COMMANDS[args.command](args)
        print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
        return 0
    except VibiError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
