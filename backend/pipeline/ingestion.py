import tempfile
import os
import json
import pandas as pd
from langchain_community.document_loaders import PyMuPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_mongodb import MongoDBAtlasVectorSearch
import anthropic

from core.config import settings
from core.database import get_collection
from core.models import CoreProfile, SkillNode
from memory.layer1 import upsert_profile
from memory.layer2 import upsert_skill_node

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
_splitter = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=50)

RESUME_PARSE_PROMPT = """Parse this resume and extract structured information.
Return ONLY valid JSON with this shape:
{{
  "overall_level": "beginner|intermediate|advanced",
  "skills": ["skill1", "skill2"],
  "experience_years": 0,
  "strong_topics": ["topic1"],
  "weak_topics": []
}}

Resume text:
{text}"""


async def process_resume(file_bytes: bytes, filename: str, user_id: str) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        loader = PyMuPDFLoader(tmp_path)
        docs = loader.load()
        full_text = "\n".join(d.page_content for d in docs)

        response = _client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{"role": "user", "content": RESUME_PARSE_PROMPT.format(text=full_text[:4000])}],
        )
        parsed = json.loads(response.content[0].text.strip())

        chunks = _splitter.split_documents(docs)
        _store_chunks(chunks, user_id, source="resume")

        return parsed
    finally:
        os.unlink(tmp_path)


async def process_leetcode_csv(file_bytes: bytes, user_id: str) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="wb") as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        df = pd.read_csv(tmp_path)
        difficulty_col = next((c for c in df.columns if "difficulty" in c.lower()), None)
        topic_col = next((c for c in df.columns if "topic" in c.lower() or "tag" in c.lower()), None)

        signals: dict = {"easy": 0, "medium": 0, "hard": 0}
        if difficulty_col:
            counts = df[difficulty_col].str.lower().value_counts().to_dict()
            signals.update({k: int(v) for k, v in counts.items() if k in signals})

        return {"leetcode_solved": signals, "total": len(df)}
    finally:
        os.unlink(tmp_path)


def _store_chunks(docs, user_id: str, source: str) -> None:
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=settings.openai_api_key,
    )
    collection = get_collection("sessions")
    metadatas = [{"user_id": user_id, "source": source} for _ in docs]
    MongoDBAtlasVectorSearch.from_documents(
        docs,
        embeddings,
        collection=collection,
        index_name="session_embedding_index",
    )
