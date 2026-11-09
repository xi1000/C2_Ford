"""本地项目导入与索引保存。

本模块只读取外部图片/清单文件，项目索引写入 Software/projects。
不会复制、重命名或修改用户选择的源文件。
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from PIL import Image, ImageDraw


SOFTWARE_ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = SOFTWARE_ROOT / "projects"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
DEFAULT_RADIUS_X = 54.0
DEFAULT_RADIUS_Y = 28.0
DEFAULT_FILENAME_TEMPLATE = "{serial:03d}_{weld_name}.png"


@dataclass(frozen=True)
class ImportPreview:
    image_count: int
    record_count: int
    valid_weld_count: int
    empty_weld_count: int
    duplicate_weld_count: int
    duplicate_names: tuple[str, ...]


@dataclass(frozen=True)
class ProjectSummary:
    project_id: str
    name: str
    project_dir: Path
    database_path: Path
    image_root: Path
    list_path: Path
    worksheet: str
    weld_column: str
    created_at: str
    image_count: int
    record_count: int
    valid_weld_count: int
    empty_weld_count: int
    duplicate_weld_count: int


@dataclass(frozen=True)
class ImageRecord:
    image_index: int
    filename: str
    original_path: Path


@dataclass(frozen=True)
class ImageSupplementPreview:
    """补充图片前的只读扫描结果。"""

    folder: Path
    scanned_paths: tuple[Path, ...]
    new_paths: tuple[Path, ...]
    skipped_paths: tuple[Path, ...]
    name_conflicts: tuple[Path, ...]


@dataclass(frozen=True)
class ImageSupplementResult:
    project: ProjectSummary
    folder: Path
    scanned_count: int
    added_paths: tuple[Path, ...]
    skipped_paths: tuple[Path, ...]
    name_conflicts: tuple[Path, ...]


@dataclass(frozen=True)
class Annotation:
    annotation_id: int
    image_index: int
    weld_serial: int | None
    center_x: float
    center_y: float
    radius_x: float
    radius_y: float
    status: str


@dataclass(frozen=True)
class WeldRecord:
    serial: int
    source_row: int
    weld_name: str


@dataclass(frozen=True)
class ExportRecord:
    annotation_id: int
    image_index: int
    source_image: Path
    serial: int
    weld_name: str
    center_x: float
    center_y: float
    radius_x: float
    radius_y: float
    output_file: str


@dataclass(frozen=True)
class ExportCheck:
    records: tuple[ExportRecord, ...]
    warnings: tuple[tuple[str, str], ...]
    blocking_issues: tuple[tuple[str, str], ...]
    unbound_annotations: tuple[tuple[int, str, float, float], ...]
    unassigned_welds: tuple[WeldRecord, ...]


@dataclass(frozen=True)
class ExportResult:
    output_dir: Path
    report_path: Path
    manifest_path: Path
    exported_count: int
    blocked: bool
    warning_count: int
    blocking_count: int


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    errors: list[UnicodeDecodeError] = []
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle)
                headers = reader.fieldnames or []
                return headers, list(reader)
        except UnicodeDecodeError as exc:
            errors.append(exc)
    raise ValueError(f"无法读取 CSV 编码：{path}") from errors[-1]


def list_sheets(path: Path) -> list[str]:
    if path.suffix.lower() == ".csv":
        return ["CSV"]
    if path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ValueError("清单文件仅支持 CSV、XLSX 或 XLSM")
    book = load_workbook(path, read_only=True, data_only=True)
    return list(book.sheetnames)


def list_columns(path: Path, worksheet: str) -> list[str]:
    if path.suffix.lower() == ".csv":
        headers, _ = _read_csv(path)
        return [str(item).strip() for item in headers if item is not None]
    book = load_workbook(path, read_only=True, data_only=True)
    if worksheet not in book.sheetnames:
        raise ValueError(f"未找到工作表：{worksheet}")
    sheet = book[worksheet]
    return [str(cell.value).strip() for cell in next(sheet.iter_rows(min_row=1, max_row=1)) if cell.value is not None]


def read_weld_records(path: Path, worksheet: str, weld_column: str) -> list[dict[str, object]]:
    """返回原始数据行顺序；serial 从 1 开始，空 Weld Name 也保留用于校验。"""
    records: list[dict[str, object]] = []
    if path.suffix.lower() == ".csv":
        headers, rows = _read_csv(path)
        if weld_column not in headers:
            raise ValueError(f"CSV 中未找到列：{weld_column}")
        for serial, row in enumerate(rows, start=1):
            records.append({"serial": serial, "source_row": serial + 1, "weld_name": str(row.get(weld_column) or "").strip()})
        return records

    book = load_workbook(path, read_only=True, data_only=True)
    if worksheet not in book.sheetnames:
        raise ValueError(f"未找到工作表：{worksheet}")
    sheet = book[worksheet]
    header_values = [cell.value for cell in next(sheet.iter_rows(min_row=1, max_row=1))]
    try:
        column_index = [str(value).strip() if value is not None else "" for value in header_values].index(weld_column)
    except ValueError as exc:
        raise ValueError(f"工作表中未找到列：{weld_column}") from exc
    for serial, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=1):
        value = row[column_index] if column_index < len(row) else None
        records.append({"serial": serial, "source_row": serial + 1, "weld_name": str(value or "").strip()})
    return records


def scan_images(folder: Path) -> list[Path]:
    if not folder.is_dir():
        raise ValueError(f"图片文件夹不存在：{folder}")
    return sorted(
        (path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS),
        key=lambda path: _natural_key(path.name),
    )


def _natural_key(value: str) -> list[object]:
    """让 1.png、2.png、10.png 按数值而不是文本顺序排列。"""
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value)]


def make_preview(image_folder: Path, list_path: Path, worksheet: str, weld_column: str) -> ImportPreview:
    images = scan_images(image_folder)
    records = read_weld_records(list_path, worksheet, weld_column)
    names = [str(record["weld_name"]) for record in records]
    seen: set[str] = set()
    duplicates: list[str] = []
    for name in names:
        if name and name in seen and name not in duplicates:
            duplicates.append(name)
        seen.add(name)
    return ImportPreview(
        image_count=len(images),
        record_count=len(records),
        valid_weld_count=sum(bool(name) for name in names),
        empty_weld_count=sum(not bool(name) for name in names),
        duplicate_weld_count=len(duplicates),
        duplicate_names=tuple(duplicates),
    )


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", name).strip(" ._")
    return cleaned or "未命名项目"


def create_project(
    name: str,
    image_folder: Path,
    list_path: Path,
    worksheet: str,
    weld_column: str,
) -> ProjectSummary:
    """建立项目 SQLite 索引；源文件保持只读。"""
    name = name.strip()
    if not name:
        raise ValueError("请输入项目名称")
    if not list_path.is_file():
        raise ValueError(f"清单文件不存在：{list_path}")
    preview = make_preview(image_folder, list_path, worksheet, weld_column)
    images = scan_images(image_folder)
    records = read_weld_records(list_path, worksheet, weld_column)

    PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
    project_id = uuid.uuid4().hex
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    project_dir = PROJECTS_ROOT / f"{timestamp}_{_safe_name(name)}"
    project_dir.mkdir(parents=False, exist_ok=False)
    database_path = project_dir / "project.sqlite"
    created_at = datetime.now().isoformat(timespec="seconds")
    summary = ProjectSummary(
        project_id=project_id,
        name=name,
        project_dir=project_dir,
        database_path=database_path,
        image_root=image_folder.resolve(),
        list_path=list_path.resolve(),
        worksheet=worksheet,
        weld_column=weld_column,
        created_at=created_at,
        image_count=preview.image_count,
        record_count=preview.record_count,
        valid_weld_count=preview.valid_weld_count,
        empty_weld_count=preview.empty_weld_count,
        duplicate_weld_count=preview.duplicate_weld_count,
    )
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE project (
                project_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                image_root TEXT NOT NULL,
                list_path TEXT NOT NULL,
                worksheet TEXT NOT NULL,
                weld_column TEXT NOT NULL,
                created_at TEXT NOT NULL,
                image_count INTEGER NOT NULL,
                record_count INTEGER NOT NULL,
                valid_weld_count INTEGER NOT NULL,
                empty_weld_count INTEGER NOT NULL,
                duplicate_weld_count INTEGER NOT NULL
            );
            CREATE TABLE images (
                image_index INTEGER PRIMARY KEY,
                filename TEXT NOT NULL,
                original_path TEXT NOT NULL
            );
            CREATE TABLE welds (
                serial INTEGER PRIMARY KEY,
                source_row INTEGER NOT NULL,
                weld_name TEXT NOT NULL
            );
            CREATE TABLE validation_issues (
                issue_type TEXT NOT NULL,
                weld_name TEXT,
                detail TEXT NOT NULL
            );
            """
        )
        _ensure_annotation_schema(connection)
        connection.execute(
            "INSERT INTO project VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                summary.project_id,
                summary.name,
                str(summary.image_root),
                str(summary.list_path),
                summary.worksheet,
                summary.weld_column,
                summary.created_at,
                summary.image_count,
                summary.record_count,
                summary.valid_weld_count,
                summary.empty_weld_count,
                summary.duplicate_weld_count,
            ),
        )
        connection.executemany(
            "INSERT INTO images VALUES (?, ?, ?)",
            [(index, path.name, str(path.resolve())) for index, path in enumerate(images, start=1)],
        )
        connection.executemany(
            "INSERT INTO welds VALUES (?, ?, ?)",
            [(int(row["serial"]), int(row["source_row"]), str(row["weld_name"])) for row in records],
        )
        empty_issues = [("空Weld Name", "", f"数据行序号 {row['serial']}") for row in records if not row["weld_name"]]
        duplicate_issues = [("重复Weld Name", value, "同一清单中出现重复值") for value in preview.duplicate_names]
        connection.executemany("INSERT INTO validation_issues VALUES (?, ?, ?)", empty_issues + duplicate_issues)

    (project_dir / "project.json").write_text(
        json.dumps({**asdict(summary), "project_dir": str(summary.project_dir), "database_path": str(summary.database_path), "image_root": str(summary.image_root), "list_path": str(summary.list_path)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def _ensure_annotation_schema(connection: sqlite3.Connection) -> None:
    """为新旧项目补齐人工标注表。"""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS annotations (
            annotation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_index INTEGER NOT NULL,
            weld_serial INTEGER,
            center_x REAL NOT NULL,
            center_y REAL NOT NULL,
            radius_x REAL NOT NULL,
            radius_y REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            source TEXT NOT NULL DEFAULT 'manual',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_annotations_weld_serial
        ON annotations(weld_serial) WHERE weld_serial IS NOT NULL;
        CREATE TABLE IF NOT EXISTS exports (
            export_id INTEGER PRIMARY KEY AUTOINCREMENT,
            output_dir TEXT NOT NULL,
            created_at TEXT NOT NULL,
            exported_count INTEGER NOT NULL,
            warning_count INTEGER NOT NULL,
            blocking_count INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS project_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS image_import_logs (
            import_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            folder_path TEXT NOT NULL,
            scanned_count INTEGER NOT NULL,
            added_count INTEGER NOT NULL,
            skipped_count INTEGER NOT NULL,
            conflict_count INTEGER NOT NULL,
            detail_json TEXT NOT NULL
        );
        """
    )
    connection.executemany(
        "INSERT OR IGNORE INTO project_settings (setting_key, setting_value) VALUES (?, ?)",
        [
            ("default_radius_x", str(DEFAULT_RADIUS_X)),
            ("default_radius_y", str(DEFAULT_RADIUS_Y)),
            ("filename_template", DEFAULT_FILENAME_TEMPLATE),
        ],
    )


def _connect(project: ProjectSummary) -> sqlite3.Connection:
    connection = sqlite3.connect(project.database_path)
    _ensure_annotation_schema(connection)
    return connection


def get_project_settings(project: ProjectSummary) -> dict[str, str]:
    with _connect(project) as connection:
        rows = connection.execute("SELECT setting_key, setting_value FROM project_settings").fetchall()
    return {str(row[0]): str(row[1]) for row in rows}


def set_project_settings(project: ProjectSummary, radius_x: float, radius_y: float, filename_template: str) -> None:
    if radius_x < 8 or radius_y < 8:
        raise ValueError("默认红框横向和纵向半径均不能小于 8 像素。")
    template = filename_template.strip()
    if not template:
        raise ValueError("请输入导出文件名模板。")
    if not template.lower().endswith(".png"):
        template += ".png"
    try:
        formatted = template.format(serial=1, weld_name="60226-15-R", source_stem="1", annotation_id=1)
    except (KeyError, ValueError) as exc:
        raise ValueError("模板仅支持 {serial}、{weld_name}、{source_stem}、{annotation_id}，且格式必须有效。") from exc
    if Path(formatted).name != formatted or any(char in formatted for char in '\\/:*?"<>|'):
        raise ValueError("格式化后的文件名不能包含文件夹路径或 Windows 非法字符。")
    with _connect(project) as connection:
        connection.executemany(
            "INSERT OR REPLACE INTO project_settings (setting_key, setting_value) VALUES (?, ?)",
            [
                ("default_radius_x", str(float(radius_x))),
                ("default_radius_y", str(float(radius_y))),
                ("filename_template", template),
            ],
        )


def _format_export_filename(template: str, serial: int, weld_name: str, source_image: Path, annotation_id: int) -> str:
    try:
        filename = template.format(
            serial=serial,
            weld_name=weld_name,
            source_stem=source_image.stem,
            annotation_id=annotation_id,
        )
    except (KeyError, ValueError) as exc:
        raise ValueError(f"导出文件名模板无效：{exc}") from exc
    if not filename.lower().endswith(".png"):
        filename += ".png"
    if Path(filename).name != filename or any(char in filename for char in '\\/:*?"<>|'):
        raise ValueError(f"导出文件名无效：{filename}")
    return filename


def load_images(project: ProjectSummary) -> list[ImageRecord]:
    with _connect(project) as connection:
        rows = connection.execute("SELECT image_index, filename, original_path FROM images ORDER BY image_index").fetchall()
    images = [ImageRecord(int(row[0]), str(row[1]), Path(row[2])) for row in rows]
    return sorted(images, key=lambda image: _natural_key(image.filename))


def _path_key(path: Path) -> str:
    """用于 Windows 路径去重；不读取或改动源文件。"""
    return str(path.resolve()).casefold()


def preview_image_supplement(project: ProjectSummary, folder: Path) -> ImageSupplementPreview:
    """扫描待补图片：同路径跳过，同名不同路径列为冲突。"""
    candidates = scan_images(folder)
    existing = load_images(project)
    existing_paths = {_path_key(image.original_path) for image in existing}
    existing_names = {image.filename.casefold() for image in existing}
    new_paths: list[Path] = []
    skipped_paths: list[Path] = []
    name_conflicts: list[Path] = []
    for candidate in candidates:
        if _path_key(candidate) in existing_paths:
            skipped_paths.append(candidate)
        elif candidate.name.casefold() in existing_names:
            name_conflicts.append(candidate)
        else:
            new_paths.append(candidate)
    return ImageSupplementPreview(
        folder=folder.resolve(),
        scanned_paths=tuple(candidates),
        new_paths=tuple(new_paths),
        skipped_paths=tuple(skipped_paths),
        name_conflicts=tuple(name_conflicts),
    )


def supplement_images(project: ProjectSummary, folder: Path) -> ImageSupplementResult:
    """将通过校验的新图片索引到既有项目，不影响任何已有标注或绑定。"""
    preview = preview_image_supplement(project, folder)
    timestamp = datetime.now().isoformat(timespec="seconds")
    with _connect(project) as connection:
        next_index = int(connection.execute("SELECT COALESCE(MAX(image_index), 0) + 1 FROM images").fetchone()[0])
        connection.executemany(
            "INSERT INTO images (image_index, filename, original_path) VALUES (?, ?, ?)",
            [
                (next_index + offset, path.name, str(path.resolve()))
                for offset, path in enumerate(preview.new_paths)
            ],
        )
        image_count = int(connection.execute("SELECT COUNT(*) FROM images").fetchone()[0])
        connection.execute("UPDATE project SET image_count = ?", (image_count,))
        connection.execute(
            """
            INSERT INTO image_import_logs
            (created_at, folder_path, scanned_count, added_count, skipped_count, conflict_count, detail_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                str(preview.folder),
                len(preview.scanned_paths),
                len(preview.new_paths),
                len(preview.skipped_paths),
                len(preview.name_conflicts),
                json.dumps(
                    {
                        "added": [path.name for path in preview.new_paths],
                        "skipped_same_path": [path.name for path in preview.skipped_paths],
                        "conflicts_same_name": [path.name for path in preview.name_conflicts],
                    },
                    ensure_ascii=False,
                ),
            ),
        )
    updated = replace(project, image_count=image_count)
    (updated.project_dir / "project.json").write_text(
        json.dumps(
            {
                **asdict(updated),
                "project_dir": str(updated.project_dir),
                "database_path": str(updated.database_path),
                "image_root": str(updated.image_root),
                "list_path": str(updated.list_path),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return ImageSupplementResult(
        project=updated,
        folder=preview.folder,
        scanned_count=len(preview.scanned_paths),
        added_paths=preview.new_paths,
        skipped_paths=preview.skipped_paths,
        name_conflicts=preview.name_conflicts,
    )


def load_welds(project: ProjectSummary) -> list[WeldRecord]:
    with _connect(project) as connection:
        rows = connection.execute("SELECT serial, source_row, weld_name FROM welds ORDER BY serial").fetchall()
    return [WeldRecord(int(row[0]), int(row[1]), str(row[2])) for row in rows]


def bound_weld_serials(project: ProjectSummary) -> set[int]:
    with _connect(project) as connection:
        rows = connection.execute("SELECT weld_serial FROM annotations WHERE weld_serial IS NOT NULL").fetchall()
    return {int(row[0]) for row in rows}


def load_annotations(project: ProjectSummary, image_index: int) -> list[Annotation]:
    with _connect(project) as connection:
        rows = connection.execute(
            """
            SELECT annotation_id, image_index, weld_serial, center_x, center_y, radius_x, radius_y, status
            FROM annotations WHERE image_index = ? ORDER BY annotation_id
            """,
            (image_index,),
        ).fetchall()
    return [
        Annotation(
            annotation_id=int(row[0]),
            image_index=int(row[1]),
            weld_serial=int(row[2]) if row[2] is not None else None,
            center_x=float(row[3]),
            center_y=float(row[4]),
            radius_x=float(row[5]),
            radius_y=float(row[6]),
            status=str(row[7]),
        )
        for row in rows
    ]


def load_all_annotations(project: ProjectSummary) -> list[Annotation]:
    with _connect(project) as connection:
        rows = connection.execute(
            """
            SELECT annotation_id, image_index, weld_serial, center_x, center_y, radius_x, radius_y, status
            FROM annotations ORDER BY annotation_id
            """
        ).fetchall()
    return [
        Annotation(
            annotation_id=int(row[0]),
            image_index=int(row[1]),
            weld_serial=int(row[2]) if row[2] is not None else None,
            center_x=float(row[3]),
            center_y=float(row[4]),
            radius_x=float(row[5]),
            radius_y=float(row[6]),
            status=str(row[7]),
        )
        for row in rows
    ]


def restore_annotations(project: ProjectSummary, annotations: list[Annotation] | tuple[Annotation, ...]) -> None:
    """恢复一次操作前的标注快照，仅供本次程序会话的撤销/恢复使用。"""
    timestamp = datetime.now().isoformat(timespec="seconds")
    with _connect(project) as connection:
        connection.execute("DELETE FROM annotations")
        connection.executemany(
            """
            INSERT INTO annotations
            (annotation_id, image_index, weld_serial, center_x, center_y, radius_x, radius_y, status, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'manual', ?, ?)
            """,
            [
                (
                    item.annotation_id,
                    item.image_index,
                    item.weld_serial,
                    item.center_x,
                    item.center_y,
                    item.radius_x,
                    item.radius_y,
                    item.status,
                    timestamp,
                    timestamp,
                )
                for item in annotations
            ],
        )


def create_annotation(project: ProjectSummary, image_index: int, center_x: float, center_y: float, radius_x: float | None = None, radius_y: float | None = None) -> Annotation:
    timestamp = datetime.now().isoformat(timespec="seconds")
    if radius_x is None or radius_y is None:
        settings = get_project_settings(project)
        radius_x = float(settings.get("default_radius_x", DEFAULT_RADIUS_X))
        radius_y = float(settings.get("default_radius_y", DEFAULT_RADIUS_Y))
    with _connect(project) as connection:
        cursor = connection.execute(
            """
            INSERT INTO annotations (image_index, weld_serial, center_x, center_y, radius_x, radius_y, status, source, created_at, updated_at)
            VALUES (?, NULL, ?, ?, ?, ?, 'draft', 'manual', ?, ?)
            """,
            (image_index, center_x, center_y, radius_x, radius_y, timestamp, timestamp),
        )
        annotation_id = int(cursor.lastrowid)
    return Annotation(annotation_id, image_index, None, center_x, center_y, radius_x, radius_y, "draft")


def update_annotation(project: ProjectSummary, annotation_id: int, center_x: float, center_y: float, radius_x: float, radius_y: float) -> None:
    timestamp = datetime.now().isoformat(timespec="seconds")
    with _connect(project) as connection:
        connection.execute(
            """
            UPDATE annotations
            SET center_x = ?, center_y = ?, radius_x = ?, radius_y = ?, updated_at = ?
            WHERE annotation_id = ?
            """,
            (center_x, center_y, radius_x, radius_y, timestamp, annotation_id),
        )


def bind_annotation(project: ProjectSummary, annotation_id: int, weld_serial: int) -> None:
    """将一个人工红圈绑定到唯一的手持序号。"""
    timestamp = datetime.now().isoformat(timespec="seconds")
    with _connect(project) as connection:
        exists = connection.execute("SELECT 1 FROM welds WHERE serial = ?", (weld_serial,)).fetchone()
        if exists is None:
            raise ValueError(f"手持序号不存在：{weld_serial}")
        try:
            cursor = connection.execute(
                "UPDATE annotations SET weld_serial = ?, status = 'confirmed', updated_at = ? WHERE annotation_id = ?",
                (weld_serial, timestamp, annotation_id),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("该 Weld Name 已绑定到其他红圈，请先解除原绑定。") from exc
        if cursor.rowcount != 1:
            raise ValueError("未找到当前红圈。")


def unbind_annotation(project: ProjectSummary, annotation_id: int) -> None:
    timestamp = datetime.now().isoformat(timespec="seconds")
    with _connect(project) as connection:
        connection.execute(
            "UPDATE annotations SET weld_serial = NULL, status = 'draft', updated_at = ? WHERE annotation_id = ?",
            (timestamp, annotation_id),
        )


def export_preflight(project: ProjectSummary) -> ExportCheck:
    """检查导出条件；未绑定项为警告，不阻止已确认项导出。"""
    with _connect(project) as connection:
        bound_rows = connection.execute(
            """
            SELECT a.annotation_id, a.image_index, i.original_path, a.weld_serial, w.weld_name,
                   a.center_x, a.center_y, a.radius_x, a.radius_y
            FROM annotations a
            JOIN images i ON i.image_index = a.image_index
            JOIN welds w ON w.serial = a.weld_serial
            WHERE a.weld_serial IS NOT NULL
            ORDER BY a.weld_serial
            """
        ).fetchall()
        unbound_rows = connection.execute(
            """
            SELECT a.annotation_id, i.filename, a.center_x, a.center_y
            FROM annotations a JOIN images i ON i.image_index = a.image_index
            WHERE a.weld_serial IS NULL ORDER BY a.image_index, a.annotation_id
            """
        ).fetchall()

    records: list[ExportRecord] = []
    warnings: list[tuple[str, str]] = []
    blocking: list[tuple[str, str]] = []
    output_names: set[str] = set()
    template = get_project_settings(project).get("filename_template", DEFAULT_FILENAME_TEMPLATE)
    for row in bound_rows:
        annotation_id, image_index, source_path, serial, weld_name, center_x, center_y, radius_x, radius_y = row
        source = Path(str(source_path))
        try:
            output_file = _format_export_filename(template, int(serial), str(weld_name), source, int(annotation_id))
        except ValueError as exc:
            blocking.append(("导出文件名模板", str(exc)))
            continue
        if output_file in output_names:
            blocking.append(("重复输出文件名", output_file))
            continue
        output_names.add(output_file)
        if not source.is_file():
            blocking.append(("原图不存在", str(source)))
            continue
        try:
            with Image.open(source) as image:
                width, height = image.size
        except OSError as exc:
            blocking.append(("原图无法读取", f"{source}：{exc}"))
            continue
        left = float(center_x) - float(radius_x)
        top = float(center_y) - float(radius_y)
        right = float(center_x) + float(radius_x)
        bottom = float(center_y) + float(radius_y)
        if left < 0 or top < 0 or right > width or bottom > height:
            blocking.append(("红圈超出原图边界", f"{source.name} · 标注 {annotation_id}"))
            continue
        records.append(
            ExportRecord(
                annotation_id=int(annotation_id),
                image_index=int(image_index),
                source_image=source,
                serial=int(serial),
                weld_name=str(weld_name),
                center_x=float(center_x),
                center_y=float(center_y),
                radius_x=float(radius_x),
                radius_y=float(radius_y),
                output_file=output_file,
            )
        )
    unbound = tuple((int(row[0]), str(row[1]), float(row[2]), float(row[3])) for row in unbound_rows)
    unassigned = tuple(weld for weld in load_welds(project) if weld.weld_name and weld.serial not in bound_weld_serials(project))
    if unbound:
        warnings.append(("未绑定红圈", f"{len(unbound)} 个；不会导出"))
    if unassigned:
        warnings.append(("未分配 Weld Name", f"{len(unassigned)} 个；不会导出"))
    if not records and not blocking:
        warnings.append(("没有已确认绑定", "当前没有可导出的图片"))
    return ExportCheck(tuple(records), tuple(warnings), tuple(blocking), unbound, unassigned)


def _next_export_dir(project: ProjectSummary) -> Path:
    root = project.project_dir / "exports"
    root.mkdir(parents=True, exist_ok=True)
    base = datetime.now().strftime("%Y%m%d_%H%M%S")
    for suffix in range(1, 1000):
        candidate = root / f"{base}_{suffix:03d}"
        if not candidate.exists():
            candidate.mkdir()
            return candidate
    raise RuntimeError("无法创建新的导出批次目录")


def _style_sheet(sheet) -> None:  # type: ignore[no-untyped-def]
    header_fill = PatternFill("solid", fgColor="1F4E78")
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center")
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for column in range(1, sheet.max_column + 1):
        longest = max(len(str(sheet.cell(row, column).value or "")) for row in range(1, sheet.max_row + 1))
        sheet.column_dimensions[get_column_letter(column)].width = min(max(longest + 2, 12), 55)


def _write_export_report(output_dir: Path, check: ExportCheck, exported: list[ExportRecord], blocked: bool) -> tuple[Path, Path]:
    report_path = output_dir / "出图清单.xlsx"
    manifest_path = output_dir / "出图清单.csv"
    book = Workbook()
    book.remove(book.active)

    summary = book.create_sheet("汇总")
    summary.append(["项目", "数量/说明"])
    summary.append(["可导出已确认绑定", len(check.records)])
    summary.append(["实际已出图", len(exported)])
    summary.append(["未绑定红圈", len(check.unbound_annotations)])
    summary.append(["未分配 Weld Name", len(check.unassigned_welds)])
    summary.append(["阻断问题", len(check.blocking_issues)])
    summary.append(["导出状态", "已阻断，仅生成问题清单" if blocked else "完成；每张图片仅绘制一个红圈"])
    _style_sheet(summary)

    exported_sheet = book.create_sheet("已出图")
    exported_sheet.append(["手持序号", "Weld Name", "原始图片", "标注ID", "圆心X", "圆心Y", "半径X", "半径Y", "输出文件"])
    for item in exported:
        exported_sheet.append([item.serial, item.weld_name, item.source_image.name, item.annotation_id, item.center_x, item.center_y, item.radius_x, item.radius_y, item.output_file])
    _style_sheet(exported_sheet)

    unbound_sheet = book.create_sheet("未绑定红圈")
    unbound_sheet.append(["标注ID", "原始图片", "圆心X", "圆心Y", "说明"])
    for annotation_id, source_image, center_x, center_y in check.unbound_annotations:
        unbound_sheet.append([annotation_id, source_image, center_x, center_y, "未绑定 Weld Name，不出图"])
    _style_sheet(unbound_sheet)

    unassigned_sheet = book.create_sheet("未分配WeldName")
    unassigned_sheet.append(["手持序号", "Weld Name", "原始行", "说明"])
    for weld in check.unassigned_welds:
        unassigned_sheet.append([weld.serial, weld.weld_name, weld.source_row, "尚未绑定红圈，不出图"])
    _style_sheet(unassigned_sheet)

    issues_sheet = book.create_sheet("问题")
    issues_sheet.append(["级别", "问题类型", "说明"])
    for issue_type, detail in check.warnings:
        issues_sheet.append(["提示", issue_type, detail])
    for issue_type, detail in check.blocking_issues:
        issues_sheet.append(["阻断", issue_type, detail])
    _style_sheet(issues_sheet)
    book.save(report_path)

    with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["手持序号", "Weld Name", "原始图片", "标注ID", "输出文件", "圆心X", "圆心Y", "半径X", "半径Y"])
        writer.writeheader()
        for item in exported:
            writer.writerow(
                {
                    "手持序号": item.serial,
                    "Weld Name": item.weld_name,
                    "原始图片": item.source_image.name,
                    "标注ID": item.annotation_id,
                    "输出文件": item.output_file,
                    "圆心X": item.center_x,
                    "圆心Y": item.center_y,
                    "半径X": item.radius_x,
                    "半径Y": item.radius_y,
                }
            )
    return report_path, manifest_path


def export_confirmed_annotations(project: ProjectSummary) -> ExportResult:
    """每个已绑定标注导出一张独立 PNG，且只绘制它自己的红圈。"""
    check = export_preflight(project)
    output_dir = _next_export_dir(project)
    exported: list[ExportRecord] = []
    blocked = bool(check.blocking_issues)
    if not blocked:
        images_dir = output_dir / "images"
        images_dir.mkdir()
        for item in check.records:
            with Image.open(item.source_image) as source:
                image = source.convert("RGB")
            draw = ImageDraw.Draw(image)
            ellipse = (
                round(item.center_x - item.radius_x),
                round(item.center_y - item.radius_y),
                round(item.center_x + item.radius_x),
                round(item.center_y + item.radius_y),
            )
            line_width = max(4, round(min(image.size) * 0.002))
            draw.ellipse(ellipse, outline=(255, 0, 0), width=line_width)
            image.save(images_dir / item.output_file, "PNG")
            exported.append(item)
    report_path, manifest_path = _write_export_report(output_dir, check, exported, blocked)
    with _connect(project) as connection:
        connection.execute(
            "INSERT INTO exports (output_dir, created_at, exported_count, warning_count, blocking_count) VALUES (?, ?, ?, ?, ?)",
            (str(output_dir), datetime.now().isoformat(timespec="seconds"), len(exported), len(check.warnings), len(check.blocking_issues)),
        )
    return ExportResult(output_dir, report_path, manifest_path, len(exported), blocked, len(check.warnings), len(check.blocking_issues))


def delete_annotation(project: ProjectSummary, annotation_id: int) -> None:
    with _connect(project) as connection:
        connection.execute("DELETE FROM annotations WHERE annotation_id = ?", (annotation_id,))


def list_projects() -> list[ProjectSummary]:
    if not PROJECTS_ROOT.exists():
        return []
    projects: list[ProjectSummary] = []
    for database_path in sorted(PROJECTS_ROOT.glob("*/project.sqlite"), reverse=True):
        try:
            with sqlite3.connect(database_path) as connection:
                row = connection.execute("SELECT * FROM project LIMIT 1").fetchone()
            if row is None:
                continue
            projects.append(
                ProjectSummary(
                    project_id=row[0],
                    name=row[1],
                    project_dir=database_path.parent,
                    database_path=database_path,
                    image_root=Path(row[2]),
                    list_path=Path(row[3]),
                    worksheet=row[4],
                    weld_column=row[5],
                    created_at=row[6],
                    image_count=row[7],
                    record_count=row[8],
                    valid_weld_count=row[9],
                    empty_weld_count=row[10],
                    duplicate_weld_count=row[11],
                )
            )
        except sqlite3.Error:
            continue
    return projects

