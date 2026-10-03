from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QProgressBar, QStyle, QStyleOptionButton, QHeaderView, QTableView, QVBoxLayout, QWidget)

from ..columns import COLUMNS
from .widgets.badge_delegate import BadgeDelegate
from .widgets.table_model import RecordsTableModel


class SelectionHeaderView(QHeaderView):
    select_all_clicked = Signal()

    def paintSection(self, painter: QPainter, rect, logical_index):
        super().paintSection(painter, rect, logical_index)
        if logical_index != 0:
            return
        state = self.model().headerData(0, Qt.Orientation.Horizontal, Qt.ItemDataRole.CheckStateRole)
        option = QStyleOptionButton()
        option.rect = rect.adjusted(9, 0, -rect.width() + 34, 0)
        option.state |= QStyle.StateFlag.State_Enabled
        if state == Qt.CheckState.Checked:
            option.state |= QStyle.StateFlag.State_On
        elif state == Qt.CheckState.PartiallyChecked:
            option.state |= QStyle.StateFlag.State_NoChange
        else:
            option.state |= QStyle.StateFlag.State_Off
        self.style().drawControl(QStyle.ControlElement.CE_CheckBox, option, painter, self)
        painter.save()
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(rect.adjusted(34, 0, -5, 0), Qt.AlignmentFlag.AlignVCenter, "Select All")
        painter.restore()

    def mousePressEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and self.logicalIndexAt(event.pos()) == 0):
            self.select_all_clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class DataPage(QWidget):
    DEFAULT_WIDTHS = {
        "to_number": 160, "to_high_value": 145, "spx_tracking_number": 190,
        "order_high_value": 155, "to_status": 140, "high_value": 125,
        "sender_id": 145, "sender_name": 190, "sender_type": 130,
        "sender_station_type": 170, "receiver_id": 145, "receiver_name": 190,
        "receiver_type": 140, "receiver_station_type": 175, "current_station": 185,
        "to_order_quantity": 150, "to_direction": 140, "line_haul_trip_number": 180,
        "create_time": 165, "complete_time": 165, "driver_scan_time": 175,
        "receive_status": 150, "exception_tag": 150, "packing_method": 155,
        "dangerous_goods": 150,
    }
    search_changed = Signal(str)
    import_requested = Signal()
    filter_requested = Signal()
    columns_requested = Signal()
    reset_requested = Signal()
    page_requested = Signal(int)
    row_activated = Signal(int)
    select_all_requested = Signal()
    clear_selection_requested = Signal()
    send_email_requested = Signal()
    selected_ids_changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(14)
        header = QHBoxLayout(); title_box = QVBoxLayout()
        self.title = QLabel("Workspace"); self.title.setObjectName("dataPageTitle")
        self.metadata = QLabel(""); self.metadata.setProperty("muted", True)
        self.metadata.setObjectName("dataPageSubtitle")
        title_box.setSpacing(3)
        title_box.addWidget(self.title); title_box.addWidget(self.metadata)
        header.addLayout(title_box); header.addStretch()
        self.import_button = QPushButton("Import Excel"); self.import_button.setProperty("primary", True)
        self.import_button.setMinimumWidth(132)
        self.import_button.clicked.connect(self.import_requested); header.addWidget(self.import_button); root.addLayout(header)
        card = QFrame(); card.setObjectName("dataTableCard"); card.setProperty("card", True)
        body = QVBoxLayout(card); body.setContentsMargins(14, 14, 14, 12); body.setSpacing(10)
        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.search = QLineEdit(); self.search.setObjectName("dataSearch")
        self.search.setPlaceholderText("Tìm mã vận đơn, người gửi, trạm…"); self.search.setClearButtonEnabled(True)
        self.search.setMinimumHeight(40)
        self.search.textChanged.connect(self.search_changed); controls.addWidget(self.search, 1)
        self.filter_button, self.columns_button, self.reset_button = QPushButton("Lọc"), QPushButton("Cột"), QPushButton("Xóa bộ lọc")
        for button in (self.filter_button, self.columns_button, self.reset_button):
            button.setMinimumHeight(40); controls.addWidget(button)
        self.filter_button.clicked.connect(self.filter_requested); self.columns_button.clicked.connect(self.columns_requested)
        self.reset_button.clicked.connect(self.reset_requested); body.addLayout(controls)
        self.active_filters = QLabel(""); self.active_filters.setObjectName("activeFilterSummary")
        self.active_filters.setProperty("muted", True); self.active_filters.hide(); body.addWidget(self.active_filters)
        self.selection_bar = QFrame(); self.selection_bar.setObjectName("selectionActionBar")
        selection_layout = QHBoxLayout(self.selection_bar); selection_layout.setContentsMargins(12, 7, 10, 7)
        self.selection_summary = QLabel("Đã chọn: 0 bản ghi"); self.selection_summary.setObjectName("selectionSummary")
        selection_layout.addWidget(self.selection_summary); selection_layout.addStretch()
        self.clear_selection_button = QPushButton("Bỏ chọn"); self.clear_selection_button.clicked.connect(self.clear_selection_requested)
        self.send_email_button = QPushButton("Gửi Email"); self.send_email_button.setProperty("primary", True)
        self.send_email_button.clicked.connect(self.send_email_requested)
        selection_layout.addWidget(self.clear_selection_button); selection_layout.addWidget(self.send_email_button)
        self.selection_bar.hide(); body.addWidget(self.selection_bar)
        self.progress = QProgressBar(); self.progress.setObjectName("tableLoadingBar")
        self.progress.setRange(0, 0); self.progress.setTextVisible(False); self.progress.hide(); body.addWidget(self.progress)
        self.model = RecordsTableModel(COLUMNS, parent=self); self.table = QTableView(); self.table.setModel(self.model)
        self.table.setObjectName("recordsTable")
        self.table.setHorizontalHeader(SelectionHeaderView(Qt.Orientation.Horizontal, self.table))
        self.table.horizontalHeader().select_all_clicked.connect(self.select_all_requested)
        self.model.selection_changed.connect(self.selected_ids_changed)
        self.table.setItemDelegate(BadgeDelegate(self.table))
        self.table.setAlternatingRowColors(True); self.table.setSelectionMode(QTableView.SelectionMode.NoSelection); self.table.setWordWrap(False)
        self.table.setShowGrid(False)
        self.table.setVerticalScrollMode(QTableView.ScrollMode.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QTableView.ScrollMode.ScrollPerPixel)
        self.table.setCornerButtonEnabled(False)
        header_view = self.table.horizontalHeader()
        header_view.setSectionsMovable(True); header_view.setHighlightSections(False)
        header_view.setMinimumSectionSize(90); header_view.setDefaultSectionSize(150)
        header_view.setSectionResizeMode(header_view.ResizeMode.Interactive)
        header_view.setSortIndicatorShown(True)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.verticalHeader().setMinimumWidth(48)
        self.table.verticalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.doubleClicked.connect(lambda idx: self.row_activated.emit(idx.row())); body.addWidget(self.table, 1)
        foot = QHBoxLayout(); self.count_label = QLabel("Đang tải…"); self.page_label = QLabel("")
        foot.addWidget(self.count_label); foot.addStretch()
        self.previous, self.next = QPushButton("← Trước"), QPushButton("Tiếp →")
        self.previous.clicked.connect(lambda: self.page_requested.emit(-1)); self.next.clicked.connect(lambda: self.page_requested.emit(1))
        foot.addWidget(self.previous); foot.addWidget(self.page_label); foot.addWidget(self.next); body.addLayout(foot)
        root.addWidget(card, 1)

    def set_loading(self, loading, message="Đang xử lý…"):
        self.progress.setToolTip(message); self.progress.setVisible(loading); self.import_button.setEnabled(not loading)

    def set_records(self, columns, rows, total, page, page_size, widths=None, scope_ids=None):
        self.model.columns = list(columns); self.model.replace(rows)
        self.model.set_scope_ids(scope_ids or ())
        self.count_label.setText(f"{total:,} bản ghi")
        pages = max(1, (total + page_size - 1) // page_size)
        self.page_label.setText(f"Trang {page + 1:,} / {pages:,}")
        self.previous.setEnabled(page > 0); self.next.setEnabled(page + 1 < pages)
        widths = widths or {}
        self.table.setColumnWidth(0, 128)
        for index, column in enumerate(columns, 1):
            default = self.DEFAULT_WIDTHS.get(column.field, 135 if column.kind == "text" else 105)
            self.table.setColumnWidth(index, int(widths.get(column.field, default)))

    def set_selection_summary(self, count):
        self.selection_summary.setText(f"Đã chọn: {count:,} bản ghi")
        self.selection_bar.setVisible(count > 0)
        self.send_email_button.setEnabled(count > 0)

    def set_selected_ids(self, ids):
        self.model.update_selection(ids)

    def selected_record(self):
        indexes = self.table.selectionModel().selectedRows()
        return self.model.rows[indexes[0].row()] if indexes else None
