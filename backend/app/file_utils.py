"""File content extraction, formatting, and truncation utilities."""

import os
import hashlib
from pathlib import Path


# Image MIME types supported for multimodal
_IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}


def is_image_file(file_path: str) -> bool:
    """Check if a file is an image based on extension."""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in _IMAGE_MIME_TYPES


def image_to_base64(file_path: str) -> tuple[str, str]:
    """Read an image file and return (base64_string, mime_type).

    Returns:
        (base64_data, mime_type) where base64_data is the raw base64 string
        without the data URI prefix.
    """
    ext = os.path.splitext(file_path)[1].lower()
    mime_type = _IMAGE_MIME_TYPES.get(ext, "image/png")
    with open(file_path, "rb") as f:
        data = f.read()
    import base64
    return base64.b64encode(data).decode("utf-8"), mime_type


# File extensions that are treated as plain text
TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".json", ".csv", ".tsv",
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs",
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".sql", ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd",
    ".java", ".kt", ".scala", ".groovy",
    ".go", ".rs", ".rb", ".php", ".lua", ".r", ".pl", ".pm",
    ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh",
    ".cs", ".swift", ".m", ".mm",
    ".Dockerfile", ".dockerfile", ".gitignore", ".env",
}

# Extensions that we know we cannot extract text from
UNSUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".mkv",
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2",
    ".exe", ".dll", ".so", ".dylib", ".bin",
    ".doc", ".xls", ".ppt", ".odt", ".ods", ".odp",
}


def get_file_extension(filename: str) -> str:
    """Get the lowercase extension including the dot."""
    return Path(filename).suffix.lower()


def is_text_file(filename: str) -> bool:
    """Check if a file is a known text file by extension."""
    ext = get_file_extension(filename)
    # Also handle files like "Dockerfile" without extension
    base = Path(filename).name
    if base in TEXT_EXTENSIONS:
        return True
    return ext in TEXT_EXTENSIONS


def is_unsupported_file(filename: str) -> bool:
    """Check if a file type is known to be unsupported."""
    ext = get_file_extension(filename)
    return ext in UNSUPPORTED_EXTENSIONS


def read_text_file(file_path: str) -> str:
    """Read a text file with encoding fallback."""
    for encoding in ("utf-8", "utf-8-sig", "gbk", "gb2312", "latin-1"):
        try:
            with open(file_path, "r", encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    return f"[Error: Unable to decode file with any known encoding]"


def extract_pdf_text(file_path: str) -> str:
    """Extract text from PDF using pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return "[Error: PDF support not available. Please install pypdf.]"

    try:
        reader = PdfReader(file_path)
        parts = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                parts.append(text)
        full_text = "\n\n".join(parts)
        if not full_text.strip():
            return "[Note: This PDF appears to contain no extractable text (possibly scanned images).]"
        return full_text
    except Exception as e:
        return f"[Error extracting PDF: {e}]"


def extract_text(file_path: str, filename: str | None = None) -> str:
    """Extract text content from a file based on its type.

    Returns the extracted text, or an error/info message string.
    """
    if filename is None:
        filename = os.path.basename(file_path)

    if is_unsupported_file(filename):
        return f"[Note: File type '{get_file_extension(filename)}' is not supported for text extraction.]"

    ext = get_file_extension(filename)

    if ext == ".pdf":
        return extract_pdf_text(file_path)

    if is_text_file(filename) or ext == "":
        return read_text_file(file_path)

    # Unknown extension: try to read as text first
    try:
        content = read_text_file(file_path)
        # If it looks like binary (many null bytes or non-printable chars), bail
        null_count = content.count("\x00")
        if null_count > 10:
            return f"[Note: File appears to be binary and cannot be read as text.]"
        return content
    except Exception as e:
        return f"[Error reading file: {e}]"


def compute_content_hash(content: str) -> str:
    """Compute a hash of file content for cache invalidation."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def truncate_content(content: str, max_chars: int, label: str = "") -> str:
    """Intelligently truncate content, keeping head and tail.

    Args:
        content: The full content string.
        max_chars: Maximum characters to keep.
        label: Optional label to include in truncation notice.

    Returns:
        Truncated string with a notice in the middle if truncated.
    """
    if len(content) <= max_chars:
        return content

    half = max_chars // 2
    head = content[:half]
    tail = content[-half:]
    omitted = len(content) - max_chars

    label_info = f" ({label})" if label else ""
    notice = f"\n\n[... 中间省略 {omitted} 字符{label_info}，共 {len(content)} 字符 ...]\n\n"
    return head + notice + tail


def format_file_for_prompt(name: str, content: str, is_summary: bool = False) -> str:
    """Format a single file's content for inclusion in a prompt."""
    suffix = "（摘要）" if is_summary else ""
    return f"=== 文件: {name}{suffix} ({len(content)} 字符) ===\n{content}\n==="


def format_files_for_prompt(file_items: list[dict]) -> str:
    """Format multiple files into a prompt fragment.

    Args:
        file_items: List of dicts with keys:
            - name: filename
            - content: extracted text content
            - is_summary: bool, whether this is a summary

    Returns:
        A formatted string ready to prepend to user message.
    """
    if not file_items:
        return ""

    lines = ["以下是用户上传的参考文件，请在回答时参考这些内容：\n"]
    for item in file_items:
        name = item.get("name", "unknown")
        content = item.get("content", "")
        is_summary = item.get("is_summary", False)
        lines.append(format_file_for_prompt(name, content, is_summary))
        lines.append("")

    return "\n".join(lines)


def format_summary_prompt(file_content: str, filename: str) -> str:
    """Build the prompt used to summarize a long file."""
    return (
        f"请为以下文件生成一份结构化摘要。文件名：{filename}\n\n"
        "摘要应包括：\n"
        "1. 文件主旨（1-2 句话）\n"
        "2. 核心要点（最多 5 条 bullet points）\n"
        "3. 关键数据/结论（如有）\n"
        "4. 重要细节补充（不超过 500 字）\n\n"
        "请确保摘要不超过 2000 字符。\n\n"
        f"【文件内容】\n{file_content}\n\n"
        "【摘要】"
    )
