import pytest

tk = pytest.importorskip("tkinter")

from learn_kids import CodeEditor  # noqa: E402


@pytest.fixture(scope="module")
def root():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("needs a display (on Linux, run under xvfb-run)")
    root.withdraw()
    yield root
    root.destroy()


def press_enter(root, text, cursor="end-1c"):
    editor = CodeEditor(root)
    editor.code_area.insert("1.0", text)
    editor.code_area.mark_set(tk.INSERT, cursor)
    editor._on_enter_key()
    new_line = editor.code_area.get("insert linestart", "insert lineend")
    editor.destroy()
    return new_line


def test_indents_after_opening_brace_on_first_line(root):
    assert press_enter(root, "int main() {") == "    "


def test_keeps_indent_of_current_line_not_line_above(root):
    assert press_enter(root, "x;\n    y;") == "    "
    assert press_enter(root, "    x;\ny;") == ""


def test_adds_indent_after_brace_on_indented_line(root):
    assert press_enter(root, "int main() {\n    if (a) {") == "        "


def test_enter_mid_line_moves_rest_of_line_down(root):
    assert press_enter(root, "    a; b;", cursor="1.7") == "    b;"
