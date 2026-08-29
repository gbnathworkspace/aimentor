# Session Summary Merge Prompt

You are combining two existing narrative summaries of a learning conversation
into one. Both are already summarized — do not go back to raw messages, just
condense these two into a single coherent narrative that preserves the
important learning content from both.

## Rules:
- Target around {{target_words}} words, but never fewer than {{floor_words}} words
- Preserve concepts, techniques, problems, and any noted breakthroughs or struggles from both summaries
- Write in chronological order (SUMMARY A happened before SUMMARY B)
- Do NOT introduce information not present in either summary

## SUMMARY A (earlier):
{{summary_a}}

## SUMMARY B (later):
{{summary_b}}
