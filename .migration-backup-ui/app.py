"""Legacy application module; Qt implementation is in ui.main_window."""
from __future__ import annotations

import os
import queue
import subprocess
import shutil
import sys
import threading
import ctypes
from datetime import datetime
from pathlib import Path
from typing import Any
import tkinter as tk
from tkinter import filedialog, ttk

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageTk

from .columns import COLUMNS, COLUMN_BY_FIELD, DEFAULT_FIELDS
from .database import Database
from .email_page import EmailPage
from .email_template_page import EmailTemplatePage
from .excel_import import iter_import_rows, preview_workbook

CATEGORY_FIELDS = {
    "sender_type", "sender_station_type", "receiver_type", "receiver_station_type",
    "to_direction", "journey_type", "receive_status", "exception_tag",
    "packing_method", "dangerous_goods",
}
BADGE_FIELDS = {"receive_status", "exception_tag", "dangerous_goods"}
FILTER_OPERATORS = {
    "contains": "Chứa", "equals": "Bằng", "starts": "Bắt đầu bằng",
    "ends": "Kết thúc bằng", ">": "Lớn hơn", ">=": "Từ",
    "<": "Nhỏ hơn", "<=": "Đến", "between": "Trong khoảng",
    "in": "Một trong",
}
FILTER_OPERATOR_KEYS = {label: key for key, label in FILTER_OPERATORS.items()}
COLUMN_WIDTHS = {
    "sender_name": 180, "sender_type": 115, "sender_station_type": 165,
    "receiver_id": 115, "receiver_name": 190, "receiver_type": 125,
    "receiver_station_type": 170, "current_station": 180,
    "to_order_quantity": 135, "to_direction": 125, "weight": 100,
    "length": 90, "width": 90, "height": 90, "line_haul_trip_number": 160,
    "operator": 130, "create_time": 155, "complete_time": 155,
    "driver": 130, "driver_scan_time": 155, "journey_type": 115,
    "remark": 190, "receive_status": 140, "to_remark": 190,
    "staging_area_id": 135, "exception_tag": 135, "packing_method": 145,
    "dangerous_goods": 135,
}

SPACING = {"page_x": 24, "page_y": 20, "card_pad": 16, "control_gap": 10}
RADIUS = {"card": 12, "control": 9, "button": 8}
TYPOGRAPHY = {"title": 27, "body": 13, "table": 10, "caption": 11}
BORDERS = {"default": "#E5E9EF", "focus": "#E85A3A"}

UI = {
    "nav": "#10253D",
    "nav_hover": "#1B3551",
    "nav_text": "#E6EDF5",
    "nav_muted": "#9AADC1",
    "accent": "#E94F2E",
    "accent_hover": "#D94327",
    "accent_soft": "#FFF2ED",
    "canvas": "#F4F6F8",
    "surface": "#FFFFFF",
    "surface_alt": "#F8FAFC",
    "line": "#E5E9EF",
    "line_strong": "#D5DCE5",
    "text": "#17212F",
    "muted": "#667384",
    "success": "#16835D",
    "danger": "#B5473C",
    "blue": "#475467",
    "focus_ring": "#F8D5C9",
}


def data_root() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "SPXReconciliation"


def _build_taskbar_icon() -> Image.Image:
    """Draw a high-contrast SPX mark that stays legible at 16–32 px."""
    size = 1024
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)
    draw.rounded_rectangle((12, 12, size - 12, size - 12), radius=220, fill="#102D4D")

    fonts_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    font = None
    for filename in ("arialbi.ttf", "segoeuib.ttf"):
        try:
            font = ImageFont.truetype(str(fonts_dir / filename), 410)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default(size=410)

    mark_width = draw.textlength("SPX", font=font)
    start_x = (size - mark_width) / 2
    bounds = draw.textbbox((0, 0), "SPX", font=font)
    mark_height = bounds[3] - bounds[1]
    mark_y = (size - mark_height) / 2 - bounds[1] - 32
    draw.text((start_x, mark_y), "SP", font=font, fill="#FFFFFF")
    draw.text((start_x + draw.textlength("SP", font=font), mark_y),
              "X", font=font, fill="#FF633E")
    draw.rounded_rectangle((260, 704, 764, 742), radius=19, fill="#FF633E")
    return icon


