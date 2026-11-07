import pytest

tk = pytest.importorskip("tkinter")

from tkinter import scrolledtext  # noqa: E402

from learn_kids import CodeEditor, ScrollableFrame  # noqa: E402


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


@pytest.mark.parametrize("event,options,direction", [
    ("<MouseWheel>", {"delta": -120}, 1),  # Windows / macOS
    ("<MouseWheel>", {"delta": 120}, -1),
    ("<MouseWheel>", {"delta": -1}, 1),  # macOS Tk 8.6 and touchpads send less than 120
    ("<Button-5>", {}, 1),  # Linux (X11)
    ("<Button-4>", {}, -1),
])
def test_mouse_wheel_scrolls_editor_and_line_numbers(root, event, options, direction):
    editor = CodeEditor(root)
    editor.pack()
    editor.code_area.insert("1.0", "\n".join(f"x{i};" for i in range(100)))
    root.update_idletasks()
    editor.code_area.yview_moveto(0.5)
    before = editor.code_area.yview()[0]
    editor.code_area.event_generate(event, **options)
    after = editor.code_area.yview()[0]
    line_numbers_top = editor.line_numbers.yview()[0]
    editor.destroy()
    assert (after - before) * direction > 0
    assert line_numbers_top == pytest.approx(after, abs=0.01)


@pytest.mark.parametrize("delta,direction", [(-120, 1), (120, -1), (-1, 1), (1, -1), (-30, 1)])
def test_mouse_wheel_scrolls_lesson_page(root, delta, direction):
    page = ScrollableFrame(root)
    page.pack()
    for i in range(200):
        tk.Label(page.scrollable_content_frame, text=f"row {i}").pack()
    root.update()
    canvas = page.winfo_children()[0]
    canvas.yview_moveto(0.5)
    before = canvas.yview()[0]
    canvas.event_generate("<MouseWheel>", delta=delta)
    after = canvas.yview()[0]
    page.destroy()
    assert (after - before) * direction > 0


@pytest.mark.parametrize("event,options,direction", [
    ("<MouseWheel>", {"delta": -120}, 1),
    ("<MouseWheel>", {"delta": 120}, -1),
    ("<Button-5>", {}, 1),  # X11
    ("<Button-4>", {}, -1),
])
@pytest.mark.parametrize("text_lines,lines_left,moves", [
    (100, 40, "text"),  # the text can still scroll that way: only the text moves
    (100, 1, "text"),  # one line short of its end, it still moves alone
    (100, 0, "page"),  # at its end in that direction, the page moves instead
    (2, 0, "page"),  # all of it fits
])
def test_mouse_wheel_over_text_scrolls_text_or_page_not_both(root, event, options, direction, text_lines, lines_left, moves):
    root.deiconify()  # a withdrawn window leaves the page canvas 1px tall, too small to scroll
    page = ScrollableFrame(root)
    page.pack()
    text = scrolledtext.ScrolledText(page.scrollable_content_frame, height=6)
    text.pack()
    text.insert("1.0", "\n".join(f"line {i}" for i in range(text_lines)))
    for i in range(200):
        tk.Label(page.scrollable_content_frame, text=f"row {i}").pack()
    root.update()
    canvas = page.winfo_children()[0]
    canvas.yview_moveto(0.5)
    text.yview_moveto(1.0 if direction > 0 else 0.0)
    text.yview_scroll(-direction * lines_left, "units")
    before = text.yview()[0], canvas.yview()[0]
    text.event_generate(event, **options)
    after = text.yview()[0], canvas.yview()[0]
    page.destroy()
    root.withdraw()
    assert [name for name, b, a in zip(("text", "page"), before, after) if b != a] == [moves]


@pytest.mark.parametrize("part", ["code_area", "line_numbers"])
@pytest.mark.parametrize("lines_left,moves", [(40, "editor"), (0, "page")])
def test_mouse_wheel_over_editor_scrolls_editor_or_page_not_both(root, part, lines_left, moves):
    root.deiconify()
    page = ScrollableFrame(root)
    page.pack()
    editor = CodeEditor(page.scrollable_content_frame, height=6)
    editor.pack()
    editor.code_area.insert("1.0", "\n".join(f"x{i};" for i in range(100)))
    editor._update_line_numbers()
    for i in range(200):
        tk.Label(page.scrollable_content_frame, text=f"row {i}").pack()
    root.update()
    canvas = page.winfo_children()[0]
    canvas.yview_moveto(0.5)
    editor.code_area.yview_moveto(1.0)
    editor.code_area.yview_scroll(-lines_left, "units")
    editor.line_numbers.yview_moveto(editor.code_area.yview()[0])
    before = editor.code_area.yview()[0], canvas.yview()[0]
    getattr(editor, part).event_generate("<Button-5>")
    after = editor.code_area.yview()[0], canvas.yview()[0]
    line_numbers_top = editor.line_numbers.yview()[0]
    page.destroy()
    root.withdraw()
    assert [name for name, b, a in zip(("editor", "page"), before, after) if b != a] == [moves]
    assert line_numbers_top == pytest.approx(after[0], abs=0.01)  # the numbers stay next to their lines
