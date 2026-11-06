---
name: vibi-voice
description: Dùng toàn bộ API Vibi (api.vibi.pro) bằng một key, gồm ElevenLabs, MiniMax và CapCut. Có tạo giọng đọc, hội thoại nhiều giọng, đổi giọng một file audio (voice changer), lồng tiếng AI dịch video hoặc audio sang ngôn ngữ khác, clone giọng MiniMax, chuyển giọng thành chữ có tách người nói, SRT theo câu hoặc theo từng từ, xem lịch sử, chạy lại hoặc xóa task. Dùng khi người dùng nói "tạo voice bằng Vibi", "đọc tiếng Việt bằng ElevenLabs qua Vibi", "giọng CapCut", "giọng MiniMax", "hội thoại hai giọng", "đổi giọng file này", "lồng tiếng video sang tiếng Anh", "clone giọng", "chuyển audio thành chữ", "SRT từng từ", "xem credit Vibi", hoặc khi cần tìm giọng tiếng Việt. Không có nhạc, SFX hay clone giọng ElevenLabs.
---

# Vibi

Tài liệu API chính thức: https://vibi.pro/docs. Khi có gì ở đây không khớp với API thật, tin tài liệu đó và báo người dùng.

Mọi thao tác đi qua một script, chỉ cần Python 3.8+ có sẵn thư viện chuẩn:

```
python "${CLAUDE_SKILL_DIR}/scripts/vibi.py" <lệnh> ...
```

Mỗi lệnh in ra một object JSON. `"ok": false` kèm `error` là lỗi; đọc `error`, báo nguyên văn cho người dùng, đừng đoán.

## Key

Script tìm `VIBI_API_KEY` theo thứ tự: biến môi trường, file `.env` ở thư mục hiện tại hoặc thư mục cha, rồi `~/.config/vibi/.env`.

Nếu báo thiếu key: bảo người dùng **tự chạy** lệnh dưới trong terminal của họ (key được gõ ẩn và lưu vào `~/.config/vibi/.env`). Không bao giờ xin họ dán key vào chat, không tự ghi key ra file.

```
python "${CLAUDE_SKILL_DIR}/scripts/vibi.py" set-key
```

Xem hoặc tạo lại API key chỉ làm được trên web vibi.pro: endpoint `/v1/api-keys` dùng phiên đăng nhập web, gọi bằng API key sẽ trả 401.

## Quy tắc trước khi tiêu credit

1. Lệnh miễn phí: `credits`, `voices`, `models`, `languages`, `history`, `task`, `resume`, `clone-delete`, `delete`. Lệnh tốn credit: `speak`, `dialogue`, `voice-change`, `dub`, `clone`, `clone-retry`, `transcribe`, `words`, `retry`.
2. Trước lệnh tốn credit, báo người dùng: lệnh, provider, model, voice và số credit ước tính. Các lệnh `speak`, `dialogue`, `voice-change`, `dub` có `--dry-run` để lấy con số này mà không trừ credit.
3. Làm một mẫu ngắn trước, đợi người dùng duyệt, rồi mới chạy cả kịch bản hoặc cả file.
4. `dub` tốn 50 credit cho mỗi giây file gốc, trừ ngay từ đầu (1 phút = 3.000 credit). Luôn chạy `--dry-run` và hỏi người dùng trước.
5. Khi chờ quá lâu, đừng gửi lại lệnh vì sẽ bị trừ credit hai lần. Tạo giọng thì dùng `resume TASK_ID --out ...`; loại khác dùng `task TASK_ID --kind ... --download ...`.
6. `retry` và `clone-retry` trừ credit lại từ đầu.
7. `delete` và `clone-delete` xóa vĩnh viễn, kể cả file trên server. Chỉ chạy khi người dùng yêu cầu rõ ràng, và nhắc lại ID trước khi xóa.
8. `clone` chỉ dùng với giọng của chính người dùng, hoặc giọng mà họ có quyền dùng. Không clone giọng người khác, kể cả giọng mẫu trong thư viện Vibi.

## Lệnh