class App(ctk.CTk):
    PAGE_SIZE = 100

    def __init__(self):
        if os.name == "nt":
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    ctypes.c_wchar_p("SPX.ReconciliationReport.Desktop"))
            except (AttributeError, OSError):
                pass
        super().__init__()
        self.UI = UI
        self.title("SPX Reconciliation Report")
        logo_path = Path(__file__).parent / "assets" / "logo.png"
        icon_bitmap = _build_taskbar_icon()
        self.window_icons = tuple(
            ImageTk.PhotoImage(
                icon_bitmap.resize((size, size), Image.Resampling.LANCZOS), master=self
            )
            for size in (16, 20, 24, 32, 40, 48, 64, 128, 256)
        )
        self.window_icon = self.window_icons[3]
        self.iconphoto(True, *self.window_icons)
        self.native_icon_path = None
        try:
            native_icon_path = data_root() / "logo.ico"
            native_icon_path.parent.mkdir(parents=True, exist_ok=True)
            icon_bitmap.save(
                native_icon_path, format="ICO",
                sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48),
                       (64, 64), (128, 128), (256, 256)],
            )
            self.native_icon_path = native_icon_path
            self.iconbitmap(default=str(self.native_icon_path))
        except (OSError, tk.TclError):
            pass
        self.geometry("1360x700")
        self.minsize(1120, 620)
        ctk.set_appearance_mode("Light")
        ctk.set_default_color_theme("blue")
        self.root_dir = data_root()
        self.db = Database(self.root_dir / "spx_reconciliation.db")
        self.workspaces: dict[str, dict] = {}
        self.workspace_id: str | None = None
        self.email_template_page: EmailTemplatePage | None = None
        self.email_page: EmailPage | None = None
        self.workspace_home_frame: ctk.CTkFrame | None = None
        self.data_page_frame: ctk.CTkFrame | None = None
        self._data_page_workspace_id: str | None = None
        self._active_page: str | None = None
        self._workspace_summary_dirty = True
        self.settings: dict = {}
        self.page = 0
        self.total = 0
        self._page_loading = False
        self.search_var = tk.StringVar()
        self.search_text = ""
        self.sort_field: str | None = None
        self.sort_direction = "asc"
        self.jobs: queue.Queue = queue.Queue()
        self.request_number = 0
        self._search_after = None
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._close_app)
        self.show_workspaces()
        self.after(100, self._poll_jobs)

    def _build(self):
        self.configure(fg_color=UI["canvas"])
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.sidebar = ctk.CTkFrame(self, width=232, corner_radius=0, fg_color=UI["nav"])
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=17, pady=(22, 25))
        logo_path = Path(__file__).parent / "assets" / "logo.png"
        with Image.open(logo_path) as logo_file:
            logo_bitmap = logo_file.convert("RGBA")
            self.logo_image = ctk.CTkImage(light_image=logo_bitmap, dark_image=logo_bitmap, size=(52, 52))
        ctk.CTkLabel(brand, text="", image=self.logo_image).pack(side="left", padx=(0, 10))
        brand_copy = ctk.CTkFrame(brand, fg_color="transparent")
        brand_copy.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(brand_copy, text="SPX", font=ctk.CTkFont(family="Segoe UI", size=19, weight="bold"),
                     text_color=UI["nav_text"]).pack(anchor="w")
        ctk.CTkLabel(brand_copy, text="RECONCILIATION", font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
                     text_color=UI["nav_muted"]).pack(anchor="w", pady=(0, 1))

        ctk.CTkLabel(self.sidebar, text="ĐIỀU HƯỚNG", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=UI["nav_muted"]).pack(anchor="w", padx=20, pady=(0, 8))
        self.nav_workspaces = ctk.CTkButton(self.sidebar, text="Workspace", anchor="w", height=42,
                                             fg_color=UI["nav_hover"], hover_color=UI["nav_hover"],
                                             text_color=UI["nav_text"], command=self.show_workspaces,
                                             corner_radius=7, font=ctk.CTkFont(size=12, weight="bold"))
        self.nav_workspaces.pack(fill="x", padx=12, pady=3)
        self.nav_current = ctk.CTkButton(self.sidebar, text="Dữ liệu chính", anchor="w", height=42,
                                          fg_color="transparent", hover_color=UI["nav_hover"],
                                          text_color=UI["nav_muted"], state="disabled", corner_radius=7,
                                          font=ctk.CTkFont(size=12, weight="bold"))
        self.nav_current.pack(fill="x", padx=12, pady=3)
        self.nav_email_templates = ctk.CTkButton(
            self.sidebar, text="Email Template", anchor="w", height=42,
            fg_color="transparent", hover_color=UI["nav_hover"], text_color=UI["nav_muted"],
            command=self.show_email_templates, corner_radius=7,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.nav_email_templates.pack(fill="x", padx=12, pady=3)
        self.nav_email = ctk.CTkButton(
            self.sidebar, text="Gửi Email", anchor="w", height=42,
            fg_color="transparent", hover_color=UI["nav_hover"], text_color=UI["nav_muted"],
            command=self.show_email, corner_radius=7,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.nav_email.pack(fill="x", padx=12, pady=3)
        self.nav_new = self._primary(self.sidebar, "+   Tạo workspace", self._create_workspace,
                                     height=42, corner_radius=8)
        self.nav_new.pack(fill="x", padx=12, pady=(13, 0))

        self.sidebar_workspace = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.sidebar_workspace.pack(fill="x", padx=20, pady=(25, 0))
        ctk.CTkLabel(self.sidebar_workspace, text="WORKSPACE ĐANG MỞ", font=ctk.CTkFont(size=9, weight="bold"),
                     text_color=UI["nav_muted"]).pack(anchor="w")
        self.sidebar_workspace_name = ctk.CTkLabel(self.sidebar_workspace, text="Chưa chọn workspace",
                                                    text_color=UI["nav_text"], anchor="w", justify="left",
                                                    wraplength=190, font=ctk.CTkFont(size=12))
        self.sidebar_workspace_name.pack(fill="x", anchor="w", pady=(7, 0))

        bottom = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=18, pady=18)
        ctk.CTkFrame(bottom, height=1, fg_color="#34485E").pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(bottom, text="●  LƯU TRỮ CỤC BỘ", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#83D3B0").pack(anchor="w")
        ctk.CTkLabel(bottom, text="Dữ liệu được lưu trên thiết bị này", font=ctk.CTkFont(size=10),
                     text_color=UI["nav_muted"]).pack(anchor="w", pady=(4, 0))

        self.main_area = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.main_area.grid(row=0, column=1, sticky="nsew")
        self.main_area.grid_rowconfigure(1, weight=1)
        self.main_area.grid_columnconfigure(0, weight=1)
        topbar = ctk.CTkFrame(self.main_area, height=50, corner_radius=0, fg_color=UI["surface"])
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.grid_propagate(False)
        self.breadcrumb = ctk.CTkLabel(topbar, text="SPX  /  Workspace", font=ctk.CTkFont(size=12),
                                        text_color=UI["muted"])
        self.breadcrumb.pack(side="left", padx=25)
        if not getattr(sys, "frozen", False):
            self._ghost(topbar, "R", self._reload_ui, width=30, height=30,
                        text_color=UI["muted"], hover_color="#F2F4F7",
                        font=ctk.CTkFont(size=12, weight="bold")).pack(side="right", padx=(0, 8))
            self.bind_all("<Control-r>", self._reload_ui, add="+")
            self.bind_all("<F5>", self._reload_ui, add="+")
        ctk.CTkLabel(topbar, text="●  Sẵn sàng", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=UI["success"]).pack(side="right", padx=24)
        ctk.CTkFrame(topbar, height=1, fg_color=UI["line"]).place(relx=0, rely=1, relwidth=1, anchor="sw")
        self.shell = ctk.CTkFrame(self.main_area, fg_color="transparent", corner_radius=0)
        self.shell.grid(row=1, column=0, sticky="nsew", padx=24, pady=20)
        self.shell.grid_columnconfigure(0, weight=1)

    def _primary(self, parent, text, command, **kwargs):
        options = {"fg_color": UI["accent"], "hover_color": UI["accent_hover"], "text_color": "#FFFFFF",
                   "corner_radius": RADIUS["button"], "font": ctk.CTkFont(family="Segoe UI", size=12, weight="bold")}
        options.update(kwargs)
        return ctk.CTkButton(parent, text=text, command=command, **options)

    def _secondary(self, parent, text, command, **kwargs):
        options = {"fg_color": UI["surface"], "hover_color": "#EEF2F6", "text_color": UI["text"],
                   "border_width": 1, "border_color": UI["line_strong"], "corner_radius": RADIUS["button"],
                   "font": ctk.CTkFont(family="Segoe UI", size=12, weight="bold")}
        options.update(kwargs)
        return ctk.CTkButton(parent, text=text, command=command, **options)

    def _ghost(self, parent, text, command, **kwargs):
        options = {"fg_color": "transparent", "hover_color": "#EEF2F6", "text_color": UI["muted"],
                   "corner_radius": RADIUS["button"], "font": ctk.CTkFont(family="Segoe UI", size=11, weight="bold")}
        options.update(kwargs)
        return ctk.CTkButton(parent, text=text, command=command, **options)

    def _styled_dropdown(self, parent, variable, values, command=None, searchable=False):
        # The outer shell provides a soft focus ring; the inner frame owns the
        # uninterrupted 1px control border. Keep the arrow inside that frame.
        shell = ctk.CTkFrame(parent, height=46, fg_color=UI["surface"], corner_radius=10)
        shell.pack_propagate(False)
        control = ctk.CTkFrame(shell, height=42, fg_color=UI["surface"],
                               border_width=1, border_color="#D0D5DD", corner_radius=8)
        control.pack(fill="both", expand=True, padx=2, pady=2)
        control.pack_propagate(False)
        contents = ctk.CTkFrame(control, fg_color=UI["surface"], corner_radius=6)
        contents.pack(fill="both", expand=True, padx=8, pady=2)
        value_label = ctk.CTkLabel(contents, text=variable.get(), anchor="w",
                                   text_color=UI["text"], font=ctk.CTkFont(family="Segoe UI", size=13))
        value_label.pack(side="left", fill="both", expand=True, padx=(3, 4), pady=1)
        arrow = tk.Canvas(contents, width=18, height=18, bg=UI["surface"],
                          highlightthickness=0, bd=0)
        arrow.create_line(4, 6, 9, 11, fill=UI["muted"], width=1.5)
        arrow.create_line(9, 11, 14, 6, fill=UI["muted"], width=1.5)
        arrow.pack(side="right", padx=(4, 3), pady=1)
        state = {"values": list(values), "popup": None, "owner": None}

        def close_popup():
            popup = state.get("popup")
            if popup is not None:
                try:
                    if popup.winfo_exists():
                        owns_grab = popup.grab_current() is popup
                        if owns_grab:
                            popup.grab_release()
                        popup.destroy()
                        owner = state.get("owner")
                        if owns_grab and owner is not None and owner.winfo_exists():
                            owner.grab_set()
                except tk.TclError:
                    pass
                state["popup"] = None
                control.configure(border_color="#D0D5DD")
                shell.configure(fg_color=UI["surface"])

        def choose(value):
            variable.set(value)
            close_popup()
            if command:
                command(value)

        def open_popup(_event=None):
            if state.get("popup") is not None:
                close_popup()
                return "break"
            options = state["values"]
            if not options:
                return "break"
            owner = parent.winfo_toplevel()
            state["owner"] = owner
            popup = ctk.CTkToplevel(owner)
            control.configure(border_color="#D0D5DD")
            shell.configure(fg_color=UI["focus_ring"])
            popup.overrideredirect(True)
            popup.configure(fg_color=UI["surface"])
            popup.transient(owner)
            state["popup"] = popup
            popup_width = max(control.winfo_width(), 250)
            search_height = 58 if searchable else 0
            popup_height = min(312, max(56 + search_height, min(len(options), 6) * 38 + 12 + search_height))
            x = control.winfo_rootx()
            y = control.winfo_rooty() + control.winfo_height() + 4
            screen_w, screen_h = popup.winfo_screenwidth(), popup.winfo_screenheight()
            x = min(max(8, x), screen_w - popup_width - 8)
            if y + popup_height > screen_h - 8:
                y = max(8, control.winfo_rooty() - popup_height - 4)
            popup.geometry(f"{popup_width}x{popup_height}+{x}+{y}")
            popup.grab_set()

            surface = ctk.CTkFrame(popup, fg_color=UI["surface"], corner_radius=10,
                                   border_width=1, border_color=UI["line_strong"])
            surface.pack(fill="both", expand=True)
            if searchable:
                search_shell = ctk.CTkFrame(surface, height=46, fg_color=UI["surface"], corner_radius=10)
                search_shell.pack_propagate(False)
                search_control = ctk.CTkFrame(
                    search_shell, height=42, fg_color=UI["surface"],
                    border_width=1, border_color="#D0D5DD", corner_radius=8)
                search_control.pack(fill="both", expand=True, padx=2, pady=2)
                search_control.pack_propagate(False)
                search_entry = ctk.CTkEntry(
                    search_control, height=34,
                    border_width=0, fg_color=UI["surface"], corner_radius=0,
                    placeholder_text="Tìm nhanh theo tên cột",
                    placeholder_text_color="#98A2B3", text_color=UI["text"],
                    font=ctk.CTkFont(family="Segoe UI", size=12))
                search_entry._entry.configure(selectbackground="#EEF2F6",
                                              selectforeground=UI["text"])
                search_entry.pack(fill="both", expand=True, padx=10, pady=3)
                search_shell.pack(fill="x", padx=10, pady=(8, 4))
                search_entry.bind(
                    "<FocusIn>", lambda _event: search_shell.configure(fg_color=UI["focus_ring"]))
                search_entry.bind(
                    "<FocusOut>", lambda _event: search_shell.configure(fg_color=UI["surface"]))

            options_frame = ctk.CTkScrollableFrame(
                surface, fg_color=UI["surface"], corner_radius=7,
                scrollbar_fg_color="transparent", scrollbar_button_color="#E4E7EC",
                scrollbar_button_hover_color="#AEB8C4", border_width=0)
            options_frame._scrollbar.configure(width=5, corner_radius=3, border_spacing=1)
            options_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4) if searchable else 4)

            def render_options(*_):
                for child in options_frame.winfo_children():
                    child.destroy()
                query = search_entry.get().strip().casefold() if searchable else ""
                matches = [option for option in state["values"] if query in option.casefold()]
                if not matches:
                    ctk.CTkLabel(options_frame, text="Không tìm thấy cột phù hợp.",
                                 text_color=UI["muted"], font=ctk.CTkFont(size=12)
                                 ).pack(anchor="w", padx=8, pady=10)
                    return
                for option in matches:
                    selected = option == variable.get()
                    ctk.CTkButton(
                        options_frame, text=option, anchor="w", height=35,
                        fg_color=UI["accent_soft"] if selected else "transparent",
                        hover_color="#F5F7FA", text_color=UI["text"],
                        corner_radius=7, font=ctk.CTkFont(family="Segoe UI", size=12),
                        command=lambda choice=option: choose(choice)
                    ).pack(fill="x", padx=3, pady=1)

            render_options()
            if searchable:
                search_entry.bind("<KeyRelease>", render_options, add="+")
                search_entry.bind("<<Paste>>", render_options, add="+")
                search_entry.bind("<<Cut>>", render_options, add="+")
                search_entry.bind("<Escape>", lambda _event: close_popup())

            def close_if_focus_left(_event=None):
                def check_focus():
                    if not popup.winfo_exists():
                        return
                    focused = popup.focus_get()
                    try:
                        focus_stays_in_popup = focused is not None and focused.winfo_toplevel() is popup
                    except tk.TclError:
                        focus_stays_in_popup = False
                    if not focus_stays_in_popup:
                        close_popup()
                popup.after(160, check_focus)

            popup.bind("<FocusOut>", close_if_focus_left)
            popup.bind("<Escape>", lambda _event: close_popup())
            popup.lift()
            popup.focus_force()
            if searchable:
                selected_option = next(
                    (child for child in options_frame.winfo_children()
                     if isinstance(child, ctk.CTkButton) and child.cget("text") == variable.get()),
                    None)
                if selected_option is not None:
                    popup.after_idle(selected_option.focus_force)
            return "break"

        for widget in (shell, control, contents, value_label, arrow):
            widget.bind("<Button-1>", open_popup)
        variable.trace_add("write", lambda *_: value_label.configure(text=variable.get()))

        def set_values(new_values):
            state["values"] = list(new_values)
            close_popup()

        shell.set_values = set_values
        return shell

    def _reload_ui(self, _event=None):
        if not self._confirm_leave_email_templates():
            return "break"
        focused = self.focus_get()
        if focused is not None and focused.winfo_toplevel() is not self:
            return "break"
        if getattr(self, "_restarting", False):
            return "break"

        # Re-execute the original Python command so edits on disk are imported.
        # sys.orig_argv preserves launch modes such as `python -m ...`.
        original_args = getattr(sys, "orig_argv", [])[1:]
        command = [sys.executable, *original_args]
        if len(command) == 1:
            command.extend(("-m", "spx_reconciliation_report"))
        try:
            subprocess.Popen(command, cwd=os.getcwd())
        except OSError as exc:
            self._dialog("Không thể tải lại ứng dụng", str(exc), kind="error")
            return "break"

        self._restarting = True
        self._dispose_email_template_page()
        self._dispose_email_page()
        self.destroy()
        return "break"

    def _close_app(self):
        if self._confirm_leave_email_templates():
            self._dispose_email_template_page()
            self._dispose_email_page()
            self.destroy()

    def _dispose_email_template_page(self) -> None:
        page = self.email_template_page
        if page is None:
            return
        try:
            if page.frame.winfo_exists():
                page.dispose()
        except tk.TclError:
            pass
        self.email_template_page = None

    def _dispose_email_page(self) -> None:
        page = self.email_page
        if page is None:
            return
        try:
            if page.frame.winfo_exists():
                page.dispose()
        except tk.TclError:
            pass
        self.email_page = None

    def _dialog(self, title: str, message: str, *, parent=None, confirm: bool = False,
                confirm_text: str = "Continue", kind: str = "info") -> bool:
        owner = parent or self
        dialog = ctk.CTkToplevel(owner)
        self._apply_window_icon(dialog)
        dialog.title(title)
        minimum_height = 340 if confirm else 255
        height = min(590, max(minimum_height, 185 + len(message.splitlines()) * 20))
        width = 590
        dialog.geometry(f"{width}x{height}")
        dialog.resizable(False, False)
        dialog.configure(fg_color=UI["canvas"])
        dialog.transient(owner)
        dialog.grab_set()
        dialog.update_idletasks()
        x = owner.winfo_rootx() + (owner.winfo_width() - width) // 2
        y = owner.winfo_rooty() + (owner.winfo_height() - height) // 2
        dialog.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")

        panel = ctk.CTkFrame(dialog, fg_color=UI["surface"], corner_radius=10,
                             border_width=1, border_color=UI["line"])
        panel.pack(fill="both", expand=True, padx=16, pady=16)
        bar_color = UI["danger"] if kind == "error" else UI["accent"] if kind == "warning" else UI["blue"]
        ctk.CTkFrame(panel, height=4, corner_radius=4, fg_color=bar_color).pack(fill="x", padx=18, pady=(16, 13))
        ctk.CTkLabel(panel, text=title, font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=UI["text"]).pack(anchor="w", padx=20)
        if confirm:
            content = ctk.CTkLabel(panel, text=message, anchor="nw", justify="left",
                                   wraplength=510, text_color=UI["muted"],
                                   font=ctk.CTkFont(size=12))
            content.pack(fill="x", padx=20, pady=(12, 22))
        else:
            content = ctk.CTkTextbox(panel, wrap="word", fg_color=UI["surface"],
                                     text_color=UI["muted"], border_width=0,
                                     font=ctk.CTkFont(size=11), activate_scrollbars=True)
            content.pack(fill="both", expand=True, padx=14, pady=(5, 8))
            content.insert("1.0", message)
            content.configure(state="disabled")

        result = {"confirmed": False}
        actions = ctk.CTkFrame(panel, fg_color="transparent")
        actions.pack(fill="x", padx=18, pady=(0, 14), side="bottom")
        if confirm:
            self._secondary(actions, "Hủy", dialog.destroy, width=90, height=36).pack(side="right", padx=(8, 0))
        def accept():
            result["confirmed"] = True
            dialog.destroy()
        if confirm and kind == "warning":
            ctk.CTkButton(actions, text=confirm_text, command=accept, width=140, height=36,
                          fg_color=UI["danger"], hover_color="#96372F", text_color="#FFFFFF",
                          corner_radius=7, font=ctk.CTkFont(size=12, weight="bold")).pack(side="right")
        else:
            self._primary(actions, confirm_text if confirm else "Đóng", accept,
                          width=120 if confirm else 90, height=36).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        self.wait_window(dialog)
        return result["confirmed"]

    def _apply_window_icon(self, window):
        try:
            window.iconphoto(True, *self.window_icons)
            if self.native_icon_path and self.native_icon_path.exists():
                # Stop CTkToplevel from replacing the app icon after its startup delay.
                window.iconbitmap(default=str(self.native_icon_path))
        except (OSError, tk.TclError):
            pass

    def _toast(self, message: str, kind: str = "success"):
        current = getattr(self, "toast_frame", None)
        if current is not None:
            try:
                current.destroy()
            except tk.TclError:
                pass
        color = UI["success"] if kind == "success" else UI["danger"]
        frame = ctk.CTkFrame(self.main_area, width=390, height=68, fg_color=UI["surface"],
                             border_width=1, border_color=UI["line"], corner_radius=9)
        frame.place(relx=1, rely=1, x=-22, y=-22, anchor="se")
        frame.pack_propagate(False)
        ctk.CTkFrame(frame, width=4, corner_radius=3, fg_color=color).pack(side="left", fill="y", padx=(0, 12), pady=12)
        content = ctk.CTkFrame(frame, fg_color="transparent")
        content.pack(side="left", fill="both", expand=True, pady=11, padx=(0, 10))
        ctk.CTkLabel(content, text="Import thành công" if kind == "success" else "Có lỗi xảy ra",
                     text_color=UI["text"], font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(content, text=message, text_color=UI["muted"], font=ctk.CTkFont(size=11),
                     anchor="w", justify="left", wraplength=335).pack(anchor="w", pady=(2, 0))
        self.toast_frame = frame
        self.after(4500, lambda target=frame: target.destroy() if target.winfo_exists() else None)

    def _clear(self):
        for widget in self.shell.winfo_children():
            widget.pack_forget()

    def _show_page_frame(self, frame) -> None:
        """Keep page widgets alive and switch pages without rebuilding them."""
        for widget in self.shell.winfo_children():
            if widget is not frame:
                widget.pack_forget()
        if frame.winfo_manager() != "pack":
            frame.pack(fill="both", expand=True)

    def _confirm_leave_email_templates(self) -> bool:
        page = self.email_template_page
        if page is None:
            return True
        try:
            if page.frame.winfo_exists() and self._active_page == "email_templates" and page._is_dirty():
                if not page._confirm_discard():
                    return False
                page.cancel_changes()
        except tk.TclError:
            return True
        return True

    def show_email_templates(self):
        if self._active_page == "email_templates":
            return
        if not self._confirm_leave_email_templates():
            return
        if self.email_template_page is not None:
            try:
                if self.email_template_page.frame.winfo_exists():
                    page_frame = self.email_template_page.frame
                else:
                    self.email_template_page = None
                    page_frame = None
            except tk.TclError:
                self.email_template_page = None
                page_frame = None
        else:
            page_frame = None
        self.nav_workspaces.configure(fg_color="transparent", text_color=UI["nav_muted"])
        self.nav_current.configure(fg_color="transparent", text_color=UI["nav_muted"])
        self.nav_email_templates.configure(fg_color=UI["nav_hover"], text_color=UI["nav_text"])
        self.nav_email.configure(fg_color="transparent", text_color=UI["nav_muted"])
        self.nav_new.pack_forget()
        self.breadcrumb.configure(text="SPX  /  Email Template")
        if page_frame is None:
            self.email_template_page = EmailTemplatePage(self)
            page_frame = self.email_template_page.frame
        self._show_page_frame(page_frame)
        self._active_page = "email_templates"

    def show_email(self):
        if self._active_page == "email":
            if self.email_page is not None:
                self.email_page.refresh()
            return
        if not self._confirm_leave_email_templates():
            return
        self.nav_workspaces.configure(fg_color="transparent", text_color=UI["nav_muted"])
        self.nav_current.configure(fg_color="transparent", text_color=UI["nav_muted"])
        self.nav_email_templates.configure(fg_color="transparent", text_color=UI["nav_muted"])
        self.nav_email.configure(fg_color=UI["nav_hover"], text_color=UI["nav_text"])
        self.nav_new.pack_forget()
        self.breadcrumb.configure(text="SPX  /  Gửi Email")
        if self.email_page is None or not self.email_page.frame.winfo_exists():
            self.email_page = EmailPage(self)
        else:
            self.email_page.refresh()
        self._show_page_frame(self.email_page.frame)
        self._active_page = "email"

    def show_workspaces(self):
        if not self._confirm_leave_email_templates():
            return
        if self._active_page == "workspaces":
            return
        self.workspace_id = None
        self.nav_new.pack(fill="x", padx=12, pady=(13, 0), before=self.sidebar_workspace)
        self.nav_workspaces.configure(fg_color=UI["nav_hover"], text_color=UI["nav_text"])
        self.nav_current.configure(fg_color="transparent", text_color=UI["nav_muted"])
        self.nav_email_templates.configure(fg_color="transparent", text_color=UI["nav_muted"])
        self.nav_email.configure(fg_color="transparent", text_color=UI["nav_muted"])
        self.sidebar_workspace_name.configure(text="Chưa chọn workspace")
        self.nav_current.configure(state="disabled", text_color=UI["nav_muted"])
        self.breadcrumb.configure(text="SPX  /  Workspace")
        if self.workspace_home_frame is not None and self.workspace_home_frame.winfo_exists():
            self._show_page_frame(self.workspace_home_frame)
            self._active_page = "workspaces"
            if self._workspace_summary_dirty:
                self._refresh_workspaces()
            return
        self.workspace_home_frame = ctk.CTkFrame(self.shell, fg_color="transparent", corner_radius=0)
        self.workspace_home_frame.pack(fill="both", expand=True)
        top = ctk.CTkFrame(self.workspace_home_frame, fg_color="transparent")
        top.pack(fill="x", pady=(4, 23))
        copy = ctk.CTkFrame(top, fg_color="transparent")
        copy.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(copy, text="QUẢN LÝ DỮ LIỆU", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=UI["accent"]).pack(anchor="w", pady=(0, 5))
        ctk.CTkLabel(copy, text="Workspace", font=ctk.CTkFont(family="Segoe UI", size=27, weight="bold"),
                     text_color=UI["text"]).pack(anchor="w")
        ctk.CTkLabel(copy, text="Quản lý dự án và dữ liệu đối soát được lưu trên thiết bị.",
                     font=ctk.CTkFont(size=12), text_color=UI["muted"]).pack(anchor="w", pady=(4, 0))
        self._primary(top, "+   Tạo workspace", self._create_workspace, width=164, height=40).pack(side="right", anchor="s")

        self.workspace_summary = ctk.CTkFrame(self.workspace_home_frame, width=100, height=132,
                                              fg_color=UI["surface"], corner_radius=RADIUS["card"],
                                              border_width=1, border_color=UI["line"])
        self.workspace_summary.pack(fill="x", pady=(0, 18))
        self.workspace_summary.pack_propagate(False)
        self._workspace_summary_values = ctk.CTkFrame(self.workspace_summary, fg_color="transparent")
        self._workspace_summary_values.pack(fill="both", expand=True, padx=20, pady=10)
        self._workspace_summary_values.pack_propagate(False)

        self.workspace_list = ctk.CTkScrollableFrame(
            self.workspace_home_frame, fg_color="transparent", scrollbar_fg_color="transparent",
            scrollbar_button_color="#E4E7EC", scrollbar_button_hover_color="#AEB8C4")
        self.workspace_list._scrollbar.configure(width=6, corner_radius=4, border_spacing=1)
        self.workspace_list.pack(fill="both", expand=True, padx=(1, 4))
        self._refresh_workspaces()
        self._active_page = "workspaces"

    def _refresh_workspaces(self):
        self.workspaces = {w["id"]: w for w in self.db.list_workspaces()}
        self._workspace_summary_dirty = False
        for widget in self._workspace_summary_values.winfo_children():
            widget.destroy()
        total_records = sum(item["total_records"] for item in self.workspaces.values())
        latest = max((item.get("last_imported_at") or "" for item in self.workspaces.values()), default="")
        stats = (
            ("WORKSPACE", str(len(self.workspaces)), "Đang lưu trên thiết bị"),
            ("TỔNG BẢN GHI", f"{total_records:,}", "Đã import trên tất cả workspace"),
            ("IMPORT GẦN NHẤT", self._format_date(latest) if latest else "Chưa có",
             "Ngày import mới nhất" if latest else "Chưa có lượt import"),
        )
        for index, (label, value, hint) in enumerate(stats):
            cell = ctk.CTkFrame(self._workspace_summary_values, height=110,
                                fg_color="transparent", corner_radius=0,
                                border_width=0)
            cell.pack(side="left", fill="both", expand=True,
                      padx=(0 if index == 0 else 16, 16 if index < 2 else 0))
            cell.pack_propagate(False)
            heading = ctk.CTkFrame(cell, fg_color="transparent", height=36)
            heading.pack(fill="x", pady=(2, 4))
            heading.pack_propagate(False)
            icon = tk.Canvas(heading, width=36, height=36, bg=UI["accent_soft"],
                             highlightthickness=0, bd=0)
            icon.pack(side="left")
            icon_color = UI["accent"]
            if index == 0:  # Workspace folder
                icon.create_line(10, 14, 15, 14, 18, 17, 26, 17,
                                 fill=icon_color, width=2, capstyle="round", joinstyle="round")
                icon.create_line(10, 14, 10, 25, 26, 25, 26, 17,
                                 fill=icon_color, width=2, capstyle="round", joinstyle="round")
            elif index == 1:  # Record table
                icon.create_rectangle(10, 10, 26, 26, outline=icon_color, width=2)
                icon.create_line(10, 15, 26, 15, fill=icon_color, width=1.5)
                icon.create_line(10, 20, 26, 20, fill=icon_color, width=1.5)
                icon.create_line(16, 15, 16, 26, fill=icon_color, width=1.5)
            else:  # Latest import time
                icon.create_oval(10, 10, 26, 26, outline=icon_color, width=2)
                icon.create_line(18, 13, 18, 18, 22, 20,
                                 fill=icon_color, width=2, capstyle="round", joinstyle="round")
            ctk.CTkLabel(heading, text=label, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=UI["muted"]).pack(side="left", anchor="center", padx=(10, 0))
            ctk.CTkLabel(cell, text=value, font=ctk.CTkFont(size=22, weight="bold"),
                         text_color=UI["text"]).pack(anchor="w", pady=(0, 2))
            ctk.CTkLabel(cell, text=hint, font=ctk.CTkFont(size=11),
                         text_color=UI["muted"]).pack(anchor="w")
            if index < len(stats) - 1:
                ctk.CTkFrame(self._workspace_summary_values, width=1,
                             fg_color=UI["line"]).pack(side="left", fill="y", pady=8)
        for widget in self.workspace_list.winfo_children():
            widget.destroy()
        if not self.workspaces:
            empty = ctk.CTkFrame(self.workspace_list, fg_color=UI["surface"], border_width=1,
                                 border_color=UI["line"], corner_radius=10)
            empty.pack(fill="x", pady=5)
            ctk.CTkLabel(empty, text="Chưa có workspace", font=ctk.CTkFont(size=17, weight="bold"),
                         text_color=UI["text"]).pack(anchor="w", padx=24, pady=(25, 5))
            ctk.CTkLabel(empty, text="Tạo workspace để bắt đầu import và xem dữ liệu Main Data.",
                         font=ctk.CTkFont(size=12), text_color=UI["muted"]).pack(anchor="w", padx=24, pady=(0, 18))
            self._primary(empty, "Tạo workspace đầu tiên", self._create_workspace, width=200).pack(anchor="w", padx=24, pady=(0, 24))
            return
        for wid, item in self.workspaces.items():
            card = ctk.CTkFrame(self.workspace_list, fg_color=UI["surface"], border_width=1,
                                border_color=UI["line_strong"], corner_radius=13)
            card.pack(fill="x", padx=(1, 2), pady=(0, 12))
            body = ctk.CTkFrame(card, fg_color="transparent")
            body.pack(fill="x", padx=18, pady=13)
            title_row = ctk.CTkFrame(body, fg_color="transparent")
            title_row.pack(fill="x")
            ctk.CTkLabel(title_row, text=item["name"], font=ctk.CTkFont(size=16, weight="bold"),
                         text_color=UI["text"]).pack(side="left")
            count_badge = ctk.CTkFrame(title_row, fg_color="#F2F4F7", corner_radius=6)
            count_badge.pack(side="right", padx=(10, 0))
            ctk.CTkLabel(count_badge, text=f'{item["total_records"]:,} bản ghi',
                         font=ctk.CTkFont(size=11, weight="bold"), text_color=UI["muted"]
                         ).pack(padx=9, pady=4)
            description = item.get("description") or "Chưa có mô tả"
            ctk.CTkLabel(body, text=description, font=ctk.CTkFont(size=11), text_color=UI["muted"],
                         anchor="w").pack(fill="x", pady=(5, 12))
            separator = ctk.CTkFrame(body, height=1, fg_color=UI["line"])
            separator.pack(fill="x", pady=(0, 10))
            actions = ctk.CTkFrame(body, fg_color="transparent")
            actions.pack(fill="x")
            detail = f'Tạo {self._format_date(item["created_at"])}   ·   Cập nhật {self._format_date(item["updated_at"])}'
            if item.get("last_imported_at"):
                detail += f'   ·   Import gần nhất {self._format_date(item["last_imported_at"])}'
            ctk.CTkLabel(actions, text=detail, font=ctk.CTkFont(size=10), text_color=UI["muted"],
                         anchor="w").pack(side="left", fill="x", expand=True, padx=(0, 12))
            self._ghost(actions, "Đổi tên", lambda current=wid: self._rename_workspace(current), width=72, height=32).pack(side="right", padx=(5, 0))
            self._ghost(actions, "Xóa", lambda current=wid: self._delete_workspace(current), width=62, height=32,
                        text_color=UI["danger"], hover_color="#FCEDEA").pack(side="right", padx=(4, 0))
            self._primary(actions, "Mở workspace   ›", lambda current=wid: self.open_workspace(current),
                          width=148, height=34, corner_radius=8,
                          font=ctk.CTkFont(size=11, weight="bold")).pack(side="right", padx=(0, 7))

    def _workspace_dialog(self, title: str, name: str = "", description: str = ""):
        dialog = ctk.CTkToplevel(self)
        self._apply_window_icon(dialog)
        dialog.title(title)
        width = max(360, min(620, self.winfo_screenwidth() - 48, self.winfo_width() - 48))
        height = min(460, self.winfo_screenheight() - 48)
        dialog.geometry(f"{width}x{height}")
        dialog.resizable(False, False)
        dialog.configure(fg_color=UI["canvas"])
        dialog.transient(self)
        dialog.grab_set()
        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - width) // 2
        y = self.winfo_rooty() + (self.winfo_height() - height) // 2
        dialog.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")

        panel = ctk.CTkFrame(dialog, fg_color=UI["surface"], corner_radius=RADIUS["card"],
                             border_width=1, border_color=UI["line"])
        panel.pack(fill="both", expand=True, padx=1, pady=1)
        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.pack(fill="x", padx=26, pady=(22, 28))
        heading_copy = ctk.CTkFrame(header, fg_color="transparent")
        heading_copy.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(heading_copy, text=title, font=ctk.CTkFont(family="Segoe UI", size=23, weight="bold"),
                     text_color=UI["text"]).pack(anchor="w")
        ctk.CTkLabel(heading_copy, text="Đặt tên để nhận biết và thêm mô tả nếu cần.",
                     font=ctk.CTkFont(size=13), text_color=UI["muted"]
                     ).pack(anchor="w", pady=(6, 0))
        fields = ctk.CTkFrame(panel, fg_color="transparent")
        fields.pack(fill="x", padx=26)
        ctk.CTkLabel(fields, text="TÊN WORKSPACE", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#475467").pack(anchor="w", pady=(0, 8))
        name_entry = ctk.CTkEntry(fields, height=44, border_width=1, border_color=UI["line_strong"],
                                  corner_radius=RADIUS["control"], fg_color=UI["surface"],
                                  placeholder_text="Ví dụ: SPX tháng 10",
                                  font=ctk.CTkFont(size=14))
        name_entry.pack(fill="x")
        name_entry.insert(0, name)
        name_entry.bind("<FocusIn>", lambda _event: name_entry.configure(border_color=UI["accent"]))
        name_entry.bind("<FocusOut>", lambda _event: name_entry.configure(border_color=UI["line_strong"]))
        ctk.CTkLabel(fields, text="MÔ TẢ", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#475467").pack(anchor="w", pady=(24, 8))
        desc_entry = ctk.CTkTextbox(fields, height=96, border_width=1, border_spacing=12,
                                    border_color=UI["line_strong"],
                                    corner_radius=RADIUS["control"], fg_color=UI["surface"], text_color=UI["text"],
                                    font=ctk.CTkFont(size=14), wrap="word")
        desc_entry.pack(fill="x")
        if description:
            desc_entry.insert("1.0", description)
        desc_entry.bind("<FocusIn>", lambda _event: desc_entry.configure(border_color=UI["accent"]))
        desc_entry.bind("<FocusOut>", lambda _event: desc_entry.configure(border_color=UI["line_strong"]))
        result = {}

        def submit():
            value = name_entry.get().strip()
            if not value:
                self._dialog("Thiếu tên workspace", "Vui lòng nhập tên workspace trước khi lưu.",
                             parent=dialog, kind="error")
                name_entry.focus_set()
                return
            result.update(name=value, description=desc_entry.get("1.0", "end").strip())
            dialog.destroy()

        buttons = ctk.CTkFrame(panel, fg_color="transparent")
        buttons.pack(side="bottom", fill="x", padx=26, pady=(30, 22))
        button_row = ctk.CTkFrame(buttons, fg_color="transparent")
        button_row.pack(fill="x")
        self._primary(button_row, "Lưu workspace", submit, width=164, height=42,
                      corner_radius=8, font=ctk.CTkFont(size=13, weight="bold")
                      ).pack(side="right", padx=(12, 0))
        self._secondary(button_row, "Hủy", dialog.destroy, width=108, height=42,
                        corner_radius=RADIUS["button"], border_color=UI["line_strong"],
                        font=ctk.CTkFont(size=13, weight="bold")).pack(side="right")
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        name_entry.bind("<Return>", lambda _event: submit())
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        name_entry.focus_set()
        self.wait_window(dialog)
        return result or None

    def _create_workspace(self):
        result = self._workspace_dialog("Tạo workspace")
        if result:
            self.db.create_workspace(**result)
            list_is_visible = False
            try:
                list_is_visible = hasattr(self, "workspace_list") and bool(self.workspace_list.winfo_exists())
            except tk.TclError:
                pass
            if list_is_visible:
                self._refresh_workspaces()
            else:
                self.show_workspaces()

    def _rename_workspace(self, wid: str):
        item = self.workspaces[wid]
        result = self._workspace_dialog("Đổi tên workspace", item["name"], item.get("description") or "")
        if result:
            self.db.rename_workspace(wid, **result)
            self._refresh_workspaces()

    def _delete_workspace(self, wid: str):
        item = self.workspaces[wid]
        if not self._dialog("Xóa workspace", f'Bạn có chắc muốn xóa "{item["name"]}" cùng toàn bộ dữ liệu import?\n\nThao tác này không thể hoàn tác.', confirm=True, confirm_text="Xóa workspace", kind="warning"):
            return
        self.db.delete_workspace(wid)
        shutil.rmtree(self.root_dir / "imports" / wid, ignore_errors=True)
        self._refresh_workspaces()

    def open_workspace(self, wid: str):
        if not self._confirm_leave_email_templates():
            return
        same_data_page = (self._data_page_workspace_id == wid and self.data_page_frame is not None
                          and self.data_page_frame.winfo_exists())
        if same_data_page and self._active_page == "data":
            return
        self.workspace_id = wid
        self.nav_new.pack(fill="x", padx=12, pady=(13, 0), before=self.sidebar_workspace)
        if not same_data_page:
            self.settings = self.db.get_settings(wid)
            self.page, self.search_text = 0, ""
            self.search_var.set("")
            self.sort_field = None
        item = self.workspaces.get(wid, {})
        self.sidebar_workspace_name.configure(text=item.get("name", "Workspace"))
        self.nav_workspaces.configure(fg_color="transparent", text_color=UI["nav_muted"])
        self.nav_current.configure(fg_color=UI["nav_hover"])
        self.nav_email_templates.configure(fg_color="transparent", text_color=UI["nav_muted"])
        self.nav_email.configure(fg_color="transparent", text_color=UI["nav_muted"])
        self.nav_current.configure(state="normal", text_color=UI["nav_text"],
                                   command=lambda current=wid: self.open_workspace(current))
        self.breadcrumb.configure(text=f'SPX  /  Workspace  /  {item.get("name", "Workspace")}')
        if same_data_page:
            self._show_page_frame(self.data_page_frame)
            if self._page_loading:
                self._load_page()
        else:
            self._build_workspace()
            self._load_page()
        self._active_page = "data"

    def _build_workspace(self):
        if self.data_page_frame is None or not self.data_page_frame.winfo_exists():
            self.data_page_frame = ctk.CTkFrame(self.shell, fg_color="transparent", corner_radius=0)
        else:
            for widget in self.data_page_frame.winfo_children():
                widget.destroy()
        self._data_page_workspace_id = self.workspace_id
        self._show_page_frame(self.data_page_frame)
        item = self.workspaces.get(self.workspace_id, {})
        header = ctk.CTkFrame(self.data_page_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, 16))
        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(title_box, text=item.get("name", "Workspace"),
                     font=ctk.CTkFont(family="Segoe UI", size=27, weight="bold"),
                     text_color=UI["text"]).pack(anchor="w")
        metadata = item.get("description") or "Bản ghi Main Data và lịch sử import"
        self.record_label = ctk.CTkLabel(title_box, text=metadata, text_color=UI["muted"],
                                         font=ctk.CTkFont(size=13))
        self.record_label.pack(anchor="w", pady=(3, 0))
        self.import_button = self._primary(header, "+   Import Excel", self._select_file,
                                           width=148, height=42, corner_radius=8)
        self.import_button.pack(side="right", anchor="s")

        table_wrap = ctk.CTkFrame(self.data_page_frame, fg_color=UI["surface"], corner_radius=10,
                                  border_width=1, border_color=UI["line"])
        table_wrap.pack(fill="both", expand=True)
        self.table_wrap = table_wrap
        controls = ctk.CTkFrame(table_wrap, fg_color="transparent")
        controls.pack(fill="x", padx=14, pady=(12, 8))
        search_box = ctk.CTkFrame(controls, width=320, height=40, fg_color=UI["surface"],
                                  border_width=1, border_color=UI["line"], corner_radius=8)
        search_box.pack(side="left", padx=(0, 8)); search_box.pack_propagate(False)
        search_icon = tk.Canvas(search_box, width=16, height=16, bg=UI["surface"],
                                highlightthickness=0, bd=0)
        search_icon.create_oval(2, 2, 10, 10, outline=UI["muted"], width=1.5)
        search_icon.create_line(9, 9, 14, 14, fill=UI["muted"], width=1.5, capstyle="round")
        search_icon.pack(side="left", padx=(11, 7))
        self.search_entry = ctk.CTkEntry(search_box, textvariable=self.search_var,
                                         placeholder_text="Tìm kiếm trong dữ liệu...", height=36,
                                         border_width=0, fg_color=UI["surface"],
                                         text_color=UI["text"], placeholder_text_color="#98A2B3",
                                         font=ctk.CTkFont(size=13))
        self.search_entry.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=1)
        self.search_entry.bind("<FocusIn>", lambda _event: search_box.configure(border_color=UI["accent"]))
        self.search_entry.bind("<FocusOut>", lambda _event: search_box.configure(border_color=UI["line"]))
        self.search_var.trace_add("write", self._schedule_search)
        self.filter_button = self._secondary(controls, "Bộ lọc", self._filter_dialog, width=98,
                                             height=40, corner_radius=8, font=ctk.CTkFont(size=12, weight="bold"))
        self.filter_button.pack(side="left", padx=(0, 8))
        self.columns_button = self._secondary(controls, "Cột dữ liệu", self._columns_dialog, width=120,
                                              height=40, corner_radius=8, font=ctk.CTkFont(size=12, weight="bold"))
        self.columns_button.pack(side="left")
        self.record_count_label = ctk.CTkLabel(controls, text="Đang tải dữ liệu…", text_color=UI["blue"],
                                               font=ctk.CTkFont(size=13, weight="bold"))
        self.record_count_label.pack(side="right", padx=(8, 2))
        self.filter_label = ctk.CTkFrame(table_wrap, fg_color="transparent")

        table_body = ctk.CTkFrame(table_wrap, fg_color="transparent")
        table_body.pack(fill="both", expand=True, padx=(7, 7), pady=(0, 4))
        self.table_body = table_body
        self._badge_widgets = []
        self._badge_refresh_pending = False
        self._update_filter_label()
        self.empty_state = ctk.CTkFrame(self.data_page_frame, fg_color="transparent")
        self.empty_title = ctk.CTkLabel(self.empty_state, text="Chưa có Main Data",
                                        font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"), text_color=UI["text"])
        self.empty_title.pack(pady=(80, 8))
        self.empty_description = ctk.CTkLabel(self.empty_state, text='Import file Excel có sheet "Main Data" để bắt đầu.',
                                              text_color=UI["muted"])
        self.empty_description.pack(pady=(0, 16))
        self.empty_import_button = self._primary(self.empty_state, "Import Excel", self._select_file, width=140, height=38)
        self.empty_import_button.pack()
        self.empty_reset_button = self._secondary(self.empty_state, "Đặt lại bộ lọc", self._reset_search_and_filters,
                                                   width=150, height=38)
        style = ttk.Style()
        style.theme_use("clam")
        style.layout("Workspace.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.configure("Workspace.Treeview", rowheight=42, font=("Segoe UI", 10),
                        background=UI["surface"], fieldbackground=UI["surface"],
                        foreground="#344054", borderwidth=0, padding=0, relief="flat")
        style.configure("Workspace.Treeview.Heading", font=("Segoe UI", 10, "bold"),
                        background="#F8FAFC", foreground="#475467", padding=(14, 13),
                        borderwidth=0, relief="flat")
        style.map("Workspace.Treeview.Heading", background=[("active", "#F1F4F8")],
                  foreground=[("active", UI["text"])])
        style.map("Workspace.Treeview", background=[("selected", UI["accent_soft"])],
                  foreground=[("selected", UI["text"])])
        style.configure("Workspace.Vertical.TScrollbar", gripcount=0, background="#D5DCE5",
                        darkcolor="#D5DCE5", lightcolor="#D5DCE5", troughcolor=UI["surface"],
                        bordercolor=UI["surface"], arrowsize=10, relief="flat")
        style.map("Workspace.Vertical.TScrollbar", background=[("active", "#AEB9C6")])
        self.tree = ttk.Treeview(table_body, show="headings", style="Workspace.Treeview")
        self.tree.grid(row=0, column=0, columnspan=3, sticky="nsew", padx=(1, 0), pady=(4, 0))
        ybar = ctk.CTkScrollbar(table_body, orientation="vertical", command=self._scroll_both,
                                width=8, fg_color="transparent", button_color="#CBD5E1",
                                button_hover_color="#98A2B3")
        xbar = ctk.CTkScrollbar(table_body, orientation="horizontal", command=self._scroll_tree_x,
                                height=8, fg_color="transparent", button_color="#CBD5E1",
                                button_hover_color="#98A2B3")
        ybar.grid(row=0, column=3, sticky="ns", padx=(5, 1), pady=(4, 0))
        xbar.grid(row=1, column=0, columnspan=3, sticky="ew")
        self.ybar = ybar
        self.xbar = xbar
        self.tree.configure(yscrollcommand=self._tree_yview_changed,
                            xscrollcommand=self._tree_xview_changed)
        self.tree.bind("<Motion>", self._tree_hover)
        self.tree.bind("<Leave>", lambda _event: self._tree_hover(None))
        self.tree.bind("<Configure>", lambda _event: self._schedule_badge_refresh())
        self.tree.bind("<ButtonRelease-1>", self._on_data_row_click)
        self.tree.bind("<MouseWheel>", self._sync_mousewheel)
        table_body.grid_rowconfigure(0, weight=1)
        table_body.grid_columnconfigure(0, weight=1)
        table_body.grid_columnconfigure(1, weight=0)
        table_body.grid_columnconfigure(2, weight=0)
        table_body.grid_columnconfigure(3, weight=0)
        ctk.CTkFrame(table_body, height=1, fg_color=UI["line"]).grid(row=2, column=0, columnspan=4, sticky="ew", pady=(5, 0))
        footer = ctk.CTkFrame(table_body, fg_color=UI["surface"], corner_radius=10)
        self.footer = footer
        footer.grid(row=3, column=0, columnspan=4, sticky="ew", padx=(4, 2), pady=(5, 7))
        footer.grid_columnconfigure(0, weight=1)
        self.page_label = ctk.CTkLabel(footer, text="", text_color=UI["muted"], font=ctk.CTkFont(size=11))
        self.page_label.grid(row=0, column=0, sticky="w", padx=(4, 12))
        self.prev_button = self._secondary(footer, "‹  Trước", self._prev_page, width=88, height=34, corner_radius=7)
        self.prev_button.grid(row=0, column=2, padx=(6, 0))
        self.page_number_label = ctk.CTkLabel(footer, text="", text_color=UI["text"], font=ctk.CTkFont(size=11, weight="bold"))
        self.page_number_label.grid(row=0, column=3, padx=10)
        self.next_button = self._secondary(footer, "Sau  ›", self._next_page, width=82, height=34, corner_radius=7)
        self.next_button.grid(row=0, column=4, padx=(0, 4))
        self.progress = ctk.CTkProgressBar(self.data_page_frame, mode="indeterminate", progress_color=UI["accent"],
                                           fg_color="#DFE5EC")
        self.progress_label = ctk.CTkLabel(self.data_page_frame, text="", anchor="w", text_color=UI["muted"],
                                           font=ctk.CTkFont(size=10))

    def _schedule_search(self, *_):
        if self._search_after:
            self.after_cancel(self._search_after)
        self._search_after = self.after(350, self._search_changed)

    def _search_changed(self):
        self.search_text = self.search_var.get()
        self.page = 0
        self._load_page()

    def _load_page(self):
        if not self.workspace_id or not hasattr(self, "tree"):
            return
        self._page_loading = True
        self.request_number += 1
        request_id, wid = self.request_number, self.workspace_id
        self.record_count_label.configure(text="Đang tải…")
        filters, page, search = dict(self.settings.get("filters", {})), self.page, self.search_text
        sort_field, sort_direction = self.sort_field, self.sort_direction
        def worker():
            try:
                count = self.db.row_count(wid, search, filters)
                rows = self.db.get_rows(wid, page, self.PAGE_SIZE, search, filters, sort_field, sort_direction)
                self.jobs.put(("page", request_id, (count, rows)))
            except Exception as exc:
                self.jobs.put(("error", request_id, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _render_page(self, count: int, rows: list[dict]):
        self.total = count
        self.record_count_label.configure(text=f"{count:,} bản ghi")
        self._clear_badges()
        if count == 0:
            self.table_wrap.pack_forget()
            self.empty_state.pack(fill="both", expand=True)
            if self.search_text or self.settings.get("filters"):
                self.empty_title.configure(text="Không tìm thấy bản ghi")
                self.empty_description.configure(text="Thử thay đổi từ khóa hoặc xóa bộ lọc.")
                self.empty_import_button.pack_forget()
                self.empty_reset_button.pack(pady=(0, 8))
            else:
                self.empty_title.configure(text="Chưa có Main Data")
                self.empty_description.configure(text='Import file Excel có sheet "Main Data" để bắt đầu.')
                self.empty_reset_button.pack_forget()
                self.empty_import_button.pack(pady=(0, 8))
        else:
            self.empty_state.pack_forget()
            self.table_wrap.pack(fill="both", expand=True)
        ordered = [field for field in self.settings.get("order", DEFAULT_FIELDS) if field in self.settings.get("visible", DEFAULT_FIELDS)]
        if not ordered:
            ordered = DEFAULT_FIELDS.copy()
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = ["__stt__", *ordered]
        self.tree.heading("__stt__", text="STT", anchor="center")
        self.tree.column("__stt__", width=64, minwidth=64, stretch=False, anchor="center")
        for field in ordered:
            col = COLUMN_BY_FIELD[field]
            marker = "  ↑" if self.sort_field == field and self.sort_direction == "asc" else "  ↓" if self.sort_field == field else ""
            self.tree.heading(field, text=col.label + marker, anchor="w",
                              command=lambda f=field: self._sort(f))
            min_width = COLUMN_WIDTHS.get(field, 100)
            width = max(min_width, int(self.settings.get("widths", {}).get(field, min_width)))
            anchor = "e" if col.kind == "number" else "w"
            self.tree.column(field, width=width, minwidth=min_width, stretch=False, anchor=anchor)
        self.tree.tag_configure("odd", background="#FAFBFC", foreground="#344054")
        self.tree.tag_configure("hover", background="#F3F6F9", foreground=UI["text"])
        self.current_rows = {}

        def display_value(field, row):
            value = row.get(field)
            if value is None or value == "":
                return ""
            if field in BADGE_FIELDS:
                return ""
            return value

        for index, row in enumerate(rows):
            tags = ("odd",) if index % 2 else ()
            row_number = row.get("_stt", self.page * self.PAGE_SIZE + index + 1)
            iid = self.tree.insert("", "end", values=[row_number, *(display_value(f, row) for f in ordered)], tags=tags)
            self.current_rows[iid] = (row, row_number)
        self._schedule_badge_refresh()
        first = self.page * self.PAGE_SIZE + (1 if count else 0)
        last = min((self.page + 1) * self.PAGE_SIZE, count)
        self.page_label.configure(text=f"Hiển thị {first:,}–{last:,} trên {count:,} bản ghi")
        page_count = max(1, (count + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.page_number_label.configure(text=f"{self.page + 1} / {page_count}")
        self.prev_button.configure(state="normal" if self.page else "disabled")
        self.next_button.configure(state="normal" if last < count else "disabled")

    def _sort(self, field: str):
        if self.sort_field != field:
            self.sort_field, self.sort_direction = field, "asc"
        elif self.sort_direction == "asc":
            self.sort_direction = "desc"
        else:
            self.sort_field = None
        self.page = 0
        self._load_page()

    def _tree_hover(self, event):
        source = event.widget if event is not None else self.tree
        item = source.identify_row(event.y) if event is not None else ""
        if item == getattr(self, "_hover_item", ""):
            return
        old = getattr(self, "_hover_item", "")
        if old and self.tree.exists(old):
            self.tree.item(old, tags=tuple(tag for tag in self.tree.item(old, "tags") if tag != "hover"))
        if item:
            tags = tuple(tag for tag in self.tree.item(item, "tags") if tag != "hover") + ("hover",)
            self.tree.item(item, tags=tags)
        self._hover_item = item
        for changed in (old, item):
            if changed:
                self._sync_badge_background(changed)

    def _badge_palette(self, field: str, value: Any):
        normalized = str(value).strip().casefold()
        green = ("#E8F5EE", "#177245")
        blue = ("#EAF2FF", "#315FA8")
        amber = ("#FFF3D9", "#8A5A00")
        red = ("#FDEBE9", "#B42318")
        neutral = ("#EEF2F6", "#475467")
        if field == "dangerous_goods":
            if normalized in {"no", "false", "0", "n", "không", "khong", "none"}:
                return green
            if normalized in {"yes", "true", "1", "y", "có", "co", "dangerous"}:
                return red
            return neutral
        if field == "exception_tag":
            if any(token in normalized for token in ("lost", "damage", "broken", "fail", "exception", "mất", "hỏng")):
                return red
            return amber
        if field == "receive_status":
            if any(token in normalized for token in ("not received", "not complete", "unreceived", "chưa nhận", "chưa hoàn tất")):
                return red
            if any(token in normalized for token in ("complete", "received", "success", "done", "hoàn tất", "đã nhận", "hoàn thành")):
                return green
            if any(token in normalized for token in ("pending", "wait", "process", "transit", "đang", "chờ")):
                return blue
            if any(token in normalized for token in ("fail", "exception", "return", "cancel", "lỗi", "không nhận")):
                return red
            return amber
        return neutral

    @staticmethod
    def _rounded_badge(canvas, x1, y1, x2, y2, radius, color):
        points = [
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        ]
        canvas.create_polygon(points, smooth=True, splinesteps=12,
                              fill=color, outline=color)

    def _row_background(self, tree, iid):
        if iid in tree.selection():
            return UI["accent_soft"]
        tags = tree.item(iid, "tags")
        if "hover" in tags:
            return "#F3F6F9"
        if "odd" in tags:
            return "#FAFBFC"
        return UI["surface"]

    def _refresh_badges(self):
        self._badge_refresh_pending = False
        self._clear_badges()
        if not hasattr(self, "current_rows") or not self.tree.winfo_exists():
            return
        trees = ((self.tree, list(self.tree["columns"])),)
        for tree, fields in trees:
            if not fields or not tree.winfo_ismapped():
                continue
            for iid in tree.get_children(""):
                record = self.current_rows.get(iid)
                if record is None:
                    continue
                row, _row_number = record
                for field in fields:
                    value = row.get(field)
                    if field not in BADGE_FIELDS or value is None or not str(value).strip():
                        continue
                    if field == "exception_tag" and str(value).strip().casefold() in {
                            "-", "none", "no exception", "n/a", "na"}:
                        continue
                    bounds = tree.bbox(iid, field)
                    if not bounds:
                        continue
                    x, y, width, height = bounds
                    if width < 42 or height < 18:
                        continue
                    label = str(value).strip()
                    max_chars = max(2, int((width - 34) / 6.5))
                    if len(label) > max_chars:
                        label = label[:max(1, max_chars - 1)].rstrip() + "…"
                    chip_width = min(width - 16, max(38, len(label) * 7 + 20))
                    chip_height = min(24, height - 8)
                    bg, fg = self._badge_palette(field, value)
                    canvas = tk.Canvas(tree, width=width, height=height,
                                       bg=self._row_background(tree, iid),
                                       highlightthickness=0, bd=0, takefocus=0)
                    canvas.place(x=x, y=y)
                    chip_x = 8
                    chip_y = (height - chip_height) // 2
                    self._rounded_badge(canvas, chip_x, chip_y,
                                        chip_x + chip_width, chip_y + chip_height,
                                        min(8, chip_height // 2), bg)
                    canvas.create_text(chip_x + 10, height // 2, text=label,
                                       anchor="w", fill=fg,
                                       font=("Segoe UI", 9, "bold"),
                                       width=max(8, chip_width - 20),
                                       tags=("badge_text",))
                    canvas.bind("<Enter>", lambda _event, current=iid: self._set_tree_hover(current))
                    canvas.bind("<Leave>", lambda _event: self._tree_hover(None))
                    canvas.bind("<MouseWheel>", self._sync_mousewheel)
                    canvas.bind("<ButtonRelease-1>",
                                lambda _event, current_tree=tree, current_iid=iid:
                                self._open_badge_row(current_tree, current_iid))
                    self._badge_widgets.append((canvas, tree, iid))

    def _clear_badges(self):
        for canvas, _tree, _iid in getattr(self, "_badge_widgets", []):
            try:
                if canvas.winfo_exists():
                    canvas.destroy()
            except tk.TclError:
                pass
        self._badge_widgets = []

    def _schedule_badge_refresh(self):
        if getattr(self, "_badge_refresh_pending", False):
            return
        if not hasattr(self, "table_body"):
            return
        self._badge_refresh_pending = True
        self.after_idle(self._refresh_badges)

    def _sync_badge_background(self, iid):
        for canvas, tree, current_iid in getattr(self, "_badge_widgets", []):
            if current_iid == iid and canvas.winfo_exists() and tree.exists(iid):
                canvas.configure(bg=self._row_background(tree, iid))

    def _set_tree_hover(self, iid):
        self._tree_hover_item(iid)

    def _tree_hover_item(self, item):
        old = getattr(self, "_hover_item", "")
        if item == old:
            return
        if old and self.tree.exists(old):
            self.tree.item(old, tags=tuple(tag for tag in self.tree.item(old, "tags") if tag != "hover"))
        if item and self.tree.exists(item):
            tags = tuple(tag for tag in self.tree.item(item, "tags") if tag != "hover") + ("hover",)
            self.tree.item(item, tags=tags)
        self._hover_item = item
        for changed in (old, item):
            if changed:
                self._sync_badge_background(changed)

    def _open_badge_row(self, tree, iid):
        if not tree.exists(iid):
            return
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self._sync_badge_background(iid)
        record = self.current_rows.get(iid)
        if record:
            row, row_number = record
            self._show_row_details(row, row_number)

    def _tree_yview_changed(self, *args):
        if hasattr(self, "ybar"):
            self.ybar.set(*args)
        self._schedule_badge_refresh()

    def _tree_xview_changed(self, *args):
        if hasattr(self, "xbar"):
            self.xbar.set(*args)
        self._schedule_badge_refresh()

    def _scroll_tree_x(self, *args):
        self.tree.xview(*args)
        self._schedule_badge_refresh()

    def _scroll_both(self, *args):
        self.tree.yview(*args)
        self._schedule_badge_refresh()

    def _sync_mousewheel(self, event):
        units = int(-event.delta / 120) if event.delta else 0
        if units:
            self._scroll_both("scroll", units, "units")
        return "break"

    def _save_column_widths(self, event):
        widget = event.widget
        if widget.identify_region(event.x, event.y) != "separator":
            return
        for field in self.tree["columns"]:
            if field != "__stt__":
                self.settings["widths"][field] = self.tree.column(field, "width")
        self.db.save_settings(self.workspace_id, self.settings)
        self._schedule_badge_refresh()

    def _on_data_row_click(self, event):
        widget = event.widget
        region = widget.identify_region(event.x, event.y)
        if region == "separator":
            self._save_column_widths(event)
            return
        if region not in {"cell", "tree"}:
            return
        item = widget.identify_row(event.y)
        record = getattr(self, "current_rows", {}).get(item)
        if record:
            row, row_number = record
            self._show_row_details(row, row_number)

    def _show_row_details(self, row: dict, row_number: int):
        current = getattr(self, "row_detail_dialog", None)
        if current is not None and current.winfo_exists():
            current.lift()
            return

        dialog = ctk.CTkToplevel(self)
        self._apply_window_icon(dialog)
        dialog.title("Chi tiết bản ghi")
        dialog.configure(fg_color=UI["canvas"])
        dialog.transient(self)
        dialog.resizable(True, True)
        width, height = min(820, max(660, self.winfo_width() - 120)), min(720, max(540, self.winfo_height() - 100))
        dialog.geometry(f"{width}x{height}")
        dialog.minsize(600, 480)
        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - width) // 2
        y = self.winfo_rooty() + (self.winfo_height() - height) // 2
        dialog.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")

        panel = ctk.CTkFrame(dialog, fg_color=UI["surface"], corner_radius=RADIUS["card"],
                             border_width=1, border_color=UI["line"])
        panel.pack(fill="both", expand=True, padx=14, pady=14)
        heading = ctk.CTkFrame(panel, fg_color="transparent")
        heading.pack(fill="x", padx=20, pady=(18, 13))
        text_group = ctk.CTkFrame(heading, fg_color="transparent")
        text_group.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(text_group, text="Chi tiết bản ghi", text_color=UI["text"],
                     font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(text_group, text=f"Bản ghi {row_number:,} · đầy đủ thông tin các cột",
                     text_color=UI["muted"], font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(3, 0))
        self._secondary(heading, "Đóng", dialog.destroy, width=78, height=34).pack(side="right", anchor="n")

        divider = ctk.CTkFrame(panel, height=1, fg_color=UI["line"])
        divider.pack(fill="x", padx=20)
        details = ctk.CTkScrollableFrame(panel, fg_color="transparent", corner_radius=0)
        details.pack(fill="both", expand=True, padx=14, pady=(10, 12))
        for column_index in (0, 1):
            details.grid_columnconfigure(column_index, weight=1, uniform="detail")
        for index, column in enumerate(COLUMNS):
            value = row.get(column.field)
            display_value = "—" if value is None or value == "" else str(value)
            cell = ctk.CTkFrame(details, fg_color=UI["surface_alt"], corner_radius=RADIUS["control"],
                                 border_width=1, border_color=UI["line"])
            cell.grid(row=index // 2, column=index % 2, sticky="nsew", padx=5, pady=5)
            ctk.CTkLabel(cell, text=column.label, text_color=UI["muted"], anchor="w",
                         font=ctk.CTkFont(size=10, weight="bold")).pack(fill="x", padx=11, pady=(9, 2))
            ctk.CTkLabel(cell, text=display_value, text_color=UI["text"], anchor="w", justify="left",
                         wraplength=330, font=ctk.CTkFont(size=12)).pack(fill="x", padx=11, pady=(0, 10))

        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.grab_set()
        self.row_detail_dialog = dialog

    def _prev_page(self):
        if self.page:
            self.page -= 1; self._load_page()

    def _next_page(self):
        if (self.page + 1) * self.PAGE_SIZE < self.total:
            self.page += 1; self._load_page()

    def _columns_dialog(self):
        dialog = ctk.CTkToplevel(self)
        self._apply_window_icon(dialog)
        dialog.title("Chọn cột hiển thị")
        width, height = 560, 620
        dialog.geometry(f"{width}x{height}")
        dialog.resizable(False, False)
        dialog.configure(fg_color=UI["canvas"])
        dialog.transient(self)
        dialog.grab_set()
        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - width) // 2
        y = self.winfo_rooty() + (self.winfo_height() - height) // 2
        dialog.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")

        panel = ctk.CTkFrame(dialog, fg_color=UI["surface"], corner_radius=RADIUS["card"],
                             border_width=1, border_color=UI["line"])
        panel.pack(fill="both", expand=True, padx=12, pady=12)
        ctk.CTkLabel(panel, text="Chọn cột hiển thị",
                     font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
                     text_color=UI["text"]).pack(anchor="w", padx=24, pady=(22, 4))
        ctk.CTkLabel(panel, text="Thiết lập được lưu riêng cho workspace này.",
                     font=ctk.CTkFont(family="Segoe UI", size=12), text_color=UI["muted"]
                     ).pack(anchor="w", padx=24, pady=(0, 24))
        variables = {}
        visible = set(self.settings.get("visible", DEFAULT_FIELDS))
        for column in COLUMNS:
            variables[column.field] = tk.BooleanVar(value=column.field in visible)
        search_shell = ctk.CTkFrame(panel, height=46, fg_color=UI["surface"], corner_radius=10)
        search_shell.pack_propagate(False)
        search_box = ctk.CTkEntry(search_shell, height=42,
                                  placeholder_text="Tìm nhanh theo tên cột...",
                                  placeholder_text_color="#98A2B3",
                                  border_width=1, border_color="#D0D5DD", corner_radius=8,
                                  fg_color=UI["surface"], text_color=UI["text"],
                                  font=ctk.CTkFont(family="Segoe UI", size=12))
        search_box._entry.configure(selectbackground="#EEF2F6",
                                    selectforeground=UI["text"])
        search_box.pack(fill="both", expand=True, padx=2, pady=2)
        search_box.bind("<FocusIn>", lambda _event: search_shell.configure(fg_color=UI["focus_ring"]))
        search_box.bind("<FocusOut>", lambda _event: search_shell.configure(fg_color=UI["surface"]))
        search_shell.pack(fill="x", padx=24)

        quick_actions = ctk.CTkFrame(panel, fg_color="transparent")
        quick_actions.pack(fill="x", padx=20, pady=(7, 5))
        frame = ctk.CTkScrollableFrame(
            panel, fg_color=UI["surface"], corner_radius=RADIUS["control"],
            border_width=1, border_color=UI["line"])
        frame.pack(fill="both", expand=True, padx=24, pady=(0, 12))

        def render_options(*_):
            for widget in frame.winfo_children():
                widget.destroy()
            query = search_box.get().strip().casefold()
            matches = [column for column in COLUMNS if query in column.label.casefold()]
            for column in matches:
                ctk.CTkCheckBox(frame, text=column.label, variable=variables[column.field],
                                text_color=UI["text"], fg_color=UI["accent"],
                                hover_color=UI["accent_hover"], border_color=UI["line_strong"],
                                checkmark_color="#FFFFFF", checkbox_width=18, checkbox_height=18,
                                border_width=1, corner_radius=5,
                                font=ctk.CTkFont(family="Segoe UI", size=12)
                                ).pack(anchor="w", padx=12, pady=5)
            if not matches:
                ctk.CTkLabel(frame, text="Không tìm thấy cột phù hợp.",
                             text_color=UI["muted"], font=ctk.CTkFont(family="Segoe UI", size=12)
                             ).pack(anchor="w", padx=12, pady=12)
        search_box.bind("<KeyRelease>", render_options, add="+")
        search_box.bind("<<Paste>>", render_options, add="+")
        search_box.bind("<<Cut>>", render_options, add="+")
        render_options()

        def set_columns(fields):
            chosen = set(fields)
            for field, var in variables.items():
                var.set(field in chosen)

        self._ghost(quick_actions, "Hiện tất cả", lambda: set_columns(DEFAULT_FIELDS),
                    height=30).pack(side="left")
        self._ghost(quick_actions, "Ẩn tất cả", lambda: set_columns([DEFAULT_FIELDS[0]]),
                    height=30).pack(side="left", padx=(5, 0))
        self._ghost(quick_actions, "Mặc định", lambda: set_columns(DEFAULT_FIELDS),
                    height=30).pack(side="right")

        def save():
            chosen = [field for field in self.settings.get("order", DEFAULT_FIELDS) if variables[field].get()]
            self.settings["visible"] = chosen or [DEFAULT_FIELDS[0]]
            self.db.save_settings(self.workspace_id, self.settings)
            dialog.destroy(); self._load_page()

        ctk.CTkFrame(panel, height=1, fg_color=UI["line"]).pack(
            side="bottom", fill="x", padx=24, pady=(0, 14))
        actions = ctk.CTkFrame(panel, fg_color="transparent")
        actions.pack(side="bottom", fill="x", padx=24, pady=(0, 18))
        self._secondary(actions, "Hủy", dialog.destroy, width=100, height=40,
                        corner_radius=RADIUS["button"]).pack(side="right", padx=(10, 0))
        self._primary(actions, "Lưu thiết lập", save, width=140, height=40,
                      corner_radius=RADIUS["button"]).pack(side="right")
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)

    def _filter_dialog(self):
        dialog = ctk.CTkToplevel(self)
        self._apply_window_icon(dialog)
        dialog.title("Lọc dữ liệu")
        width, height = 560, 620
        dialog.geometry(f"{width}x{height}")
        dialog.resizable(False, False)
        dialog.configure(fg_color=UI["canvas"])
        dialog.transient(self)
        dialog.grab_set()
        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - width) // 2
        y = self.winfo_rooty() + (self.winfo_height() - height) // 2
        dialog.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")

        panel = ctk.CTkFrame(dialog, fg_color=UI["surface"], corner_radius=RADIUS["card"],
                             border_width=1, border_color=UI["line"])
        panel.pack(fill="both", expand=True, padx=12, pady=12)
        ctk.CTkLabel(panel, text="Lọc dữ liệu", font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
                     text_color=UI["text"]).pack(anchor="w", padx=24, pady=(22, 4))
        ctk.CTkLabel(panel, text="Bộ lọc áp dụng trên toàn bộ dữ liệu workspace.",
                     font=ctk.CTkFont(family="Segoe UI", size=12), text_color=UI["muted"]
                     ).pack(anchor="w", padx=24, pady=(0, 24))
        ctk.CTkLabel(panel, text="CỘT DỮ LIỆU", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=UI["muted"]).pack(anchor="w", padx=24, pady=(0, 7))
        labels = [c.label for c in COLUMNS]
        field_var = tk.StringVar(value=labels[0])
        field_dropdown = self._styled_dropdown(panel, field_var, labels,
                                               command=lambda _value: refresh_values(), searchable=True)
        field_dropdown.pack(fill="x", padx=24)
        ctk.CTkLabel(panel, text="ĐIỀU KIỆN", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=UI["muted"]).pack(anchor="w", padx=24, pady=(17, 7))
        op_var = tk.StringVar(value=FILTER_OPERATORS["contains"])
        op_dropdown = self._styled_dropdown(
            panel, op_var,
            [FILTER_OPERATORS[key] for key in
             ("contains", "equals", "starts", "ends", ">", ">=", "<", "<=", "between")])
        op_dropdown.pack(fill="x", padx=24)
        ctk.CTkLabel(panel, text="GIÁ TRỊ", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=UI["muted"]).pack(anchor="w", padx=24, pady=(17, 7))
        value_shell = ctk.CTkFrame(panel, height=46, fg_color=UI["surface"], corner_radius=10)
        value_shell.pack_propagate(False)
        value_entry = ctk.CTkEntry(value_shell, height=42, border_width=1, border_color="#D0D5DD",
                                   fg_color=UI["surface"], corner_radius=8,
                                   font=ctk.CTkFont(family="Segoe UI", size=13),
                                   placeholder_text="Nhập giá trị cần lọc")
        value_entry.pack(fill="both", expand=True, padx=2, pady=2)
        value_entry.bind("<FocusIn>", lambda _event: value_shell.configure(fg_color=UI["focus_ring"]))
        value_entry.bind("<FocusOut>", lambda _event: value_shell.configure(fg_color=UI["surface"]))

        category_shell = ctk.CTkFrame(panel, height=164, fg_color=UI["surface"], corner_radius=10)
        category_frame = ctk.CTkFrame(category_shell, fg_color=UI["surface"], corner_radius=8,
                                      border_width=1, border_color="#D0D5DD")
        category_frame.pack(fill="both", expand=True, padx=2, pady=2)
        category_list = tk.Listbox(category_frame, selectmode="multiple", height=6, exportselection=False,
                                   font=("Segoe UI", 11), bg=UI["surface"], fg=UI["text"],
                                   selectbackground="#FCE4DA", selectforeground=UI["text"],
                                   highlightthickness=0, relief="flat", borderwidth=0,
                                   activestyle="none", selectborderwidth=0, yscrollcommand=None)
        category_scroll = ttk.Scrollbar(category_frame, orient="vertical", command=category_list.yview,
                                        style="Workspace.Vertical.TScrollbar")
        category_list.configure(yscrollcommand=category_scroll.set)
        category_list.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=5)
        category_scroll.pack(side="right", fill="y", padx=(0, 5), pady=5)
        category_list.bind("<FocusIn>", lambda _event: category_shell.configure(fg_color=UI["focus_ring"]))
        category_list.bind("<FocusOut>", lambda _event: category_shell.configure(fg_color=UI["surface"]))
        def refresh_values():
            column = next(c for c in COLUMNS if c.label == field_var.get())
            if column.field in CATEGORY_FIELDS:
                values = self.db.distinct_values(self.workspace_id, column.field)
                category_list.delete(0, "end")
                for value in values:
                    category_list.insert("end", value)
                value_shell.pack_forget()
                category_shell.pack(fill="x", padx=24, pady=(0, 2))
                op_dropdown.set_values([FILTER_OPERATORS["equals"], FILTER_OPERATORS["contains"], FILTER_OPERATORS["in"]])
                op_var.set(FILTER_OPERATORS["equals"])
            else:
                category_shell.pack_forget()
                value_shell.pack(fill="x", padx=24)
                if column.kind == "number":
                    keys = ("equals", ">", ">=", "<", "<=", "between")
                    op_dropdown.set_values([FILTER_OPERATORS[key] for key in keys])
                elif column.kind == "date":
                    keys = ("equals", ">=", "<=", "between")
                    op_dropdown.set_values([FILTER_OPERATORS[key] for key in keys])
                else:
                    keys = ("contains", "equals", "starts", "ends")
                    op_dropdown.set_values([FILTER_OPERATORS[key] for key in keys])
                op_var.set(FILTER_OPERATORS["contains" if column.kind == "text" else "equals"])
        value_shell.pack(fill="x", padx=24)
        refresh_values()
        def add():
            column = next(c for c in COLUMNS if c.label == field_var.get())
            op = FILTER_OPERATOR_KEYS[op_var.get()]
            if column.field in CATEGORY_FIELDS:
                selected_values = [category_list.get(i) for i in category_list.curselection()]
                if not selected_values:
                    self._dialog("Bộ lọc", "Chọn ít nhất một giá trị.", parent=dialog, kind="error"); return
                if op == "in":
                    value, op = selected_values, "in"
                elif len(selected_values) == 1:
                    value = selected_values[0]
                else:
                    self._dialog("Bộ lọc", "Với equals/contains, hãy chọn đúng một giá trị.", parent=dialog, kind="error"); return
            else:
                value: Any = value_entry.get().strip()
            if not value:
                return
            if op == "between":
                pieces = [x.strip() for x in value.split(",", 1)]
                if len(pieces) != 2 or not all(pieces):
                    self._dialog("Bộ lọc", "Nhập hai giá trị, cách nhau bởi dấu phẩy.", parent=dialog, kind="error"); return
                value = pieces
            elif column.kind == "number" and op in {"equals", ">", ">=", "<", "<="}:
                try: value = float(value)
                except ValueError:
                    self._dialog("Bộ lọc", "Giá trị phải là số.", parent=dialog, kind="error"); return
            self.settings.setdefault("filters", {})[column.field] = {"op": op, "value": value}
            self.db.save_settings(self.workspace_id, self.settings)
            dialog.destroy(); self.page = 0; self._update_filter_label(); self._load_page()
        ctk.CTkFrame(panel, height=1, fg_color=UI["line"]).pack(side="bottom", fill="x", padx=24, pady=(0, 14))
        actions = ctk.CTkFrame(panel, fg_color="transparent")
        actions.pack(side="bottom", fill="x", padx=24, pady=(0, 18))
        self._secondary(actions, "Hủy", dialog.destroy, width=100, height=40,
                        corner_radius=RADIUS["button"]).pack(side="right", padx=(10, 0))
        self._primary(actions, "Áp dụng", add, width=130, height=40,
                      corner_radius=RADIUS["button"]).pack(side="right")
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)

    def _clear_filters(self):
        self.settings["filters"] = {}
        self.db.save_settings(self.workspace_id, self.settings)
        self.page = 0; self._update_filter_label(); self._load_page()

    def _reset_search_and_filters(self):
        if self._search_after:
            self.after_cancel(self._search_after)
            self._search_after = None
        self.settings["filters"] = {}
        self.db.save_settings(self.workspace_id, self.settings)
        self.search_var.set("")
        self.search_text = ""
        self.page = 0
        self._update_filter_label()
        self._load_page()

    def _update_filter_label(self):
        for widget in self.filter_label.winfo_children():
            widget.destroy()
        filters = self.settings.get("filters", {})
        if not filters:
            self.filter_label.pack_forget()
            return
        if not self.filter_label.winfo_manager():
            self.filter_label.pack(fill="x", padx=14, pady=(0, 8), before=self.table_body)
        ctk.CTkLabel(self.filter_label, text="Đang lọc:", text_color=UI["muted"],
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 6))
        for field, rule in filters.items():
            if field not in COLUMN_BY_FIELD:
                continue
            title = f'{COLUMN_BY_FIELD[field].label}: {rule.get("value")}  ×'
            ctk.CTkButton(self.filter_label, text=title, height=26, width=10, fg_color="#F1F4F8",
                          text_color="#475467", hover_color="#E8EDF3", corner_radius=6,
                          font=ctk.CTkFont(size=10),
                          command=lambda current=field: self._remove_filter(current)).pack(side="left", padx=3)
        if filters:
            self._ghost(self.filter_label, "Xóa bộ lọc", self._clear_filters, height=26, width=88).pack(side="left", padx=(5, 0))

    def _remove_filter(self, field: str):
        self.settings.get("filters", {}).pop(field, None)
        self.db.save_settings(self.workspace_id, self.settings)
        self.page = 0
        self._update_filter_label()
        self._load_page()

    def _select_file(self):
        filename = filedialog.askopenfilename(title="Chọn file Excel", filetypes=[("Tệp Excel", "*.xlsx *.xls"), ("Tất cả tệp", "*.*")])
        if not filename:
            return
        self.import_button.configure(state="disabled")
        self.nav_workspaces.configure(state="disabled")
        self.nav_current.configure(state="disabled")
        self.nav_email_templates.configure(state="disabled")
        self.nav_email.configure(state="disabled")
        self.nav_new.configure(state="disabled")
        self.progress.pack(fill="x", pady=(4, 0)); self.progress.start()
        def worker():
            try:
                preview = preview_workbook(filename)
                self.jobs.put(("preview", self.request_number, preview))
            except Exception as exc:
                self.jobs.put(("import_error", self.request_number, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _show_preview(self, preview):
        self._stop_progress()
        message = [f"Tệp: {preview.path.name}", f"Sheet: {preview.sheet_name}", f"Số dòng phát hiện: {preview.row_count:,}",
                   f"Số cột: {len(preview.original_headers)} / {len(COLUMNS)}"]
        if preview.missing_columns:
            message += ["", "Cột còn thiếu (giá trị sẽ để trống):", "• " + "\n• ".join(preview.missing_columns)]
        if preview.unexpected_columns:
            message += ["", "Cột không sử dụng:", "• " + "\n• ".join(preview.unexpected_columns)]
        if preview.row_count == 0:
            message += ["", "Sheet không có dòng dữ liệu để import."]
            self._dialog("Xem trước import", "\n".join(message))
            self.import_button.configure(state="normal"); return
        if not self._dialog("Xem trước dữ liệu Main Data", "\n".join(message) + "\n\nBạn muốn import dữ liệu này?", confirm=True, confirm_text="Import dữ liệu"):
            self.import_button.configure(state="normal"); return
        self.progress.pack(fill="x", pady=(4, 0)); self.progress.start()
        self.import_button.configure(state="disabled")
        self.nav_workspaces.configure(state="disabled")
        self.nav_current.configure(state="disabled")
        self.nav_email_templates.configure(state="disabled")
        self.nav_email.configure(state="disabled")
        self.nav_new.configure(state="disabled")
        self.progress_label.configure(text="Đang đọc và import dữ liệu Excel…")
        self.progress_label.pack(fill="x", pady=(4, 0))
        source = preview.path
        workspace_id = self.workspace_id
        warning_count = [0]
        def warn(amount): warning_count.__setitem__(0, warning_count[0] + amount)
        def worker():
            try:
                import_id, count = self.db.import_rows(workspace_id, source.name, None, preview.sheet_name,
                                                       iter_import_rows(source, warn),
                                                       lambda value: self.jobs.put(("progress", self.request_number, (value, preview.row_count))))
                stored_path = None
                try:
                    target_dir = self.root_dir / "imports" / workspace_id
                    target_dir.mkdir(parents=True, exist_ok=True)
                    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    target = target_dir / f"{stamp}_{source.name}"
                    counter = 1
                    while target.exists():
                        target = target_dir / f"{stamp}_{counter}_{source.name}"; counter += 1
                    shutil.copy2(source, target)
                    stored_path = str(target)
                    self.db.set_import_source(import_id, stored_path)
                except Exception:
                    pass
                self.jobs.put(("import_done", self.request_number, (count, warning_count[0], stored_path)))
            except Exception as exc:
                self.jobs.put(("import_error", self.request_number, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _stop_progress(self):
        try:
            if self.progress.winfo_exists():
                self.progress.stop(); self.progress.pack_forget()
            if self.progress_label.winfo_exists():
                self.progress_label.pack_forget()
        except tk.TclError:
            pass
        self.nav_workspaces.configure(state="normal")
        self.nav_email_templates.configure(state="normal")
        self.nav_email.configure(state="normal")
        self.nav_new.configure(state="normal")
        if self.workspace_id:
            self.nav_current.configure(state="normal")
        if hasattr(self, "import_button") and self.import_button.winfo_exists():
            self.import_button.configure(state="normal")

    def _poll_jobs(self):
        try:
            while True:
                kind, request_id, value = self.jobs.get_nowait()
                if kind.startswith("email_"):
                    if self.email_page is not None:
                        self.email_page.handle_job(kind, value)
                    continue
                if kind in {"page", "error"} and request_id != self.request_number:
                    continue
                if kind == "page" and self.workspace_id:
                    self._page_loading = False
                    self._render_page(*value)
                elif kind == "error":
                    self._page_loading = False
                    self.record_count_label.configure(text="Lỗi tải dữ liệu")
                    self._dialog("Lỗi cơ sở dữ liệu", value, kind="error")
                elif kind == "preview":
                    self._show_preview(value)
                elif kind == "progress":
                    current, expected = value
                    self.progress_label.configure(text=f"Đang import {current:,} / {expected:,} dòng…")
                elif kind == "import_done":
                    self._stop_progress()
                    count, warnings, stored_path = value
                    self.workspaces = {w["id"]: w for w in self.db.list_workspaces()}
                    self._workspace_summary_dirty = True
                    self._load_page()
                    if not stored_path:
                        self._dialog("Import hoàn tất",
                                     f"Đã nhập {count:,} bản ghi vào SQLite nhưng không sao chép được tệp Excel gốc.\n\nÔ dữ liệu không hợp lệ: {warnings}",
                                     kind="warning")
                    else:
                        self._toast(f"Đã thêm {count:,} bản ghi. Ô dữ liệu không hợp lệ: {warnings}.")
                elif kind == "import_error":
                    self._stop_progress()
                    self._dialog("Import thất bại", value, kind="error")
        except queue.Empty:
            pass
        self.after(100, self._poll_jobs)

    @staticmethod
    def _format_date(value: str) -> str:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            return value or ""


def main():
    App().mainloop()
