from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import re

from PySide6.QtCore import QTimer, Qt, QRect, QSize, Signal, QUrl, QPoint
from PySide6.QtGui import QDesktopServices
from PySide6.QtGui import QColor, QFont, QPainter, QSyntaxHighlighter, QTextCharFormat, QTextFormat
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFormLayout,
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLayout, QLayoutItem, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QSplitter, QTextEdit, QVBoxLayout, QWidget,
    QInputDialog, QProgressBar, QSizePolicy)
from PySide6.QtWebEngineWidgets import QWebEngineView

from ..columns import COLUMNS
from ..email_service import (EmailAccountRepository, EmailProviderService,
    EmailRecipientGroupRepository, GOOGLE)
from ..email_templates import (EmailTemplateRepository, TemplateVariableResolver,
                               build_reconciliation_summary, sanitize_preview_html)
from ..email_workflow import EmailBatchService, ReconciliationAttachment
from ..workers import FunctionWorker
from .widgets.chevron_combo import ChevronComboBox


class DeleteTemplateDialog(QDialog):
    def __init__(self, parent=None, template_name=""):
        super().__init__(parent)
        self.setObjectName("templateDeleteDialog")
        self.setWindowTitle("Xóa template")
        self.setMinimumWidth(440)
        self.resize(470, 250)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(14)
        icon = QLabel("!")
        icon.setObjectName("templateDeleteIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(46, 46)
        header.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        copy = QVBoxLayout()
        copy.setSpacing(6)
        heading = QLabel("Xóa template này?")
        heading.setObjectName("templateDeleteHeading")
        copy.addWidget(heading)
        name = QLabel(template_name or "Template")
        name.setObjectName("templateDeleteName")
        name.setWordWrap(True)
        copy.addWidget(name)
        header.addLayout(copy, 1)
        layout.addLayout(header)

        detail = QLabel("Template sẽ bị xóa khỏi thư viện. Thao tác này không thể hoàn tác.")
        detail.setObjectName("templateDeleteHint")
        detail.setWordWrap(True)
        layout.addWidget(detail)
        layout.addStretch()

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 8, 0, 0)
        footer.setSpacing(10)
        footer.addStretch()
        cancel = QPushButton("Giữ lại")
        cancel.setObjectName("dialogCancelButton")
        cancel.setDefault(True)
        cancel.clicked.connect(self.reject)
        delete = QPushButton("Xóa template")
        delete.setObjectName("templateDeleteConfirmButton")
        delete.clicked.connect(self.accept)
        footer.addWidget(cancel)
        footer.addWidget(delete)
        layout.addLayout(footer)


class HtmlHighlighter(QSyntaxHighlighter):
    """Small syntax highlighter for readable HTML and embedded CSS editing."""
    def __init__(self, document):
        super().__init__(document)
        self.rules = []
        for pattern, color, weight in (
            (r"</?[-\w:]+", "#B45309", True),
            (r"\b[a-zA-Z-]+(?==)", "#7C3AED", False),
            (r"\b[a-zA-Z-]+\s*:", "#0369A1", False),
            (r"\{[a-zA-Z_][\w]*\}", "#C2410C", True),
            (r"<!--.*?-->", "#8793A1", False),
        ):
            style = QTextCharFormat(); style.setForeground(QColor(color)); style.setFontWeight(QFont.Weight.Bold if weight else QFont.Weight.Normal)
            self.rules.append((re.compile(pattern), style))

    def highlightBlock(self, text):
        for pattern, style in self.rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), style)


class _LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_line_numbers(event)


