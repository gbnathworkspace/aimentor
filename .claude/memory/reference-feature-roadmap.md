---
name: reference-feature-roadmap
description: MentorMan's planned-feature roadmap lives in MongoDB Atlas, db mentorman_product, collection feature_analysis
type: reference
---

The product roadmap is stored in MongoDB Atlas, not in the repo:
cluster `mentorman` (Atlas "Project 0"), database `mentorman_product`,
collection `feature_analysis`.

Each doc has `feature_id` (F01…), `name`, `category`, `component`, `status`
(idea / designed / in_progress), `priority` (P0–P2), `depends_on`, `origin`
(user_design / suggested), `differentiation_vs_chatgpt`, `why_hard_to_copy`.

**How to apply:** when asked about planned features, roadmap or "what's next",
query this collection rather than guessing from code.
