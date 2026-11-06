---
name: vibi-voice
description: Tạo giọng đọc (text-to-speech) qua Vibi (api.vibi.pro), một API bên thứ ba đứng trước ElevenLabs, MiniMax và CapCut, dùng chung một key, kèm phụ đề SRT theo câu hoặc theo từng từ. Dùng khi người dùng muốn "tạo voice bằng Vibi", "đọc tiếng Việt bằng ElevenLabs qua Vibi", "giọng CapCut", "giọng MiniMax", lồng tiếng thuyết minh cho video, "SRT từng từ", "phụ đề chạy theo từ", xem số credit Vibi, hoặc tìm giọng tiếng Việt. Chỉ có giọng đọc, không có clone giọng ElevenLabs, nhạc hay SFX.
---

# Vibi voice

Mọi thao tác đi qua một script, chỉ dùng thư viện chuẩn của Python 3.8+:

```
python "${CLAUDE_SKILL_DIR}/scripts/vibi.py" <lệnh> ...
```

Mỗi lệnh in ra một object JSON. `"ok": false` kèm `error` là lỗi; đọc `error` rồi báo người dùng, đừng đoán.

## Key

Script tìm `VIBI_API_KEY` theo thứ tự: biến môi trường, file `.env` ở thư mục hiện tại hoặc thư mục cha, rồi `~/.config/vibi/.env`.

Nếu báo thiếu key: bảo người dùng **tự chạy** lệnh dưới trong terminal của họ (key được gõ ẩn và lưu vào `~/.config/vibi/.env`). Không bao giờ xin họ dán key vào chat, không tự ghi key ra file.

```
python "${CLAUDE_SKILL_DIR}/scripts/vibi.py" set-key
```

## Quy trình

1. `credits` để xem số dư. Lệnh này và `voices`, `models`, `languages` không tốn credit.
2. Chọn giọng bằng `voices`, gửi người dùng tên giọng kèm link `preview` để họ nghe trước.
3. Trước khi chạy `speak` thật, báo: provider, model, voice, số ký tự và `estimated_credits` (có thể chạy `--dry-run` để lấy con số này).
4. Làm một câu mẫu ngắn trước, đợi người dùng duyệt, rồi mới đọc cả kịch bản.
5. Nếu `speak` báo hết giờ chờ, chạy `resume TASK_ID --out ...`. Đừng gửi lại `speak`, vì như vậy bị trừ credit hai lần.

## Lệnh

```
vibi.py credits
vibi.py models    [--provider elevenlabs|minimax|capcut]
vibi.py languages [--provider ...]
vibi.py voices    [--provider ...] [--library system|shared|cloned] [--search TÊN] [--filter k=v ...] [--page-size 30]
vibi.py speak     --out FILE.mp3 (--text "..." | --text-file kichban.txt) [--provider ...] [--voice ID] [--model ID]
                  [--lang vi] [--speed 1.0] [--stability 0.5] [--similarity-boost 0.75] [--style 0]
                  [--pitch 0] [--vol 1.0] [--srt] [--dry-run]
                  [--word-srt] [--words-per-cue 1]
vibi.py resume    TASK_ID --out FILE.mp3 [--word-srt --text-file kichban.txt]
vibi.py words     FILE.mp3 (--text "..." | --text-file kichban.txt) [--lang vi] [--words-per-cue 1]
```

Mặc định: provider `elevenlabs`, model `eleven_v4_turbo` (mới nhất), ngôn ngữ `vi`, giọng Rachel.

## Phụ đề

- `--srt`: SRT **theo câu**, do bước tạo giọng trả về, tốn thêm khoảng 15% credit giọng. Lưu thành `FILE.srt`.
- `--word-srt`: SRT **theo từng từ**. Script đưa audio vừa tạo qua speech-to-text của Vibi (Scribe v2, khoảng 0,3 credit/giây audio; 5 giây tốn 1–2 credit), rồi đặt chữ của kịch bản lên mốc thời gian nghe được. Lưu thành `FILE.words.srt` và `FILE.words.json` (mỗi từ có `start`, `end`, `source`).
  - Chữ trên phụ đề luôn là chữ của kịch bản. Speech-to-text hay nghe nhầm tên riêng (thử thật: "Vibi" thành "VB", "ElevenLabs" thành "Element Labs"); những từ đó có `source: "interpolated"`, thời gian chia theo hai từ khớp bên cạnh.
  - `matched_ratio` là tỉ lệ từ khớp trực tiếp. Dưới khoảng 0,7 thì mở `.words.json` kiểm tra trước khi dùng.
  - `--words-per-cue N`: mỗi dòng phụ đề N từ (mặc định 1, tức từng từ). Dòng luôn ngắt ở dấu câu.
  - Có audio rồi (kể cả từ nguồn khác) thì chạy `words` riêng, không phải tạo giọng lại.
  - Nếu bước mốc từ lỗi, file mp3 vẫn được giữ và có `word_srt_error`; chạy lại `words`, đừng chạy lại `speak`.

## Ba nguồn giọng

| provider | model mặc định | voice | cài đặt nhận | speed |
|---|---|---|---|---|
| `elevenlabs` | `eleven_v4_turbo` | không bắt buộc (mặc định Rachel) | stability, similarity-boost, style, speaker-boost, speed | 0.7–1.2 |
| `minimax` | `speech-2.8-turbo` | bắt buộc: `voice_id` hoặc `uniq_id` | speed, pitch (-12..12), vol | 0.5–2.0 |
| `capcut` | `capcut` | bắt buộc | speed, pitch | 0.5–2.0 |

Cài đặt không thuộc provider đã chọn sẽ bị bỏ qua.

Tìm giọng tiếng Việt:

```
vibi.py voices --provider elevenlabs --library shared --filter required_languages=vi
vibi.py voices --provider minimax --filter language=Vietnamese
vibi.py voices --provider capcut --filter language=vi
```

Bộ lọc khác: ElevenLabs shared nhận `gender` (male/female/neutral), `age` (young/middle_aged/old), `accent`, `sort`; MiniMax nhận `gender`, `age`, `use_cases`; CapCut nhận `gender` (Male/Female), `age`, `emotion`, `accent`.

Model ElevenLabs có trên Vibi (2026-11-06): `eleven_v4`, `eleven_v4_turbo`, `eleven_v3`, `eleven_v3_conversational`, `eleven_multilingual_v2`, `eleven_flash_v2_5`, `eleven_turbo_v2_5`. Chạy `models` để xem danh sách hiện tại.

## Lưu ý

- Credit đo được (2026-11-06): `eleven_v4_turbo` khoảng 0,5 credit/ký tự (87 ký tự trừ 44 credit, thêm SRT thì 51); CapCut gần như miễn phí (46 ký tự trừ 1 credit). Model khác ước 1 credit/ký tự; con số thật nằm ở `credits_deducted` trong kết quả.
- Chất lượng file: ElevenLabs trả mp3 44,1 kHz / 128 kbps. CapCut trả mp3 24 kHz / 32 kbps, nghe được nhưng mỏng, hợp làm bản nháp hơn bản mix cuối.
- Kịch bản dài: tách theo đoạn, mỗi đoạn một file (`vo_01.mp3`, `vo_02.mp3`...), giữ cùng voice và cùng cài đặt. Một request của ElevenLabs tối đa khoảng 10.000 ký tự.
- Không có trên Vibi: clone giọng ElevenLabs, nhạc, SFX. Cần mấy thứ đó thì dùng công cụ khác và nói rõ với người dùng.
- Text và key đi qua server của Vibi chứ không gửi thẳng tới ElevenLabs.
