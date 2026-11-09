"""焊点人工标注软件：图片浏览与人工红圈标注。

项目仅索引外部图片和清单；人工红圈保存到 Software/projects 中的 SQLite，源文件保持不变。
"""

from __future__ import annotations

import sys
import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from project_store import (
    ImportPreview,
    Annotation,
    ImageRecord,
    ProjectSummary,
    WeldRecord,
    bind_annotation,
    bound_weld_serials,
    create_annotation,
    create_project,
    delete_annotation,
    export_confirmed_annotations,
    export_preflight,
    get_project_settings,
    list_columns,
    load_annotations,
    load_all_annotations,
    load_images,
    list_projects,
    load_welds,
    list_sheets,
    make_preview,
    read_weld_records,
    scan_images,
    preview_image_supplement,
    supplement_images,
    restore_annotations,
    set_project_settings,
    update_annotation,
    unbind_annotation,
)


APP_NAME = "焊点人工标注"


STYLE = """
QMainWindow {
    background: #F4F7FB;
}
QWidget {
    color: #1F2937;
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
}
QFrame#sidebar {
    background: #12233F;
}
QLabel#brandTitle {
    color: white;
    font-size: 21px;
    font-weight: 700;
}
QLabel#brandSubtitle {
    color: #9FB0C9;
    font-size: 11px;
}
QLabel#navSection {
    color: #8495AD;
    font-size: 10px;
    font-weight: 700;
    padding: 16px 14px 6px 14px;
}
QPushButton#navButton {
    background: transparent;
    color: #D5E0F0;
    border: 0;
    border-radius: 7px;
    min-height: 38px;
    padding: 0 14px;
    text-align: left;
    font-size: 13px;
}
QPushButton#navButton:hover {
    background: #203858;
}
QPushButton#navButton[active="true"] {
    background: #285A98;
    color: white;
    font-weight: 700;
}
QLabel#eyebrow {
    color: #5B6B82;
    font-size: 11px;
    font-weight: 700;
}
QLabel#pageTitle {
    color: #17243A;
    font-size: 26px;
    font-weight: 700;
}
QLabel#muted {
    color: #718096;
    font-size: 12px;
}
QFrame#card, QFrame#workspaceCard, QFrame#panel {
    background: white;
    border: 1px solid #E1E8F1;
    border-radius: 12px;
}
QLabel#cardValue {
    color: #1A365D;
    font-size: 26px;
    font-weight: 700;
}
QLabel#cardLabel {
    color: #66758A;
    font-size: 12px;
}
QLabel#sectionTitle {
    color: #26364E;
    font-size: 15px;
    font-weight: 700;
}
QPushButton#primaryButton {
    background: #1769AA;
    color: white;
    border: 0;
    border-radius: 7px;
    min-height: 34px;
    padding: 0 16px;
    font-weight: 700;
}
QPushButton#primaryButton:hover {
    background: #14598F;
}
QPushButton#secondaryButton {
    background: #F5F8FC;
    color: #35506F;
    border: 1px solid #D7E0EB;
    border-radius: 7px;
    min-height: 34px;
    padding: 0 14px;
}
QPushButton#secondaryButton:hover {
    background: #E9F0F8;
}
QLabel#badge {
    background: #E8F3FF;
    color: #1769AA;
    border-radius: 10px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 700;
}
QLabel#imageRow {
    border: 0;
    border-radius: 6px;
    padding: 9px 10px;
}
QLabel#imageRow[selected="true"] {
    background: #E9F3FF;
    color: #14598F;
    font-weight: 700;
}
QLabel#listRow {
    background: #F9FBFD;
    border: 1px solid #E4EAF1;
    border-radius: 7px;
    padding: 9px;
}
QFrame#bottomStatus {
    background: #FFFFFF;
    border-top: 1px solid #DFE6EF;
}
"""


def hbox(*, spacing: int = 0, margins: tuple[int, int, int, int] = (0, 0, 0, 0)) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setSpacing(spacing)
    layout.setContentsMargins(*margins)
    return layout


def vbox(*, spacing: int = 0, margins: tuple[int, int, int, int] = (0, 0, 0, 0)) -> QVBoxLayout:
    layout = QVBoxLayout()
    layout.setSpacing(spacing)
    layout.setContentsMargins(*margins)
    return layout


def label(text: str, object_name: str | None = None) -> QLabel:
    widget = QLabel(text)
    if object_name:
        widget.setObjectName(object_name)
    widget.setWordWrap(True)
    return widget


def button(text: str, object_name: str = "secondaryButton") -> QPushButton:
    widget = QPushButton(text)
    widget.setObjectName(object_name)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    return widget


def card(value: str, title: str, detail: str, color: str) -> QFrame:
    panel = QFrame()
    panel.setObjectName("card")
    panel.setMinimumWidth(178)
    layout = vbox(spacing=7, margins=(18, 16, 18, 16))
    accent = QFrame()
    accent.setFixedHeight(4)
    accent.setStyleSheet(f"background: {color}; border-radius: 2px;")
    layout.addWidget(accent)
    layout.addSpacing(4)
    layout.addWidget(label(value, "cardValue"))
    layout.addWidget(label(title, "cardLabel"))
    detail_label = label(detail, "muted")
    detail_label.setStyleSheet("font-size: 11px;")
    layout.addWidget(detail_label)
    panel.setLayout(layout)
    return panel


class PreviewCanvas(QGraphicsView):
    """仅用于阶段 1 的静态画布示意，不加载真实图片。"""

    def __init__(self) -> None:
        super().__init__()
        scene = QGraphicsScene(self)
        scene.setSceneRect(0, 0, 1080, 650)
        self.setScene(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QColor("#F8FAFD"))
        self._build_demo_scene(scene)

    def _build_demo_scene(self, scene: QGraphicsScene) -> None:
        background = QGraphicsRectItem(40, 35, 1000, 580)
        background.setBrush(QColor("#E8EEF5"))
        background.setPen(QPen(QColor("#D6E0EB"), 1))
        scene.addItem(background)

        # 用抽象分区代替真实车型图片，避免静态页面误用业务数据。
        for x, y, width, height in (
            (115, 125, 290, 115),
            (475, 90, 380, 150),
            (235, 335, 410, 150),
            (735, 365, 180, 110),
        ):
            block = QGraphicsRectItem(x, y, width, height)
            block.setBrush(QColor("#D4DFEA"))
            block.setPen(QPen(QColor("#C3D0DD"), 1))
            scene.addItem(block)

        for x, y, state, number in (
            (240, 185, "confirmed", "001"),
            (505, 145, "candidate", "010"),
            (735, 185, "candidate", "011"),
            (430, 390, "review", "待定"),
            (820, 422, "confirmed", "018"),
        ):
            colors = {
                "confirmed": ("#28A36A", "#DFF6EA"),
                "candidate": ("#D99816", "#FFF3D3"),
                "review": ("#D84B4B", "#FDE4E4"),
            }
            line, fill = colors[state]
            ellipse = QGraphicsEllipseItem(x - 26, y - 26, 52, 52)
            ellipse.setPen(QPen(QColor(line), 3))
            ellipse.setBrush(QColor(fill))
            scene.addItem(ellipse)
            number_text = QGraphicsTextItem(number)
            number_text.setDefaultTextColor(QColor(line))
            number_text.setFont(QFont("Microsoft YaHei UI", 9, QFont.Weight.DemiBold))
            number_text.setPos(x - 16, y - 11)
            scene.addItem(number_text)

        note = QGraphicsTextItem("静态预览：真实图片将在“导入项目”功能完成后显示")
        note.setDefaultTextColor(QColor("#708198"))
        note.setFont(QFont("Microsoft YaHei UI", 11))
        note.setPos(355, 545)
        scene.addItem(note)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


