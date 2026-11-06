# vibi-voice

Plugin Claude Code: tạo giọng đọc qua Vibi (api.vibi.pro). Một key Vibi dùng được ElevenLabs (mặc định `eleven_v4_turbo`), MiniMax và CapCut. Cài xong, agent tự biết cách tìm giọng, xem credit, đọc thử rồi đọc cả kịch bản.

Cần: Claude Code và Python 3.8+. Không cần cài thêm gói Python nào.

## Cài nhanh bằng một prompt

Mở [INSTALL-PROMPT.md](INSTALL-PROMPT.md), chép khối prompt vào Claude Code trên máy mới và gửi. Agent tự kiểm tra Python và quyền GitHub, cài plugin, rồi đưa bạn đúng một lệnh để tự nhập key. Key không bao giờ đi qua chat.

## Cài tay trên máy khác (Claude Code)

**Cách 1: chép thư mục.** Chép cả thư mục `vibi-voice` sang máy kia (USB, Google Drive, zip...), rồi chạy:

```
claude plugin marketplace add "<đường dẫn tới thư mục vibi-voice>"
claude plugin install vibi-voice@vibi-voice
```

**Cách 2: qua GitHub (tiện khi có nhiều máy hoặc nhiều tài khoản).** Plugin nằm ở repo private `tungpm21/vibi-voice`. Máy cần đăng nhập GitHub bằng tài khoản có quyền đọc repo (`gh auth login`, hoặc git đã lưu đăng nhập), rồi chạy:

```
claude plugin marketplace add tungpm21/vibi-voice
claude plugin install vibi-voice@vibi-voice
```

Khi plugin có bản mới thì chạy `claude plugin marketplace update vibi-voice` rồi cài lại. Người khác muốn dùng thì mời họ vào repo (Settings → Collaborators) và để họ dùng key Vibi riêng.

Mở lại Claude Code sau khi cài. Skill hiện với tên `vibi-voice:vibi-voice`.

## Nhập key (mỗi máy một lần)

Tự chạy lệnh dưới trong terminal của bạn. Key được gõ ẩn và lưu vào `~/.config/vibi/.env`, không đi qua chat:

```
python "<thư mục plugin>/skills/vibi-voice/scripts/vibi.py" set-key
```

Lệnh in ra số credit nếu key đúng. Cũng có thể đặt biến môi trường `VIBI_API_KEY`, hoặc thêm `VIBI_API_KEY=...` vào file `.env` của dự án.

## Tài khoản Claude khác trên claude.ai (bản web)

Nén thư mục `skills/vibi-voice` thành zip rồi tải lên mục Skills trong phần cài đặt của claude.ai. Lưu ý: môi trường chạy code trên web thường chặn mạng ra ngoài, nên phải cho phép domain `api.vibi.pro` thì script mới gọi được. Bản web cũng không có `set-key` theo kiểu terminal; cách này chưa được thử.

## Thử nhanh

```
python vibi.py credits
python vibi.py voices --provider elevenlabs --library shared --filter required_languages=vi
python vibi.py speak --text "Xin chào" --out thu.mp3 --dry-run
```
