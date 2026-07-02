# Feature Clarification Process

When a new feature is being added or requested, ALWAYS ask clarifying questions before proceeding with implementation or spec creation. Do not jump straight into building.

## Questions to ask (select the most relevant ones based on context):

1. **Purpose & Goal** — What problem does this feature solve? Who is it for?
2. **Scope** — What's the minimum viable version? What's explicitly out of scope?
3. **User Flow** — How does the user interact with this? What triggers it and what's the expected outcome?
4. **Edge Cases** — What happens with invalid input, empty states, or errors?
5. **Dependencies** — Does this depend on other features or services being in place?
6. **Data** — What data does this need? Where does it come from? Does it need persistence?
7. **Existing Patterns** — Should this follow an existing pattern in the codebase or introduce something new?
8. **Priority & Constraints** — Any deadlines, performance requirements, or technical constraints?

## Rules

- Ask 3-5 of the most relevant questions (not all 8 every time)
- Tailor questions to the complexity of the feature — simple features need fewer questions
- Once answers are received, summarize understanding before proceeding
- If the user says "just do it" or similar, proceed with reasonable defaults but state your assumptions
