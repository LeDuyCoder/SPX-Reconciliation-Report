from __future__ import annotations
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QFrame,
    QGraphicsOpacityEffect,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)


class WorkspaceDialog(QDialog):
    def __init__(self, parent=None, title="Workspace", name="", description=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setObjectName("workspaceDialog")
        self.setMinimumWidth(470)
        self.resize(500, 390)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 23, 26, 22)
        layout.setSpacing(10)

        eyebrow = QLabel("WORKSPACE")
        eyebrow.setObjectName("dialogEyebrow")
        layout.addWidget(eyebrow)

        heading = QLabel("Thông tin workspace")
        heading.setObjectName("dialogHeading")
        layout.addWidget(heading)

        hint = QLabel("Cập nhật tên và mô tả để dễ nhận biết workspace.")
        hint.setObjectName("dialogHint")
        layout.addWidget(hint)
        layout.addSpacing(8)

        name_label = QLabel("Tên workspace")
        name_label.setObjectName("dialogFieldLabel")
        layout.addWidget(name_label)
        self.name = QLineEdit(name)
        self.name.setObjectName("workspaceNameInput")
        self.name.setPlaceholderText("Nhập tên workspace")
        self.name.setMinimumHeight(42)
        self.name.setClearButtonEnabled(True)
        layout.addWidget(self.name)

        description_label = QLabel("Mô tả")
        description_label.setObjectName("dialogFieldLabel")
        layout.addWidget(description_label)
        self.description = QPlainTextEdit(description)
        self.description.setObjectName("workspaceDescriptionInput")
        self.description.setPlaceholderText("Thêm mô tả ngắn (không bắt buộc)")
        self.description.setMinimumHeight(100)
        layout.addWidget(self.description)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 8, 0, 0)
        footer.setSpacing(10)
        footer.addStretch()
        cancel = QPushButton("Hủy")
        cancel.setObjectName("dialogCancelButton")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Lưu thay đổi" if name else "Tạo workspace")
        save.setObjectName("dialogSaveButton")
        save.setProperty("primary", True)
        save.setDefault(True)
        save.clicked.connect(self.accept)
        footer.addWidget(cancel)
        footer.addWidget(save)
        layout.addLayout(footer)


