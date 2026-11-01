import shutil
from unittest import mock

import pytest

tk = pytest.importorskip("tkinter")

import learn_kids  # noqa: E402
from learn_kids import LESSONS_DATA, InteractiveLearningApp, accepted_answers  # noqa: E402

CHALLENGES = [
    (topic, i, lesson)
    for topic, lessons in LESSONS_DATA.items()
    for i, lesson in enumerate(lessons)
    if lesson["type"] == "code_challenge" and "standard_answer_code" in lesson
]


@pytest.fixture(scope="module")
def app():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("needs a display (on Linux, run under xvfb-run)")
    root.withdraw()
    yield InteractiveLearningApp(root)
    root.destroy()


@pytest.mark.skipif(not shutil.which("g++"), reason="needs g++")
@pytest.mark.parametrize("topic,i,lesson", CHALLENGES, ids=[f"{t}#{i}" for t, i, _ in CHALLENGES])
def test_standard_answer_passes(app, topic, i, lesson):
    result = app.execute_cpp_code(lesson["standard_answer_code"], lesson["cpp_context"])
    assert result["success"], result["error"]
    assert result["output"].strip() == lesson["expected_output"].strip()


def test_finishing_a_topic_shows_completion_and_stops_navigation(app):
    topic = next(iter(LESSONS_DATA))
    app.select_topic(topic)
    app.current_lesson_index = len(LESSONS_DATA[topic]) - 1
    app.load_lesson()
    last_text = app.explanation_text.get("1.0", "end-1c")

    app.next_lesson()

    assert app.explanation_text.get("1.0", "end-1c") != last_text
    assert str(app.next_button.cget("state")) == tk.DISABLED
    assert str(app.skip_button.cget("state")) == tk.DISABLED
    assert str(app.prev_button.cget("state")) == tk.NORMAL


def test_last_correct_answer_congratulates(app, monkeypatch):
    monkeypatch.setattr(app, "lesson_points_awarded", {})
    monkeypatch.setattr(app, "scores", dict(app.scores))
    topic, i = next(
        (t, i)
        for t, lessons in LESSONS_DATA.items()
        for i, lesson in enumerate(lessons)
        if lesson["type"] == "fill_blank" and lesson.get("points", 0) > 0
    )
    for t, lessons in LESSONS_DATA.items():
        for j, lesson in enumerate(lessons):
            if lesson.get("points", 0) > 0 and (t, j) != (topic, i):
                app.lesson_points_awarded[(t, j)] = True
    app.current_topic_key, app.current_lesson_index = topic, i
    app.load_lesson()
    app.answer_entry.insert(0, accepted_answers(LESSONS_DATA[topic][i])[0])

    with mock.patch.object(learn_kids.messagebox, "showinfo") as showinfo:
        app.check_answer()

    showinfo.assert_called_once()


def submit_fill_blank(app, monkeypatch, answer, typed):
    """Type into the fill_blank lesson that accepts `answer`; True if it was marked correct."""
    for attr in ("lesson_points_awarded", "failed_attempts"):
        monkeypatch.setattr(app, attr, {})
    monkeypatch.setattr(app, "scores", dict(app.scores))
    monkeypatch.setattr(app, "total_score", app.total_score)
    lesson_id = next(
        (t, i)
        for t, lessons in LESSONS_DATA.items()
        for i, lesson in enumerate(lessons)
        if lesson["type"] == "fill_blank" and answer in accepted_answers(lesson)
    )
    app.current_topic_key, app.current_lesson_index = lesson_id
    app.load_lesson()
    app.answer_entry.insert(0, typed)
    app.check_answer()
    return app.lesson_points_awarded.get(lesson_id, False)


@pytest.mark.parametrize("answer,typed", [
    ("i <= n", "i<=n"),
    ("i < n", " I  <  N "),
    ("i--", "i--"),
    ("i--", "--i"),
    ("i--", "i -= 1"),
    ("i--", "i=i-1"),
])
def test_fill_blank_ignores_spaces_and_accepts_equivalents(app, monkeypatch, answer, typed):
    assert submit_fill_blank(app, monkeypatch, answer, typed)


def test_fill_blank_rejects_wrong_answer(app, monkeypatch):
    assert not submit_fill_blank(app, monkeypatch, "i--", "i++")


def test_fill_blank_shows_first_accepted_answer(app, monkeypatch):
    submit_fill_blank(app, monkeypatch, "i--", "x")
    for _ in range(app.MAX_FAILED_ATTEMPTS - 1):
        app.check_answer()
    assert "“i--”" in app.feedback_label.cget("text")

    app.lesson_points_awarded[(app.current_topic_key, app.current_lesson_index)] = True
    app.load_lesson()
    assert app.answer_entry.get() == "i--"


def test_fill_blank_questions_have_at_most_two_parts():
    # load_lesson shows question_parts[0] + blank + question_parts[1]; a 3rd part would be dropped.
    assert [
        (t, i)
        for t, lessons in LESSONS_DATA.items()
        for i, lesson in enumerate(lessons)
        if lesson["type"] == "fill_blank" and len(lesson["question_parts"]) > 2
    ] == []


@pytest.mark.parametrize("last", [False, True], ids=["middle", "last"])
def test_skip_says_the_lesson_was_skipped(app, last):
    topic = next(iter(LESSONS_DATA))
    app.select_topic(topic)
    if last:
        app.current_lesson_index = len(LESSONS_DATA[topic]) - 1
        app.load_lesson()

    app.skip_lesson()

    assert app.feedback_label.cget("text") == "已跳过当前关卡。"
