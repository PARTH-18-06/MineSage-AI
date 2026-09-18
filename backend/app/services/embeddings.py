from functools import lru_cache

from app.config import settings


@lru_cache(maxsize=1)
def get_embedding_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embedding_model_name)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    model = get_embedding_model()
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    vectors = embeddings.tolist()
    for vector in vectors:
        if len(vector) != settings.embedding_dimension:
            raise ValueError(
                f"Embedding dimension mismatch: expected {settings.embedding_dimension}, got {len(vector)}"
            )
    return vectors


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]


def to_vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