class AnnotationItem(QGraphicsEllipseItem):
    """一个可移动的人工红圈，几何数据以原图像素坐标保存。"""

    def __init__(self, annotation: Annotation, persist, changed, begin_change) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.annotation_id = annotation.annotation_id
        self.weld_serial = annotation.weld_serial
        self.status = annotation.status
        self.radius_x = annotation.radius_x
        self.radius_y = annotation.radius_y
        self._persist = persist
        self._changed = changed
        self._begin_change = begin_change
        self.setRect(-self.radius_x, -self.radius_y, self.radius_x * 2, self.radius_y * 2)
        self.setPos(annotation.center_x, annotation.center_y)
        self.serial_label = QGraphicsTextItem(self)
        self.serial_label.setFont(QFont("Microsoft YaHei UI", 9, QFont.Weight.DemiBold))
        self.serial_label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(10)
        self._apply_style()

    def _apply_style(self) -> None:
        if self.weld_serial is None:
            line, fill, text = "#D94242", QColor(255, 238, 238, 50), ""
        else:
            line, fill, text = "#1E9B63", QColor(224, 247, 234, 75), f"{self.weld_serial:03d}"
        self.setPen(QPen(QColor(line), 4))
        self.setBrush(fill)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, self.weld_serial is None)
        self.serial_label.setDefaultTextColor(QColor(line))
        self.serial_label.setPlainText(text)
        self.serial_label.setPos(-self.serial_label.boundingRect().width() / 2, -self.serial_label.boundingRect().height() / 2)

    def set_binding(self, weld_serial: int | None) -> None:
        self.weld_serial = weld_serial
        self.status = "confirmed" if weld_serial is not None else "draft"
        self._apply_style()

    def set_radius(self, radius_x: float, radius_y: float) -> None:
        self.radius_x = max(8.0, radius_x)
        self.radius_y = max(8.0, radius_y)
        self.setRect(-self.radius_x, -self.radius_y, self.radius_x * 2, self.radius_y * 2)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().mouseReleaseEvent(event)
        self._persist(self)
        self._changed()

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() == Qt.MouseButton.LeftButton and self.weld_serial is None:
            self._begin_change()
        super().mousePressEvent(event)


