from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QThreadPool, QProcess
from PySide6.QtGui import QIcon, QPixmap, QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox,
    QApplication, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QProgressBar,
    QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from ..columns import COLUMNS, COLUMN_BY_FIELD, DEFAULT_FIELDS
from ..database import Database
from ..excel_import import iter_import_rows, preview_workbook
from .data_page import DataPage
from .email_pages import EmailPage, EmailTemplatePage
from .workspace_page import DeleteWorkspaceDialog, WorkspaceDialog, WorkspacesPage
from .widgets.chevron_combo import ChevronComboBox
from ..workers import FunctionWorker


class FilterComboBox(ChevronComboBox):
    pass


def data_root() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "SPXReconciliation"


class FilterDialog(QDialog):
    OPERATORS = [("Chứa", "contains"), ("Bằng", "equals"), ("Bắt đầu bằng", "starts"),
                 ("Kết thúc bằng", "ends"), ("Lớn hơn", ">"), ("Từ", ">="),
                 ("Nhỏ hơn", "<"), ("Đến", "<="), ("Trong khoảng", "between")]

    def __init__(self, parent, rules):
        super().__init__(parent); self.setWindowTitle("Lọc dữ liệu"); self.setObjectName("filterDialog"); self.setMinimumSize(540, 500); self.resize(580, 540)
        layout = QVBoxLayout(self); layout.setContentsMargins(24, 20, 24, 18); layout.setSpacing(10)
        heading = QLabel("Lọc dữ liệu"); heading.setObjectName("filterHeading")
        subtitle = QLabel("Tạo điều kiện để thu hẹp danh sách bản ghi."); subtitle.setObjectName("filterSubtitle")
        layout.addWidget(heading); layout.addWidget(subtitle)
        rule_header = QHBoxLayout(); rule_header.setContentsMargins(0, 4, 0, 0)
        rule_title = QLabel("ĐIỀU KIỆN ĐANG ÁP DỤNG"); rule_title.setObjectName("filterSectionLabel")
        self.rule_count = QLabel(str(len(rules))); self.rule_count.setObjectName("filterCountBadge")
        rule_header.addWidget(rule_title); rule_header.addStretch(); rule_header.addWidget(self.rule_count)
        layout.addLayout(rule_header)
        self.rule_list = QListWidget(); self.rule_list.setObjectName("filterRuleList")
        self.rule_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        for field, rule in rules.items():
            column = COLUMN_BY_FIELD.get(field)
            if column:
                item = QListWidgetItem(f"{column.label} {rule.get('op')}: {rule.get('value')}")
                item.setData(Qt.ItemDataRole.UserRole, field)
                self.rule_list.addItem(item)
        self.rule_stack = QStackedWidget(); self.rule_stack.setObjectName("filterRuleStack"); self.rule_stack.setFixedHeight(116)
        self.empty_rules = QLabel("Chưa có điều kiện lọc\nThêm điều kiện bên dưới để bắt đầu.")
        self.empty_rules.setObjectName("filterEmptyState"); self.empty_rules.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rule_stack.addWidget(self.empty_rules); self.rule_stack.addWidget(self.rule_list)
        self.rule_stack.setCurrentWidget(self.rule_list if self.rule_list.count() else self.empty_rules)
        layout.addWidget(self.rule_stack)
        form = QFormLayout(); form.setVerticalSpacing(12); form.setHorizontalSpacing(16); self.field = FilterComboBox(); self.field.setObjectName("filterField")
        for column in COLUMNS: self.field.addItem(column.label, column.field)
        self.operator = FilterComboBox(); self.operator.setObjectName("filterOperator")
        for label, key in self.OPERATORS: self.operator.addItem(label, key)
        self.value = QLineEdit(); self.value.setObjectName("filterValue"); self.value.setPlaceholderText("Nhập giá trị")
        self.value2 = QLineEdit(); self.value2.setObjectName("filterValueTo"); self.value2.setPlaceholderText("Giá trị kết thúc"); self.value2.hide()
        value_row = QWidget(); value_layout = QHBoxLayout(value_row); value_layout.setContentsMargins(0, 0, 0, 0); value_layout.setSpacing(8)
        value_layout.addWidget(self.value, 1); value_layout.addWidget(self.value2, 1)
        form.addRow("Cột", self.field); form.addRow("Điều kiện", self.operator); form.addRow("Giá trị", value_row); layout.addLayout(form)
        actions = QHBoxLayout(); actions.setSpacing(10); self.add = QPushButton("Thêm / cập nhật"); self.add.setObjectName("filterAddButton"); self.remove = QPushButton("Xóa chọn"); self.remove.setObjectName("filterRemoveButton")
        actions.addWidget(self.add); actions.addWidget(self.remove); layout.addLayout(actions)
        self.add.clicked.connect(self._add); self.remove.clicked.connect(self._remove)
        self.rule_list.currentItemChanged.connect(self._load_rule)
        self.operator.currentIndexChanged.connect(self._toggle_range)
        self._toggle_range()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        buttons.setObjectName("filterDialogButtons")
        buttons.button(QDialogButtonBox.StandardButton.Apply).setText("Áp dụng")
        buttons.button(QDialogButtonBox.StandardButton.Apply).setProperty("primary", True)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Hủy")
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.rules = {key: dict(value) for key, value in rules.items()}

    def _toggle_range(self, *_args):
        ranged = self.operator.currentData() == "between"
        self.value2.setVisible(ranged)
        self.value.setPlaceholderText("Giá trị bắt đầu" if ranged else "Nhập giá trị")

    def _load_rule(self, item, _previous=None):
        if item is None: return
        field = item.data(Qt.ItemDataRole.UserRole)
        self.field.setCurrentIndex(max(0, self.field.findData(field)))
        rule = self.rules.get(field, {})
        index = self.operator.findData(rule.get("op", "contains"))
        if index >= 0: self.operator.setCurrentIndex(index)
        value = rule.get("value", "")
        if isinstance(value, list):
            self.value.setText(str(value[0]) if value else "")
            self.value2.setText(str(value[1]) if len(value) > 1 else "")
        else:
            self.value.setText(str(value)); self.value2.clear()
        self.add.setText("Cập nhật điều kiện")

    def _add(self):
        field, op, raw = self.field.currentData(), self.operator.currentData(), self.value.text().strip()
        if not raw:
            QMessageBox.warning(self, "Thiếu giá trị", "Vui lòng nhập giá trị lọc.")
            return
        value = raw
        if op == "between":
            upper = self.value2.text().strip()
            if not upper:
                QMessageBox.warning(self, "Thiếu giá trị", "Vui lòng nhập cả giá trị bắt đầu và kết thúc.")
                return
            value = [raw, upper]
        if COLUMN_BY_FIELD[field].kind == "number":
            try:
                bounds = value if isinstance(value, list) else [value]
                value = [float(part.replace(",", "")) for part in bounds]
                value = value if op == "between" else value[0]
            except ValueError:
                QMessageBox.warning(self, "Giá trị không hợp lệ", "Vui lòng nhập giá trị số hợp lệ.")
                return
            if op == "between" and value[0] > value[1]:
                QMessageBox.warning(self, "Khoảng không hợp lệ", "Giá trị bắt đầu phải nhỏ hơn hoặc bằng giá trị kết thúc.")
                return
        self.rules[field] = {"op": op, "value": value}
        for index in range(self.rule_list.count() - 1, -1, -1):
            existing = self.rule_list.item(index)
            if existing.data(Qt.ItemDataRole.UserRole) == field:
                self.rule_list.takeItem(index)
        item = QListWidgetItem(f"{COLUMN_BY_FIELD[field].label} {op}: {value}")
        item.setData(Qt.ItemDataRole.UserRole, field)
        self.rule_list.addItem(item)
        self.rule_count.setText(str(len(self.rules)))
        self.rule_stack.setCurrentWidget(self.rule_list)

    def _remove(self):
        item = self.rule_list.currentItem()
        if not item: return
        field = item.data(Qt.ItemDataRole.UserRole)
        self.rules.pop(field, None)
        self.rule_list.takeItem(self.rule_list.row(item))
        self.add.setText("Thêm / cập nhật")
        self.rule_count.setText(str(len(self.rules)))
        if not self.rule_list.count(): self.rule_stack.setCurrentWidget(self.empty_rules)