class HtmlCodeEditor(QPlainTextEdit):
    """HTML editor with line numbers, current-line highlight and code-friendly keys."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_line_number_area_width(0)
        self._highlight_current_line()

    def line_number_area_width(self):
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 12 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_line_number_area_width(self, _block_count):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        contents = self.contentsRect()
        self.line_number_area.setGeometry(QRect(contents.left(), contents.top(), self.line_number_area_width(), contents.height()))

    def paint_line_numbers(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#F3F5F8"))
        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        current = self.textCursor().blockNumber()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor("#A64D39") if number == current else QColor("#8995A3"))
                painter.drawText(0, top, self.line_number_area.width() - 7, self.fontMetrics().height(),
                                 Qt.AlignmentFlag.AlignRight, str(number + 1))
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            number += 1

    def _highlight_current_line(self):
        selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(QColor("#F3F7FC"))
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            selections.append(selection)
        self.setExtraSelections(selections)
        self.line_number_area.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Tab and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.textCursor().insertText("    ")
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            indent = re.match(r"[ \t]*", self.textCursor().block().text()).group(0)
            super().keyPressEvent(event)
            self.textCursor().insertText(indent)
            return
        super().keyPressEvent(event)


class EmailTemplatePage(QWidget):
    """Template CRUD, HTML editing and a debounced Chromium preview."""
    def __init__(self, database, parent=None):
        super().__init__(parent)
        self.repository = EmailTemplateRepository(database)
        self.records = []
        self.current_id = None
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20); root.setSpacing(16)
        header = QHBoxLayout(); header.setSpacing(8)
        title_block = QVBoxLayout(); title_block.setSpacing(3)
        eyebrow = QLabel("EMAIL WORKSPACE"); eyebrow.setObjectName("templateEyebrow")
        title = QLabel("Email Template"); title.setObjectName("templatePageTitle")
        subtitle = QLabel("Soạn, xem trước và quản lý mẫu email của bạn."); subtitle.setObjectName("templatePageSubtitle")
        title_block.addWidget(eyebrow); title_block.addWidget(title); title_block.addWidget(subtitle)
        header.addLayout(title_block); header.addStretch()
        self.new_button = QPushButton("Mẫu mới"); self.duplicate_button = QPushButton("Nhân bản")
        self.revert_button = QPushButton("Hoàn tác"); self.save_button = QPushButton("Lưu template"); self.save_button.setProperty("primary", True)
        self.delete_button = QPushButton("Xóa")
        for button in (self.new_button, self.duplicate_button, self.revert_button, self.save_button, self.delete_button):
            button.setMinimumHeight(38)
        self.delete_button.setObjectName("templateDeleteButton")
        for button in (self.new_button, self.duplicate_button, self.revert_button, self.save_button, self.delete_button): header.addWidget(button)
        root.addLayout(header)
        splitter = QSplitter(Qt.Orientation.Horizontal); splitter.setObjectName("templateMainSplitter")
        left = QFrame(); left.setObjectName("templateLibraryCard")
        left_layout = QVBoxLayout(left); left_layout.setContentsMargins(14, 16, 14, 14); left_layout.setSpacing(12)
        library_header = QHBoxLayout(); library_title = QLabel("Thư viện mẫu"); library_title.setObjectName("templateSectionTitle")
        self.count = QLabel("0 mẫu"); self.count.setObjectName("templateCountBadge")
        library_header.addWidget(library_title); library_header.addStretch(); library_header.addWidget(self.count)
        left_layout.addLayout(library_header)
        self.search = QLineEdit(); self.search.setObjectName("templateSearch"); self.search.setPlaceholderText("Tìm template...")
        left_layout.addWidget(self.search); self.list = QListWidget(); self.list.setObjectName("templateList"); left_layout.addWidget(self.list, 1)
        splitter.addWidget(left)
        right = QWidget(); right.setObjectName("templateEditorPane"); layout = QVBoxLayout(right)
        layout.setContentsMargins(18, 0, 0, 0); layout.setSpacing(12)
        metadata = QFrame(); metadata.setObjectName("templateMetadataCard")
        form = QFormLayout(metadata); form.setContentsMargins(18, 14, 18, 16); form.setHorizontalSpacing(16); form.setVerticalSpacing(10)
        self.name = QLineEdit(); self.name.setObjectName("templateName"); self.name.setPlaceholderText("Ví dụ: Báo cáo tuần")
        self.subject = QLineEdit(); self.subject.setObjectName("templateSubject"); self.subject.setPlaceholderText("Nhập tiêu đề email")
        form.addRow("Tên template", self.name); form.addRow("Subject", self.subject); layout.addWidget(metadata)
        tokens_frame = QFrame(); tokens_frame.setObjectName("templateTokensCard")
        tokens = QHBoxLayout(tokens_frame); tokens.setContentsMargins(12, 9, 12, 9); tokens.setSpacing(7)
        tokens_title = QLabel("BIẾN CÓ SẴN"); tokens_title.setObjectName("templateTokenHeading"); tokens.addWidget(tokens_title)
        token_scroll = QScrollArea(); token_scroll.setObjectName("templateTokenScroll")
        token_scroll.setWidgetResizable(True)
        token_scroll.setFrameShape(QFrame.Shape.NoFrame)
        token_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        token_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        token_scroll.horizontalScrollBar().setObjectName("templateTokenScrollBar")
        token_widget = QWidget(); token_widget.setObjectName("templateTokenScrollContent")
        token_widget.setAutoFillBackground(False)
        token_scroll.viewport().setAutoFillBackground(False)
        token_layout = QHBoxLayout(token_widget)
        token_layout.setContentsMargins(0, 0, 0, 0); token_layout.setSpacing(7)
        for token in (
            "{name}", "{email}", "{company}", "{date}", "{report_date}",
            "{record_count}", "{selected_count}", "{workspace_name}", "{sender_name}",
            "{trip_summary}", "{total_to_count}", "{total_order_count}",
        ):
            button = QPushButton(token); button.setObjectName("templateTokenButton")
            button.clicked.connect(lambda _=False, value=token: self.editor.insertPlainText(value))
            token_layout.addWidget(button)
        token_scroll.setWidget(token_widget); tokens.addWidget(token_scroll, 1)
        layout.addWidget(tokens_frame)
        panes = QSplitter(Qt.Orientation.Horizontal)
        editor_card = QFrame(); editor_card.setObjectName("templateWorkCard")
        editor_layout = QVBoxLayout(editor_card); editor_layout.setContentsMargins(12, 12, 12, 12); editor_layout.setSpacing(9)
        editor_header = QHBoxLayout(); editor_label = QLabel("Mã HTML"); editor_label.setObjectName("templatePaneTitle")
        editor_hint = QLabel("HTML + CSS"); editor_hint.setObjectName("templatePaneHint")
        editor_header.addWidget(editor_label); editor_header.addStretch(); editor_header.addWidget(editor_hint); editor_layout.addLayout(editor_header)
        self.editor = HtmlCodeEditor(); self.editor.setObjectName("htmlEditor"); self.editor.setPlaceholderText("Dán hoặc viết HTML email tại đây...")
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setFont(QFont("Cascadia Code", 10))
        self.editor.setTabStopDistance(self.editor.fontMetrics().horizontalAdvance(" ") * 4)
        self.editor._update_line_number_area_width(0)
        self.highlighter = HtmlHighlighter(self.editor.document())
        editor_layout.addWidget(self.editor, 1)
        self.editor_position = QLabel("DÒNG 1, CỘT 1"); self.editor_position.setObjectName("templatePaneHint")
        editor_layout.addWidget(self.editor_position, 0, Qt.AlignmentFlag.AlignRight)
        preview_card = QFrame(); preview_card.setObjectName("templateWorkCard")
        preview_layout = QVBoxLayout(preview_card); preview_layout.setContentsMargins(12, 12, 12, 12); preview_layout.setSpacing(9)
        preview_header = QHBoxLayout(); preview_label = QLabel("Xem trước email"); preview_label.setObjectName("templatePaneTitle")
        preview_hint = QLabel("LIVE PREVIEW"); preview_hint.setObjectName("templatePaneHint")
        self.expand_preview_button = QPushButton("Mở rộng ↗"); self.expand_preview_button.setObjectName("templateExpandPreviewButton")
        self.expand_preview_button.clicked.connect(self._open_expanded_preview)
        preview_header.addWidget(preview_label); preview_header.addStretch(); preview_header.addWidget(preview_hint); preview_header.addWidget(self.expand_preview_button); preview_layout.addLayout(preview_header)
        self.preview = QWebEngineView(); self.preview.setObjectName("templatePreview"); self.preview.setMinimumWidth(260)
        preview_layout.addWidget(self.preview, 1)
        self.expanded_preview_dialog = None
        self.expanded_preview = None
        panes.addWidget(editor_card); panes.addWidget(preview_card); panes.setChildrenCollapsible(False); panes.setSizes([1, 1]); layout.addWidget(panes, 1)
        self.state = QLabel(""); self.state.setObjectName("templateState"); layout.addWidget(self.state)
        splitter.addWidget(right); splitter.setChildrenCollapsible(False); splitter.setSizes([250, 1050]); root.addWidget(splitter, 1)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(350); self.timer.timeout.connect(self._render_preview)
        self.search.textChanged.connect(self.refresh); self.list.currentItemChanged.connect(self._select)
        self.new_button.clicked.connect(self.new_template); self.save_button.clicked.connect(self.save_template); self.delete_button.clicked.connect(self.delete_template)
        self.duplicate_button.clicked.connect(self.duplicate_template); self.revert_button.clicked.connect(self.revert_template)
        self.subject.textChanged.connect(self._schedule_preview); self.editor.textChanged.connect(self._schedule_preview)
        self.editor.cursorPositionChanged.connect(self._update_editor_position)
        self.refresh()

    def _update_editor_position(self):
        cursor = self.editor.textCursor()
        self.editor_position.setText(f"DÒNG {cursor.blockNumber() + 1}, CỘT {cursor.positionInBlock() + 1}")

    def refresh(self, *_):
        query = self.search.text().casefold()
        previous = self.current_id
        self.records = [row for row in self.repository.get_all() if query in (row["name"] + " " + row["subject"]).casefold()]
        self.count.setText(f"{len(self.records)} mẫu")
        self.list.blockSignals(True); self.list.clear()
        selected = None
        for row in self.records:
            item = QListWidgetItem(f"{row['name']}\n{row['subject']}"); item.setData(Qt.ItemDataRole.UserRole, row["id"]); self.list.addItem(item)
            if row["id"] == previous: selected = item
        if selected: self.list.setCurrentItem(selected)
        elif self.records: self.list.setCurrentRow(0)
        self.list.blockSignals(False)
        if not selected and self.records: self._load(self.records[0])
        elif not self.records: self._clear()

    def _select(self, item, _old=None):
        if item:
            record = next((row for row in self.records if row["id"] == item.data(Qt.ItemDataRole.UserRole)), None)
            if record: self._load(record)

    def _load(self, record):
        self.current_id = record["id"]
        for widget, value in ((self.name, record["name"]), (self.subject, record["subject"])):
            widget.blockSignals(True); widget.setText(value); widget.blockSignals(False)
        self.editor.blockSignals(True); self.editor.setPlainText(record["html_content"]); self.editor.blockSignals(False)
        self.state.setText(""); self._render_preview()

    def _clear(self):
        self.current_id = None; self.name.clear(); self.subject.clear(); self.editor.clear(); self._render_preview()

    def new_template(self):
        self.list.setCurrentRow(-1)
        self.list.clearSelection()
        self._clear()
        self.state.setText("Mẫu mới chưa được lưu.")
        self.name.setFocus()

    def duplicate_template(self):
        record = next((row for row in self.records if row["id"] == self.current_id), None)
        if not record: return
        self.current_id = None
        self.name.setText(f"{record['name']} — copy")
        self.subject.setText(record["subject"])
        self.editor.setPlainText(record["html_content"])
        self.state.setText("Bản sao chưa được lưu.")

    def revert_template(self):
        record = next((row for row in self.repository.get_all() if row["id"] == self.current_id), None)
        if record: self._load(record)
        else: self._clear()

    def _schedule_preview(self): self.timer.start()

    def _render_preview(self):
        source = self.editor.toPlainText()
        variables = {
            key: self._demo_value(key)
            for key in TemplateVariableResolver.extract_variables(source)
        }
        body = sanitize_preview_html(TemplateVariableResolver.resolve(source, variables))
        if "<html" not in body.casefold():
            body = f"<!doctype html><html><head><meta charset='utf-8'></head><body>{body}</body></html>"
        self.preview.setHtml(body)
        if self.expanded_preview is not None:
            self.expanded_preview.setHtml(body)

    @staticmethod
    def _demo_value(key):
        normalized = key.casefold()
        if "email" in normalized:
            return "minh.anh@example.com"
        if "date" in normalized:
            return "03/10/2026"
        if "workspace" in normalized:
            return "SPX Demo Workspace"
        if any(part in normalized for part in ("count", "quantity", "orders", "records")):
            return "128"
        if "name" in normalized:
            return "Nguyễn Minh Anh"
        if "company" in normalized:
            return "SPX Logistics"
        if "color" in normalized:
            return "#E65B3F"
        if any(part in normalized for part in ("total", "amount", "revenue", "price")):
            return "12.500.000 ₫"
        return "Dữ liệu demo"

    def _open_expanded_preview(self):
        if self.expanded_preview_dialog is None:
            dialog = QDialog(self, Qt.WindowType.Window)
            dialog.setObjectName("expandedTemplatePreviewDialog")
            dialog.setWindowTitle("Xem trước email — SPX Reconciliation Report")
            dialog.setMinimumSize(800, 560)
            dialog.resize(1120, 780)
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(20, 16, 20, 20); layout.setSpacing(12)
            header = QHBoxLayout()
            title = QLabel("Xem trước email"); title.setObjectName("expandedPreviewTitle")
            note = QLabel("Các biến được hiển thị bằng dữ liệu demo."); note.setObjectName("expandedPreviewNote")
            close_button = QPushButton("Đóng"); close_button.clicked.connect(dialog.close)
            header.addWidget(title); header.addSpacing(12); header.addWidget(note); header.addStretch(); header.addWidget(close_button)
            layout.addLayout(header)
            self.expanded_preview = QWebEngineView(); self.expanded_preview.setObjectName("expandedTemplatePreview")
            layout.addWidget(self.expanded_preview, 1)
            self.expanded_preview_dialog = dialog
        self._render_preview()
        self.expanded_preview_dialog.showMaximized()
        self.expanded_preview_dialog.raise_()
        self.expanded_preview_dialog.activateWindow()

    def save_template(self):
        name, subject = self.name.text().strip(), self.subject.text().strip()
        if not name or not subject:
            QMessageBox.warning(self, "Thiếu thông tin", "Nhập tên và subject trước khi lưu."); return
        content = self.editor.toPlainText()
        if self.current_id: self.repository.update(self.current_id, name, subject, content)
        else: self.current_id = self.repository.create(name, subject, content)
        self.refresh(); self.state.setText("Đã lưu template.")

    def delete_template(self):
        item = self.list.currentItem()
        selected_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        # The visible library selection is authoritative; the editor may be blank
        # after starting a new template while Qt still retains its current item.
        template_id = selected_id or self.current_id
        if not template_id:
            self.state.setText("Chọn một template trong thư viện để xóa.")
            return

        record = next((row for row in self.records if row["id"] == template_id), None)
        name = record["name"] if record else self.name.text().strip() or "template này"
        dialog = DeleteTemplateDialog(self, name)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            self.repository.delete(template_id)
        except Exception as exc:
            QMessageBox.critical(self, "Không thể xóa template", str(exc))
            return
        self.current_id = None
        self.refresh()
        self.state.setText(f'Đã xóa “{name}”.')


class FlowLayout(QLayout):
    """A compact wrapping layout for recipient chips and their editor."""
    def __init__(self, parent=None, margin=8, spacing=6):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)
        self.invalidate()
    def count(self): return len(self._items)
    def itemAt(self, index): return self._items[index] if 0 <= index < len(self._items) else None
    def takeAt(self, index):
        item = self._items.pop(index) if 0 <= index < len(self._items) else None
        if item: self.invalidate()
        return item
    def expandingDirections(self): return Qt.Orientation(0)
    def hasHeightForWidth(self): return True
    def heightForWidth(self, width): return self._do_layout(QRect(0, 0, width, 0), True)
    def sizeHint(self): return QSize(360, self.heightForWidth(360))
    def minimumSize(self):
        margins = self.contentsMargins()
        return QSize(150, self.heightForWidth(150))
    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def _do_layout(self, rect, test_only):
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x, y, line_height = area.x(), area.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self.spacing()
            if line_height and next_x - self.spacing() > area.right() + 1:
                x = area.x(); y += line_height + self.spacing()
                next_x = x + hint.width() + self.spacing(); line_height = 0
            if not test_only: item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x; line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()


class _RecipientLineEdit(QLineEdit):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setPlaceholderText("nhập email...")
        self.setMinimumWidth(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(28)

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter,
                   Qt.Key.Key_Comma, Qt.Key.Key_Semicolon):
            self.owner.commit_input()
            return
        if key == Qt.Key.Key_Backspace and not self.text() and self.owner._emails:
            self.owner.remove_email(len(self.owner._emails) - 1)
            return
        if key == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.owner.add_pasted(QApplication.clipboard().text())
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.owner.container.setProperty("focused", True)
        self.owner._refresh_container_style()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.owner.container.setProperty("focused", False)
        self.owner._refresh_container_style()


class EmailChipInput(QWidget):
    """Email recipient editor exposing validated values as ``list[str]``."""
    recipientsChanged = Signal(object)
    EMAIL_PATTERN = re.compile(r"^[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+$")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._emails = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(3)
        self.container = QFrame(); self.container.setObjectName("emailChipContainer")
        self.container.setMinimumHeight(42)
        self.flow = FlowLayout(self.container)
        self.input = _RecipientLineEdit(self)
        self.input.setObjectName("emailChipEditor")
        self.flow.addWidget(self.input)
        root.addWidget(self.container)
        self.error = QLabel("Email không hợp lệ")
        self.error.setObjectName("emailChipError"); self.error.hide()
        root.addWidget(self.error)
        self.input.textChanged.connect(self._clear_error)
        self.input.editingFinished.connect(self.commit_input)

    def emails(self): return list(self._emails)

    def set_emails(self, emails):
        self.clear_emails()
        self.input.clear()
        for email in emails: self._add_email(str(email).strip())
        self.recipientsChanged.emit(self.emails())

    def clear_emails(self):
        while self.flow.count() > 1:
            item = self.flow.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._emails.clear()
        self._clear_error()

    def _clear_error(self, *_):
        if not self.error.isHidden():
            self.error.hide(); self.container.setProperty("invalid", False)
            self._refresh_container_style()

    def _set_error(self):
        self.container.setProperty("invalid", True)
        self._refresh_container_style()
        self.error.show()

    def _refresh_container_style(self):
        self.container.style().unpolish(self.container); self.container.style().polish(self.container)

    def _valid(self, email): return bool(self.EMAIL_PATTERN.fullmatch(email))

    def _add_email(self, email):
        if not self._valid(email): return False
        if email.casefold() in {value.casefold() for value in self._emails}: return True
        self._emails.append(email)
        chip = QFrame(); chip.setObjectName("emailChip")
        chip_layout = QHBoxLayout(chip); chip_layout.setContentsMargins(8, 2, 3, 2); chip_layout.setSpacing(4)
        label = QLabel(email); label.setObjectName("emailChipText")
        remove = QPushButton("×"); remove.setObjectName("emailChipRemove")
        remove.setFixedSize(18, 18); remove.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        chip_layout.addWidget(label); chip_layout.addWidget(remove)
        self.flow.removeWidget(self.input)
        self.flow.addWidget(chip)
        self.flow.addWidget(self.input)
        remove.clicked.connect(lambda _checked=False, value=email: self.remove_email_by_value(value))
        self.recipientsChanged.emit(self.emails())
        return True

    def remove_email_by_value(self, email):
        for index, value in enumerate(self._emails):
            if value == email:
                self.remove_email(index); break

    def remove_email(self, index):
        if not 0 <= index < len(self._emails): return
        self._emails.pop(index)
        item = self.flow.takeAt(index)
        if item and item.widget(): item.widget().deleteLater()
        self.recipientsChanged.emit(self.emails())
        self.input.setFocus()

    def commit_input(self):
        value = self.input.text().strip()
        if not value: return
        if self._add_email(value):
            self.input.clear(); self._clear_error()
        else:
            self._set_error()

    def add_pasted(self, text):
        entries = [part.strip() for part in re.split(r"[,;\s]+", text) if part.strip()]
        invalid = []
        for entry in entries:
            if self._valid(entry): self._add_email(entry)
            else: invalid.append(entry)
        self.input.setText(" ".join(invalid))
        if invalid: self._set_error()
        else: self._clear_error()
        self.input.setFocus()


class RecipientGroupEditor(QFrame):
    remove_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("recipientGroupCard")
        root = QVBoxLayout(self); root.setContentsMargins(18, 16, 18, 18); root.setSpacing(12)
        header = QHBoxLayout(); self.title = QLabel("Destination 1"); self.title.setObjectName("recipientGroupTitle")
        header.addWidget(self.title); header.addStretch()
        self.remove_button = QPushButton("Xóa nhóm"); self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        header.addWidget(self.remove_button); root.addLayout(header)
        fields = QVBoxLayout(); fields.setSpacing(10)
        self.to, self.cc, self.bcc = EmailChipInput(), EmailChipInput(), EmailChipInput()
        for name, editor, hint in (
            ("To", self.to, "email@example.com"),
            ("CC", self.cc, "Optional"),
            ("BCC", self.bcc, "Optional"),
        ):
            label = QLabel(name); label.setObjectName("recipientFieldLabel")
            editor.input.setPlaceholderText(hint if name == "To" else "nhập email...")
            fields.addWidget(label); fields.addWidget(editor)
        root.addLayout(fields)

    def set_values(self, to, cc, bcc):
        self.to.set_emails(to); self.cc.set_emails(cc); self.bcc.set_emails(bcc)


class EmailPage(QWidget):
    back_requested = Signal()

    SYSTEM_VARIABLES = {"date", "report_date", "record_count", "selected_count",
                        "sender_name", "email", "name", "company", "workspace_name",
                        "trip_summary", "total_to_count", "total_order_count"}

    def __init__(self, database, thread_pool, parent=None):
        super().__init__(parent)
        self.database = database; self.pool = thread_pool
        self.accounts = EmailAccountRepository(database); self.provider = EmailProviderService(self.accounts)
        self.batch_service = EmailBatchService(self.accounts, self.provider)
        self.templates = EmailTemplateRepository(database); self.recipient_groups_repo = EmailRecipientGroupRepository(database)
        self.records = []; self.variables = {}; self.account_ids = {}; self.accounts_by_id = {}
        self.recipient_editors = []; self.selected_record_ids = []; self.workspace_id = None
        self.summary_values = build_reconciliation_summary([])
        self.selected_columns = tuple(COLUMNS)
        self.workspace_name = ""; self.source_description = ""; self.attachment_path: Path | None = None
        self.prepare_worker = None; self.send_worker = None; self._prepare_token = 0
        root = QVBoxLayout(self); root.setContentsMargins(18, 0, 18, 14); root.setSpacing(10)
        self.scroll = QScrollArea(); self.scroll.setObjectName("emailPageScroll")
        self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        content = QWidget(); content.setObjectName("emailPageContent")
        content_outer = QHBoxLayout(content); content_outer.setContentsMargins(18, 14, 18, 14)
        content_outer.setSpacing(0)
        column = QWidget(); column.setMaximumWidth(1560)
        page_layout = QVBoxLayout(column); page_layout.setContentsMargins(0, 0, 0, 22); page_layout.setSpacing(18)
        content_outer.addWidget(column, 1)
        self.scroll.setWidget(content); root.addWidget(self.scroll, 1)
        title_row = QHBoxLayout(); heading = QVBoxLayout()
        title = QLabel("Send Email"); title.setObjectName("templatePageTitle")
        subtitle = QLabel("Prepare your report and recipients.")
        subtitle.setObjectName("templatePageSubtitle"); heading.addWidget(title); heading.addWidget(subtitle)
        title_row.addLayout(heading); title_row.addStretch()
        self.back_button = QPushButton("Quay lại Main Data"); self.back_button.clicked.connect(self.back_requested)
        title_row.addWidget(self.back_button); page_layout.addLayout(title_row)

        self.selected_card = QFrame(); self.selected_card.setObjectName("emailSectionCard")
        selected = QHBoxLayout(self.selected_card); selected.setContentsMargins(20, 18, 20, 18)
        summary = QVBoxLayout(); label = QLabel("SELECTED DATA"); label.setObjectName("emailSectionEyebrow")
        self.selection_summary = QLabel("Chưa chọn dữ liệu từ Main Data"); self.selection_summary.setObjectName("emailSectionTitle")
        self.source_summary = QLabel("Quay lại Main Data và chọn các bản ghi cần gửi."); self.source_summary.setProperty("muted", True)
        self.attachment_summary = QLabel("Excel: Not ready"); self.attachment_summary.setObjectName("attachmentSummary")
        summary.addWidget(label); summary.addWidget(self.selection_summary); summary.addWidget(self.source_summary)
        summary.addWidget(self.attachment_summary); selected.addLayout(summary, 1)
        self.open_attachment = QPushButton("Mở Excel"); self.open_attachment.setEnabled(False)
        self.open_attachment.clicked.connect(self._open_attachment); selected.addWidget(self.open_attachment)
        page_layout.addWidget(self.selected_card)

        self.sender_card = QFrame(); self.sender_card.setObjectName("emailSectionCard")
        sender = QVBoxLayout(self.sender_card); sender.setContentsMargins(20, 18, 20, 18); sender.setSpacing(12)
        sender_title = QLabel("Sender Account"); sender_title.setObjectName("emailSectionTitle"); sender.addWidget(sender_title)
        sender_controls = QHBoxLayout(); sender_controls.setSpacing(10)
        self.sender_state = QLabel("Not connected"); self.sender_state.setObjectName("senderConnectionState")
        sender_controls.addWidget(self.sender_state)
        self.account_combo = ChevronComboBox(); self.account_combo.setMinimumWidth(220); sender_controls.addWidget(self.account_combo, 1)
        self.gmail = QPushButton("Kết nối Gmail")
        self.disconnect = QPushButton("Ngắt kết nối")
        self.change_account = QPushButton("Đổi tài khoản")
        self.reconnect = QPushButton("Reconnect sender")
        sender_controls.addWidget(self.gmail)
        sender_controls.addWidget(self.change_account); sender_controls.addWidget(self.reconnect)
        sender_controls.addWidget(self.disconnect)
        sender.addLayout(sender_controls)
        page_layout.addWidget(self.sender_card)
        self.gmail.clicked.connect(lambda: self.connect_account(GOOGLE))
        self.disconnect.clicked.connect(self.disconnect_account)
        self.change_account.clicked.connect(self.account_combo.showPopup)
        self.reconnect.clicked.connect(self._reconnect_sender)

        self.recipient_card = QFrame(); self.recipient_card.setObjectName("emailSectionCard")
        recipient_layout = QVBoxLayout(self.recipient_card); recipient_layout.setContentsMargins(20, 18, 20, 20); recipient_layout.setSpacing(14)
        recipient_head = QHBoxLayout(); recipient_title = QLabel("Recipients"); recipient_title.setObjectName("emailSectionTitle")
        recipient_head.addWidget(recipient_title); recipient_head.addStretch()
        self.saved_recipients = ChevronComboBox(); self.saved_recipients.setMinimumWidth(150); self.saved_recipients.setMinimumHeight(42); recipient_head.addWidget(self.saved_recipients)
        self.load_recipients = QPushButton("Load Group"); self.save_recipients = QPushButton("Save Group")
        self.delete_recipients = QPushButton("Delete Saved")
        for button in (self.load_recipients, self.save_recipients, self.delete_recipients):
            button.setMinimumHeight(42); recipient_head.addWidget(button)
        recipient_layout.addLayout(recipient_head)
        self.recipient_description = QLabel("Configure who will receive this report. Each group will be sent as a separate email.")
        self.recipient_description.setObjectName("emailSectionDescription"); recipient_layout.addWidget(self.recipient_description)
        self.group_list = QVBoxLayout(); self.group_list.setSpacing(12); recipient_layout.addLayout(self.group_list)
        self.add_group_button = QPushButton("+ Add recipient group"); self.add_group_button.setMinimumHeight(44)
        self.add_group_button.clicked.connect(self._add_group)
        recipient_layout.addWidget(self.add_group_button); page_layout.addWidget(self.recipient_card)
        self.load_recipients.clicked.connect(self._load_recipient_group)
        self.save_recipients.clicked.connect(self._save_recipient_group)
        self.delete_recipients.clicked.connect(self._delete_recipient_group)

        self.template_card = QFrame(); self.template_card.setObjectName("emailSectionCard")
        template_layout = QVBoxLayout(self.template_card); template_layout.setContentsMargins(20, 18, 20, 20); template_layout.setSpacing(10)
        template_title = QLabel("Email Template"); template_title.setObjectName("emailSectionTitle"); template_layout.addWidget(template_title)
        template_label = QLabel("Template"); template_label.setObjectName("emailFieldLabel"); template_layout.addWidget(template_label)
        self.template_combo = ChevronComboBox(); self.template_combo.setMinimumHeight(44); template_layout.addWidget(self.template_combo)
        subject_label = QLabel("Subject"); subject_label.setObjectName("emailFieldLabel"); template_layout.addWidget(subject_label)
        self.subject = QLineEdit(); self.subject.setMinimumHeight(44); self.subject.setPlaceholderText("Subject"); template_layout.addWidget(self.subject)
        variables_hint = QLabel(
            "System variables: {{date}} · {{record_count}} · {{workspace_name}} · "
            "{{trip_summary}} · {{total_to_count}} · {{total_order_count}}. "
            "Đặt trip_summary trong khối có white-space: pre-line để giữ xuống dòng."
        )
        variables_hint.setObjectName("emailSectionDescription"); template_layout.addWidget(variables_hint)
        self.variable_form = QFormLayout(); self.variable_form.setVerticalSpacing(5); template_layout.addLayout(self.variable_form)
        page_layout.addWidget(self.template_card)

        preview_card = QFrame(); preview_card.setObjectName("emailSectionCard")
        preview_layout = QVBoxLayout(preview_card); preview_layout.setContentsMargins(20, 18, 20, 20); preview_layout.setSpacing(10)
        preview_title = QLabel("Email Preview"); preview_title.setObjectName("emailSectionTitle"); preview_layout.addWidget(preview_title)
        self.preview_from = QLabel("From: —"); self.preview_to = QLabel("To: —"); self.preview_cc = QLabel("CC: —")
        self.preview_bcc = QLabel("BCC: —"); self.preview_subject = QLabel("Subject: —")
        for item in (self.preview_from, self.preview_to, self.preview_cc, self.preview_bcc, self.preview_subject):
            item.setWordWrap(True); item.setObjectName("emailPreviewMeta"); preview_layout.addWidget(item)
        self.preview_attachment = QLabel("Attachment: —"); self.preview_attachment.setObjectName("emailPreviewAttachment")
        preview_layout.addWidget(self.preview_attachment)
        self.preview = QWebEngineView(); self.preview.setObjectName("emailBodyPreview"); self.preview.setMinimumHeight(560); preview_layout.addWidget(self.preview)
        page_layout.addWidget(preview_card)

        self.history = QListWidget(); self.history.setMaximumHeight(150); self.history.setObjectName("emailHistory")
        self.history.itemDoubleClicked.connect(self._show_history_details)
        page_layout.addWidget(self.history)
        self.status = QLabel("")
        self.progress = QProgressBar(); self.progress.setObjectName("emailSendProgress")
        self.progress.setMinimumWidth(180); self.progress.setMinimumHeight(22); self.progress.setMaximumHeight(22)
        self.progress.setTextVisible(False)
        self.progress.hide()
        footer_card = QFrame(); footer_card.setObjectName("emailActionBar")
        footer = QHBoxLayout(footer_card); footer.setContentsMargins(20, 12, 20, 12); footer.setSpacing(14)
        footer_shadow = QGraphicsDropShadowEffect(footer_card)
        footer_shadow.setBlurRadius(22); footer_shadow.setOffset(0, 3)
        footer_shadow.setColor(QColor(28, 45, 61, 34)); footer_card.setGraphicsEffect(footer_shadow)
        self.action_summary = QLabel("0 records · 1 recipient group"); self.action_summary.setObjectName("emailActionSummary")
        self.status.setWordWrap(True)
        footer.addWidget(self.action_summary); footer.addWidget(self.status, 1); footer.addWidget(self.progress)
        self.send_button = QPushButton("Gửi Email"); self.send_button.setProperty("primary", True); self.send_button.setEnabled(False)
        self.send_button.setMinimumHeight(48); self.send_button.setMinimumWidth(150)
        self.send_button.clicked.connect(self.send); footer.addWidget(self.send_button); root.addWidget(footer_card)

        self.template_combo.currentIndexChanged.connect(self._select_template)
        self.subject.textChanged.connect(self._schedule_preview)
        self.account_combo.currentIndexChanged.connect(self._schedule_preview)
        self.account_combo.currentIndexChanged.connect(self._update_sender_controls)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(300)
        self.timer.timeout.connect(self._render_preview)
        self._add_group(); self.refresh()

    def set_context(self, selected_ids, workspace_id, workspace_name, source_description,
                    visible_columns=None):
        self._prepare_token += 1; token = self._prepare_token
        self.cleanup_attachment(); self.selected_record_ids = list(dict.fromkeys(int(value) for value in selected_ids))
        self.workspace_id = workspace_id; self.workspace_name = workspace_name; self.source_description = source_description
        self.selected_columns = tuple(COLUMNS if visible_columns is None else visible_columns)
        self.selection_summary.setText(f"{len(self.selected_record_ids):,} records selected")
        self.source_summary.setText(f"{workspace_name} · {source_description}")
        self.attachment_summary.setText("Preparing Excel…")
        self._update_action_summary()
        self.open_attachment.setEnabled(False); self.send_button.setEnabled(False)
        self.status.setText("Đang tải lại dữ liệu đã chọn và tạo Excel…")
        self.progress.setRange(0, max(1, len(self.selected_record_ids)))
        self.progress.setValue(0)
        self.progress.show()
        selected_ids = tuple(self.selected_record_ids)
        selected_columns = self.selected_columns
        worker_ref = {}
        def prepare():
            rows = self.database.get_rows_by_ids(
                workspace_id, selected_ids,
                progress=lambda done, total: worker_ref["worker"].signals.progress.emit(
                    (token, "loading", done, total)))
            if len(rows) != len(selected_ids):
                raise RuntimeError("Một số bản ghi đã bị xóa hoặc không còn thuộc workspace hiện tại.")
            summary_values = build_reconciliation_summary(rows)
            path = ReconciliationAttachment.create(
                rows, selected_columns,
                progress=lambda phase, done, total: worker_ref["worker"].signals.progress.emit(
                    (token, phase, done, total)))
            return token, str(path), len(rows), len(selected_columns), summary_values
        self.prepare_worker = FunctionWorker(prepare)
        worker_ref["worker"] = self.prepare_worker
        self.prepare_worker.signals.progress.connect(self._attachment_progress)
        self.prepare_worker.signals.result.connect(self._attachment_ready)
        self.prepare_worker.signals.error.connect(lambda error: self._attachment_error(error, token))
        self.pool.start(self.prepare_worker)
        self._render_preview()

    def clear_context(self):
        self._prepare_token += 1
        self.cleanup_attachment(); self.selected_record_ids = []; self.workspace_id = None
        self.summary_values = build_reconciliation_summary([])
        self.selected_columns = tuple(COLUMNS)
        self.workspace_name = ""; self.source_description = ""
        self.selection_summary.setText("Chưa chọn dữ liệu từ Main Data")
        self.source_summary.setText("Quay lại Main Data và chọn các bản ghi cần gửi.")
        self.attachment_summary.setText("Excel: Not ready"); self.preview_attachment.setText("Attachment: —")
        self._update_action_summary()
        self.open_attachment.setEnabled(False); self.status.setText("")
        self.progress.hide()
        self.send_button.setEnabled(False); self._render_preview()

    def _attachment_ready(self, result):
        token, filename, count, column_count, summary_values = result
        if token != self._prepare_token:
            try:
                stale_path = Path(filename); stale_path.unlink(missing_ok=True); stale_path.parent.rmdir()
            except OSError: pass
            return
        self.attachment_path = Path(filename)
        self.summary_values = summary_values
        self.progress.hide()
        self.attachment_summary.setText(
            f"Ready · {self.attachment_path.name} · {count:,} records · {column_count} columns")
        self.preview_attachment.setText(
            f"Attachment: {self.attachment_path.name} · {count:,} records · {column_count} columns")
        self.open_attachment.setEnabled(True); self.status.setText("Excel đã sẵn sàng để xem trước hoặc gửi.")
        self._update_send_enabled(); self._render_preview()

    def _attachment_error(self, error, token):
        if token != self._prepare_token:
            return
        self.progress.hide()
        self.attachment_summary.setText("Failed · Excel attachment could not be created")
        self.status.setText(error.splitlines()[0]); self.send_button.setEnabled(False)

    def _attachment_progress(self, update):
        token, phase, done, total = update
        if token != self._prepare_token:
            return
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(min(done, total))
        if phase == "loading":
            self.attachment_summary.setText(f"Preparing Excel · Đang tải dữ liệu {done:,} / {total:,} records…")
            self.status.setText(f"Đang tải dữ liệu: {done:,} / {total:,} records")
        elif phase == "writing":
            self.attachment_summary.setText(f"Preparing Excel · Đang ghi dữ liệu {done:,} / {total:,} records…")
            self.status.setText(f"Đang tạo Excel: {done:,} / {total:,} records")
        elif phase == "saving":
            self.attachment_summary.setText(f"Preparing Excel · Đang lưu file ({total:,} records)…")
            self.status.setText("Đang lưu file Excel…")

    def _open_attachment(self):
        if self.attachment_path and self.attachment_path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.attachment_path)))

    def cleanup_attachment(self):
        if self.attachment_path:
            try:
                folder = self.attachment_path.parent
                self.attachment_path.unlink(missing_ok=True)
                folder.rmdir()
            except OSError:
                pass
            self.attachment_path = None

    def _add_group(self, values=None):
        editor = RecipientGroupEditor(self)
        editor.title.setText(f"Recipient Group {len(self.recipient_editors) + 1}")
        editor.remove_requested.connect(self._remove_group)
        self.recipient_editors.append(editor); self.group_list.addWidget(editor)
        if values: editor.set_values(values["to"], values["cc"], values["bcc"])
        editor.to.recipientsChanged.connect(self._schedule_preview)
        editor.cc.recipientsChanged.connect(self._schedule_preview)
        editor.bcc.recipientsChanged.connect(self._schedule_preview); self._schedule_preview()
        self._update_action_summary()
        return editor

    def _remove_group(self, editor):
        if len(self.recipient_editors) <= 1:
            return
        self.recipient_editors.remove(editor); editor.deleteLater()
        for index, group in enumerate(self.recipient_editors, 1): group.title.setText(f"Recipient Group {index}")
        self._schedule_preview(); self._update_action_summary()

    def refresh(self):
        previous_account = self.account_combo.currentData()
        self.accounts_by_id = {account["id"]: account for account in self.accounts.list()}
        self.account_combo.blockSignals(True); self.account_combo.clear()
        for account_id, account in self.accounts_by_id.items():
            self.account_combo.addItem(f"{account['email']}  ·  {account['provider']}", account_id)
        restored = self.account_combo.findData(previous_account)
        if restored >= 0: self.account_combo.setCurrentIndex(restored)
        self.account_combo.blockSignals(False)
        self._update_sender_controls()
        previous_template = self.template_combo.currentData()
        self.records = self.templates.get_all(); self.template_combo.blockSignals(True); self.template_combo.clear()
        for record in self.records: self.template_combo.addItem(record["name"], record["id"])
        restored = self.template_combo.findData(previous_template)
        if restored >= 0: self.template_combo.setCurrentIndex(restored)
        self.template_combo.blockSignals(False)
        self._refresh_saved_groups(); self.refresh_history()
        self._select_template(self.template_combo.currentIndex()); self._update_send_enabled()

    def connect_account(self, provider):
        self.status.setText("Đang chuẩn bị đăng nhập OAuth…")
        self.gmail.setEnabled(False); self.reconnect.setEnabled(False)
        worker = FunctionWorker(self.provider.connect, provider)
        worker.kwargs["on_status"] = worker.signals.progress.emit
        worker.signals.progress.connect(self.status.setText)
        worker.signals.result.connect(lambda email: (self.status.setText(f"Đã kết nối {email}"), self.refresh()))
        worker.signals.error.connect(lambda error: self.status.setText(error.splitlines()[0]))
        worker.signals.finished.connect(lambda: (self.gmail.setEnabled(True), self.reconnect.setEnabled(True)))
        self.pool.start(worker)

    def _reconnect_sender(self):
        account = self.accounts_by_id.get(self.account_combo.currentData())
        if account:
            self.connect_account(account["provider"])

    def disconnect_account(self):
        account_id = self.account_combo.currentData()
        if account_id:
            self.accounts.disconnect(account_id); self.refresh()

    def _update_sender_controls(self, *_):
        account = self.accounts_by_id.get(self.account_combo.currentData(), {})
        connected = bool(account)
        provider = account.get("provider", "").title()
        self.sender_state.setText(f"Connected with {provider}" if connected else "Connect an account")
        self.account_combo.setVisible(connected)
        self.change_account.setVisible(connected)
        self.reconnect.setVisible(connected)
        self.disconnect.setVisible(connected)
        self.gmail.setVisible(not connected)

    def _refresh_saved_groups(self):
        self.saved_recipients.clear()
        for group in self.recipient_groups_repo.list():
            self.saved_recipients.addItem(group["name"], group)

    def _load_recipient_group(self):
        group = self.saved_recipients.currentData()
        if group:
            self.recipient_editors[0].set_values(group["to"], group["cc"], group["bcc"])

    def _save_recipient_group(self):
        try:
            group = self._recipient_group(self.recipient_editors[0])
        except ValueError as exc:
            self.status.setText(str(exc)); return
        name, accepted = QInputDialog.getText(self, "Lưu recipient group", "Tên nhóm:")
        if accepted and name.strip():
            self.recipient_groups_repo.save(name, group["to"], group["cc"], group["bcc"])
            self._refresh_saved_groups(); self.status.setText(f"Đã lưu recipient group: {name.strip()}")

    def _delete_recipient_group(self):
        name = self.saved_recipients.currentText()
        if name:
            self.recipient_groups_repo.delete(name); self._refresh_saved_groups()

    def _recipient_group(self, editor):
        group = {key: getattr(editor, key).emails() for key in ("to", "cc", "bcc")}
        for key in ("to", "cc", "bcc"):
            field = getattr(editor, key)
            pending = field.input.text().strip()
            if pending:
                if not field._valid(pending):
                    field._set_error()
                    raise ValueError(f"{editor.title.text()}: Email không hợp lệ trong {key.upper()}.")
                field.commit_input()
                group[key] = field.emails()
        if not group["to"]:
            raise ValueError(f"{editor.title.text()}: TO không được để trống.")
        if any(len(values) != len(set(values)) for values in group.values()):
            raise ValueError(f"{editor.title.text()}: địa chỉ email bị trùng trong cùng loại người nhận.")
        return group

    def _select_template(self, index):
        while self.variable_form.rowCount(): self.variable_form.removeRow(0)
        self.variables.clear()
        if not 0 <= index < len(self.records):
            self._render_preview(); self._update_send_enabled(); return
        record = self.records[index]; self.subject.setText(record["subject"])
        keys = TemplateVariableResolver.extract_variables(record["subject"] + "\n" + record["html_content"])
        for key in keys:
            if key in self.SYSTEM_VARIABLES:
                continue
            entry = QLineEdit(); entry.setPlaceholderText(key); entry.textChanged.connect(self._schedule_preview)
            self.variables[key] = entry; self.variable_form.addRow(key, entry)
        self._render_preview(); self._update_send_enabled()

    def _schedule_preview(self, *_): self.timer.start()

    def _groups_for_preview(self):
        groups = []
        for editor in self.recipient_editors:
            groups.append({key: "; ".join(getattr(editor, key).emails() + ([getattr(editor, key).input.text().strip()]
                               if getattr(editor, key).input.text().strip() else []))
                           for key in ("to", "cc", "bcc")})
        return groups

    def _values(self):
        selected_account = self.accounts_by_id.get(self.account_combo.currentData(), {})
        email = selected_account.get("email", "")
        current_date = datetime.now().strftime("%d/%m/%Y")
        values = {"date": current_date, "report_date": current_date,
                  "record_count": len(self.selected_record_ids), "selected_count": len(self.selected_record_ids),
                  "sender_name": email, "email": email, "name": email,
                  "company": "SPX Reconciliation Report", "workspace_name": self.workspace_name}
        values.update(self.summary_values)
        values.update({key: editor.text().strip() for key, editor in self.variables.items()})
        return values

    def _resolved(self):
        index = self.template_combo.currentIndex()
        if not 0 <= index < len(self.records):
            return "", ""
        record = self.records[index]; values = self._values()
        subject = TemplateVariableResolver.resolve(self.subject.text(), values, escape_html=False)
        body = TemplateVariableResolver.resolve(record["html_content"], values)
        return subject, sanitize_preview_html(body)

    def _render_preview(self):
        subject, body = self._resolved()
        from_account = self.accounts_by_id.get(self.account_combo.currentData(), {}).get("email", "—")
        groups = self._groups_for_preview()
        recipients = {key: "; ".join(value[key] for value in groups if value[key]) or "—"
                      for key in ("to", "cc", "bcc")}
        self.preview_from.setText(f"From: {from_account}")
        self.preview_to.setText(f"To: {recipients['to']}")
        self.preview_cc.setText(f"CC: {recipients['cc']}")
        self.preview_bcc.setText(f"BCC: {recipients['bcc']}")
        self.preview_subject.setText(f"Subject: {subject or '—'}")
        self.preview_attachment.setText(
            f"Attachment: {self.attachment_path.name} · {len(self.selected_record_ids):,} records"
            if self.attachment_path else "Attachment: —"
        )
        if "<html" not in body.casefold():
            body = f"<!doctype html><html><head><meta charset='utf-8'></head><body>{body}</body></html>"
        self.preview.setHtml(body)

    def _update_send_enabled(self):
        ready = bool(self.selected_record_ids and self.attachment_path and self.attachment_path.is_file()
                     and self.account_combo.currentData() and self.template_combo.currentData())
        self.send_button.setEnabled(ready)
        self._update_action_summary()

    def _update_action_summary(self):
        records = len(self.selected_record_ids)
        groups = len(self.recipient_editors)
        self.action_summary.setText(f"{records:,} records · {groups} recipient group{'s' if groups != 1 else ''}")

    def send(self):
        if not self.selected_record_ids:
            self.status.setText("Chưa chọn bản ghi từ Main Data."); return
        account_id = self.account_combo.currentData()
        if not account_id:
            self.status.setText("Hãy chọn hoặc kết nối sender account."); return
        if not self.template_combo.currentData():
            self.status.setText("Hãy chọn Email Template."); return
        if not self.attachment_path or not self.attachment_path.is_file():
            self.status.setText("Chưa tạo được file Excel đính kèm."); return
        try:
            groups = [self._recipient_group(editor) for editor in self.recipient_editors]
            subject, body = self._resolved()
            if not subject.strip(): raise ValueError("Subject email không được để trống.")
            unresolved = TemplateVariableResolver.extract_variables(subject + "\n" + body)
            if unresolved: raise ValueError("Template còn biến chưa render: " + ", ".join(unresolved))
        except ValueError as exc:
            self.status.setText(str(exc)); return
        recipient_total = sum(len(group[key]) for group in groups for key in ("to", "cc", "bcc"))
        detail = (f"Bạn chuẩn bị gửi {len(groups)} email tới {recipient_total} địa chỉ.\n"
                  f"File Excel gồm {len(self.selected_record_ids):,} records sẽ được đính kèm:\n"
                  f"{self.attachment_path.name}\n\nBạn có chắc chắn muốn gửi?")
        confirm = QMessageBox.question(self, "Xác nhận gửi email", detail,
                                       QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
                                       QMessageBox.StandardButton.Cancel)
        if confirm != QMessageBox.StandardButton.Yes: return
        template_id = self.template_combo.currentData(); self.send_button.setEnabled(False)
        self.gmail.setEnabled(False); self.progress.setRange(0, len(groups))
        self.progress.setValue(0); self.progress.show(); self.status.setText("Sending emails… 0 / " + str(len(groups)))
        worker = FunctionWorker(self._send_job, account_id, groups, subject, body,
                                template_id, str(self.attachment_path), tuple(self.selected_record_ids), self.workspace_id)
        worker.kwargs["progress_callback"] = lambda done, total: worker.signals.progress.emit((done, total))
        worker.signals.progress.connect(self._send_progress)
        worker.signals.result.connect(self._sent)
        worker.signals.error.connect(lambda error: self._send_error(error.splitlines()[0]))
        self.send_worker = worker; self.pool.start(worker)

    def _send_job(self, account_id, groups, subject, body, template_id, attachment,
                  selected_ids, workspace_id, progress_callback=None):
        results = self.batch_service.send(account_id, groups, subject=subject, html_body=body,
                                          attachment_path=Path(attachment), progress=progress_callback)
        self.accounts.add_batch_history(workspace_id, account_id, template_id, subject,
                                        len(selected_ids), Path(attachment).name, groups, results)
        return results

    def _send_progress(self, progress):
        done, total = progress; self.progress.setValue(done)
        self.status.setText(f"Sending emails… {done} / {total} emails sent")

    def _sent(self, results):
        success = sum(item["status"] == "SENT" for item in results); failed = len(results) - success
        self.progress.hide(); self.send_button.setEnabled(True); self.gmail.setEnabled(True)
        self.status.setText(f"Email sending completed · Success: {success} · Failed: {failed}")
        self.refresh_history()
        if failed:
            failures = []
            for index, result in enumerate(results, 1):
                if result["status"] == "FAILED":
                    addresses = ", ".join(result["to"] + result["cc"] + result["bcc"])
                    failures.append(f"Destination {index} ({addresses})\nReason: {result['error']}")
            QMessageBox.warning(self, "Kết quả gửi email", self.status.text() + "\n\n" + "\n\n".join(failures))
        else:
            QMessageBox.information(self, "Kết quả gửi email", self.status.text())

    def _send_error(self, message):
        self.progress.hide(); self.send_button.setEnabled(True); self.gmail.setEnabled(True)
        self.status.setText("Không thể hoàn tất batch: " + message)

    def refresh_history(self):
        self.history.clear()
        for row in self.accounts.history(5):
            item = QListWidgetItem(
                f"{row['sent_at'][:16]} · {row['status']} · {row['subject']} · "
                f"{row.get('success_count', 0)}/{row.get('success_count', 0) + row.get('failed_count', 0)} emails"
            )
            item.setData(Qt.ItemDataRole.UserRole, row["id"]); self.history.addItem(item)
        self.history.setVisible(self.history.count() > 0)

    def _show_history_details(self, item):
        rows = self.accounts.recipient_history(item.data(Qt.ItemDataRole.UserRole))
        if not rows:
            QMessageBox.information(self, "Lịch sử gửi", "Lần gửi này không có chi tiết recipient (bản ghi lịch sử cũ).")
            return
        failed_rows = [row for row in rows if row["status"] == "FAILED"]
        if not failed_rows:
            QMessageBox.information(self, "Chi tiết lịch sử gửi", "Tất cả email trong lần gửi này đã gửi thành công.")
            return
        details = []
        for row in failed_rows:
            detail = (f"Group {row['recipient_group']} · {row['recipient_type']} · {row['email']} · {row['status']}")
            if row["error_message"]: detail += f"\nReason: {row['error_message']}"
            details.append(detail)
        QMessageBox.information(self, "Chi tiết lịch sử gửi", "\n\n".join(details))
