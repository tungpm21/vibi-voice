#!/usr/bin/env python3
"""Vibi CLI for api.vibi.pro: text-to-speech (ElevenLabs, MiniMax, CapCut), dialogue,
voice changer, AI dubbing, MiniMax voice cloning, speech-to-text and task history.
API reference: https://vibi.pro/docs

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
# capcut 1 credit for 46, speech-2.8-turbo 31 for 51, dialogue 17 for 69 (mixed).
# Other models assume 1 credit per character.
CREDITS_PER_CHAR = {"eleven_v4_turbo": 0.5, "capcut": 0.025, "speech-2.8-turbo": 0.6}


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
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_name(out.name + ".part")
    with urllib.request.urlopen(req, timeout=600) as resp, open(part, "wb") as handle:
        while True:
            block = resp.read(1 << 20)
            if not block:
                break
            handle.write(block)
    if part.stat().st_size == 0:
        part.unlink()
        raise VibiError(f"Empty file from {url}")
    part.replace(out)


def multipart(path: str, fields: dict, files: list, timeout: int = 300) -> dict:
    """POST multipart/form-data. fields: name -> str | list[str] (repeated);
    files: [(field_name, filename, bytes)]."""
    key = find_key()
    boundary = "----vibi" + os.urandom(12).hex()
    parts = []
    for name, value in fields.items():
        for item in value if isinstance(value, list) else [value]:
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{item}\r\n'.encode()
            )
    for field, filename, content in files:
        parts.append(
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; '
                f'filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'
            ).encode()
            + content
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
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise VibiError(f"HTTP {exc.code} on {path}: {detail}".replace(key, "[REDACTED]"))
    except urllib.error.URLError as exc:
        raise VibiError(f"Cannot reach {API_HOST}: {exc.reason}")
    return json.loads(raw.decode("utf-8")) if raw else {}


# Task families and where their history lives.
KINDS = {
    "tts": "/v1/history",  # text-to-speech and dialogue
    "voice-changer": "/v1/voice-changer/history",
    "dubbing": "/v1/aidubbing/history",
    "stt": "/v1/speech-to-text",
}
RETRYABLE = ("tts", "voice-changer", "dubbing")


def poll(kind: str, task_id: str, max_wait: int, out_hint: str = "OUT") -> dict:
    """Poll a task until completed; raise on failure or timeout."""
    deadline = time.monotonic() + max_wait
    while True:
        task = request("GET", f"{KINDS[kind]}/{task_id}", timeout=30)
        status = task.get("status")
        if status in ("completed", "done"):
            return task
        if status == "failed":
            detail = task.get("detail_error")
            raise VibiError(
                f"{kind} task {task_id} failed: {task.get('error')}" + (f" ({detail})" if detail else "")
            )
        if time.monotonic() >= deadline:
            raise VibiError(
                f"{kind} task {task_id} still {status} ({task.get('progress')}%); finish later with: "
                f"vibi.py task {task_id} --kind {kind} --download {out_hint}"
            )
        time.sleep(3 if kind == "dubbing" else 2)


def save_outputs(task: dict, out: Path) -> dict:
    """Download result.audio_url to `out` (keeping the URL's extension when `out`
    has none) and result.srt_url next to it."""
    result = task.get("result") or {}
    saved = {}
    audio_url = result.get("audio_url")
    if audio_url:
        url_suffix = Path(urllib.parse.urlparse(audio_url).path).suffix
        target = out if out.suffix else out.with_suffix(url_suffix or ".mp3")
        download(audio_url, target)
        saved["output"] = str(target)
        saved["bytes"] = target.stat().st_size
    srt_url = result.get("srt_url")
    if srt_url:
        srt_path = (Path(saved["output"]) if saved else out).with_suffix(".srt")
        download(srt_url, srt_path)
        saved["srt"] = str(srt_path)
    if not saved:
        raise VibiError(f"Task {task.get('id') or task.get('task_id')} has no downloadable result")
    return saved


def _probe_seconds(path: Path) -> float | None:
    """Media duration via ffprobe, if installed (used for credit estimates)."""
    import shutil
    import subprocess

    if not shutil.which("ffprobe"):
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=60,
        ).stdout.strip()
        return float(out) if out else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


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
                "voice_id": v.get("voice_id") or v.get("id"),
                "uniq_id": v.get("uniq_id"),
                "status": v.get("status"),
                "error": v.get("error_message"),
                "name": v.get("name") or v.get("voice_name"),
                "gender": v.get("gender"),
                "language": v.get("language"),
                "tags": v.get("tags") or v.get("tag_list"),
                "preview": v.get("preview_url") or v.get("sample_audio") or v.get("sample_audio_url"),
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


def transcribe_words(audio: Path, lang: str, max_wait: int = 300) -> dict:
    """Run Vibi speech-to-text (Scribe v2) and return the finished task."""
    submitted = multipart(
        "/v1/speech-to-text",
        {"language_code": _iso_lang(lang), "timestamps_granularity": "word",
         "tag_audio_events": "false"},
        [("file", audio.name, audio.read_bytes())],
    )
    task_id = submitted.get("task_id") or submitted.get("id")
    if not task_id:
        raise VibiError(f"No task id from speech-to-text: {submitted}")
    return poll("stt", task_id, max_wait)


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


# ---- dialogue (several voices in one file) ------------------------------


def _parse_speaker(spec: str, default_lang: str) -> tuple:
    """'Name=provider:voice_id[:model[:language]]' -> (name, config)."""
    name, sep, rest = spec.partition("=")
    bits = rest.split(":") if sep else []
    if not name.strip() or len(bits) < 2:
        raise VibiError(f"--speaker needs Name=provider:voice_id[:model[:language]], got {spec!r}")
    provider, voice = bits[0].strip(), bits[1].strip()
    if provider not in PROVIDERS:
        raise VibiError(f"--speaker {name}: provider must be one of {', '.join(PROVIDERS)}")
    model = (bits[2].strip() if len(bits) > 2 and bits[2].strip() else DEFAULT_MODELS[provider])
    lang = bits[3].strip() if len(bits) > 3 and bits[3].strip() else default_lang
    if provider == "minimax" and len(lang) <= 3:
        lang = {v: k.title() for k, v in _ISO.items()}.get(lang, lang)  # vi -> Vietnamese
    return name.strip(), {"provider": provider, "voice_id": voice, "model_id": model, "language_code": lang}


def _spoken_text(script: str) -> str:
    """Dialogue script without the 'Name:' prefixes, for word timings."""
    import re

    return "\n".join(re.sub(r"^\s*[^:\n]{1,40}:\s*", "", line) for line in script.splitlines())


def cmd_dialogue(args) -> dict:
    script = (
        Path(args.script_file).read_text(encoding="utf-8") if args.script_file else (args.text or "")
    ).strip()
    if not script:
        raise VibiError("Give --script-file or --text in 'Name: line' format")
    speakers = {}
    if args.speakers_json:
        speakers.update(json.loads(Path(args.speakers_json).read_text(encoding="utf-8")))
    for spec in args.speaker or []:
        name, config = _parse_speaker(spec, args.lang)
        speakers[name] = config
    if len(speakers) < 2:
        raise VibiError("Dialogue needs at least 2 speakers (--speaker or --speakers-json)")
    body = {"text": script, "speakers": speakers}
    if args.pause is not None:
        if not 0 <= args.pause <= 3:
            raise VibiError("--pause must be 0-3 seconds")
        body["pause_between_turns"] = args.pause
    spoken = _spoken_text(script)
    estimate = sum(
        len(spoken) * CREDITS_PER_CHAR.get(c.get("model_id"), 1.0) for c in speakers.values()
    ) / len(speakers)
    if args.dry_run:
        return {"dry_run": True, "request": body, "estimated_credits": round(estimate, 1)}
    submitted = request("POST", "/v1/dialogue", body=body)
    task_id = submitted.get("id") or submitted.get("task_id")
    if not task_id:
        raise VibiError(f"No task id in response: {submitted}")
    task = poll("tts", task_id, args.max_wait, args.out)
    report = {"task_id": task_id, **save_outputs(task, Path(args.out)),
              "characters_used": task.get("characters_used"),
              "credits_deducted": task.get("credits_deducted"),
              "estimated_credits": round(estimate, 1)}
    if args.word_srt:
        try:
            report["word_srt"] = word_timings(
                Path(report["output"]), spoken, args.lang, args.words_per_cue, args.max_wait
            )
        except VibiError as exc:
            report["word_srt_error"] = str(exc)
    return report


# ---- voice changer (speech-to-speech, ElevenLabs voices) -----------------


def cmd_voice_change(args) -> dict:
    audio = Path(args.audio)
    if not audio.is_file():
        raise VibiError(f"No audio file at {audio}")
    seconds = _probe_seconds(audio)
    estimate = round(seconds / 60 * 1000) if seconds else None  # docs: ~1000 credits/minute
    fields = {"voice_id": args.voice, "model_id": args.model,
              "remove_background_noise": "true" if args.denoise else "false"}
    settings = {k: getattr(args, k) for k in ("stability", "similarity_boost", "style", "use_speaker_boost")
                if getattr(args, k) is not None}
    if settings:
        fields["voice_settings"] = json.dumps(settings)
    if args.dry_run:
        return {"dry_run": True, "fields": fields, "audio_seconds": seconds, "estimated_credits": estimate}
    submitted = multipart("/v1/voice-changer", fields, [("audio", audio.name, audio.read_bytes())])
    task_id = submitted.get("task_id") or submitted.get("id")
    if not task_id:
        raise VibiError(f"No task id in response: {submitted}")
    task = poll("voice-changer", task_id, args.max_wait, args.out)
    return {"task_id": task_id, **save_outputs(task, Path(args.out)),
            "credits_deducted": task.get("credits_deducted"), "estimated_credits": estimate}


# ---- AI dubbing (translate + re-voice an audio or video) -----------------


def cmd_dub(args) -> dict:
    source = Path(args.source)
    if not source.is_file():
        raise VibiError(f"No source file at {source}")
    seconds = _probe_seconds(source)
    estimate = round(seconds * 50) if seconds else None  # docs: 50 credits per source second
    fields = {"target_language": args.to, "source_language": args.source_lang,
              "provider": args.provider, "voice_id": args.voice, "filename": source.name}
    if args.content_type:
        fields["content_type"] = args.content_type
    elif source.suffix.lower() in (".mp4", ".mov"):
        fields["content_type"] = "video/mp4" if source.suffix.lower() == ".mp4" else "video/quicktime"
    if args.dry_run:
        return {"dry_run": True, "fields": fields, "source_seconds": seconds,
                "estimated_credits": estimate,
                "note": "50 credits per second of source, charged upfront"}
    init = request("POST", "/v1/aidubbing/upload/init", body={})
    upload_id, chunk_size = init.get("upload_id"), int(init.get("chunk_size") or 50 * 1024 * 1024)
    if not upload_id:
        raise VibiError(f"upload/init returned no upload_id: {init}")
    chunk_size = min(chunk_size, 100 * 1024 * 1024)
    index = 0
    with open(source, "rb") as handle:
        while True:
            block = handle.read(chunk_size)
            if not block:
                break
            multipart("/v1/aidubbing/upload/chunk", {"upload_id": upload_id, "index": str(index)},
                      [("chunk", f"{source.name}.part{index}", block)], timeout=600)
            index += 1
    if index == 0:
        raise VibiError("Source file is empty")
    submitted = multipart("/v1/aidubbing/upload/complete",
                          {**fields, "upload_id": upload_id, "total_chunks": str(index)}, [])
    task_id = submitted.get("task_id") or submitted.get("id")
    if not task_id:
        raise VibiError(f"No task id in response: {submitted}")
    task = poll("dubbing", task_id, args.max_wait, args.out)
    return {"task_id": task_id, **save_outputs(task, Path(args.out)), "chunks": index,
            "credits_deducted": task.get("credits_deducted"), "estimated_credits": estimate}


# ---- MiniMax voice cloning ------------------------------------------------


def _find_clone(clone_id: str) -> dict | None:
    for voice in request("GET", "/v1/minimax/voices").get("voices", []):
        if voice.get("id") == clone_id:
            return voice
    return None


def _wait_clone(clone_id: str, max_wait: int) -> dict:
    deadline = time.monotonic() + max_wait
    while True:
        voice = _find_clone(clone_id)
        status = (voice or {}).get("status")
        if status == "done":
            return voice
        if status == "failed":
            raise VibiError(f"Clone {clone_id} failed: {voice}")
        if voice is None:
            raise VibiError(f"Clone {clone_id} not found")
        if time.monotonic() >= deadline:
            raise VibiError(f"Clone {clone_id} still {status}; check later with: vibi.py voices --provider minimax --library cloned")
        time.sleep(3)


def cmd_clone(args) -> dict:
    audio = Path(args.audio)
    if not audio.is_file():
        raise VibiError(f"No audio file at {audio}")
    if audio.stat().st_size > 20 * 1024 * 1024:
        raise VibiError("Clone source must be at most 20 MB")
    fields = {"voice_name": args.name, "language_tag": args.language, "gender": args.gender,
              "need_noise_reduction": "false" if args.no_denoise else "true"}
    if args.preview_text:
        fields["preview_text"] = args.preview_text[:200]
    created = multipart("/v1/minimax/voices/clone", fields, [("file", audio.name, audio.read_bytes())])
    clone_id = created.get("id")
    if not clone_id:
        raise VibiError(f"No clone id in response: {created}")
    voice = _wait_clone(clone_id, args.max_wait)
    report = {"clone_id": clone_id, "voice_name": voice.get("voice_name"), "status": voice.get("status"),
              "use_with": f"speak --provider minimax --voice {clone_id}",
              "sample_audio_url": voice.get("sample_audio_url")}
    if args.sample_out and voice.get("sample_audio_url"):
        download(voice["sample_audio_url"], Path(args.sample_out))
        report["sample"] = args.sample_out
    return report


def cmd_clone_retry(args) -> dict:
    created = request("POST", f"/v1/minimax/voices/{urllib.parse.quote(args.clone_id)}/retry")
    voice = _wait_clone(created.get("id") or args.clone_id, args.max_wait)
    return {"clone_id": voice.get("id"), "status": voice.get("status")}


def cmd_clone_delete(args) -> dict:
    return request("DELETE", f"/v1/minimax/voices/{urllib.parse.quote(args.clone_id)}")


# ---- full speech-to-text --------------------------------------------------


def cmd_transcribe(args) -> dict:
    audio = Path(args.audio)
    if not audio.is_file():
        raise VibiError(f"No audio file at {audio}")
    fields = {"language_code": _iso_lang(args.lang), "timestamps_granularity": args.granularity,
              "tag_audio_events": "true" if args.audio_events else "false"}
    if args.diarize:
        fields["diarize"] = "true"
        if args.num_speakers:
            fields["num_speakers"] = str(args.num_speakers)
    if args.no_verbatim:
        fields["no_verbatim"] = "true"
    if args.keyterm:
        fields["keyterms"] = list(args.keyterm)
    if args.format:
        fields["additional_formats"] = list(args.format)
    for item in args.field or []:
        key, sep, value = item.partition("=")
        if not sep:
            raise VibiError(f"--field needs key=value, got {item!r}")
        fields.setdefault(key, [])
        if not isinstance(fields[key], list):
            fields[key] = [fields[key]]
        fields[key].append(value)
    submitted = multipart("/v1/speech-to-text", fields, [("file", audio.name, audio.read_bytes())])
    task_id = submitted.get("task_id") or submitted.get("id")
    if not task_id:
        raise VibiError(f"No task id from speech-to-text: {submitted}")
    task = poll("stt", task_id, args.max_wait)
    result = task.get("result") or {}
    prefix = Path(args.out_prefix) if args.out_prefix else audio.with_suffix("")
    json_path = Path(f"{prefix}.transcript.json")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    files = [str(json_path)]
    for extra in result.get("additional_formats") or []:
        ext = extra.get("file_extension") or extra.get("requested_format") or "txt"
        content = extra.get("content") or ""
        path = Path(f"{prefix}.{ext}")
        if extra.get("is_base64_encoded"):
            import base64

            path.write_bytes(base64.b64decode(content))
        else:
            path.write_text(content, encoding="utf-8")
        files.append(str(path))
    return {"task_id": task_id, "text": (result.get("text") or "")[:500],
            "language_code": result.get("language_code"),
            "audio_seconds": task.get("audio_duration_secs"),
            "credits_deducted": task.get("credits_deducted"), "files": files}


# ---- history: list, inspect, download, retry, delete ---------------------


def _slim_task(task: dict) -> dict:
    keep = ("id", "task_id", "status", "progress", "provider", "voice_id", "model_id",
            "source_lang", "target_lang", "filename", "audio_duration_secs",
            "characters_used", "credits_deducted", "error", "created_at")
    slim = {k: task.get(k) for k in keep if task.get(k) not in (None, "")}
    if task.get("text"):
        slim["text"] = task["text"][:80]
    if task.get("result") and isinstance(task["result"], dict):
        slim["result"] = {k: v for k, v in task["result"].items() if k.endswith("_url")}
    return slim


def cmd_history(args) -> dict:
    data = request("GET", KINDS[args.kind], params={"page": args.page, "page_size": args.page_size})
    return {"kind": args.kind, "has_more": data.get("has_more"),
            "tasks": [_slim_task(t) for t in data.get("tasks", [])]}


def cmd_task(args) -> dict:
    task = request("GET", f"{KINDS[args.kind]}/{urllib.parse.quote(args.task_id)}")
    report = {"kind": args.kind, "task": _slim_task(task) if args.kind != "stt" else
              {k: v for k, v in task.items() if k != "result"}}
    if args.download:
        if task.get("status") not in ("completed", "done"):
            raise VibiError(f"Task is {task.get('status')} ({task.get('progress')}%), nothing to download yet")
        if args.kind == "stt":
            path = Path(args.download)
            path.write_text(json.dumps(task.get("result"), ensure_ascii=False, indent=1), encoding="utf-8")
            report["saved"] = {"output": str(path)}
        else:
            report["saved"] = save_outputs(task, Path(args.download))
    return report


def cmd_retry(args) -> dict:
    if args.kind not in RETRYABLE:
        raise VibiError(f"{args.kind} tasks cannot be retried")
    submitted = request("POST", f"{KINDS[args.kind]}/{urllib.parse.quote(args.task_id)}/retry")
    task_id = submitted.get("id") or submitted.get("task_id") or args.task_id
    report = {"kind": args.kind, "task_id": task_id, "status": submitted.get("status"),
              "note": "retry charges credits again"}
    if args.out:
        task = poll(args.kind, task_id, args.max_wait, args.out)
        report.update(save_outputs(task, Path(args.out)))
        report["credits_deducted"] = task.get("credits_deducted")
    return report


def cmd_delete(args) -> dict:
    return {"kind": args.kind, "task_id": args.task_id,
            "response": request("DELETE", f"{KINDS[args.kind]}/{urllib.parse.quote(args.task_id)}")}


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

    p = sub.add_parser("dialogue", help="Several voices in one file, 'Name: line' script (spends credits)")
    p.add_argument("--script-file", help="UTF-8 file, one 'Name: line' per turn")
    p.add_argument("--text", help="script inline instead of --script-file")
    p.add_argument("--speaker", action="append",
                   help="Name=provider:voice_id[:model[:language]], repeat per speaker")
    p.add_argument("--speakers-json", help="JSON {Name: {provider, voice_id, model_id, language_code, voice_settings}}")
    p.add_argument("--out", required=True)
    p.add_argument("--lang", default="vi", help="default language for speakers")
    p.add_argument("--pause", type=float, help="seconds of silence between turns, 0-3")
    p.add_argument("--max-wait", type=int, default=600)
    p.add_argument("--dry-run", action="store_true")
    _word_args(p)

    p = sub.add_parser("voice-change", help="Re-voice an audio file with an ElevenLabs voice (~1000 credits/min)")
    p.add_argument("audio")
    p.add_argument("--voice", required=True, help="target ElevenLabs voice_id")
    p.add_argument("--out", required=True)
    p.add_argument("--model", default="eleven_multilingual_sts_v2")
    p.add_argument("--denoise", action="store_true", help="remove background noise first")
    p.add_argument("--stability", type=float)
    p.add_argument("--similarity-boost", dest="similarity_boost", type=float)
    p.add_argument("--style", type=float)
    p.add_argument("--speaker-boost", dest="use_speaker_boost", action="store_true", default=None)
    p.add_argument("--max-wait", type=int, default=600)
    p.add_argument("--dry-run", action="store_true", help="show fields and credit estimate only")

    p = sub.add_parser("dub", help="AI dubbing: translate and re-voice audio/video (50 credits per source second)")
    p.add_argument("source", help="mp3, wav, aac, m4a, mp4 or mov; max 2 GB / 2.5 h")
    p.add_argument("--to", required=True, help="target language ISO code, e.g. vi")
    p.add_argument("--from", dest="source_lang", required=True, help="source language ISO code ('auto' not accepted)")
    p.add_argument("--provider", choices=PROVIDERS, default="minimax")
    p.add_argument("--voice", required=True,
                   help="MiniMax uniq_id or clone id; ElevenLabs voice_id; CapCut voice_id")
    p.add_argument("--out", required=True, help="dubbed file; extension follows the result if omitted")
    p.add_argument("--content-type", help="MIME type hint, e.g. video/mp4")
    p.add_argument("--max-wait", type=int, default=3600)
    p.add_argument("--dry-run", action="store_true", help="show fields and credit estimate only")

    p = sub.add_parser("clone", help="Clone a voice with MiniMax from an audio sample")
    p.add_argument("audio", help="clean speech sample, max 20 MB")
    p.add_argument("--name", required=True)
    p.add_argument("--language", default="Vietnamese", help="MiniMax language name")
    p.add_argument("--gender", default="Male", choices=("Male", "Female"))
    p.add_argument("--no-denoise", action="store_true")
    p.add_argument("--preview-text", help="sample sentence, max 200 characters")
    p.add_argument("--sample-out", help="save the preview sample here")
    p.add_argument("--max-wait", type=int, default=600)

    p = sub.add_parser("clone-retry", help="Re-run a MiniMax clone (charges again)")
    p.add_argument("clone_id")
    p.add_argument("--max-wait", type=int, default=600)

    p = sub.add_parser("clone-delete", help="Delete a MiniMax cloned voice (permanent)")
    p.add_argument("clone_id")

    p = sub.add_parser("transcribe", help="Speech-to-text with all Scribe v2 options (~0.3 credit/s)")
    p.add_argument("audio")
    p.add_argument("--lang", default="vi")
    p.add_argument("--granularity", choices=("word", "character", "none"), default="word")
    p.add_argument("--diarize", action="store_true", help="label speakers")
    p.add_argument("--num-speakers", type=int)
    p.add_argument("--no-verbatim", action="store_true", help="drop fillers and false starts")
    p.add_argument("--audio-events", action="store_true", help="keep (laughter), (music) tags")
    p.add_argument("--keyterm", action="append", help="word or name to bias toward, repeatable")
    p.add_argument("--format", action="append",
                   choices=("srt", "txt", "docx", "html", "pdf", "segmented_json"),
                   help="extra export format, repeatable")
    p.add_argument("--field", action="append", help="any other form field key=value (entity_detection=pii ...)")
    p.add_argument("--out-prefix", help="default: audio path without extension")
    p.add_argument("--max-wait", type=int, default=900)

    p = sub.add_parser("history", help="List past tasks (free)")
    p.add_argument("--kind", choices=tuple(KINDS), default="tts")
    p.add_argument("--page", type=int, default=0)
    p.add_argument("--page-size", type=int, default=20)

    p = sub.add_parser("task", help="Show one task; --download saves its result (free)")
    p.add_argument("task_id")
    p.add_argument("--kind", choices=tuple(KINDS), default="tts")
    p.add_argument("--download", help="save the result here")

    p = sub.add_parser("retry", help="Re-run a tts/dialogue, voice-changer or dubbing task (charges again)")
    p.add_argument("task_id")
    p.add_argument("--kind", choices=RETRYABLE, default="tts")
    p.add_argument("--out", help="wait and save the new result here")
    p.add_argument("--max-wait", type=int, default=900)

    p = sub.add_parser("delete", help="Delete a task and its stored files (permanent)")
    p.add_argument("task_id")
    p.add_argument("--kind", choices=tuple(KINDS), default="tts")
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
    "dialogue": cmd_dialogue,
    "voice-change": cmd_voice_change,
    "dub": cmd_dub,
    "clone": cmd_clone,
    "clone-retry": cmd_clone_retry,
    "clone-delete": cmd_clone_delete,
    "transcribe": cmd_transcribe,
    "history": cmd_history,
    "task": cmd_task,
    "retry": cmd_retry,
    "delete": cmd_delete,
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
