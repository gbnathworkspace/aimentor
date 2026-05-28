from langchain_mongodb import MongoDBAtlasVectorSearch
from langchain_openai import OpenAIEmbeddings
from core.config import settings
from core.database import get_collection


def _get_vector_store() -> MongoDBAtlasVectorSearch:
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=settings.openai_api_key,
    )
    collection = get_collection("sessions")
    return MongoDBAtlasVectorSearch(
        collection=collection,
        embedding=embeddings,
        index_name="session_embedding_index",
        text_key="summary",
        embedding_key="embedding",
    )


async def store_summary(
    summary: str,
    metadata: dict,
) -> None:
    store = _get_vector_store()
    store.add_texts(texts=[summary], metadatas=[metadata])


async def retrieve_relevant(
    query: str,
    topic_category: str | None = None,
    k: int = 5,
) -> list[str]:
    store = _get_vector_store()
    search_kwargs: dict = {"k": k}
    if topic_category:
        search_kwargs["pre_filter"] = {"topic_category": {"$eq": topic_category}}

    retriever = store.as_retriever(search_kwargs=search_kwargs)
    docs = retriever.invoke(query)
    return [doc.page_content for doc in docs]


def format_for_context(summaries: list[str]) -> str:
    if not summaries:
        return ""
    lines = ["Relevant past sessions:"]
    for s in summaries:
        lines.append(f"- {s}")
    return "\n".join(lines)
