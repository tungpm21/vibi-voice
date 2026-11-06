# vibi-voice

> **Gửi Claude / agent được nhờ cài plugin này** (người dùng chỉ đưa link repo):
>
> 1. Đây là plugin Claude Code có marketplace riêng. Cài bằng CLI, **không** clone hay chép thư mục vào `~/.claude/skills`:
>    `claude plugin marketplace add tungpm21/vibi-voice` (đã có thì `claude plugin marketplace update vibi-voice`), rồi `claude plugin install vibi-voice@vibi-voice`, rồi `claude plugin list` để xác nhận.
> 2. Tìm lệnh Python 3.8+ chạy được (`python`, `python3` hoặc `py -3`). Script nằm ở `~/.claude/plugins/cache/vibi-voice/vibi-voice/<version>/skills/vibi-voice/scripts/vibi.py`. Chạy `<python> "<đường dẫn tuyệt đối>" credits`.
> 3. Nếu báo thiếu key: **không hỏi key trong chat**, không tự ghi key ra file. Đưa người dùng đúng một lệnh có đường dẫn tuyệt đối để họ tự chạy trong terminal: `<python> "<đường dẫn>" set-key`. Họ báo xong thì chạy lại `credits`.
> 4. Nhắc người dùng khởi động lại Claude Code (hoặc `/reload-plugins`) để skill `vibi-voice:vibi-voice` hiện ra.
>
> Bản đầy đủ từng bước, kèm cách xử lý lỗi: [INSTALL-PROMPT.md](INSTALL-PROMPT.md).

Plugin Claude Code: tạo giọng đọc qua Vibi (api.vibi.pro). Một key Vibi dùng được ElevenLabs (mặc định `eleven_v4_turbo`), MiniMax và CapCut. Cài xong, agent tự biết cách tìm giọng, xem credit, đọc thử rồi đọc cả kịch bản.

Cần: Claude Code, Python 3.8+ và một tài khoản Vibi có API key riêng (credit trừ theo key của bạn). Không cần cài thêm gói Python nào.

Plugin không chính thức, không thuộc Vibi hay ElevenLabs. Text bạn gửi đi qua server của Vibi.

## Cài nhanh bằng một prompt

Mở [INSTALL-PROMPT.md](INSTALL-PROMPT.md), chép khối prompt vào Claude Code và gửi. Agent tự kiểm tra Python, cài plugin, rồi đưa bạn đúng một lệnh để tự nhập key. Key không bao giờ đi qua chat.

Hoặc cài tay bằng 2 lệnh:

```
claude plugin marketplace add tungpm21/vibi-voice
claude plugin install vibi-voice@vibi-voice
```

Mở lại Claude Code sau khi cài. Skill hiện với tên `vibi-voice:vibi-voice`.

Khi có bản mới: `claude plugin marketplace update vibi-voice` rồi `claude plugin update vibi-voice@vibi-voice`.

Máy không vào được GitHub thì chép cả thư mục repo sang, rồi thay `tungpm21/vibi-voice` trong lệnh đầu bằng đường dẫn tới thư mục đó.

## Nhập key (mỗi máy một lần)

Tự chạy lệnh dưới trong terminal của bạn. Key được gõ ẩn và lưu vào `~/.config/vibi/.env`, không đi qua chat:

```
python "<thư mục plugin>/skills/vibi-voice/scripts/vibi.py" set-key
```

Lệnh in ra số credit nếu key đúng. Cũng có thể đặt biến môi trường `VIBI_API_KEY`, hoặc thêm `VIBI_API_KEY=...` vào file `.env` của dự án.

## Tài khoản Claude khác trên claude.ai (bản web)

Tải repo về (Code → Download ZIP), nén riêng thư mục `skills/vibi-voice` thành zip rồi tải lên mục Skills trong phần cài đặt của claude.ai. Lưu ý: môi trường chạy code trên web thường chặn mạng ra ngoài, nên phải cho phép domain `api.vibi.pro` thì script mới gọi được. Bản web cũng không có `set-key` theo kiểu terminal; cách này chưa được thử.

## Thử nhanh

```
python vibi.py credits
python vibi.py voices --provider elevenlabs --library shared --filter required_languages=vi
python vibi.py speak --text "Xin chào" --out thu.mp3 --dry-run
```

## Giấy phép

MIT, xem [LICENSE](LICENSE).
