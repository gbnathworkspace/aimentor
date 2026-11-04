"""MCQ quiz template (.kiro/specs/mcq-quiz): parse/validate + history rendering."""

import json

from app.services.mentor_agent import _render_quiz_for_model
from app.services.response_parsing import extract_quiz

QUIZ = {
    "q": 1, "of": 5, "subtopic": "DI", "difficulty": "easy", "kind": "concept",
    "stem": "Which lifetime shares one instance app-wide?",
    "options": [{"id": i, "text": t} for i, t in zip("ABCD", ["Transient", "Scoped", "Singleton", "Pooled"])],
    "answer": "C", "why": "Singleton is created once.",
    "misconceptions": {"A": "thinks new means shared", "B": "confuses request scope with app", "D": "invents a lifetime"},
}


def _reply(quiz) -> str:
    return f"Here's one.\n\n```json quiz\n{json.dumps(quiz)}\n```"


def test_valid_block_is_extracted_and_stripped():
    text, quiz = extract_quiz(_reply(QUIZ))
    assert text == "Here's one."
    assert quiz["answer"] == "C" and quiz["subtopic"] == "DI"


def test_off_template_blocks_are_dropped():
    three_opts = {**QUIZ, "options": QUIZ["options"][:3]}
    bad_answer = {**QUIZ, "answer": "E"}
    past_end = {**QUIZ, "q": 6}
    missing_mistake = {**QUIZ, "misconceptions": {"A": "x", "B": "y"}}
    for bad in (three_opts, bad_answer, past_end, missing_mistake):
        text, quiz = extract_quiz(_reply(bad))
        assert quiz is None and "```" not in text
    assert extract_quiz("```json quiz\n{not json\n```")[1] is None


def test_history_rendering_shows_pick_result():
    assert "not answered yet" in _render_quiz_for_model(QUIZ)
    assert "picked B (wrong) — likely misconception: confuses request scope" in _render_quiz_for_model({**QUIZ, "picked": "B"})
    assert "picked C (correct)" in _render_quiz_for_model({**QUIZ, "picked": "C"})


def test_summary_scores_latest_run_only():
    from app.services.mentor_agent import _quiz_run, _summarize_quiz_run
    old = {"quiz": {**QUIZ, "q": 1, "picked": "A"}}
    q1 = {"quiz": {**QUIZ, "q": 1, "picked": "C"}}
    chat = {"role": "assistant", "content": "discussion"}
    q2 = {"quiz": {**QUIZ, "q": 2, "subtopic": "async", "picked": "B"}}
    s = _summarize_quiz_run(_quiz_run([old, q1, chat, q2]))
    assert (s["correct"], s["total"], s["weakest"]) == (1, 2, "async")
    assert sorted(s["subtopics"], key=lambda u: u["subtopic"]) == [
        {"subtopic": "DI", "mastery": 100}, {"subtopic": "async", "mastery": 0},
    ]
    [miss] = s["missed"]
    assert (miss["q"], miss["pickedText"], miss["answerText"]) == (2, "Scoped", "Singleton")
    assert miss["misconception"] == "confuses request scope with app"
