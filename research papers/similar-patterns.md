# Similar Patterns & Research

Papers and articles found that closely match MentorMan's architecture.

---

## 1. LOOM — Dynamic Learner Memory Graph
**Link:** https://arxiv.org/html/2511.21037

Closest overall match. Uses a dynamic learner memory graph (similar to L2 Skill Graph),
daily conversation summarization (similar to session-end write), goal and knowledge
connection tracking over time, and topic planning driven by the graph.

---

## 2. GenMentor — Goal-Oriented LLM Tutoring
**Link:** https://tianfuwang.tech/gen-mentor/

Maps learner goals → required skills using a fine-tuned LLM (similar to Goal KB lookup).
Identifies skill gaps and schedules a learning path. Evolving learner profile that updates
over sessions (similar to L1 + L2).

---

## 3. SEEM — Structured Episodic Event Memory
**Link:** https://arxiv.org/pdf/2601.06411

Combines a graph memory layer (relational facts) with an episodic memory layer (narrative
progression) — exactly the L2 + L3 split. Grounded in cognitive frame theory.

---

## 4. MemMachine — Ground-Truth-Preserving Memory System
**Link:** https://arxiv.org/pdf/2604.04853

Short-term + long-term episodic + profile memory in one system. The three-layer
decomposition matches MentorMan's L1/L2/L3 architecture closely.

---

## 5. Personalized Learning Tutor: LLM + Student Knowledge Graph
**Link:** https://medium.com/@tunamuna29/personalized-learning-tutor-llm-student-knowledge-graph-9d994d942efe

Practical implementation: knowledge graph tracks per-topic progress, LLM generates
explanations and quizzes, personalized path instead of generic content.

---

## 6. Architecture and Orchestration of Memory Systems in AI Agents
**Link:** https://www.analyticsvidhya.com/blog/2026/04/memory-systems-in-ai-agents/

Covers the hot/warm/cold memory tiering pattern that underpins MentorMan's layered memory.

---

## 7. RAG Is Not Memory: Why LLM Agents Need Episodic Memory
**Link:** https://www.toolmintx.in/blog/rag-llm-memory-limits-episodic-agents

Explains why RAG alone is insufficient — the distinction between "knowing more" (RAG)
and "becoming better" (episodic memory). Validates the L3 design choice.

---

## What MentorMan Does Differently

Most of these systems track absolute proficiency ("user knows medium graphs").
MentorMan tracks goal-relative proficiency ("user needs medium graphs for 20 LPA,
currently at easy — 40% gap"). The benchmark shifts with the goal, and the system
reasons proactively about pace and deadlines — not just topic mastery.
