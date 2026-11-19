import re


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Split text into overlapping chunks, preferring sentence or word boundaries."""
    if overlap >= size:
        raise ValueError("chunk overlap must be smaller than chunk size")
    text = re.sub(r"\s+", " ", text).strip()
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            window = start + int(size * 0.6)
            cut = text.rfind(". ", window, end)
            if cut == -1:
                cut = text.rfind(" ", window, end)
            if cut != -1:
                end = cut + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks
