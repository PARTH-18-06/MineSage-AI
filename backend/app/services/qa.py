import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import QAAnswer, User
from app.services.audit import write_audit_log
from app.services.embeddings import embed_text, to_vector_literal

NO_CONTEXT_ANSWER = "I could not find enough relevant information in the uploaded documents."


def answer_question(db: Session, question: str, limit: int, user: User) -> dict:
    write_audit_log(
        db,
        action="qa_question_asked",
        entity_type="qa",
        user_id=user.id,
        metadata={"question": question, "limit": limit},
    )
    db.flush()

    citations = retrieve_relevant_chunks(db, question, limit)
    mode = "local_extractive"
    answer = generate_local_extractive_answer(question, citations)

    if settings.qa_mode == "llm" and citations:
        try:
            llm_answer = generate_provider_answer(question, citations)
        except Exception as exc:
            write_audit_log(
                db,
                action="qa_answer_failed",
                entity_type="qa",
                user_id=user.id,
                metadata={
                    "question": question,
                    "mode_requested": "llm",
                    "provider": settings.llm_provider,
                    "error_message": str(exc),
                },
            )
        else:
            if llm_answer:
                answer = llm_answer
                mode = "llm"

    saved = QAAnswer(
        user_id=user.id,
        question=question,
        answer=answer,
        mode=mode,
        citations=citations,
    )
    db.add(saved)
    db.flush()
    write_audit_log(
        db,
        action="qa_answer_generated",
        entity_type="qa_answer",
        entity_id=saved.id,
        user_id=user.id,
        metadata={"mode": mode, "citation_count": len(citations)},
    )
    db.commit()
    db.refresh(saved)

    return {
        "question": saved.question,
        "answer": saved.answer,
        "mode": saved.mode,
        "citations": saved.citations,
        "saved_answer_id": saved.id,
    }


def retrieve_relevant_chunks(db: Session, question: str, limit: int) -> list[dict]:
    query_vector = to_vector_literal(embed_text(question))
    rows = db.execute(
        text(
            """
            SELECT
                chunks.id AS chunk_id,
                chunks.document_id,
                documents.original_filename AS filename,
                chunks.chunk_index,
                chunks.page_number,
                chunks.source_reference,
                (chunks.embedding <=> CAST(:query_embedding AS vector))::float AS distance,
                (1 - (chunks.embedding <=> CAST(:query_embedding AS vector)))::float AS similarity,
                LEFT(chunks.text, 700) AS text_snippet
            FROM chunks
            JOIN documents ON documents.id = chunks.document_id
            WHERE chunks.embedding IS NOT NULL
            ORDER BY chunks.embedding <=> CAST(:query_embedding AS vector)
            LIMIT :limit
            """
        ),
        {"query_embedding": query_vector, "limit": limit},
    ).mappings().all()
    return [dict(row) for row in rows]


def generate_local_extractive_answer(question: str, citations: list[dict]) -> str:
    if not citations:
        return NO_CONTEXT_ANSWER

    selected = select_relevant_sentences(question, citations)
    if not selected:
        selected = [citations[0]["text_snippet"].strip()]

    answer = " ".join(selected)
    return answer[:1200].strip() or NO_CONTEXT_ANSWER


def select_relevant_sentences(question: str, citations: list[dict]) -> list[str]:
    query_terms = {
        term
        for term in re.findall(r"[a-zA-Z0-9.]+", question.lower())
        if len(term) > 2 and term not in {"what", "are", "the", "and", "for", "with", "from", "that", "this"}
    }
    sentences: list[tuple[int, str]] = []
    for citation in citations[:3]:
        text_snippet = citation["text_snippet"]
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text_snippet):
            clean_sentence = sentence.strip()
            if not clean_sentence:
                continue
            sentence_terms = set(re.findall(r"[a-zA-Z0-9.]+", clean_sentence.lower()))
            score = len(query_terms & sentence_terms)
            if score:
                sentences.append((score, clean_sentence))

    sentences.sort(key=lambda item: item[0], reverse=True)
    unique: list[str] = []
    seen: set[str] = set()
    for _score, sentence in sentences:
        if sentence not in seen:
            unique.append(sentence)
            seen.add(sentence)
        if len(unique) >= 3:
            break
    return unique


def build_llm_prompt(question: str, citations: list[dict]) -> str:
    context = "\n\n".join(
        f"[{index}] document_id={citation['document_id']} filename={citation['filename']} "
        f"chunk_id={citation['chunk_id']} source={citation['source_reference']}\n{citation['text_snippet']}"
        for index, citation in enumerate(citations, start=1)
    )
    return (
        "Answer the question using only the provided retrieved context. "
        "If the context does not contain enough information, say so clearly. "
        "Keep the answer concise and do not invent facts.\n\n"
        f"Question: {question}\n\nRetrieved context:\n{context}"
    )


def generate_provider_answer(question: str, citations: list[dict]) -> str | None:
    provider = settings.llm_provider.lower()
    if provider == "groq":
        return generate_groq_answer(question, citations)
    if provider == "gemini":
        return generate_gemini_answer(question, citations)
    raise ValueError(f"Unsupported LLM provider '{settings.llm_provider}'")


def generate_groq_answer(question: str, citations: list[dict]) -> str | None:
    from openai import OpenAI

    if not settings.groq_api_key:
        raise ValueError("GROQ_API_KEY is not configured")

    client = OpenAI(
        api_key=settings.groq_api_key,
        base_url="https://api.groq.com/openai/v1",
        timeout=45.0,
    )
    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": "You answer with grounded facts from retrieved mining documents only."},
            {"role": "user", "content": build_llm_prompt(question, citations)},
        ],
        temperature=0.1,
    )
    content = response.choices[0].message.content
    return content.strip() if content else None


def generate_gemini_answer(question: str, citations: list[dict]) -> str | None:
    import google.generativeai as genai

    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not configured")

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(settings.gemini_model)
    response = model.generate_content(build_llm_prompt(question, citations))
    text_response = getattr(response, "text", None)
    return text_response.strip() if text_response else None
