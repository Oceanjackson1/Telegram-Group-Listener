"""File parser — extract text from PDF, TXT, MD, DOCX files and split into chunks."""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

CHUNK_SIZE = 800  # characters per chunk
CHUNK_OVERLAP = 100  # overlap between chunks


def parse_file(file_path: str, file_type: str) -> list[str]:
    """Parse a file and return a list of text chunks."""
    text = _extract_text(file_path, file_type)
    text = _clean_text(text)
    if not text.strip():
        return []
    return _split_into_chunks(text)


def _extract_text(file_path: str, file_type: str) -> str:
    """Extract raw text from a file based on its type."""
    path = Path(file_path)

    if file_type in ("txt", "md"):
        return path.read_text(encoding="utf-8", errors="replace")

    if file_type == "pdf":
        return _extract_pdf(path)

    if file_type == "docx":
        return _extract_docx(path)

    raise ValueError(f"Unsupported file type: {file_type}")


def _extract_pdf(path: Path) -> str:
    """Extract text from PDF using PyPDF2."""
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        return "\n\n".join(pages)
    except ImportError:
        logger.warning("PyPDF2 not installed, trying pdfplumber")
        try:
            import pdfplumber
            with pdfplumber.open(str(path)) as pdf:
                pages = []
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        pages.append(text)
                return "\n\n".join(pages)
        except ImportError:
            raise ImportError("Neither PyPDF2 nor pdfplumber is installed. Install with: pip install PyPDF2")


def _extract_docx(path: Path) -> str:
    """Extract text from DOCX using python-docx."""
    try:
        import docx
        doc = docx.Document(str(path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    except ImportError:
        raise ImportError("python-docx is not installed. Install with: pip install python-docx")


def _clean_text(text: str) -> str:
    """Clean extracted text."""
    # Collapse multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Remove excessive whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def _split_into_chunks(text: str) -> list[str]:
    """Split text into overlapping chunks."""
    # First try splitting by paragraphs
    paragraphs = text.split("\n\n")

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current_chunk) + len(para) + 2 <= CHUNK_SIZE:
            current_chunk = (current_chunk + "\n\n" + para).strip()
        else:
            if current_chunk:
                chunks.append(current_chunk)
            # If a single paragraph is longer than CHUNK_SIZE, split it
            if len(para) > CHUNK_SIZE:
                words = para.split()
                current_chunk = ""
                for word in words:
                    if len(current_chunk) + len(word) + 1 <= CHUNK_SIZE:
                        current_chunk = (current_chunk + " " + word).strip()
                    else:
                        if current_chunk:
                            chunks.append(current_chunk)
                        current_chunk = word
            else:
                current_chunk = para

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def extract_keywords(text: str, max_keywords: int = 10) -> list[str]:
    """Extract simple keywords from text (most frequent meaningful words)."""
    # Simple approach: split into words, filter short/common words, count frequency
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "to", "of", "in", "for",
        "on", "with", "at", "by", "from", "as", "into", "through", "during",
        "before", "after", "above", "below", "between", "under", "again",
        "further", "then", "once", "here", "there", "when", "where", "why",
        "how", "all", "both", "each", "few", "more", "most", "other", "some",
        "such", "no", "not", "only", "own", "same", "so", "than", "too",
        "very", "just", "don", "now", "and", "but", "or", "if", "it", "its",
        "this", "that", "these", "those", "i", "me", "my", "we", "our", "you",
        "your", "he", "him", "his", "she", "her", "they", "them", "their",
        "what", "which", "who", "whom",
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
        "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
        "会", "着", "没有", "看", "好", "自己", "这",
    }

    words = re.findall(r'[\w\u4e00-\u9fff]+', text.lower())
    word_count: dict[str, int] = {}
    for w in words:
        if len(w) < 2 or w in stop_words or w.isdigit():
            continue
        word_count[w] = word_count.get(w, 0) + 1

    sorted_words = sorted(word_count.items(), key=lambda x: x[1], reverse=True)
    return [w for w, _ in sorted_words[:max_keywords]]