class MainWindow(QMainWindow):
    PAGE_SIZE = 100

    def __init__(self):
        super().__init__()
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SPX.ReconciliationReport.Desktop")
            except (AttributeError, OSError):
                pass
        self.setWindowTitle("SPX Reconciliation Report")
        self.resize(1360, 780); self.setMinimumSize(980, 620)
        logo = Path(__file__).parents[1] / "assets" / "logo.png"
        if logo.is_file(): self.setWindowIcon(QIcon(str(logo)))
        qss = Path(__file__).parent / "styles" / "main.qss"
        if qss.is_file(): self.setStyleSheet(qss.read_text(encoding="utf-8"))
        self.root_dir = data_root(); self.db = Database(self.root_dir / "spx_reconciliation.db")
        self.pool = QThreadPool.globalInstance(); self.workspace_id = None; self.workspaces = {}
        self.settings = {}; self.page = 0; self.total = 0; self.search_text = ""; self.filters = {}
        self.selected_record_ids: set[int] = set()
        self.sort_field = None; self.sort_direction = "asc"; self.request_id = 0; self._import_preview = None
        central = QWidget(); layout = QHBoxLayout(central); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        self.setCentralWidget(central)
        sidebar = QWidget(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(236)
        nav = QVBoxLayout(sidebar); nav.setContentsMargins(14, 22, 14, 16)
        brand = QWidget(); brand.setObjectName("brandPanel")
        brand.setMinimumHeight(70)
        brand_layout = QHBoxLayout(brand); brand_layout.setContentsMargins(8, 7, 7, 7); brand_layout.setSpacing(9)
        brand_icon = QLabel(); brand_icon.setObjectName("brandLogo")
        if logo.is_file():
            pixmap = QPixmap(str(logo)).scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation)
            brand_icon.setPixmap(pixmap)
        brand_icon.setFixedSize(50, 50)
        brand_layout.addWidget(brand_icon)
        brand_copy = QVBoxLayout(); brand_copy.setSpacing(0)
        brand_name = QLabel("SP<span style='color:#FF704F'>X</span>")
        brand_name.setObjectName("brandName"); brand_name.setTextFormat(Qt.TextFormat.RichText)
        brand_subtitle = QLabel("RECONCILIATION")
        brand_subtitle.setObjectName("brandSubtitle")
        brand_tagline = QLabel("REPORTING WORKSPACE")
        brand_tagline.setObjectName("brandTagline")
        brand_copy.addWidget(brand_name); brand_copy.addWidget(brand_subtitle); brand_copy.addWidget(brand_tagline)
        brand_layout.addLayout(brand_copy, 1)
        nav.addWidget(brand); nav.addSpacing(27)
        section_label = QLabel("WORKSPACE"); section_label.setObjectName("navSection")
        nav.addWidget(section_label)
        self.nav_workspaces = QPushButton("Workspaces"); self.nav_data = QPushButton("Dữ liệu chính")
        self.nav_templates = QPushButton("Email Template"); self.nav_email = QPushButton("Gửi Email")
        self.nav_new = QPushButton("＋  Tạo workspace"); self.nav_new.setObjectName("newWorkspaceButton")
        for button in (self.nav_workspaces, self.nav_data, self.nav_templates, self.nav_email, self.nav_new):
            button.setProperty("navButton", True)
            nav.addWidget(button)
        nav.addStretch()
        self.sidebar_workspace = QLabel("Chưa chọn workspace")
        self.sidebar_workspace.setObjectName("sidebarWorkspace")
        nav.addWidget(self.sidebar_workspace)
        self.status = QLabel("Lưu trữ cục bộ · SQLite")
        self.status.setObjectName("sidebarStatus"); self.status.setWordWrap(True); nav.addWidget(self.status)
        layout.addWidget(sidebar)
        self.main_area = QWidget(); main_layout = QVBoxLayout(self.main_area)
        main_layout.setContentsMargins(0, 0, 0, 0); main_layout.setSpacing(0)
        topbar = QWidget(); topbar.setObjectName("topbar")
        top_layout = QHBoxLayout(topbar); top_layout.setContentsMargins(28, 12, 28, 12)
        context = QVBoxLayout(); self.breadcrumb = QLabel("SPX  /  Workspaces"); self.breadcrumb.setObjectName("breadcrumb")
        self.page_heading = QLabel("Quản lý workspace"); self.page_heading.setObjectName("pageHeading")
        context.addWidget(self.breadcrumb); context.addWidget(self.page_heading); top_layout.addLayout(context)
        top_layout.addStretch()
        self.top_status = QLabel("●  Sẵn sàng"); self.top_status.setObjectName("readyStatus")
        self.top_status.setProperty("state", "ready"); top_layout.addWidget(self.top_status)
        main_layout.addWidget(topbar)
        self.stack = QStackedWidget(); self.stack.setContentsMargins(26, 22, 26, 24); main_layout.addWidget(self.stack, 1)
        layout.addWidget(self.main_area, 1)
        self.workspace_page = WorkspacesPage(); self.data_page = DataPage()
        self.template_page = EmailTemplatePage(self.db); self.email_page = EmailPage(self.db, self.pool)
        self.email_page.back_requested.connect(self.show_data)
        for page in (self.workspace_page, self.data_page, self.template_page, self.email_page): self.stack.addWidget(page)
        self.nav_workspaces.clicked.connect(self.show_workspaces); self.nav_data.clicked.connect(self.show_data)
        self.nav_templates.clicked.connect(self.show_templates)
        self.nav_email.clicked.connect(self.show_email)
        self.nav_new.clicked.connect(self.create_workspace)
        self.workspace_page.open_requested.connect(self.open_workspace)
        self.workspace_page.create_requested.connect(self.create_workspace)
        self.workspace_page.rename_requested.connect(self.rename_workspace)
        self.workspace_page.delete_requested.connect(self.delete_workspace)
        self.data_page.search_changed.connect(self.schedule_search)
        self.data_page.import_requested.connect(self.select_file)
        self.data_page.filter_requested.connect(self.filter_dialog)
        self.data_page.columns_requested.connect(self.columns_dialog)
        self.data_page.reset_requested.connect(self.reset_filters)
        self.data_page.page_requested.connect(self.change_page)
        self.data_page.row_activated.connect(self.show_row_details)
        self.data_page.selected_ids_changed.connect(self._selection_changed)
        self.data_page.select_all_requested.connect(self._toggle_filtered_selection)
        self.data_page.clear_selection_requested.connect(self._clear_selection)
        self.data_page.send_email_requested.connect(self._start_email_flow)
        header = self.data_page.table.horizontalHeader()
        header.setFirstSectionMovable(False)
        header.sectionClicked.connect(self.sort_by_column)
        header.sectionResized.connect(self.schedule_columns_save)
        header.sectionMoved.connect(self.schedule_columns_save)
        self.search_timer = QTimer(self); self.search_timer.setSingleShot(True); self.search_timer.setInterval(400)
        self.search_timer.timeout.connect(self.apply_search)
        self.columns_timer = QTimer(self); self.columns_timer.setSingleShot(True); self.columns_timer.setInterval(500)
        self.columns_timer.timeout.connect(self.save_column_settings)
        self._restoring_columns = False
        self.reload_shortcut = QShortcut(QKeySequence("Ctrl+Shift+R"), self)
        self.reload_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.reload_shortcut.activated.connect(self._restart_application)
        self.show_workspaces()

    def _restart_application(self):
        if getattr(sys, "frozen", False):
            program = sys.executable
            arguments = sys.argv[1:]
        else:
            program = sys.executable
            arguments = getattr(
                sys, "orig_argv", [sys.executable, "-m", "spx_reconciliation_report"]
            )[1:]

        result = QProcess.startDetached(program, arguments, str(Path.cwd()))
        started = result[0] if isinstance(result, tuple) else result
        if not started:
            QMessageBox.warning(self, "Không thể reload", "Ứng dụng không khởi động lại được.")
            return
        QApplication.quit()

    def show_workspaces(self):
        self.stack.setCurrentWidget(self.workspace_page)
        self._set_page_context("Workspaces", "Quản lý workspace", self.nav_workspaces)
        records = self.db.list_workspaces(); self.workspaces = {row["id"]: row for row in records}
        self.workspace_page.set_workspaces(records)

    def _set_page_context(self, section, title, active_button):
        self.breadcrumb.setText(f"SPX  /  {section}")
        self.page_heading.setText(title)
        for button in (self.nav_workspaces, self.nav_data, self.nav_templates, self.nav_email):
            button.setProperty("active", button is active_button)
            button.style().unpolish(button); button.style().polish(button)

    def _set_top_status(self, text, state="ready"):
        self.top_status.setText(text)
        self.top_status.setProperty("state", state)
        self.top_status.style().unpolish(self.top_status)
        self.top_status.style().polish(self.top_status)

    def show_templates(self):
        self.stack.setCurrentWidget(self.template_page)
        self._set_page_context("Email", "Email Template", self.nav_templates)

    def show_email(self):
        self.email_page.refresh()
        self.email_page.clear_context()
        self.stack.setCurrentWidget(self.email_page)
        self._set_page_context("Email", "Gửi Email", self.nav_email)

    def _workspace_dialog(self, title, record=None):
        dialog = WorkspaceDialog(self, title, (record or {}).get("name", ""), (record or {}).get("description") or "")
        if dialog.exec() != QDialog.DialogCode.Accepted: return None
        name = dialog.name.text().strip()
        if not name:
            QMessageBox.warning(self, "Thiếu tên", "Tên workspace không được để trống."); return None
        return name, dialog.description.toPlainText()

    def create_workspace(self):
        values = self._workspace_dialog("Tạo workspace")
        if values:
            self.workspace_id = self.db.create_workspace(*values); self.show_workspaces(); self.open_workspace(self.workspace_id)

    def rename_workspace(self, wid):
        record = self.workspaces.get(wid)
        values = self._workspace_dialog("Đổi tên workspace", record)
        if values: self.db.rename_workspace(wid, *values); self.show_workspaces()

    def delete_workspace(self, wid):
        record = self.workspaces.get(wid, {})
        dialog = DeleteWorkspaceDialog(self, record.get("name", ""))
        if dialog.exec() != QDialog.DialogCode.Accepted: return
        self.db.delete_workspace(wid)
        shutil.rmtree(self.root_dir / "imports" / wid, ignore_errors=True)
        if self.workspace_id == wid: self.workspace_id = None
        self.show_workspaces()

    def open_workspace(self, wid):
        self._clear_selection()
        self.workspace_id = wid; self.settings = self.db.get_settings(wid); self.page = 0
        record = self.db.list_workspaces()
        item = next((row for row in record if row["id"] == wid), {})
        self.data_page.title.setText(item.get("name", "Workspace"))
        self.data_page.metadata.setText(item.get("description") or "Main Data")
        self.sidebar_workspace.setText(item.get("name", "Workspace đang mở"))
        self.search_timer.stop()
        self.data_page.search.setText(""); self.search_text = ""; self.filters = dict(self.settings.get("filters", {}))
        self.stack.setCurrentWidget(self.data_page); self._set_page_context("Workspace", "Main Data", self.nav_data); self.load_page()

    def show_data(self):
        if self.workspace_id:
            self.stack.setCurrentWidget(self.data_page); self._set_page_context("Workspace", "Main Data", self.nav_data); self.load_page()
        else: self.show_workspaces()

    def schedule_search(self, text):
        self.search_text = text; self.search_timer.start()

    def apply_search(self):
        self.page = 0; self.load_page()

    def reset_filters(self):
        self.filters = {}
        self.search_timer.stop()
        self.data_page.search.clear()
        self.page = 0
        if self.workspace_id:
            self.settings["filters"] = {}
            self.db.save_settings(self.workspace_id, self.settings)
        self.load_page()

    def load_page(self):
        if not self.workspace_id: return
        self.request_id += 1; rid, wid = self.request_id, self.workspace_id
        page, search_text = self.page, self.search_text
        filters = {field: dict(rule) for field, rule in self.filters.items()}
        sort_field, sort_direction = self.sort_field, self.sort_direction
        self.data_page.set_loading(True, "Đang tải dữ liệu")
        self._set_top_status("●  Đang tải", "busy")
        def query():
            total = self.db.row_count(wid, search_text, filters)
            rows = self.db.get_rows(wid, page, self.PAGE_SIZE, search_text, filters, sort_field, sort_direction)
            matching_ids = self.db.get_matching_ids(wid, search_text, filters)
            return rid, page, total, rows, matching_ids
        worker = FunctionWorker(query); worker.signals.result.connect(self._page_loaded)
        worker.signals.error.connect(lambda message, request=rid: self._page_error(request, message))
        worker.signals.finished.connect(lambda request=rid: self._page_finished(request))
        self.pool.start(worker)

    def _page_loaded(self, result):
        rid, page, self.total, rows, matching_ids = result
        if rid != self.request_id: return
        fields = self.settings.get("order", DEFAULT_FIELDS)
        visible = set(self.settings.get("visible", DEFAULT_FIELDS))
        columns = [COLUMN_BY_FIELD[field] for field in fields if field in visible and field in COLUMN_BY_FIELD]
        self._restoring_columns = True
        self.data_page.set_records(columns, rows, self.total, page, self.PAGE_SIZE,
                                   self.settings.get("widths", {}), matching_ids)
        self.data_page.set_selected_ids(self.selected_record_ids)
        self._restoring_columns = False
        filter_text = "Bộ lọc đang áp dụng: " + ", ".join(
            COLUMN_BY_FIELD[f].label for f in self.filters if f in COLUMN_BY_FIELD
        ) if self.filters else ""
        self.data_page.active_filters.setText(filter_text)
        self.data_page.active_filters.setVisible(bool(filter_text))
        self.data_page.set_loading(False)
        self._set_top_status("●  Sẵn sàng", "ready")

    def _show_error(self, message):
        self.data_page.set_loading(False); self._set_top_status("●  Có lỗi", "error")
        QMessageBox.critical(self, "Lỗi", message.splitlines()[0])

    def _page_error(self, request_id, message):
        if request_id == self.request_id: self._show_error(message)

    def _page_finished(self, request_id):
        if request_id == self.request_id:
            self.data_page.set_loading(False)
            self._set_top_status("●  Sẵn sàng", "ready")

    def change_page(self, delta):
        max_page = max(0, (self.total - 1) // self.PAGE_SIZE)
        self.page = min(max_page, max(0, self.page + delta)); self.load_page()

    def sort_by_column(self, index):
        columns = self.data_page.model.columns
        if not 1 <= index <= len(columns): return
        field = columns[index - 1].field
        self.sort_direction = "desc" if self.sort_field == field and self.sort_direction == "asc" else "asc"
        self.sort_field = field; self.page = 0; self.load_page()

    def schedule_columns_save(self, *_args):
        if not self._restoring_columns and self.workspace_id:
            self.columns_timer.start()

    def save_column_settings(self):
        if not self.workspace_id: return
        header = self.data_page.table.horizontalHeader()
        columns = self.data_page.model.columns
        visible_fields = set(self.settings.get("visible", DEFAULT_FIELDS))
        visible_order = [columns[logical - 1].field
                         for visual in range(header.count())
                         if 1 <= (logical := header.logicalIndex(visual)) <= len(columns)
                         and columns[logical - 1].field in visible_fields
                         and not header.isSectionHidden(logical)]
        visible_order.extend(field for field in self.settings.get("order", DEFAULT_FIELDS)
                             if field in visible_fields and field not in visible_order)
        hidden_order = [field for field in self.settings.get("order", DEFAULT_FIELDS)
                        if field not in visible_fields]
        self.settings["order"] = visible_order + hidden_order
        self.settings["widths"] = {column.field: header.sectionSize(index + 1) for index, column in enumerate(columns)}
        self.db.save_settings(self.workspace_id, self.settings)

    def _selection_changed(self, selected_ids):
        self.selected_record_ids = set(selected_ids)
        self.data_page.set_selection_summary(len(self.selected_record_ids))

    def _clear_selection(self):
        self.selected_record_ids.clear()
        self.data_page.set_selected_ids(set())
        self.data_page.set_selection_summary(0)

    def _toggle_filtered_selection(self):
        if not self.workspace_id:
            return
        matching_ids = self.data_page.model.scope_ids
        state = self.data_page.model.headerData(0, Qt.Orientation.Horizontal, Qt.ItemDataRole.CheckStateRole)
        if state == Qt.CheckState.Checked:
            self.selected_record_ids.difference_update(matching_ids)
        else:
            self.selected_record_ids.update(matching_ids)
        self.data_page.set_selected_ids(self.selected_record_ids)
        self._selection_changed(self.selected_record_ids)

    def _start_email_flow(self):
        if not self.selected_record_ids or not self.workspace_id:
            return
        self.save_column_settings()
        visible_fields = set(self.settings.get("visible", DEFAULT_FIELDS))
        visible_columns = [COLUMN_BY_FIELD[field]
                           for field in self.settings.get("order", DEFAULT_FIELDS)
                           if field in visible_fields and field in COLUMN_BY_FIELD]
        workspace = self.workspaces.get(self.workspace_id, {})
        source_parts = [f"Tìm kiếm: {self.search_text}"] if self.search_text else []
        for field, rule in self.filters.items():
            column = COLUMN_BY_FIELD.get(field)
            if not column:
                continue
            value = rule.get("value", "") if isinstance(rule, dict) else ""
            operator = rule.get("op", "") if isinstance(rule, dict) else ""
            rendered_value = ", ".join(str(item) for item in value) if isinstance(value, list) else str(value)
            source_parts.append(f"{column.label} {operator} {rendered_value}".strip())
        source = " · ".join(source_parts) or "Main Data"
        self.email_page.set_context(
            sorted(self.selected_record_ids), self.workspace_id,
            workspace.get("name", "Workspace"), source, visible_columns,
        )
        self.stack.setCurrentWidget(self.email_page)
        self._set_page_context("Email", "Send Email", self.nav_email)

    def filter_dialog(self):
        dialog = FilterDialog(self, self.filters)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.filters = dialog.rules; self.page = 0
            if self.workspace_id:
                self.settings["filters"] = self.filters; self.db.save_settings(self.workspace_id, self.settings)
            self.load_page()

    def columns_dialog(self):
        dialog = QDialog(self)
        dialog.setObjectName("columnsDialog")
        dialog.setWindowTitle("Cột hiển thị")
        dialog.setMinimumSize(560, 460)
        dialog.resize(700, 660)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        heading = QLabel("Tùy chỉnh cột hiển thị")
        heading.setObjectName("columnsHeading")
        subtitle = QLabel("Chọn những cột bạn muốn xem trong bảng dữ liệu.")
        subtitle.setObjectName("columnsSubtitle")
        layout.addWidget(heading)
        layout.addWidget(subtitle)

        toolbar = QHBoxLayout()
        search = QLineEdit()
        search.setObjectName("columnsSearch")
        search.setPlaceholderText("Tìm tên cột…")
        toolbar.addWidget(search, 1)
        selected_label = QLabel()
        selected_label.setObjectName("columnsCount")
        toolbar.addWidget(selected_label)
        layout.addLayout(toolbar)

        checks = {}
        grid_content = QWidget()
        grid_content.setObjectName("columnsGridContent")
        grid = QGridLayout(grid_content)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(3)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        visible = set(self.settings.get("visible", DEFAULT_FIELDS))
        for index, column in enumerate(COLUMNS):
            check = QCheckBox(column.label)
            check.setObjectName("columnVisibilityCheck")
            check.setChecked(column.field in visible)
            checks[column.field] = check
            grid.addWidget(check, index // 2, index % 2)

        scroll = QScrollArea()
        scroll.setObjectName("columnsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(grid_content)
        layout.addWidget(scroll, 1)

        actions = QHBoxLayout()
        select_all = QPushButton("Chọn tất cả")
        clear_all = QPushButton("Bỏ chọn")
        for button in (select_all, clear_all):
            button.setObjectName("columnsQuickAction")
        actions.addWidget(select_all)
        actions.addWidget(clear_all)
        actions.addStretch()
        layout.addLayout(actions)

        def update_count():
            count = sum(check.isChecked() for check in checks.values())
            selected_label.setText(f"{count}/{len(checks)} cột")

        def filter_columns(query):
            query = query.strip().casefold()
            for column in COLUMNS:
                checks[column.field].setVisible(query in column.label.casefold())

        search.textChanged.connect(filter_columns)
        select_all.clicked.connect(lambda: [check.setChecked(True) for check in checks.values()])
        clear_all.clicked.connect(lambda: [check.setChecked(False) for check in checks.values()])
        for check in checks.values():
            check.toggled.connect(update_count)
        update_count()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Lưu")
        buttons.button(QDialogButtonBox.StandardButton.Save).setProperty("primary", True)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Hủy")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            visible = [field for field, check in checks.items() if check.isChecked()]
            if not visible:
                QMessageBox.warning(self, "Chọn cột", "Cần giữ lại ít nhất một cột hiển thị."); return
            self.settings["visible"] = visible
            self.db.save_settings(self.workspace_id, self.settings); self.load_page()

    def show_row_details(self, row_index):
        if not 0 <= row_index < len(self.data_page.model.rows): return
        row = self.data_page.model.rows[row_index]
        dialog = QDialog(self); dialog.setWindowTitle(f"Bản ghi {row.get('_stt', row_index + 1)}"); dialog.resize(620, 650)
        layout = QVBoxLayout(dialog); listing = QListWidget()
        for column in COLUMNS:
            value = row.get(column.field)
            listing.addItem(QListWidgetItem(f"{column.label}: {'' if value is None else value}"))
        layout.addWidget(listing); close = QPushButton("Đóng"); close.clicked.connect(dialog.accept); layout.addWidget(close); dialog.exec()

    def select_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Chọn file Excel", "", "Excel (*.xlsx *.xls)")
        if not filename: return
        self._set_busy(True, "Đang kiểm tra workbook…")
        worker = FunctionWorker(preview_workbook, filename)
        worker.signals.result.connect(self._preview_ready); worker.signals.error.connect(self._import_error)
        self.pool.start(worker)

    def _preview_ready(self, preview):
        self._import_preview = preview
        message = [f"Tệp: {preview.path.name}", f"Sheet: {preview.sheet_name}", f"Số dòng: {preview.row_count:,}", f"Số cột: {len(preview.original_headers)} / {len(COLUMNS)}"]
        if preview.missing_columns: message += ["", "Cột thiếu (được để trống):", "• " + "\n• ".join(preview.missing_columns)]
        if preview.unexpected_columns: message += ["", "Cột không sử dụng:", "• " + "\n• ".join(preview.unexpected_columns)]
        if preview.row_count == 0:
            QMessageBox.information(self, "Xem trước import", "\n".join(message)); self._set_busy(False); return
        if QMessageBox.question(self, "Xem trước import", "\n".join(message) + "\n\nImport dữ liệu này?") != QMessageBox.StandardButton.Yes:
            self._set_busy(False); return
        self._set_busy(True, "Đang import Excel…")
        wid = self.workspace_id
        def import_data():
            warnings = [0]
            import_id, count = self.db.import_rows(wid, preview.path.name, None, preview.sheet_name,
                iter_import_rows(preview.path, lambda amount: warnings.__setitem__(0, warnings[0] + amount)))
            stored_path = None
            try:
                target_dir = self.root_dir / "imports" / wid; target_dir.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                target = target_dir / f"{stamp}_{preview.path.name}"
                suffix = 1
                while target.exists():
                    target = target_dir / f"{stamp}_{suffix}_{preview.path.name}"
                    suffix += 1
                shutil.copy2(preview.path, target)
                stored_path = str(target)
                self.db.set_import_source(import_id, stored_path)
            except OSError:
                pass
            return count, warnings[0], stored_path
        worker = FunctionWorker(import_data); worker.signals.result.connect(self._import_done)
        worker.signals.error.connect(self._import_error)
        self.pool.start(worker)

    def _set_busy(self, busy, message=""):
        self.data_page.set_loading(busy, message); self.status.setText(message or "Dữ liệu SQLite được lưu trên thiết bị.")
        self._set_top_status("●  Đang xử lý" if busy else "●  Sẵn sàng", "busy" if busy else "ready")

    def _import_done(self, result):
        count, warnings, stored_path = result
        self._set_busy(False)
        if not stored_path:
            QMessageBox.warning(self, "Import hoàn tất", f"Đã nhập {count:,} bản ghi nhưng không sao chép được file Excel gốc. Giá trị không hợp lệ: {warnings}.")
        records = self.db.list_workspaces(); self.workspaces = {row["id"]: row for row in records}
        self.workspace_page.set_workspaces(records)
        self.status.setText(f"Đã import {count:,} bản ghi · {warnings} giá trị không hợp lệ.")
        self._set_top_status("●  Đã import", "success")
        QTimer.singleShot(0, self.load_page)

    def _import_error(self, message):
        self._set_busy(False)
        QMessageBox.critical(self, "Import thất bại", message.splitlines()[0])

    def closeEvent(self, event):
        self.email_page.cleanup_attachment()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SPX Reconciliation Report")
    window = MainWindow(); window.show()
    return app.exec()
