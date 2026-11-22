"""报修附件的格式、数量和本地存储控制。"""

from pathlib import Path
from uuid import uuid4

from werkzeug.datastructures import FileStorage
from app.models import TicketAttachment


ALLOWED_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}


def prepare_attachments(files: list[FileStorage], *, existing_count: int, max_count: int, max_size: int):
    """读取并校验附件；仅允许照片、截图和 PDF，防止危险文件写入运行目录。"""

    selected = [file for file in files if file and file.filename]
    if existing_count + len(selected) > max_count:
        raise ValueError(f"每张工单最多上传 {max_count} 个附件。")

    prepared = []
    for file in selected:
        original_name = Path(file.filename.replace("\\", "/")).name.strip()[:255]
        suffix = Path(original_name).suffix.lower()
        expected_mime = ALLOWED_TYPES.get(suffix)
        if not original_name or not expected_mime or file.mimetype not in {expected_mime, "application/octet-stream"}:
            raise ValueError("仅支持 JPG、PNG、WEBP 图片或 PDF 文件。")
        content = file.read(max_size + 1)
        if not content:
            raise ValueError("附件内容不能为空。")
        if len(content) > max_size:
            raise ValueError(f"单个附件不能超过 {max_size // (1024 * 1024)} MB。")
        prepared.append((original_name, suffix, expected_mime, content))
    return prepared


def save_attachments(ticket, prepared, *, uploaded_by: str, upload_dir: str) -> list[TicketAttachment]:
    """保存已验证内容，并返回待写入数据库的附件记录。"""

    directory = Path(upload_dir)
    directory.mkdir(parents=True, exist_ok=True)
    records = []
    for original_name, suffix, mime_type, content in prepared:
        stored_name = f"{uuid4().hex}{suffix}"
        (directory / stored_name).write_bytes(content)
        records.append(TicketAttachment(
            ticket=ticket,
            original_name=original_name,
            stored_name=stored_name,
            mime_type=mime_type,
            file_size=len(content),
            uploaded_by=uploaded_by,
        ))
    return records
