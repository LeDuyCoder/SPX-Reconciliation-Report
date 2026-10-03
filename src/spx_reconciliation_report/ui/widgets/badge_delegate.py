from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem


class BadgeDelegate(QStyledItemDelegate):
    """Render categorical table values as compact, rounded badges."""

    BADGE_FIELDS = {
        "to_status", "receive_status", "sender_type", "receiver_type",
        "sender_station_type", "receiver_station_type", "to_high_value",
        "order_high_value", "to_direction", "journey_type",
        "dangerous_goods", "exception_tag", "packing_method",
    }

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        # Native focus cues can appear as thin blue bars between cells on
        # Windows. The table's selected-row styling provides the focus cue.
        option = QStyleOptionViewItem(option)
        option.state &= ~QStyle.StateFlag.State_HasFocus
        if index.column() == 0:
            super().paint(painter, option, index)
            return
        model = index.model()
        column = model.columns[index.column() - 1]
        if column.field not in self.BADGE_FIELDS:
            super().paint(painter, option, index)
            return

        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "").strip()
        style = option.widget.style() if option.widget else None
        background_option = QStyleOptionViewItem(option)
        background_option.text = ""
        if style:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, background_option, painter, option.widget)
        if not text:
            return

        foreground, background = self._colors(column.field, text)
        rect = option.rect.adjusted(5, 5, -5, -5)
        metrics = painter.fontMetrics()
        width = min(metrics.horizontalAdvance(text) + 18, rect.width())
        height = min(23, rect.height())
        chip = rect
        chip.setWidth(width)
        chip.setHeight(height)
        chip.moveCenter(option.rect.center())

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(chip, height / 2, height / 2)
        painter.setPen(foreground)
        painter.drawText(chip, Qt.AlignmentFlag.AlignCenter, metrics.elidedText(text, Qt.TextElideMode.ElideRight, max(0, width - 12)))
        painter.restore()

    @staticmethod
    def _colors(field: str, text: str) -> tuple[QColor, QColor]:
        value = text.casefold()
        if field in {"to_high_value", "order_high_value", "dangerous_goods"}:
            positive = value in {"y", "yes", "true", "1", "có", "dangerous"}
            return ((QColor("#8B4936"), QColor("#F8E9E4")) if positive
                    else (QColor("#697580"), QColor("#F0F2F3")))
        if any(word in value for word in ("exception", "fail", "cancel", "reject", "error")):
            return QColor("#A6463D"), QColor("#FBECEA")
        if any(word in value for word in ("complete", "received", "success", "delivered")):
            return QColor("#287657"), QColor("#EAF5EF")
        if any(word in value for word in ("transport", "transit", "ship", "moving")):
            return QColor("#356B9A"), QColor("#EAF2F9")
        if any(word in value for word in ("pending", "process", "created", "wait")):
            return QColor("#93662C"), QColor("#FBF3E5")
        if field.endswith("type") or field in {"to_direction", "journey_type", "packing_method"}:
            return QColor("#65538D"), QColor("#F1EDFA")
        return QColor("#55636F"), QColor("#EFF2F4")
