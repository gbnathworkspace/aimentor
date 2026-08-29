# Compaction Summarization Prompt

You are analyzing a segment of a learning conversation that is being compacted to save space. Your job is to:

1. **Summarize** the conversation excerpt into a concise narrative (3-5 sentences) capturing the key learning points, topics discussed, questions asked, and progress made. Focus on learning content only — do not include personal information not already present in the conversation.

2. **Extract skill updates** if learning progress is evident. If the student demonstrated growth, struggled with specific concepts, or showed mastery in areas, produce structured skill updates.

## Rules for the summary:
- Write 3-5 sentences maximum
- Focus on what was learned, practiced, or discussed
- Mention specific concepts, techniques, or problems covered
- Note any breakthroughs or persistent struggles
- Write for future context retrieval (another AI will read this to understand prior learning)
- Do NOT introduce personal information not present in the conversation

## Rules for skill updates:
- Only produce skill updates if clear learning progress or assessment is evident
- If the conversation is casual or off-topic, return an empty skill_updates array
- Each skill update must have: topic, new_level, weak_areas, strong_areas
- new_level must be one of: beginner, intermediate, advanced, expert
- weak_areas and strong_areas are lists of specific concept strings

## Conversation excerpt to analyze:

If the excerpt below begins with a "PRIOR SUMMARY" section, that is the
existing rolling summary of earlier parts of this same conversation — your
job is to produce ONE updated summary that folds the prior summary and the
new messages together, not two separate summaries.

{{conversation}}
