# Cài vibi-voice bằng một prompt

Mở Claude Code trên máy mới (app desktop hoặc terminal), dán nguyên khối dưới vào ô chat và gửi. Agent tự kiểm tra máy, cài plugin, rồi đưa bạn đúng một lệnh để tự nhập key Vibi.

Máy cần có sẵn: Claude Code, Python 3.8+, Git, và quyền đọc repo private `tungpm21/vibi-voice` trên GitHub.

---

```
Cài plugin Claude Code "vibi-voice" cho tôi từ repo GitHub private tungpm21/vibi-voice. Làm lần lượt từng bước, bước nào lỗi thì dừng lại, báo lỗi nguyên văn và cách sửa, đừng tự đổi sang cách khác.

1. Tìm lệnh Python 3.8+ chạy được trên máy này: thử lần lượt `python --version`, `python3 --version`, `py -3 --version`. Ghi nhớ lệnh chạy được, gọi là PY. Không có thì bảo tôi cài Python từ python.org rồi dừng.
2. Kiểm tra quyền đọc repo: chạy `git ls-remote https://github.com/tungpm21/vibi-voice HEAD`. Nếu lỗi xác thực hoặc không tìm thấy repo: kiểm tra `gh auth status`; chưa có gh hoặc chưa đăng nhập thì bảo tôi TỰ chạy `gh auth login` (chọn GitHub.com, HTTPS, đăng nhập bằng trình duyệt) rồi chạy `gh auth setup-git`, sau đó dừng chờ tôi.
3. Chạy `claude plugin marketplace add tungpm21/vibi-voice`. Nếu báo marketplace đã có thì chạy `claude plugin marketplace update vibi-voice` thay thế.
4. Chạy `claude plugin install vibi-voice@vibi-voice`, rồi `claude plugin list` để xác nhận vibi-voice đã cài và đang bật.
5. Tìm file vibi.py của bản vừa cài, nằm trong thư mục ~/.claude/plugins/cache/vibi-voice/vibi-voice/<version>/skills/vibi-voice/scripts/ (lấy version mới nhất). Chạy `PY "<đường dẫn tuyệt đối>/vibi.py" credits`.
   - Nếu trả "ok": true thì máy đã có key, bỏ qua bước 6.
   - Nếu báo thiếu VIBI_API_KEY: đưa tôi đúng một lệnh có đường dẫn tuyệt đối để tôi TỰ chạy trong terminal của tôi: `PY "<đường dẫn tuyệt đối>/vibi.py" set-key`. Không được hỏi key trong chat, không tự ghi key ra file. Dừng chờ tôi báo xong.
6. Khi tôi báo đã nhập key, chạy lại lệnh `credits` ở bước 5 và báo số credit.
7. Cuối cùng nhắc tôi khởi động lại Claude Code (hoặc gõ /reload-plugins) để skill vibi-voice:vibi-voice hiện ra, và tóm tắt: lệnh PY, đường dẫn plugin, số credit.
```

---

## Cập nhật bản mới trên máy đã cài

Dán vào Claude Code:

```
Cập nhật plugin vibi-voice: chạy `claude plugin marketplace update vibi-voice` rồi `claude plugin update vibi-voice@vibi-voice`, báo version trước và sau, rồi nhắc tôi khởi động lại Claude Code.
```