```
# tra cứu (miễn phí)
vibi.py credits
vibi.py models    [--provider elevenlabs|minimax|capcut]
vibi.py languages [--provider ...]
vibi.py voices    [--provider ...] [--library system|shared|cloned] [--search TÊN] [--filter k=v ...] [--page N] [--page-size 30]

# tạo giọng một người đọc
vibi.py speak     --out FILE.mp3 (--text "..." | --text-file kichban.txt) [--provider ...] [--voice ID] [--model ID]
                  [--lang vi] [--speed 1.0] [--stability 0.5] [--similarity-boost 0.75] [--style 0] [--speaker-boost]
                  [--pitch 0] [--vol 1.0] [--srt] [--word-srt] [--words-per-cue 1] [--dry-run]
vibi.py resume    TASK_ID --out FILE.mp3 [--srt] [--word-srt --text-file kichban.txt]

# hội thoại nhiều giọng trong một file
vibi.py dialogue  --out FILE.mp3 (--script-file hoithoai.txt | --text "...")
                  --speaker "An=elevenlabs:VOICE_ID" --speaker "Bình=capcut:VOICE_ID[:model[:language]]"
                  [--speakers-json speakers.json] [--pause 0.4] [--lang vi] [--word-srt] [--dry-run]

# đổi giọng một file audio có sẵn (chỉ giọng ElevenLabs)
vibi.py voice-change AUDIO --voice VOICE_ID --out FILE.mp3 [--model eleven_multilingual_sts_v2] [--denoise]
                  [--stability ..] [--similarity-boost ..] [--style ..] [--speaker-boost] [--dry-run]

# lồng tiếng AI: dịch và đọc lại audio/video
vibi.py dub       SOURCE --from vi --to en --voice VOICE --out FILE [--provider minimax|elevenlabs|capcut] [--dry-run]

# clone giọng MiniMax
vibi.py clone     MAU.mp3 --name "Tên" [--language Vietnamese] [--gender Male|Female] [--no-denoise]
                  [--preview-text "..."] [--sample-out mau_thu.mp3]
vibi.py clone-retry  CLONE_ID
vibi.py clone-delete CLONE_ID

# chuyển giọng thành chữ
vibi.py transcribe AUDIO [--lang vi] [--diarize --num-speakers 2] [--no-verbatim] [--audio-events]
                  [--keyterm "Tên riêng" ...] [--format srt|txt|docx|html|pdf|segmented_json ...]
                  [--granularity word|character|none] [--field key=value ...] [--out-prefix PATH]
vibi.py words     AUDIO (--text "..." | --text-file kichban.txt) [--lang vi] [--words-per-cue 1]

# lịch sử
vibi.py history   [--kind tts|voice-changer|dubbing|stt] [--page 0] [--page-size 20]
vibi.py task      TASK_ID [--kind ...] [--download FILE]
vibi.py retry     TASK_ID [--kind tts|voice-changer|dubbing] [--out FILE]
vibi.py delete    TASK_ID [--kind tts|voice-changer|dubbing|stt]
```

`--kind tts` gồm cả task tạo giọng một người và task hội thoại.

## Ba nguồn giọng

| provider | model mặc định | voice | cài đặt nhận | speed |
|---|---|---|---|---|
| `elevenlabs` | `eleven_v4_turbo` | không bắt buộc (mặc định Rachel) | stability, similarity-boost, style, speaker-boost, speed | 0.7–1.2 |
| `minimax` | `speech-2.8-turbo` | bắt buộc: `voice_id`, `uniq_id` hoặc ID giọng đã clone | speed, pitch (-12..12), vol | 0.5–2.0 |
| `capcut` | `capcut` | bắt buộc | speed, pitch | 0.5–2.0 |

Cài đặt không thuộc provider đã chọn sẽ bị bỏ qua. Model khác: ElevenLabs có `eleven_v4`, `eleven_v3`, `eleven_v3_conversational`, `eleven_multilingual_v2`, `eleven_flash_v2_5`; MiniMax có `speech-2.8-hd`, `speech-2.6-*`, `speech-02-*`... Chạy `models` để xem danh sách hiện tại.

Tìm giọng tiếng Việt:

```
vibi.py voices --provider elevenlabs --library shared --filter required_languages=vi
vibi.py voices --provider minimax --filter language=Vietnamese
vibi.py voices --provider capcut --filter language=vi
```

Bộ lọc khác: ElevenLabs shared nhận `gender` (male/female/neutral), `age` (young/middle_aged/old), `accent`, `sort`, `use_cases[]`; MiniMax nhận `gender`, `age`, `accent`, `use_cases`; CapCut nhận `gender` (Male/Female), `age`, `emotion`, `accent`.

## Hội thoại (`dialogue`)

- Mỗi dòng của kịch bản có dạng `Tên: câu nói`. Dòng không có `Tên:` được nối vào lượt nói trước. Cần ít nhất 2 người nói.
- Mỗi người nói chọn provider, voice, model và ngôn ngữ riêng, trộn được ElevenLabs, MiniMax và CapCut trong cùng một file. Ngôn ngữ MiniMax là tên đầy đủ (`Vietnamese`); script tự đổi `vi` sang `Vietnamese`.
- Cần `voice_settings` riêng cho từng người thì dùng `--speakers-json`: `{"An": {"provider": "elevenlabs", "voice_id": "...", "model_id": "eleven_v4_turbo", "language_code": "vi", "voice_settings": {"stability": 0.4}}}`.
- `--word-srt` bỏ phần `Tên:` rồi làm SRT từng từ trên phần lời được đọc.

## Phụ đề

