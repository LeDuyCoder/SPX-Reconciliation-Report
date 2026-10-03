"""Email account management, template composition, preview, and send UI."""
from __future__ import annotations

import json
import tkinter as tk

import customtkinter as ctk

from .email_preview import EmailBrowserPreview
from .email_service import (
    GOOGLE, MICROSOFT, EmailAccountRepository, EmailProviderService, parse_recipients,
)
from .email_templates import EmailTemplateRepository, TemplateVariableResolver, sanitize_preview_html


class EmailPage:
    def __init__(self, app):
        self.app = app
        self.colors = app.UI
        self.frame = ctk.CTkFrame(app.shell, fg_color="transparent", corner_radius=0)
        self.accounts = EmailAccountRepository(app.db)
        self.provider = EmailProviderService(self.accounts)
        self.templates = EmailTemplateRepository(app.db)
        self.records = []
        self.template_labels = {}
        self.account_records = []
        self.selected_template = None
        self.variable_entries = {}
        self.preview_after = None
        self._build()
        self.refresh()

    def _build(self):
        colors = self.colors
        header = ctk.CTkFrame(self.frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, 13))
        title = ctk.CTkFrame(header, fg_color="transparent")
        title.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(title, text="Gửi Email", font=ctk.CTkFont(family="Segoe UI", size=25, weight="bold"),
                     text_color=colors["text"]).pack(anchor="w")
        ctk.CTkLabel(title, text="Kết nối tài khoản và gửi email bằng template đã lưu.",
                     font=ctk.CTkFont(size=12), text_color=colors["muted"]).pack(anchor="w", pady=(3, 0))

        self.account_card = ctk.CTkFrame(self.frame, fg_color=colors["surface"], corner_radius=10,
                                         border_width=1, border_color=colors["line"])
        self.account_card.pack(fill="x", pady=(0, 12))
        self.account_content = ctk.CTkFrame(self.account_card, fg_color="transparent")
        self.account_content.pack(fill="x", padx=16, pady=13)

        compose = ctk.CTkFrame(self.frame, fg_color=colors["surface"], corner_radius=10,
                               border_width=1, border_color=colors["line"])
        compose.pack(fill="both", expand=True)
        ctk.CTkLabel(compose, text="Soạn email", font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=colors["text"]).pack(anchor="w", padx=17, pady=(13, 9))
        panes = ctk.CTkFrame(compose, fg_color="transparent")
        panes.pack(fill="both", expand=True, padx=14, pady=(0, 13))
        panes.grid_columnconfigure(0, weight=45, uniform="compose")
        panes.grid_columnconfigure(1, weight=55, uniform="compose")
        panes.grid_rowconfigure(0, weight=1)

        fields = ctk.CTkScrollableFrame(panes, fg_color="transparent", corner_radius=0,
                                        scrollbar_button_color="#CBD5E1")
        fields.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self._form_label(fields, "Tài khoản gửi")
        self.account_menu = ctk.CTkOptionMenu(fields, values=["Chưa kết nối"], height=36,
                                               fg_color=colors["surface_alt"], button_color="#E6EAF0",
                                               button_hover_color="#D9DFE7", text_color=colors["text"],
                                               dropdown_text_color=colors["text"], command=self._schedule_preview)
        self.account_menu.pack(fill="x", pady=(0, 8))
        self.recipient_entries = {}
        for key, label, hint in (("to", "Người nhận", "email@example.com, ..."),
                                 ("cc", "CC (không bắt buộc)", "Thêm người nhận CC"),
                                 ("bcc", "BCC (không bắt buộc)", "Thêm người nhận BCC")):
            self._form_label(fields, label)
            entry = ctk.CTkEntry(fields, height=36, placeholder_text=hint,
                                 border_color=colors["line"], text_color=colors["text"])
            entry.pack(fill="x", pady=(0, 8))
            entry.bind("<KeyRelease>", self._schedule_preview)
            self.recipient_entries[key] = entry
        self._form_label(fields, "Template")
        self.template_menu = ctk.CTkOptionMenu(fields, values=["Chưa có template"], height=36,
                                                fg_color=colors["surface_alt"], button_color="#E6EAF0",
                                                button_hover_color="#D9DFE7", text_color=colors["text"],
                                                dropdown_text_color=colors["text"], command=self._select_template)
        self.template_menu.pack(fill="x", pady=(0, 8))
        self._form_label(fields, "Subject")
        self.subject_entry = ctk.CTkEntry(fields, height=36, placeholder_text="Tiêu đề email",
                                          border_color=colors["line"], text_color=colors["text"])
        self.subject_entry.pack(fill="x", pady=(0, 8))
        self.subject_entry.bind("<KeyRelease>", self._schedule_preview)
        self._form_label(fields, "Thông tin template")
        self.variables_frame = ctk.CTkFrame(fields, fg_color="transparent")
        self.variables_frame.pack(fill="x", pady=(0, 8))

        preview_card = ctk.CTkFrame(panes, fg_color=colors["surface_alt"], corner_radius=9,
                                    border_width=1, border_color=colors["line"])
        preview_card.grid(row=0, column=1, sticky="nsew")
        preview_header = ctk.CTkFrame(preview_card, fg_color="transparent")
        preview_header.pack(fill="x", padx=12, pady=(9, 4))
        ctk.CTkLabel(preview_header, text="XEM TRƯỚC EMAIL", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=colors["muted"]).pack(side="left")
        self.preview_subject = ctk.CTkLabel(preview_card, text="Chọn template để xem trước", anchor="w",
                                            font=ctk.CTkFont(size=12, weight="bold"), text_color=colors["text"])
        self.preview_subject.pack(fill="x", padx=12, pady=(0, 7))
        self.preview = EmailBrowserPreview(preview_card)
        self.preview.pack(fill="both", expand=True, padx=9, pady=(0, 9))

        actions = ctk.CTkFrame(self.frame, fg_color="transparent")
        actions.pack(fill="x", pady=(10, 0))
        self.status = ctk.CTkLabel(actions, text="", anchor="w", text_color=colors["muted"],
                                   font=ctk.CTkFont(size=11))
        self.status.pack(side="left", fill="x", expand=True)
        self.send_button = self.app._primary(actions, "Gửi Email", self.send, width=138, height=38)
        self.send_button.pack(side="right")

        history_card = ctk.CTkFrame(self.frame, fg_color=colors["surface"], corner_radius=10,
                                    border_width=1, border_color=colors["line"])
        history_card.pack(fill="x", pady=(12, 0))
        history_header = ctk.CTkFrame(history_card, fg_color="transparent")
        history_header.pack(fill="x", padx=15, pady=(9, 5))
        ctk.CTkLabel(history_header, text="Lịch sử gửi gần đây", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=colors["text"]).pack(side="left")
        self.history_text = ctk.CTkLabel(history_card, text="Chưa có email được gửi.", anchor="w",
                                         justify="left", text_color=colors["muted"], font=ctk.CTkFont(size=10))
        self.history_text.pack(fill="x", padx=15, pady=(0, 10))

    def _form_label(self, parent, text):
        ctk.CTkLabel(parent, text=text, anchor="w", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=self.colors["text"]).pack(fill="x", pady=(3, 4))

    def refresh(self):
        self.account_records = self.accounts.list()
        self.records = self.templates.get_all()
        self._render_accounts()
        labels = {}
        for record in self.records:
            label = record["name"]
            if label in labels:
                label = f"{label} · {record['id'][:6]}"
                labels[label] = record
            else:
                labels[label] = record
        self.template_labels = labels
        names = list(labels) or ["Chưa có template"]
        self.template_menu.configure(values=names)
        if self.records:
            selected = next((r for r in self.records if r["id"] == self.selected_template), self.records[0])
            label = next((name for name, record in self.template_labels.items()
                          if record["id"] == selected["id"]), selected["name"])
            self._select_template(label)
        else:
            self.selected_template = None
            self.template_menu.set("Chưa có template")
            self.subject_entry.delete(0, "end")
            self._clear_variables()
            self._update_preview()
        self._render_history()

    def _render_accounts(self):
        for widget in self.account_content.winfo_children():
            widget.destroy()
        account_names = [f"{item['email']} · {'Gmail' if item['provider'] == GOOGLE else 'Microsoft'}"
                         for item in self.account_records]
        if self.account_records:
            row = ctk.CTkFrame(self.account_content, fg_color="transparent")
            row.pack(fill="x")
            ctk.CTkLabel(row, text="Email Account", font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=self.colors["text"]).pack(side="left", padx=(0, 12))
            ctk.CTkLabel(row, text="✓ Đã kết nối", font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=self.colors["success"]).pack(side="left")
            for item, label in zip(self.account_records, account_names):
                ctk.CTkLabel(self.account_content, text=label, font=ctk.CTkFont(size=13, weight="bold"),
                             text_color=self.colors["text"]).pack(anchor="w", pady=(5, 0))
            self.account_menu.configure(values=account_names)
            self.account_menu.set(account_names[0])
            self._account_ids = dict(zip(account_names, [item["id"] for item in self.account_records]))
            self.app._secondary(row, "Ngắt kết nối", self.disconnect, width=115, height=32).pack(side="right")
        else:
            row = ctk.CTkFrame(self.account_content, fg_color="transparent")
            row.pack(fill="x")
            ctk.CTkLabel(row, text="Email Account", font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=self.colors["text"]).pack(side="left", padx=(0, 15))
            self.app._secondary(row, "Kết nối Gmail", lambda: self.connect(GOOGLE), width=128, height=34).pack(side="left", padx=(0, 8))
            self.app._secondary(row, "Kết nối Microsoft", lambda: self.connect(MICROSOFT), width=150, height=34).pack(side="left")
            self.account_menu.configure(values=["Chưa kết nối"])
            self.account_menu.set("Chưa kết nối")
            self._account_ids = {}

    def connect(self, provider):
        self.status.configure(text="Đang mở trang đăng nhập…")
        def worker():
            try:
                email_address = self.provider.connect(provider)
                self.app.jobs.put(("email_connected", 0, (provider, email_address)))
            except Exception as exc:
                message = str(exc)
                if "CLIENT_ID is not configured" in message or "OAUTH_REDIRECT_URL" in message:
                    result = "Ứng dụng chưa được cấu hình để kết nối nhà cung cấp email này."
                else:
                    result = "Không thể kết nối tài khoản email. Hãy thử lại hoặc kiểm tra cấu hình OAuth."
                self.app.jobs.put(("email_connect_error", 0, result))
        import threading
        threading.Thread(target=worker, name="email-oauth", daemon=True).start()

    def disconnect(self):
        account_id = self._account_ids.get(self.account_menu.get())
        if not account_id:
            return
        if not self.app._dialog("Ngắt kết nối email?", "Bạn có thể kết nối lại tài khoản này bất cứ lúc nào.",
                                confirm=True, confirm_text="Ngắt kết nối", kind="warning"):
            return
        self.accounts.disconnect(account_id)
        self.refresh()
        self.app._toast("Đã ngắt kết nối tài khoản email.")

    def _select_template(self, name):
        record = self.template_labels.get(name)
        if not record:
            return
        self.selected_template = record["id"]
        self.template_menu.set(name)
        current_subject = self.subject_entry.get()
        previous = getattr(self, "_active_template_subject", None)
        if previous is None or current_subject == previous:
            self.subject_entry.delete(0, "end")
            self.subject_entry.insert(0, record["subject"])
        self._active_template_subject = record["subject"]
        variables = TemplateVariableResolver.extract_variables(record["subject"] + "\n" + record["html_content"])
        self._clear_variables()
        for variable in variables:
            entry = ctk.CTkEntry(self.variables_frame, height=32, placeholder_text=variable,
                                 border_color=self.colors["line"], text_color=self.colors["text"])
            entry.pack(fill="x", pady=(0, 5))
            entry.bind("<KeyRelease>", self._schedule_preview)
            self.variable_entries[variable] = entry
        self._schedule_preview()

    def _clear_variables(self):
        for widget in self.variables_frame.winfo_children():
            widget.destroy()
        self.variable_entries.clear()

    def _values(self):
        return {key: entry.get().strip() for key, entry in self.variable_entries.items()}

    def _update_preview(self):
        record = next((r for r in self.records if r["id"] == self.selected_template), None)
        if not record:
            self.preview_subject.configure(text="Chọn template để xem trước")
            self.preview.set_document("")
            return
        values = self._values()
        subject = TemplateVariableResolver.resolve(self.subject_entry.get(), values, escape_html=False)
        body = TemplateVariableResolver.resolve(record["html_content"], values, escape_html=True)
        self.preview_subject.configure(text=subject or "(Không có tiêu đề)")
        safe_body = sanitize_preview_html(body)
        self.preview.set_document("<!doctype html><html><head><meta charset='utf-8'></head><body>" + safe_body + "</body></html>")

    def _schedule_preview(self, _event=None):
        if self.preview_after is not None:
            try:
                self.app.after_cancel(self.preview_after)
            except tk.TclError:
                pass
        self.preview_after = self.app.after(180, self._refresh_preview)

    def _refresh_preview(self):
        self.preview_after = None
        self._update_preview()

    def send(self):
        account_id = self._account_ids.get(self.account_menu.get())
        if not account_id:
            self.status.configure(text="Hãy kết nối tài khoản Gmail hoặc Microsoft trước.", text_color=self.colors["danger"])
            return
        if not self.selected_template:
            self.status.configure(text="Hãy chọn một email template.", text_color=self.colors["danger"])
            return
        try:
            recipients = {key: parse_recipients(entry.get()) for key, entry in self.recipient_entries.items()}
            if not recipients["to"]:
                raise ValueError("Hãy nhập ít nhất một người nhận.")
            all_addresses = [address for values in recipients.values() for address in values]
            if len(all_addresses) != len(set(all_addresses)):
                raise ValueError("Một địa chỉ email không thể xuất hiện ở nhiều nhóm người nhận.")
        except ValueError as exc:
            self.status.configure(text=str(exc), text_color=self.colors["danger"])
            return
        record = next(r for r in self.records if r["id"] == self.selected_template)
        subject = TemplateVariableResolver.resolve(self.subject_entry.get().strip(), self._values(), escape_html=False)
        if not subject:
            self.status.configure(text="Hãy nhập subject email.", text_color=self.colors["danger"])
            return
        html_body = TemplateVariableResolver.resolve(record["html_content"], self._values(), escape_html=True)
        html_body = sanitize_preview_html(html_body)
        if not self.app._dialog("Gửi email?", f"Email sẽ được gửi từ tài khoản đã kết nối tới {len(recipients['to'])} người nhận chính.",
                                confirm=True, confirm_text="Gửi email"):
            return
        self.send_button.configure(state="disabled", text="Đang gửi…")
        self.status.configure(text="Đang gửi email…", text_color=self.colors["muted"])
        payload = (account_id, recipients, subject, html_body, record["id"])
        def worker():
            try:
                self.provider.send(account_id, to=recipients["to"], cc=recipients["cc"],
                                   bcc=recipients["bcc"], subject=subject, html_body=html_body)
                try:
                    self.accounts.add_history(account_id, record["id"], all_addresses, subject, "SENT")
                except Exception:
                    pass
                result = (True, "Email đã được gửi thành công.")
            except Exception:
                try:
                    self.accounts.add_history(account_id, record["id"], all_addresses, subject,
                                              "FAILED", "Unable to send email.")
                except Exception:
                    pass
                result = (False, "Không thể gửi email. Hãy thử lại hoặc kết nối lại tài khoản.")
            self.app.jobs.put(("email_sent", 0, result))
        import threading
        threading.Thread(target=worker, name="email-send", daemon=True).start()

    def handle_job(self, kind, value):
        if kind == "email_connected":
            self.status.configure(text="Đã kết nối tài khoản email.", text_color=self.colors["success"])
            self.refresh()
        elif kind == "email_connect_error":
            self.status.configure(text=value, text_color=self.colors["danger"])
        elif kind == "email_sent":
            success, message = value
            self.send_button.configure(state="normal", text="Gửi Email")
            self.status.configure(text=message, text_color=self.colors["success"] if success else self.colors["danger"])
            if success:
                self.app._toast(message)
            self._render_history()

    def _render_history(self):
        rows = self.accounts.history(5)
        if not rows:
            text = "Chưa có email được gửi."
        else:
            lines = []
            for row in rows:
                recipients = ", ".join(json.loads(row["recipients"]))
                stamp = row["sent_at"].replace("T", " ")[:16]
                marker = "Đã gửi" if row["status"] == "SENT" else "Gửi thất bại"
                lines.append(f"{stamp}  ·  {marker}  ·  {row['subject']}  ·  {recipients}")
            text = "\n".join(lines)
        self.history_text.configure(text=text)

    def dispose(self):
        if self.preview_after is not None:
            try:
                self.app.after_cancel(self.preview_after)
            except tk.TclError:
                pass
        self.preview.dispose()