class DeleteWorkspaceDialog(QDialog):
    def __init__(self, parent=None, workspace_name=""):
        super().__init__(parent)
        self.setWindowTitle("Xóa workspace")
        self.setObjectName("workspaceDeleteDialog")
        self.setMinimumWidth(440)
        self.resize(460, 270)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(14)
        icon = QLabel("!")
        icon.setObjectName("deleteWarningIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(46, 46)
        header.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        copy = QVBoxLayout()
        copy.setSpacing(5)
        heading = QLabel("Xóa workspace này?")
        heading.setObjectName("deleteDialogHeading")
        copy.addWidget(heading)
        name = QLabel(workspace_name or "Workspace")
        name.setObjectName("deleteWorkspaceName")
        name.setWordWrap(True)
        copy.addWidget(name)
        header.addLayout(copy, 1)
        layout.addLayout(header)

        detail = QLabel("Workspace và dữ liệu đã nhập liên quan sẽ bị xóa. Thao tác này không thể hoàn tác.")
        detail.setObjectName("deleteDialogHint")
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
        delete = QPushButton("Xóa workspace")
        delete.setObjectName("deleteWorkspaceButton")
        delete.setProperty("destructive", True)
        delete.clicked.connect(self.accept)
        footer.addWidget(cancel)
        footer.addWidget(delete)
        layout.addLayout(footer)


class WorkspaceCard(QFrame):
    open_requested = Signal(str)
    rename_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, record, parent=None):
        super().__init__(parent)
        self.setProperty("workspaceCard", True)
        self._entrance_animation = None
        row = QHBoxLayout(self)
        row.setContentsMargins(20, 16, 18, 16)
        row.setSpacing(16)
        marker = QLabel("SPX")
        marker.setProperty("workspaceMarker", True)
        marker.setAlignment(Qt.AlignmentFlag.AlignCenter)
        marker.setFixedSize(42, 42)
        row.addWidget(marker, 0, Qt.AlignmentFlag.AlignVCenter)
        info = QVBoxLayout()
        info.setSpacing(6)
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title = QLabel(record.get("name") or "Workspace")
        title.setProperty("workspaceTitle", True)
        count = QLabel(f"{record.get('total_records', 0):,} bản ghi")
        count.setProperty("countBadge", True)
        title_row.addWidget(title)
        title_row.addWidget(count)
        title_row.addStretch()
        info.addLayout(title_row)
        description = QLabel(record.get("description") or "Chưa có mô tả")
        description.setProperty("muted", True)
        description.setWordWrap(True)
        info.addWidget(description)
        filename = record.get("last_file_name") or "Chưa nhập dữ liệu"
        imported = (record.get("last_imported_at") or "").replace("T", " ")[:16]
        detail = f"Tệp gần nhất  ·  {filename}" + (
            f"     /     Nhập lúc {imported}" if imported else ""
        )
        file_label = QLabel(detail)
        file_label.setProperty("workspaceDetail", True)
        file_label.setToolTip(detail)
        info.addWidget(file_label)
        row.addLayout(info, 1)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        open_button = QPushButton("Mở workspace")
        open_button.setProperty("primary", True)
        rename_button = QPushButton("Đổi tên")
        delete_button = QPushButton("Xóa")
        delete_button.setProperty("quietAction", True)
        for button in (open_button, rename_button, delete_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            actions.addWidget(button)
        row.addLayout(actions)
        wid = record["id"]
        open_button.clicked.connect(lambda: self.open_requested.emit(wid))
        rename_button.clicked.connect(lambda: self.rename_requested.emit(wid))
        delete_button.clicked.connect(lambda: self.delete_requested.emit(wid))

    def animate_in(self, delay=0):
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        effect.setOpacity(0)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(320)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._entrance_animation = animation
        QTimer.singleShot(delay, animation.start)


class WorkspacesPage(QWidget):
    open_requested = Signal(str)
    create_requested = Signal()
    rename_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 0)
        layout.setSpacing(0)
        head = QHBoxLayout()
        head.setSpacing(20)
        group = QVBoxLayout()
        group.setSpacing(5)
        title = QLabel("Workspaces")
        title.setObjectName("workspacePageTitle")
        group.addWidget(title)
        self.summary = QLabel(
            "Quản lý các dự án và dữ liệu đối soát trên thiết bị này."
        )
        self.summary.setObjectName("workspaceSummary")
        group.addWidget(self.summary)
        head.addLayout(group)
        head.addStretch()
        self.create_button = QPushButton("＋  Tạo workspace")
        self.create_button.setProperty("primary", True)
        self.create_button.setObjectName("workspaceCreateButton")
        self.create_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.create_button.clicked.connect(self.create_requested)
        head.addWidget(self.create_button, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(head)
        layout.addSpacing(30)
        section = QHBoxLayout()
        section.setContentsMargins(2, 0, 2, 10)
        section_title = QLabel("DANH SÁCH WORKSPACE")
        section_title.setObjectName("workspaceSectionTitle")
        section.addWidget(section_title)
        section.addStretch()
        self.workspace_count = QLabel("0 workspace")
        self.workspace_count.setObjectName("workspaceCount")
        section.addWidget(self.workspace_count)
        layout.addLayout(section)
        self.list = QListWidget()
        self.list.setObjectName("workspaceList")
        self.list.setSpacing(10)
        self.list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        layout.addWidget(self.list, 1)

    def set_workspaces(self, records):
        self.list.clear()
        total = sum(record.get("total_records", 0) for record in records)
        self.workspace_count.setText(f"{len(records)} workspace")
        self.summary.setText(
            f"{len(records)} workspace  ·  {total:,} bản ghi đang được quản lý trên thiết bị này."
            if records
            else "Quản lý các dự án và dữ liệu đối soát trên thiết bị này."
        )
        if not records:
            item = QListWidgetItem()
            item.setSizeHint(QSize(300, 176))
            self.list.addItem(item)
            empty = QWidget()
            box = QVBoxLayout(empty)
            box.setContentsMargins(20, 22, 20, 22)
            box.setSpacing(8)
            box.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title = QLabel("Chưa có workspace")
            title.setProperty("workspaceTitle", True)
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            subtitle = QLabel("Tạo workspace để bắt đầu nhập và đối soát dữ liệu.")
            subtitle.setProperty("muted", True)
            subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(title)
            box.addWidget(subtitle)
            empty.setProperty("emptyWorkspace", True)
            self.list.setItemWidget(item, empty)
            return
        for index, record in enumerate(records):
            item = QListWidgetItem()
            item.setSizeHint(QSize(300, 124))
            self.list.addItem(item)
            card = WorkspaceCard(record, self.list)
            card.open_requested.connect(self.open_requested)
            card.rename_requested.connect(self.rename_requested)
            card.delete_requested.connect(self.delete_requested)
            self.list.setItemWidget(item, card)
            card.animate_in(min(index * 65, 260))
