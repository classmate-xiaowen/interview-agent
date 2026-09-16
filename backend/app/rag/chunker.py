def chunk_text(text: str, max_chars: int = 800, overlap: int = 80) -> list[str]:
    if not text or not text.strip():
        return []
    blocks = [b for b in text.split("\n\n") if b.strip()]
    if not blocks:
        blocks = [text]
    out: list[str] = []
    for b in blocks:
        if len(b) <= max_chars:
            out.append(b)
            continue
        start = 0
        while start < len(b):
            seg = b[start:start + max_chars]
            out.append(seg)
            start += max_chars - overlap
    return out