class AnnotationCanvas(QGraphicsView):
    """显示项目原图并保存人工红圈；不修改源图片。"""

    def __init__(self, changed, begin_change=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self._changed = changed
        self._begin_change = begin_change or (lambda: None)
        self._project: ProjectSummary | None = None
        self._image: ImageRecord | None = None
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._items: dict[int, AnnotationItem] = {}
        self._space_down = False
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setBackgroundBrush(QColor("#F1F4F8"))
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

    def clear_project(self) -> None:
        self.scene().clear()
        self._project = None
        self._image = None
        self._pixmap_item = None
        self._items.clear()

    def load_image(self, project: ProjectSummary, image: ImageRecord) -> None:
        self.scene().clear()
        self._items.clear()
        self._project = project
        self._image = image
        pixmap = QPixmap(str(image.original_path))
        if pixmap.isNull():
            message = QGraphicsTextItem(f"无法读取图片：\n{image.original_path}")
            message.setDefaultTextColor(QColor("#B42318"))
            message.setPos(30, 30)
            self.scene().addItem(message)
            self.scene().setSceneRect(0, 0, 800, 500)
            return
        self._pixmap_item = self.scene().addPixmap(pixmap)
        self._pixmap_item.setZValue(0)
        self.scene().setSceneRect(self._pixmap_item.boundingRect())
        for annotation in load_annotations(project, image.image_index):
            self._add_annotation_item(annotation)
        self.fit_image()
        self._changed()

    def fit_image(self) -> None:
        if not self.scene().sceneRect().isNull():
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def zoom_by(self, factor: float) -> None:
        if self._pixmap_item is not None:
            self.scale(factor, factor)

    def selected_item(self) -> AnnotationItem | None:
        selected = [item for item in self.scene().selectedItems() if isinstance(item, AnnotationItem)]
        return selected[0] if selected else None

    def clear_selection(self) -> None:
        self.scene().clearSelection()

    def delete_selected(self) -> bool:
        selected = self.selected_item()
        if selected is None or self._project is None or selected.weld_serial is not None:
            return False
        self._begin_change()
        delete_annotation(self._project, selected.annotation_id)
        self.scene().removeItem(selected)
        self._items.pop(selected.annotation_id, None)
        self._changed()
        return True

    def adjust_selected_radius(self, offset: float) -> bool:
        return self.adjust_selected_radius_xy(offset, offset)

    def adjust_selected_radius_xy(self, offset_x: float, offset_y: float) -> bool:
        selected = self.selected_item()
        if selected is None or selected.weld_serial is not None:
            return False
        self._begin_change()
        selected.set_radius(selected.radius_x + offset_x, selected.radius_y + offset_y)
        self._persist_item(selected)
        self._changed()
        return True

    def selected_item_is_locked(self) -> bool:
        selected = self.selected_item()
        return selected is not None and selected.weld_serial is not None

    def bind_selected(self, weld_serial: int) -> bool:
        selected = self.selected_item()
        if selected is None or self._project is None:
            return False
        self._begin_change()
        bind_annotation(self._project, selected.annotation_id, weld_serial)
        selected.set_binding(weld_serial)
        self._changed()
        return True

    def unbind_selected(self) -> bool:
        selected = self.selected_item()
        if selected is None or self._project is None or selected.weld_serial is None:
            return False
        self._begin_change()
        unbind_annotation(self._project, selected.annotation_id)
        selected.set_binding(None)
        self._changed()
        return True

    def annotation_count(self) -> int:
        return len(self._items)

    def bound_annotation_count(self) -> int:
        return sum(item.weld_serial is not None for item in self._items.values())

    def _add_annotation_item(self, annotation: Annotation) -> AnnotationItem:
        item = AnnotationItem(annotation, self._persist_item, self._changed, self._begin_change)
        self.scene().addItem(item)
        self._items[annotation.annotation_id] = item
        return item

    def _persist_item(self, item: AnnotationItem) -> None:
        if self._project is None or self._pixmap_item is None:
            return
        bounds = self._pixmap_item.boundingRect()
        x = min(max(item.pos().x(), item.radius_x), max(item.radius_x, bounds.width() - item.radius_x))
        y = min(max(item.pos().y(), item.radius_y), max(item.radius_y, bounds.height() - item.radius_y))
        if x != item.pos().x() or y != item.pos().y():
            item.setPos(x, y)
        update_annotation(self._project, item.annotation_id, x, y, item.radius_x, item.radius_y)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.setFocus()
        if event.button() == Qt.MouseButton.LeftButton and not self._space_down and self._project and self._image and self._pixmap_item:
            picked = [item for item in self.items(event.pos()) if isinstance(item, AnnotationItem)]
            if picked:
                self.clear_selection()
                picked[0].setSelected(True)
            if not picked:
                point = self.mapToScene(event.pos())
                if self._pixmap_item.boundingRect().contains(point):
                    self._begin_change()
                    annotation = create_annotation(self._project, self._image.image_index, point.x(), point.y())
                    item = self._add_annotation_item(annotation)
                    item.setSelected(True)
                    self._changed()
                    event.accept()
                    return
        super().mousePressEvent(event)

    def wheelEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._pixmap_item is None:
            super().wheelEvent(event)
            return
        self.zoom_by(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
        event.accept()

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.key() == Qt.Key.Key_Space:
            self._space_down = True
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self.delete_selected():
                event.accept()
                return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.key() == Qt.Key.Key_Space:
            self._space_down = False
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)


class ImportProjectDialog(QDialog):
    """导入向导：只创建项目索引，不改写图片或清单源文件。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("新建项目 · 导入图片与手持清单")
        self.setMinimumWidth(640)
        self.setModal(True)

        root = vbox(spacing=14, margins=(24, 22, 24, 20))
        root.addWidget(label("新建标注项目", "pageTitle"))
        root.addWidget(label("只读取所选的图片与清单文件；项目索引保存到 Software\\projects，不会复制或修改源文件。", "muted"))

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("例如：BF_BR")
        self.image_path = QLineEdit()
        self.image_path.setReadOnly(True)
        self.list_path = QLineEdit()
        self.list_path.setReadOnly(True)
        self.sheet_combo = QComboBox()
        self.column_combo = QComboBox()
        self.sheet_combo.currentTextChanged.connect(self._load_columns)

        form.addRow("项目名称", self.name_input)
        form.addRow("原始图片文件夹", self._path_field(self.image_path, "选择文件夹", self.choose_image_folder))
        form.addRow("手持清单", self._path_field(self.list_path, "选择 CSV/XLSX", self.choose_list_file))
        form.addRow("工作表", self.sheet_combo)
        form.addRow("Weld Name 列", self.column_combo)
        root.addLayout(form)

        preview_box = QFrame()
        preview_box.setObjectName("panel")
        preview_layout = vbox(spacing=6, margins=(14, 12, 14, 12))
        preview_layout.addWidget(label("导入预检查", "sectionTitle"))
        self.preview_text = label("选择图片文件夹和清单后，将显示图片数量、记录数、空值与重复 Weld Name。", "muted")
        preview_layout.addWidget(self.preview_text)
        preview_box.setLayout(preview_layout)
        root.addWidget(preview_box)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.import_button = button("创建项目索引", "primaryButton")
        buttons.addButton(self.import_button, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.rejected.connect(self.reject)
        self.import_button.clicked.connect(self._accept_if_valid)
        root.addWidget(buttons)
        self.setLayout(root)

    @staticmethod
    def _path_field(line_edit: QLineEdit, text: str, callback) -> QWidget:  # type: ignore[no-untyped-def]
        wrapper = QWidget()
        layout = hbox(spacing=8)
        layout.addWidget(line_edit, 1)
        browse = button(text, "secondaryButton")
        browse.clicked.connect(callback)
        layout.addWidget(browse)
        wrapper.setLayout(layout)
        return wrapper

    def choose_image_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择原始图片文件夹")
        if folder:
            self.image_path.setText(folder)
            self._update_preview()

    def choose_list_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "选择手持设备清单",
            "",
            "清单文件 (*.csv *.xlsx *.xlsm);;CSV 文件 (*.csv);;Excel 文件 (*.xlsx *.xlsm)",
        )
        if not filename:
            return
        self.list_path.setText(filename)
        try:
            sheets = list_sheets(Path(filename))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "无法读取清单", str(exc))
            self.sheet_combo.clear()
            self.column_combo.clear()
            return
        self.sheet_combo.blockSignals(True)
        self.sheet_combo.clear()
        self.sheet_combo.addItems(sheets)
        self.sheet_combo.blockSignals(False)
        self._load_columns()

    def _load_columns(self) -> None:
        if not self.list_path.text() or not self.sheet_combo.currentText():
            return
        try:
            columns = list_columns(Path(self.list_path.text()), self.sheet_combo.currentText())
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "无法读取列", str(exc))
            return
        self.column_combo.blockSignals(True)
        self.column_combo.clear()
        self.column_combo.addItems(columns)
        preferred_index = self.column_combo.findText("Weld Name", Qt.MatchFlag.MatchFixedString)
        if preferred_index >= 0:
            self.column_combo.setCurrentIndex(preferred_index)
        self.column_combo.blockSignals(False)
        self._update_preview()

    def _configuration(self) -> tuple[Path, Path, str, str] | None:
        if not self.image_path.text() or not self.list_path.text() or not self.sheet_combo.currentText() or not self.column_combo.currentText():
            return None
        return Path(self.image_path.text()), Path(self.list_path.text()), self.sheet_combo.currentText(), self.column_combo.currentText()

    def _update_preview(self) -> None:
        config = self._configuration()
        if config is None:
            return
        try:
            preview = make_preview(*config)
        except (OSError, ValueError) as exc:
            self.preview_text.setText(f"无法预检查：{exc}")
            self.preview_text.setStyleSheet("color: #C53030;")
            return
        self._show_preview(preview)

    def _show_preview(self, preview: ImportPreview) -> None:
        warnings: list[str] = []
        if preview.empty_weld_count:
            warnings.append(f"空 Weld Name {preview.empty_weld_count} 条")
        if preview.duplicate_weld_count:
            sample = "、".join(preview.duplicate_names[:3])
            warnings.append(f"重复 Weld Name {preview.duplicate_weld_count} 组（如：{sample}）")
        warning_text = "；".join(warnings) if warnings else "未发现空值或重复 Weld Name"
        self.preview_text.setStyleSheet("color: #718096;")
        self.preview_text.setText(
            f"图片 {preview.image_count} 张｜清单记录 {preview.record_count} 条｜有效 Weld Name {preview.valid_weld_count} 条\n{warning_text}"
        )

    def _accept_if_valid(self) -> None:
        config = self._configuration()
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "缺少项目名称", "请填写项目名称。")
            return
        if config is None:
            QMessageBox.warning(self, "缺少导入文件", "请选择原始图片文件夹、手持清单、工作表和 Weld Name 列。")
            return
        try:
            preview = make_preview(*config)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "导入检查失败", str(exc))
            return
        if preview.image_count == 0 or preview.valid_weld_count == 0:
            QMessageBox.warning(self, "无法创建项目", "图片文件夹中没有支持的图片，或清单中没有有效 Weld Name。")
            return
        if preview.empty_weld_count or preview.duplicate_weld_count:
            answer = QMessageBox.question(
                self,
                "发现数据问题",
                f"检测到空 Weld Name {preview.empty_weld_count} 条、重复 Weld Name {preview.duplicate_weld_count} 组。\n"
                "仍要建立项目索引吗？这些问题会被记录，后续出图前需要处理。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.accept()

    def create(self) -> ProjectSummary:
        config = self._configuration()
        if config is None:
            raise RuntimeError("导入参数不完整")
        return create_project(self.name_input.text(), *config)


class DashboardPage(QWidget):
    def __init__(self, open_workspace, new_project, open_project) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.open_workspace = open_workspace
        self.new_project = new_project
        self.open_project = open_project
        root = vbox(spacing=22, margins=(34, 30, 34, 30))

        header = hbox()
        title_column = vbox(spacing=5)
        title_column.addWidget(label("项目工作台", "eyebrow"))
        title_column.addWidget(label("焊点人工标注", "pageTitle"))
        title_column.addWidget(label("先确认图片位置，再绑定手持设备清单中的序号与 Weld Name。", "muted"))
        header.addLayout(title_column)
        header.addStretch()
        stage = label("阶段 3 · 图片与红圈", "badge")
        stage.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(stage)
        root.addLayout(header)

        cards = hbox(spacing=14)
        cards.addWidget(card("0", "已创建项目", "暂未导入真实项目", "#1769AA"))
        cards.addWidget(card("0", "已确认标注", "等待导入图片与清单", "#28A36A"))
        cards.addWidget(card("0", "待复核项目", "OCR 候选将在后续接入", "#D99816"))
        cards.addWidget(card("0", "本次出图", "导出功能尚未接入", "#9B6DD7"))
        root.addLayout(cards)

        setup = QFrame()
        setup.setObjectName("card")
        setup_layout = vbox(spacing=16, margins=(22, 20, 22, 20))
        setup_layout.addWidget(label("开始一个标注项目", "sectionTitle"))
        setup_layout.addWidget(label("页面已准备好。后续会按以下顺序接入图片、手持清单、人工标注与出图。", "muted"))
        steps = hbox(spacing=10)
        for index, text in enumerate(("选择原始图片", "导入手持清单", "确认焊点位置", "导出序号图片"), 1):
            step = QFrame()
            step.setStyleSheet("background: #F8FAFD; border: 1px solid #E2E9F2; border-radius: 9px;")
            step_layout = hbox(spacing=10, margins=(12, 12, 12, 12))
            chip = label(str(index))
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip.setFixedSize(26, 26)
            chip.setStyleSheet("background: #DCEBFA; color: #1769AA; border-radius: 13px; font-weight: 700;")
            step_layout.addWidget(chip)
            step_layout.addWidget(label(text))
            step.setLayout(step_layout)
            steps.addWidget(step, 1)
        setup_layout.addLayout(steps)
        action_row = hbox(spacing=10)
        action_row.addStretch()
        create_button = button("新建项目", "primaryButton")
        create_button.clicked.connect(self.new_project)
        action_row.addWidget(create_button)
        preview_button = button("查看标注工作台", "secondaryButton")
        preview_button.clicked.connect(open_workspace)
        action_row.addWidget(preview_button)
        setup_layout.addLayout(action_row)
        setup.setLayout(setup_layout)
        root.addWidget(setup)

        recent = QFrame()
        recent.setObjectName("card")
        recent_layout = vbox(spacing=12, margins=(22, 18, 22, 18))
        recent_layout.addWidget(label("项目列表", "sectionTitle"))
        self.project_list_layout = vbox(spacing=8)
        recent_layout.addLayout(self.project_list_layout)
        recent.setLayout(recent_layout)
        root.addWidget(recent)
        root.addStretch()
        self.setLayout(root)

    def update_projects(self, projects: list[ProjectSummary]) -> None:
        while self.project_list_layout.count():
            item = self.project_list_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if not projects:
            empty = QLabel("暂未创建项目\n请选择“新建项目”后导入原始图片文件夹与手持设备清单。")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #8A99AB; background: #FAFBFD; border: 1px dashed #D9E3EE; border-radius: 8px; padding: 30px;")
            self.project_list_layout.addWidget(empty)
            return
        for project in projects:
            row = QFrame()
            row.setStyleSheet("background: #FAFBFD; border: 1px solid #E3EAF2; border-radius: 8px;")
            row_layout = hbox(spacing=12, margins=(13, 11, 13, 11))
            details = vbox(spacing=3)
            details.addWidget(label(project.name, "sectionTitle"))
            details.addWidget(label(f"图片 {project.image_count} 张｜清单 {project.record_count} 条｜异常 {project.empty_weld_count + project.duplicate_weld_count} 项", "muted"))
            details.addWidget(label(f"{project.image_root}", "muted"))
            row_layout.addLayout(details, 1)
            open_button = button("查看导入结果", "secondaryButton")
            open_button.clicked.connect(lambda _checked=False, current=project: self.open_project(current))
            row_layout.addWidget(open_button)
            row.setLayout(row_layout)
            self.project_list_layout.addWidget(row)


class WorkspacePage(QWidget):
    def __init__(self, back_to_dashboard, projects_changed=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self._projects_changed = projects_changed or (lambda: None)
        self.current_project: ProjectSummary | None = None
        self.images: list[ImageRecord] = []
        self.undo_stack: list[tuple[Annotation, ...]] = []
        self.redo_stack: list[tuple[Annotation, ...]] = []
        self._restoring_history = False
        root = vbox(spacing=14, margins=(24, 20, 24, 18))

        header = hbox()
        back = button("← 项目工作台", "secondaryButton")
        back.clicked.connect(back_to_dashboard)
        header.addWidget(back)
        header.addSpacing(10)
        title_block = vbox(spacing=2)
        title_block.addWidget(label("标注工作台", "pageTitle"))
        self.workspace_subtitle = label("尚未选择项目 · 导入后可浏览真实图片并添加红圈", "muted")
        title_block.addWidget(self.workspace_subtitle)
        header.addLayout(title_block)
        header.addStretch()
        undo_button = button("撤销", "secondaryButton")
        undo_button.clicked.connect(self._undo)
        redo_button = button("恢复", "secondaryButton")
        redo_button.clicked.connect(self._redo)
        defaults_button = button("默认/命名设置", "secondaryButton")
        defaults_button.clicked.connect(self._open_project_settings)
        next_unbound = button("下一未绑定红圈", "secondaryButton")
        next_unbound.clicked.connect(self._jump_next_unbound)
        next_weld = button("下一未分配编号", "secondaryButton")
        next_weld.clicked.connect(self._select_next_unassigned_weld)
        export_button = button("导出已确认", "primaryButton")
        export_button.clicked.connect(self._export_confirmed)
        header.addWidget(undo_button)
        header.addWidget(redo_button)
        header.addWidget(defaults_button)
        header.addWidget(next_unbound)
        header.addWidget(next_weld)
        header.addWidget(export_button)
        header.addWidget(label("草稿模式", "badge"))
        root.addLayout(header)

        content = hbox(spacing=14)
        content.addWidget(self._image_panel())

        canvas_card = QFrame()
        canvas_card.setObjectName("workspaceCard")
        canvas_layout = vbox(spacing=10, margins=(14, 14, 14, 12))
        self.canvas = AnnotationCanvas(self._on_canvas_changed)
        canvas_toolbar = hbox(spacing=8)
        canvas_toolbar.addWidget(label("图片画布", "sectionTitle"))
        canvas_toolbar.addStretch()
        width_down = button("横向 −", "secondaryButton")
        width_down.clicked.connect(lambda: self._adjust_radius_xy(-6, 0))
        width_up = button("横向 ＋", "secondaryButton")
        width_up.clicked.connect(lambda: self._adjust_radius_xy(6, 0))
        height_down = button("纵向 −", "secondaryButton")
        height_down.clicked.connect(lambda: self._adjust_radius_xy(0, -5))
        height_up = button("纵向 ＋", "secondaryButton")
        height_up.clicked.connect(lambda: self._adjust_radius_xy(0, 5))
        zoom_out = button("−", "secondaryButton")
        zoom_out.clicked.connect(lambda: self.canvas.zoom_by(1 / 1.15))
        zoom_in = button("＋", "secondaryButton")
        zoom_in.clicked.connect(lambda: self.canvas.zoom_by(1.15))
        fit = button("适应画布", "secondaryButton")
        fit.clicked.connect(self.canvas.fit_image)
        clear_selection = button("取消选中", "secondaryButton")
        clear_selection.clicked.connect(self._clear_annotation_selection)
        delete = button("删除红圈", "secondaryButton")
        delete.clicked.connect(self._delete_selected)
        for control in (width_down, width_up, height_down, height_up, zoom_out, zoom_in, fit, clear_selection, delete):
            canvas_toolbar.addWidget(control)
        canvas_layout.addLayout(canvas_toolbar)
        canvas_layout.addWidget(self.canvas, 1)
        legend = hbox(spacing=18)
        for color, text in (("#D94242", "人工红圈（草稿）"), ("#5B6B82", "单击空白处新增；拖动红圈移动")):
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color}; font-size: 16px;")
            legend.addWidget(dot)
            legend.addWidget(label(text, "muted"))
        legend.addStretch()
        canvas_layout.addLayout(legend)
        canvas_card.setLayout(canvas_layout)
        content.addWidget(canvas_card, 1)
        content.addWidget(self._weld_panel())
        root.addLayout(content, 1)

        status = QFrame()
        status.setObjectName("bottomStatus")
        status_layout = hbox(spacing=18, margins=(14, 9, 14, 9))
        self.current_image_status = label("当前图片：未选择项目", "muted")
        self.annotation_status = label("本图红圈：0", "muted")
        status_layout.addWidget(self.current_image_status)
        status_layout.addWidget(self.annotation_status)
        status_layout.addStretch()
        status_layout.addWidget(label("快捷键将在标注功能接入后启用", "muted"))
        status.setLayout(status_layout)
        root.addWidget(status)
        self.setLayout(root)

    def _image_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(205)
        layout = vbox(spacing=10, margins=(14, 14, 14, 14))
        layout.addWidget(label("原始图片", "sectionTitle"))
        layout.addWidget(label("从已导入项目读取", "muted"))
        self.image_list = QListWidget()
        self.image_list.setStyleSheet(
            "QListWidget { background: #FAFBFD; border: 1px solid #E1E8F1; border-radius: 7px; padding: 4px; }"
            "QListWidget::item { padding: 7px; border-radius: 5px; }"
            "QListWidget::item:selected { background: #E4F0FC; color: #14598F; }"
        )
        self.image_list.currentRowChanged.connect(self._show_image_for_row)
        layout.addWidget(self.image_list, 1)
        self.image_import_button = button("补充图片", "primaryButton")
        self.image_import_button.setEnabled(False)
        self.image_import_button.clicked.connect(self._supplement_images)
        layout.addWidget(self.image_import_button)
        panel.setLayout(layout)
        return panel

    def _weld_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(290)
        layout = vbox(spacing=10, margins=(14, 14, 14, 14))
        header = hbox()
        header.addWidget(label("Weld Name 清单", "sectionTitle"))
        header.addStretch()
        self.weld_count_badge = label("0 / 0", "badge")
        header.addWidget(self.weld_count_badge)
        layout.addLayout(header)
        search = QLabel("🔍  搜索序号或 Weld Name")
        search.setStyleSheet("background: #F7F9FC; color: #9AA8B8; border: 1px solid #DDE6F0; border-radius: 7px; padding: 9px;")
        layout.addWidget(search)
        layout.addWidget(label("待分配编号", "muted"))
        self.weld_rows_layout = vbox(spacing=7)
        for serial, name, state in (
            ("001", "60226-15-R", "待确认"),
            ("010", "61205-01-R", "待确认"),
            ("011", "61205-07-R", "待确认"),
        ):
            self.weld_rows_layout.addWidget(self._weld_row(serial, name, state))
        layout.addLayout(self.weld_rows_layout)
        layout.addStretch()
        self.bind_button = button("绑定当前红圈（下一阶段）", "primaryButton")
        self.bind_button.setEnabled(False)
        layout.addWidget(self.bind_button)
        layout.addWidget(button("导入手持清单", "secondaryButton"))
        panel.setLayout(layout)
        return panel

    @staticmethod
    def _weld_row(serial: str, name: str, state: str) -> QFrame:
        row = QFrame()
        row.setObjectName("listRow")
        row_layout = vbox(spacing=3, margins=(9, 7, 9, 7))
        row_layout.addWidget(label(f"{serial}  ·  {name}"))
        state_label = label(state)
        state_label.setStyleSheet("color: #B7791F; font-size: 11px;")
        row_layout.addWidget(state_label)
        row.setLayout(row_layout)
        return row

    @staticmethod
    def _clear_layout(layout: QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def set_project(self, project: ProjectSummary) -> None:
        """把项目中的真实图片与清单摘要加载到工作台。"""
        self.current_project = project
        self.workspace_subtitle.setText(
            f"{project.name} · 图片 {project.image_count} 张 · 手持清单 {project.record_count} 条 · "
            f"异常 {project.empty_weld_count + project.duplicate_weld_count} 项"
        )
        self.images = load_images(project)
        self.image_list.blockSignals(True)
        self.image_list.clear()
        for image in self.images:
            self.image_list.addItem(QListWidgetItem(f"{image.image_index:03d}  {image.filename}"))
        self.image_list.blockSignals(False)
        self.image_import_button.setText("补充图片")
        self.image_import_button.setEnabled(True)

        self.weld_count_badge.setText(f"0 / {project.valid_weld_count}")
        self._clear_layout(self.weld_rows_layout)
        records = read_weld_records(project.list_path, project.worksheet, project.weld_column)
        shown = 0
        for record in records:
            weld_name = str(record["weld_name"])
            if not weld_name:
                continue
            self.weld_rows_layout.addWidget(self._weld_row(f"{int(record['serial']):03d}", weld_name, "待标注"))
            shown += 1
            if shown >= 4:
                break
        if project.valid_weld_count > shown:
            self.weld_rows_layout.addWidget(label(f"… 另有 {project.valid_weld_count - shown} 个待标注 Weld Name", "muted"))
        if self.images:
            self.image_list.setCurrentRow(0)
        else:
            self.canvas.clear_project()
            self.current_image_status.setText("当前图片：项目中没有可用图片")
            self.annotation_status.setText("本图红圈：0")

    def _supplement_images(self) -> None:
        """为当前项目索引新增原图；已有图片及标注绝不改动。"""
        if self.current_project is None:
            return
        folder_text = QFileDialog.getExistingDirectory(
            self,
            "选择需要补充的图片文件夹",
            str(self.current_project.image_root),
        )
        if not folder_text:
            return
        folder = Path(folder_text)
        try:
            preview = preview_image_supplement(self.current_project, folder)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "无法扫描图片", str(exc))
            return

        conflict_names = "、".join(path.name for path in preview.name_conflicts[:8])
        detail = (
            f"扫描图片：{len(preview.scanned_paths)} 张\n"
            f"可新增：{len(preview.new_paths)} 张\n"
            f"已存在（同一完整路径，跳过）：{len(preview.skipped_paths)} 张\n"
            f"同名冲突（不同路径，不导入）：{len(preview.name_conflicts)} 张"
        )
        if conflict_names:
            detail += f"\n冲突示例：{conflict_names}"
        if not preview.new_paths:
            QMessageBox.information(self, "补充图片", detail + "\n\n没有可新增的图片，项目未改动。")
            return
        answer = QMessageBox.question(
            self,
            "确认补充图片",
            detail + "\n\n确认后只会新增可新增图片；已有红圈和绑定不会变化。是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        current_row = self.image_list.currentRow()
        current_image_id = self.images[current_row].image_index if 0 <= current_row < len(self.images) else None
        try:
            result = supplement_images(self.current_project, folder)
        except (OSError, sqlite3.Error, ValueError) as exc:
            QMessageBox.critical(self, "补充图片失败", str(exc))
            return

        self.set_project(result.project)
        if current_image_id is not None:
            restored_row = next(
                (row for row, image in enumerate(self.images) if image.image_index == current_image_id),
                -1,
            )
            if restored_row >= 0:
                self.image_list.setCurrentRow(restored_row)
        self._projects_changed()
        QMessageBox.information(
            self,
            "补充图片完成",
            f"已新增：{len(result.added_paths)} 张\n"
            f"已跳过同路径图片：{len(result.skipped_paths)} 张\n"
            f"未导入同名冲突图片：{len(result.name_conflicts)} 张\n\n"
            "原图片、已有红圈和 Weld Name 绑定均未修改。",
        )

    def _show_image_for_row(self, row: int) -> None:
        if self.current_project is None or row < 0 or row >= len(self.images):
            return
        image = self.images[row]
        self.canvas.load_image(self.current_project, image)
        self.current_image_status.setText(f"当前图片：{image.image_index:03d}  {image.filename}")
        self.annotation_status.setText(f"本图红圈：{self.canvas.annotation_count()}")

    def _on_canvas_changed(self) -> None:
        self.annotation_status.setText(f"本图红圈：{self.canvas.annotation_count()}")

    def _adjust_radius(self, offset: float) -> None:
        if not self.canvas.adjust_selected_radius(offset):
            if self.canvas.selected_item_is_locked():
                self.annotation_status.setText("绿色已绑定红圈已锁定；请先解除绑定后再调整大小")
            else:
                self.annotation_status.setText("请先选中一个未绑定红圈，再调整大小")

    def _adjust_radius_xy(self, offset_x: float, offset_y: float) -> None:
        if not self.canvas.adjust_selected_radius_xy(offset_x, offset_y):
            if self.canvas.selected_item_is_locked():
                self.annotation_status.setText("绿色已绑定红圈已锁定；请先解除绑定后再调整大小")
            else:
                self.annotation_status.setText("请先选中一个未绑定红圈，再调整大小")

    def _delete_selected(self) -> None:
        if not self.canvas.delete_selected():
            if self.canvas.selected_item_is_locked():
                self.annotation_status.setText("绿色已绑定红圈不能删除；请先解除绑定")
            else:
                self.annotation_status.setText("请先选中需要删除的未绑定红圈")

    def _clear_annotation_selection(self) -> None:
        self.canvas.clear_selection()
        self.annotation_status.setText("已取消红圈选中状态。")

    # 以下方法覆盖阶段 2 的清单摘要面板，提供 Weld Name 一对一绑定。
    def _weld_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(310)
        layout = vbox(spacing=10, margins=(14, 14, 14, 14))
        header = hbox()
        header.addWidget(label("Weld Name 清单", "sectionTitle"))
        header.addStretch()
        self.weld_count_badge = label("0 / 0", "badge")
        header.addWidget(self.weld_count_badge)
        layout.addLayout(header)
        self.weld_search = QLineEdit()
        self.weld_search.setPlaceholderText("搜索序号或 Weld Name")
        self.weld_search.setClearButtonEnabled(True)
        self.weld_search.textChanged.connect(self._refresh_weld_list)
        layout.addWidget(self.weld_search)
        self.weld_summary = label("先导入项目，再选择红圈与 Weld Name。", "muted")
        layout.addWidget(self.weld_summary)
        self.weld_list = QListWidget()
        self.weld_list.setStyleSheet(
            "QListWidget { background: #FAFBFD; border: 1px solid #E1E8F1; border-radius: 7px; padding: 4px; }"
            "QListWidget::item { padding: 7px; border-radius: 5px; }"
            "QListWidget::item:selected { background: #E4F0FC; color: #14598F; }"
        )
        self.weld_list.itemDoubleClicked.connect(lambda _item: self._bind_selected())
        layout.addWidget(self.weld_list, 1)
        self.bind_button = button("绑定到选中红圈", "primaryButton")
        self.bind_button.clicked.connect(self._bind_selected)
        self.unbind_button = button("解除当前红圈绑定", "secondaryButton")
        self.unbind_button.clicked.connect(self._unbind_selected)
        layout.addWidget(self.bind_button)
        layout.addWidget(self.unbind_button)
        panel.setLayout(layout)
        return panel

    def _refresh_weld_list(self, _filter_text: str | None = None) -> None:
        if not hasattr(self, "weld_list"):
            return
        self.weld_list.clear()
        if self.current_project is None:
            return
        used = bound_weld_serials(self.current_project)
        keyword = self.weld_search.text().strip().casefold()
        visible = 0
        for weld in self.weld_records:
            searchable = f"{weld.serial} {weld.weld_name}".casefold()
            if keyword and keyword not in searchable:
                continue
            suffix = "已绑定" if weld.serial in used else "未分配"
            item = QListWidgetItem(f"{weld.serial:03d}  ·  {weld.weld_name}\n{suffix}")
            item.setData(Qt.ItemDataRole.UserRole, weld.serial)
            if weld.serial in used:
                item.setForeground(QColor("#8795A8"))
            else:
                item.setForeground(QColor("#1D3856"))
            self.weld_list.addItem(item)
            visible += 1
        self.weld_count_badge.setText(f"{len(used)} / {len(self.weld_records)}")
        self.weld_summary.setText(f"已绑定 {len(used)} 个｜未分配 {len(self.weld_records) - len(used)} 个｜当前显示 {visible} 个")

    def set_project(self, project: ProjectSummary) -> None:
        """加载真实图片与清单；图片在列表中按自然数字顺序排列。"""
        # 项目可能来自较早版本的工作区实例；进入项目时再次保证
        # 会话级撤销记录存在，避免该历史状态影响项目加载或退出。
        if not hasattr(self, "undo_stack"):
            self.undo_stack: list[tuple[Annotation, ...]] = []
        if not hasattr(self, "redo_stack"):
            self.redo_stack: list[tuple[Annotation, ...]] = []
        if not hasattr(self, "_restoring_history"):
            self._restoring_history = False
        self.current_project = project
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.workspace_subtitle.setText(
            f"{project.name} · 图片 {project.image_count} 张 · 手持清单 {project.record_count} 条 · "
            f"异常 {project.empty_weld_count + project.duplicate_weld_count} 项"
        )
        self.images = load_images(project)
        self.weld_records = [weld for weld in load_welds(project) if weld.weld_name]
        self.image_list.blockSignals(True)
        self.image_list.clear()
        for display_index, image in enumerate(self.images, start=1):
            self.image_list.addItem(QListWidgetItem(f"{display_index:03d}  {image.filename}"))
        self.image_list.blockSignals(False)
        self.image_import_button.setText("补充图片")
        self.image_import_button.setEnabled(True)
        self.weld_search.clear()
        self._refresh_weld_list()
        if self.images:
            self.image_list.setCurrentRow(0)
        else:
            self.canvas.clear_project()
            self.current_image_status.setText("当前图片：项目中没有可用图片")
            self.annotation_status.setText("本图红圈：0")

    def _show_image_for_row(self, row: int) -> None:
        if self.current_project is None or row < 0 or row >= len(self.images):
            return
        image = self.images[row]
        self.canvas.load_image(self.current_project, image)
        self.current_image_status.setText(f"当前图片：{row + 1:03d}  {image.filename}")
        self._on_canvas_changed()

    def _on_canvas_changed(self) -> None:
        total = self.canvas.annotation_count()
        bound = self.canvas.bound_annotation_count()
        self.annotation_status.setText(f"本图红圈：{total}｜已绑定：{bound}｜未绑定：{total - bound}")
        if self.current_project is not None:
            self._refresh_weld_list()

    def _bind_selected(self) -> None:
        if self.current_project is None:
            return
        item = self.weld_list.currentItem()
        if item is None:
            self.weld_summary.setText("请先从清单中选择一个 Weld Name。")
            return
        serial = int(item.data(Qt.ItemDataRole.UserRole))
        if serial in bound_weld_serials(self.current_project):
            self.weld_summary.setText("该 Weld Name 已绑定，请先解除原绑定。")
            return
        selected = self.canvas.selected_item()
        selected_id = selected.annotation_id if selected is not None else None
        try:
            if not self.canvas.bind_selected(serial):
                self.weld_summary.setText("请先在图片中选中一个红圈。")
                return
        except ValueError as exc:
            self.weld_summary.setText(str(exc))
            return
        self._on_canvas_changed()
        self._select_next_unassigned_weld(after_serial=serial)
        self._jump_next_unbound(after_annotation_id=selected_id)

    def _unbind_selected(self) -> None:
        if not self.canvas.unbind_selected():
            self.weld_summary.setText("请先选中一个已绑定的红圈。")
            return
        self._on_canvas_changed()

    def _open_project_settings(self) -> None:
        if self.current_project is None:
            return
        settings = get_project_settings(self.current_project)
        dialog = QDialog(self)
        dialog.setWindowTitle("默认红框与导出命名设置")
        dialog.setMinimumWidth(560)
        root = vbox(spacing=14, margins=(22, 20, 22, 18))
        root.addWidget(label("默认红框与导出命名", "pageTitle"))
        root.addWidget(label("默认红框尺寸仅应用到之后新建的红框；已有红框尺寸不会被自动改动。", "muted"))
        form = QFormLayout()
        horizontal = QDoubleSpinBox()
        horizontal.setRange(8, 1000)
        horizontal.setDecimals(0)
        horizontal.setSuffix(" 像素（半径）")
        horizontal.setValue(float(settings.get("default_radius_x", 54)))
        vertical = QDoubleSpinBox()
        vertical.setRange(8, 1000)
        vertical.setDecimals(0)
        vertical.setSuffix(" 像素（半径）")
        vertical.setValue(float(settings.get("default_radius_y", 28)))
        template = QLineEdit(settings.get("filename_template", "{serial:03d}_{weld_name}.png"))
        form.addRow("默认横向尺寸", horizontal)
        form.addRow("默认纵向尺寸", vertical)
        form.addRow("导出文件名模板", template)
        root.addLayout(form)
        hint = label(
            "可用变量：{serial}、{weld_name}、{source_stem}、{annotation_id}\n"
            "示例：{serial:03d}_{weld_name}.png 或 {source_stem}_{serial:03d}_{weld_name}.png",
            "muted",
        )
        hint.setStyleSheet("background: #F5F8FC; border: 1px solid #E1E8F1; border-radius: 7px; padding: 10px;")
        root.addWidget(hint)
        actions = hbox(spacing=8)
        actions.addStretch()
        cancel = button("取消", "secondaryButton")
        save = button("保存设置", "primaryButton")
        cancel.clicked.connect(dialog.reject)
        save.clicked.connect(dialog.accept)
        actions.addWidget(cancel)
        actions.addWidget(save)
        root.addLayout(actions)
        dialog.setLayout(root)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            set_project_settings(self.current_project, horizontal.value(), vertical.value(), template.text())
        except ValueError as exc:
            QMessageBox.warning(self, "无法保存设置", str(exc))
            return
        self.annotation_status.setText(
            f"默认红框已保存：横向 {horizontal.value():.0f}、纵向 {vertical.value():.0f}；导出命名模板已更新。"
        )

    def _record_before_change(self) -> None:
        if self.current_project is None or self._restoring_history:
            return
        snapshot = tuple(load_all_annotations(self.current_project))
        self.undo_stack.append(snapshot)
        if len(self.undo_stack) > 100:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def _reload_current_image(self) -> None:
        row = self.image_list.currentRow()
        if row >= 0:
            self._show_image_for_row(row)

    def _undo(self) -> None:
        if self.current_project is None or not self.undo_stack:
            self.annotation_status.setText("没有可撤销的操作。")
            return
        current = tuple(load_all_annotations(self.current_project))
        target = self.undo_stack.pop()
        self.redo_stack.append(current)
        self._restoring_history = True
        try:
            restore_annotations(self.current_project, target)
        finally:
            self._restoring_history = False
        self._reload_current_image()
        self.annotation_status.setText("已撤销上一步操作。")

    def _redo(self) -> None:
        if self.current_project is None or not self.redo_stack:
            self.annotation_status.setText("没有可恢复的操作。")
            return
        current = tuple(load_all_annotations(self.current_project))
        target = self.redo_stack.pop()
        self.undo_stack.append(current)
        self._restoring_history = True
        try:
            restore_annotations(self.current_project, target)
        finally:
            self._restoring_history = False
        self._reload_current_image()
        self.annotation_status.setText("已恢复上一步操作。")

    def _jump_next_unbound(self, _checked: bool = False, after_annotation_id: int | None = None) -> None:
        if self.current_project is None or not self.images:
            return
        start = self.image_list.currentRow()
        if start < 0:
            start = 0
        # 优先在当前图寻找下一处未绑定红圈，避免每次绑定后直接跳到下一张图。
        current_image = self.images[start]
        current_pending = [item for item in load_annotations(self.current_project, current_image.image_index) if item.weld_serial is None]
        if current_pending:
            current_pending.sort(key=lambda item: item.annotation_id)
            target = next((item for item in current_pending if after_annotation_id is None or item.annotation_id > after_annotation_id), current_pending[0])
            marker = self.canvas._items.get(target.annotation_id)
            if marker is not None:
                # 绑定后的旧红圈会变为绿圈；跳转前必须清空它的选择状态，
                # 否则场景中会同时存在新旧两个选中项，后续绑定会误取旧绿圈。
                self.canvas.clear_selection()
                marker.setSelected(True)
                self.canvas.centerOn(marker)
            self.annotation_status.setText(f"已定位未绑定红圈：图片 {start + 1:03d}，标注 {target.annotation_id}")
            return
        for offset in range(1, len(self.images) + 1):
            row = (start + offset) % len(self.images)
            image = self.images[row]
            pending = next((item for item in load_annotations(self.current_project, image.image_index) if item.weld_serial is None), None)
            if pending is None:
                continue
            self.image_list.setCurrentRow(row)
            marker = self.canvas._items.get(pending.annotation_id)
            if marker is not None:
                self.canvas.clear_selection()
                marker.setSelected(True)
                self.canvas.centerOn(marker)
            self.annotation_status.setText(f"已定位未绑定红圈：图片 {row + 1:03d}，标注 {pending.annotation_id}")
            return
        self.annotation_status.setText("没有未绑定红圈。")

    def _select_next_unassigned_weld(self, _checked: bool = False, after_serial: int | None = None) -> None:
        if self.current_project is None:
            return
        self.weld_search.clear()
        used = bound_weld_serials(self.current_project)
        candidates = [
            self.weld_list.item(row)
            for row in range(self.weld_list.count())
            if int(self.weld_list.item(row).data(Qt.ItemDataRole.UserRole)) not in used
        ]
        if candidates:
            item = next(
                (candidate for candidate in candidates if after_serial is None or int(candidate.data(Qt.ItemDataRole.UserRole)) > after_serial),
                candidates[0],
            )
            self.weld_list.setCurrentItem(item)
            self.weld_list.scrollToItem(item)
            self.weld_summary.setText("已定位下一条未分配 Weld Name；选择红圈后即可绑定。")
            return
        self.weld_summary.setText("没有未分配 Weld Name。")

    def _export_confirmed(self) -> None:
        if self.current_project is None:
            return
        try:
            check = export_preflight(self.current_project)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "导出检查失败", str(exc))
            return
        message = (
            f"可导出已确认图片：{len(check.records)} 张\n"
            f"未绑定红圈：{len(check.unbound_annotations)} 个\n"
            f"未分配 Weld Name：{len(check.unassigned_welds)} 个\n"
            f"阻断问题：{len(check.blocking_issues)} 项\n\n"
        )
        if check.blocking_issues:
            message += "存在阻断问题。本次只生成问题清单，不生成图片。是否继续？"
        else:
            message += "每个已确认绑定将生成一张独立 PNG，且每张仅绘制一个红圈。是否开始导出？"
        answer = QMessageBox.question(
            self,
            "确认导出",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            result = export_confirmed_annotations(self.current_project)
        except OSError as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        if result.blocked:
            QMessageBox.warning(
                self,
                "导出已阻断",
                f"未生成 PNG。问题清单已保存：\n{result.report_path}",
            )
        else:
            QMessageBox.information(
                self,
                "导出完成",
                f"已生成 {result.exported_count} 张图片。\n"
                f"提示项：{result.warning_count} 个\n\n"
                f"图片目录：{result.output_dir / 'images'}\n"
                f"出图清单：{result.report_path}",
            )


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.current_project: ProjectSummary | None = None
        self.setWindowTitle(f"{APP_NAME} · 图片浏览与人工标注")
        self.resize(1440, 900)
        self.setMinimumSize(1180, 720)

        shell = QWidget()
        shell_layout = hbox()
        sidebar = self._build_sidebar()
        shell_layout.addWidget(sidebar)
        self.pages = QStackedWidget()
        self.dashboard = DashboardPage(self.show_workspace, self.new_project, self.open_project)
        self.workspace = WorkspacePage(self.show_dashboard, self.refresh_projects)
        self.pages.addWidget(self.dashboard)
        self.pages.addWidget(self.workspace)
        shell_layout.addWidget(self.pages, 1)
        shell.setLayout(shell_layout)
        self.setCentralWidget(shell)
        self.refresh_projects()
        self.show_dashboard()

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(226)
        layout = vbox(spacing=4, margins=(14, 18, 14, 16))
        layout.addWidget(label(APP_NAME, "brandTitle"))
        layout.addWidget(label("人工确认 · 可追溯出图", "brandSubtitle"))
        layout.addSpacing(24)
        layout.addWidget(label("工作区", "navSection"))
        self.dashboard_nav = button("▦   项目工作台", "navButton")
        self.workspace_nav = button("⌖   标注工作台", "navButton")
        self.dashboard_nav.clicked.connect(self.show_dashboard)
        self.workspace_nav.clicked.connect(self.show_workspace)
        layout.addWidget(self.dashboard_nav)
        layout.addWidget(self.workspace_nav)
        layout.addWidget(label("后续功能", "navSection"))
        for text in ("◎   待复核", "⇧   出图记录", "⚙   项目设置"):
            item = button(text, "navButton")
            item.setEnabled(False)
            item.setStyleSheet("QPushButton:disabled { color: #75879F; }")
            layout.addWidget(item)
        layout.addStretch()
        note = label("当前版本\n已支持图片浏览与人工红圈\n未接入编号绑定与出图", "brandSubtitle")
        note.setStyleSheet("color: #91A2B9; background: #1A3152; border-radius: 8px; padding: 10px;")
        layout.addWidget(note)
        sidebar.setLayout(layout)
        return sidebar

    def _set_active_navigation(self, dashboard: bool) -> None:
        self.dashboard_nav.setProperty("active", dashboard)
        self.workspace_nav.setProperty("active", not dashboard)
        for item in (self.dashboard_nav, self.workspace_nav):
            item.style().unpolish(item)
            item.style().polish(item)

    def show_dashboard(self) -> None:
        self.pages.setCurrentWidget(self.dashboard)
        self._set_active_navigation(True)

    def show_workspace(self) -> None:
        self.pages.setCurrentWidget(self.workspace)
        self._set_active_navigation(False)

    def refresh_projects(self) -> None:
        self.dashboard.update_projects(list_projects())

    def new_project(self) -> None:
        dialog = ImportProjectDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            project = dialog.create()
        except (OSError, RuntimeError, ValueError) as exc:
            QMessageBox.critical(self, "创建项目失败", str(exc))
            return
        self.refresh_projects()
        self.open_project(project)
        QMessageBox.information(
            self,
            "导入完成",
            f"已建立项目索引：{project.name}\n\n"
            f"图片：{project.image_count} 张\n"
            f"清单记录：{project.record_count} 条\n"
            f"有效 Weld Name：{project.valid_weld_count} 条\n"
            f"空值：{project.empty_weld_count} 条\n"
            f"重复 Weld Name：{project.duplicate_weld_count} 组\n\n"
            f"项目数据：{project.project_dir}",
        )

    def open_project(self, project: ProjectSummary) -> None:
        self.current_project = project
        self.workspace.set_project(project)
        self.show_workspace()


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
    delete_annotation,
    load_annotations,
    load_images,
