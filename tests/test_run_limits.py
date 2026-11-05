import shutil
import time

import pytest

pytest.importorskip("tkinter")
if not shutil.which("g++"):
    pytest.skip("needs g++", allow_module_level=True)

from learn_kids import InteractiveLearningApp  # noqa: E402

CONTEXT = "#include <iostream>\nint main() {\n{user_code}\nreturn 0;\n}\n"


def run(code):
    # execute_cpp_code only uses self to explain compile errors, so no window is needed.
    return InteractiveLearningApp.execute_cpp_code(None, code, CONTEXT)


def test_endless_printing_stops_early_without_buffering_everything():
    start = time.monotonic()
    result = run('while (true) std::cout << "I love C++!\\n";')
    assert time.monotonic() - start < 8
    assert not result["success"]
    assert "输出过长" in result["error"]


def test_endless_loop_without_output_times_out():
    result = run("while (true) {}")
    assert not result["success"]
    assert "执行超时" in result["error"]


def test_normal_program_output_is_returned():
    result = run('std::cout << "a\\nb" << std::endl;')
    assert result["success"]
    assert result["output"] == "a\nb\n"


def test_crash_is_reported_as_failure():
    result = run('std::cout << "hi" << std::endl; return 3;')
    assert not result["success"]
    assert "程序异常退出 (code 3)" in result["error"]


def test_compile_error_line_counts_only_user_code():
    app = InteractiveLearningApp.__new__(InteractiveLearningApp)  # no window needed
    result = app.execute_cpp_code("int y = 2;\nstd::cout << zz;", CONTEXT)
    assert "第 2 行" in result["error"]


def test_compile_error_in_template_has_no_line_hint():
    message = InteractiveLearningApp._parse_compiler_errors(None, "a.cpp:1:1: error: 'x' was not declared in this scope", CONTEXT)
    assert "行附近" not in message


@pytest.mark.parametrize("code, hint", [
    ("int x = 5\nstd::cout << x;", "分号"),
    ("int x = 5;\nint x = 6;", "声明过两次"),
    ("else { }", "else"),
])
def test_common_mistakes_get_a_friendly_hint(code, hint):
    app = InteractiveLearningApp.__new__(InteractiveLearningApp)  # no window needed
    error = app.execute_cpp_code(code, CONTEXT)["error"]
    assert error.startswith("提示：在第") and hint in error
