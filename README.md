# SPX Reconciliation Report

Ứng dụng desktop Python/PySide6 để quản lý workspace và xem dữ liệu SPX nhập từ Excel. Bảng dữ liệu dùng Qt model/view, dữ liệu chính và cấu hình được lưu bằng SQLite cục bộ.

## Chạy ứng dụng

```powershell
python -m pip install -e .
python -m spx_reconciliation_report
```

Khi dev, nhấn **Ctrl+Shift+R** để khởi động lại ứng dụng và nạp code mới.

Chọn **Create workspace**, mở workspace, sau đó **Import Excel**. Workbook cần có sheet tên chính xác `Main Data`; các cột chưa có sẽ được để trống và cột lạ sẽ được bỏ qua sau khi hiển thị trong bước preview.

## Lưu trữ

- Windows: `%APPDATA%\SPXReconciliation\spx_reconciliation.db`
- File Excel nguồn được sao chép vào `%APPDATA%\SPXReconciliation\imports\<workspace-id>\` sau khi import thành công.
- Xóa workspace sẽ xóa dữ liệu liên quan trong SQLite và thư mục file nguồn của workspace.

SQLite dùng phân trang 100 dòng, tìm kiếm/lọc/sắp xếp trực tiếp trên toàn bộ dữ liệu workspace. Nhập Excel chạy trên worker thread và ghi theo lô trong một transaction.

## Email connection and sending

The **Gửi Email** page connects Gmail with OAuth, uses saved Email Templates, previews the rendered message, and records send history. OAuth credentials belong to the developer and are never entered by end users.

1. Create a Google OAuth application and register the local callback `http://localhost:8765/callback` for the desktop app.
2. Copy `.env.example` to `.env` and fill in the Google client ID and client secret. The app reads this file from the project root (or reads matching environment variables).
3. Enable the Gmail API and allow the `gmail.send` and OpenID email scopes.
4. Restart the app and choose **Gửi Email → Kết nối Gmail**.

Tokens are protected with Windows DPAPI before they are written to SQLite and can only be decrypted by the same Windows user profile. OAuth uses state validation and PKCE. The local callback port must be available while connecting. No SMTP settings or email passwords are stored. Because this is a desktop app with no server component, provider client configuration runs on the local machine; a confidential server-side OAuth secret requires a separate backend before distributing this as a centrally managed product.
