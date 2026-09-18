from dataclasses import dataclass
import re


@dataclass(frozen=True)
class TextSection:
    text: str
    page_number: int | None
    source_reference: str


@dataclass(frozen=True)
class TextChunk:
    text: str
    page_number: int | None
    source_reference: str


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_sections(sections: list[TextSection], max_chars: int = 1200, overlap: int = 150) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    for section in sections:
        text = clean_text(section.text)
        if not text:
            continue

        start = 0
        while start < len(text):
            end = min(start + max_chars, len(text))
            if end < len(text):
                boundary = text.rfind(" ", start, end)
                if boundary > start + max_chars // 2:
                    end = boundary

            chunk_text = clean_text(text[start:end])
            if chunk_text:
                chunks.append(
                    TextChunk(
                        text=chunk_text,
                        page_number=section.page_number,
                        source_reference=section.source_reference,
                    )
                )

            if end >= len(text):
                break
            start = max(end - overlap, 0)

    return chunks
