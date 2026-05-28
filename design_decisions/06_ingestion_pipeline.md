# Ingestion Pipeline

## Decision
Extract, route, and store uploaded files based on their content type.
Structured data goes to MongoDB. Free-form data goes to Vector DB.

## Pipeline

```
Upload
  │
  ▼
Extract (PDF / CSV / image → text)
  │
  ▼
Route
  │
  ├── free-form (resume text, session notes, images)
  │       │
  │       ▼
  │   Chunk + Embed → Vector DB
  │
  └── structured (LeetCode CSV, progress exports)
          │
          ▼
      Parse to structured facts → MongoDB (Skill Graph)
```

## File types and handling

| File | Type | Destination |
|---|---|---|
| Resume PDF | free-form | extract → parse into L1 + L2 facts |
| LeetCode CSV | structured | parse → skill graph signals |
| Session notes | free-form | chunk → embed → Vector DB |
| Images | free-form | OCR → treat as text → route |

## Resume handling
Resume is special — it's both free-form and structured.
Two-pass processing:
1. LLM parses resume into structured facts (skills, experience, roles) → MongoDB
2. Full resume text embedded → Vector DB for semantic recall

## Chunking strategy
- Resume: chunk by section (experience, skills, education)
- Session notes: chunk by topic or doubt
- Long documents: 512-token chunks with 50-token overlap

## Embedding model
Embedding model: OpenAI text-embedding-3-small.
Decided in 14_tech_stack.md — best quality/cost ratio, 1536 dimensions.

## LangChain components used

```python
# Document loaders
from langchain_community.document_loaders import PyMuPDFLoader, CSVLoader

loader = PyMuPDFLoader("resume.pdf")       # resume
loader = CSVLoader("leetcode_export.csv")  # LeetCode history

# Text splitting
from langchain.text_splitter import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=50)
chunks = splitter.split_documents(docs)

# Embeddings
from langchain_openai import OpenAIEmbeddings

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

# Vector store — store chunks into MongoDB Atlas
from langchain_mongodb import MongoDBAtlasVectorSearch

vector_store = MongoDBAtlasVectorSearch.from_documents(
    chunks, embeddings, collection=collection, index_name="session_embedding_index"
)
```