- `speak --srt`: SRT **theo câu**, do bước tạo giọng trả về, tốn thêm khoảng 15% credit giọng.
- `--word-srt` / `words`: SRT **theo từng từ**. Script đưa audio qua speech-to-text (khoảng 0,3 credit/giây audio), rồi đặt chữ của kịch bản lên mốc thời gian nghe được. Lưu `FILE.words.srt` và `FILE.words.json`.
  - Chữ trên phụ đề luôn là chữ của kịch bản. Từ bị nghe nhầm (thử thật: "Vibi" thành "VB") có `source: "interpolated"`, thời gian chia theo hai từ khớp bên cạnh. Scribe hay dồn 2–3 từ cuối vào một mốc; script tự chia lại tới hết audio.
  - `matched_ratio` dưới khoảng 0,7 thì mở `.words.json` kiểm tra trước khi dùng.
  - Bước mốc từ lỗi thì file mp3 vẫn được giữ và có `word_srt_error`; chạy lại `words`, đừng chạy lại `speak`.
- `dub` trả kèm SRT đã dịch (`FILE.srt`).
- `transcribe --format srt` cho SRT theo câu của một file audio bất kỳ, không cần kịch bản.

## Chuyển giọng thành chữ (`transcribe`)

Dùng ElevenLabs Scribe v2. Kết quả lưu `PREFIX.transcript.json` (có `text`, `words[]` với `start`, `end`, `speaker_id`) và mỗi định dạng `--format` thành một file `PREFIX.<đuôi>`.
- `--diarize` gắn `speaker_id` cho từng từ. Với file rất ngắn (thử thật: 4,7 giây, hai giọng), Scribe có thể gộp thành một người.
- `--keyterm` giúp nhận đúng tên riêng. `--no-verbatim` bỏ "ờ", "à". `--field entity_detection=pii` và các trường khác trong tài liệu truyền thẳng qua `--field`.
- `language_code` là bắt buộc; mặc định `vi`.

## Lồng tiếng AI (`dub`)

- Nhận mp3, wav, aac, m4a, mp4, mov; tối đa 2 GB, 2,5 giờ. Script tự chia file thành từng phần khi tải lên.
- `--from` bắt buộc, không nhận `auto`. Model cố định theo provider: MiniMax `speech-2.8-hd`, ElevenLabs `eleven_v3`, CapCut `capcut`. CapCut chỉ lồng sang en, zh, es, id, pt, fr, de, vi, ja, th, tr, it.
- `--voice`: với MiniMax là `uniq_id` (ví dụ `English_expressive_narrator`) hoặc ID giọng clone; với ElevenLabs là voice_id; với CapCut là voice_id có ngôn ngữ trùng ngôn ngữ đích.
- Nguồn là video thì kết quả là mp4, còn lại là mp3. `--out` không có đuôi file thì script tự lấy đuôi theo kết quả.
- Thử thật: bản dịch đọc sai tên riêng ("ElevenLabs" thành "11 Lapse"). Nhắc người dùng nghe lại trước khi dùng.

## Đổi giọng (`voice-change`)

Chỉ dùng được giọng ElevenLabs. File tối đa 50 MB, 5 phút, khoảng 1.000 credit/phút. Ngày 2026-11-06 Vibi trả `503 provider_under_maintenance` cho tính năng này; nếu gặp lại thì báo người dùng là Vibi đang bảo trì, đừng thử lại liên tục.

## Clone giọng MiniMax (`clone`)

- File mẫu tối đa 20 MB, là giọng nói rõ, không có nhạc nền. Lệnh chờ tới khi `status` thành `done`, rồi in `clone_id` để dùng như `speak --provider minimax --voice CLONE_ID` hoặc trong `dialogue`, `dub`.
- File không có giọng nói thì Vibi trả `failed` ("No voice detected") và không trừ credit.
- Xem các giọng đã clone: `voices --provider minimax --library cloned`.

## Credit đo được (2026-11-06)

| việc | ví dụ thật | credit |
|---|---|---|
| `speak` ElevenLabs `eleven_v4_turbo` | 87 ký tự | 44 (thêm `--srt` thì 51) |
| `speak` MiniMax `speech-2.8-turbo` | 51 ký tự | 31 |
| `speak` CapCut | 46 ký tự | 1 |
| `dialogue` ElevenLabs + CapCut | 69 ký tự | 17 |
| `transcribe` / `words` | 5 giây audio | 1–2 |
| `dub` | 5 giây | 253 (50/giây) |

Con số thật luôn nằm ở `credits_deducted` trong kết quả.

## Lưu ý

- Chất lượng file: ElevenLabs trả mp3 44,1 kHz / 128 kbps. CapCut trả mp3 24 kHz / 32 kbps, nghe mỏng, hợp làm bản nháp hơn bản mix cuối.
- Kịch bản dài: tách theo đoạn, mỗi đoạn một file, giữ cùng voice và cùng cài đặt. Một request ElevenLabs tối đa khoảng 10.000 ký tự.
- Không có trên Vibi: nhạc, SFX, clone giọng ElevenLabs.
- Text, audio và key đi qua server của Vibi.
