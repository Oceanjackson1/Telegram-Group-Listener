"""Knowledge store — file management, chunk storage, and BM25-based retrieval."""
from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime, timezone

from services.file_parser import extract_keywords

logger = logging.getLogger(__name__)


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


# ─── Storage ─────────────────────────────────────────────────────────────

def store_file_chunks(
    db,
    chat_id: str,
    file_name: str,
    file_type: str,
    file_size: int,
    file_path: str,
    chunks: list[str],
    uploaded_by: int,
) -> int:
    """Store a parsed file and its chunks. Returns file ID."""
    now = _now_utc()
    total_chars = sum(len(c) for c in chunks)

    db.execute(
        "INSERT INTO knowledge_files (chat_id, file_name, file_type, file_size, file_path, chunk_count, total_chars, uploaded_by, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)",
        (chat_id, file_name, file_type, file_size, file_path, len(chunks), total_chars, uploaded_by, now, now),
    )
    db.commit()

    file_row = db.fetchone("SELECT id FROM knowledge_files WHERE chat_id = ? ORDER BY id DESC LIMIT 1", (chat_id,))
    file_id = file_row["id"]

    chunk_params = []
    for i, chunk_text in enumerate(chunks):
        keywords = extract_keywords(chunk_text)
        chunk_params.append((
            file_id, chat_id, i, chunk_text,
            ",".join(keywords), len(chunk_text),
        ))

    db.executemany(
        "INSERT INTO knowledge_chunks (file_id, chat_id, chunk_index, content, keywords, char_count) VALUES (?, ?, ?, ?, ?, ?)",
        chunk_params,
    )
    db.commit()
    return file_id


def delete_file(db, file_id: int) -> None:
    """Soft-delete a knowledge file and its chunks."""
    db.execute("UPDATE knowledge_files SET status = 'deleted', updated_at = ? WHERE id = ?", (_now_utc(), file_id))
    db.execute("DELETE FROM knowledge_chunks WHERE file_id = ?", (file_id,))
    db.commit()


# ─── Retrieval ───────────────────────────────────────────────────────────

def retrieve_context(db, chat_id: str, query: str, top_k: int = 5) -> str:
    """Retrieve the most relevant knowledge context for a query using BM25-like scoring."""
    chunks = db.fetchall(
        "SELECT * FROM knowledge_chunks WHERE chat_id = ? ORDER BY id",
        (chat_id,),
    )
    if not chunks:
        return ""

    query_terms = _tokenize(query)
    if not query_terms:
        # Just return first chunks as context
        return "\n\n".join(c["content"] for c in chunks[:top_k])

    # BM25 parameters
    k1 = 1.5
    b = 0.75

    # Calculate IDF
    N = len(chunks)
    doc_freq: dict[str, int] = {}
    doc_lengths: list[int] = []
    doc_tokens: list[set[str]] = []

    for chunk in chunks:
        tokens = set(_tokenize(chunk["content"]))
        doc_tokens.append(tokens)
        doc_lengths.append(len(chunk["content"]))
        for term in tokens:
            doc_freq[term] = doc_freq.get(term, 0) + 1

    avg_dl = sum(doc_lengths) / N if N > 0 else 1

    # Score each chunk
    scored: list[tuple[float, int]] = []
    for idx, chunk in enumerate(chunks):
        score = 0.0
        dl = doc_lengths[idx]
        tokens = doc_tokens[idx]

        for term in query_terms:
            if term not in doc_freq:
                continue
            df = doc_freq[term]
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1)
            tf = 1 if term in tokens else 0
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * dl / avg_dl)
            score += idf * numerator / denominator if denominator > 0 else 0

        # Also boost by keyword match
        chunk_keywords = chunk.get("keywords", "").lower()
        for term in query_terms:
            if term in chunk_keywords:
                score += 0.5

        scored.append((score, idx))

    scored.sort(key=lambda x: -x[0])
    top_indices = [idx for _, idx in scored[:top_k] if scored[0][0] > 0]

    if not top_indices:
        # Fallback: return first chunks
        return "\n\n".join(c["content"] for c in chunks[:top_k])

    context_parts = []
    for idx in top_indices:
        content = chunks[idx]["content"]
        file_id = chunks[idx]["file_id"]
        file_info = db.fetchone("SELECT file_name FROM knowledge_files WHERE id = ?", (file_id,))
        source = file_info["file_name"] if file_info else "unknown"
        context_parts.append(f"[Source: {source}]\n{content}")

    return "\n\n---\n\n".join(context_parts)


def has_knowledge(db, chat_id: str) -> bool:
    """Check if a group has any active knowledge files."""
    row = db.fetchone(
        "SELECT COUNT(*) as cnt FROM knowledge_files WHERE chat_id = ? AND status = 'active'",
        (chat_id,),
    )
    return row["cnt"] > 0 if row else False


def _tokenize(text: str) -> list[str]:
    """Simple tokenization for BM25."""
    text_lower = text.lower()
    # Extract words (including Chinese characters as individual tokens)
    tokens = re.findall(r'[\w\u4e00-\u9fff]+', text_lower)
    # Filter very short tokens
    return [t for t in tokens if len(t) >= 2 or '\u4e00' <= t <= '\u9fff']
