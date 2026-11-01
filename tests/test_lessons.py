import shutil
from unittest import mock

import pytest

tk = pytest.importorskip("tkinter")

import learn_kids  # noqa: E402
from learn_kids import LESSONS_DATA, InteractiveLearningApp  # noqa: E402

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


def test_last_correct_answer_congratulates(app):
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
    app.answer_entry.insert(0, str(LESSONS_DATA[topic][i]["answer"]))

    with mock.patch.object(learn_kids.messagebox, "showinfo") as showinfo:
        app.check_answer()

    showinfo.assert_called_once()
