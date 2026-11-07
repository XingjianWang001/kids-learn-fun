import shutil
import time

import pytest

pytest.importorskip("tkinter")
if not shutil.which("g++"):
    pytest.skip("needs g++", allow_module_level=True)

from learn_kids import COMPILER_ERROR_HINTS, InteractiveLearningApp  # noqa: E402

CONTEXT = "#include <iostream>\nint main() {\n{user_code}\nreturn 0;\n}\n"


def run(code):
    # execute_cpp_code only uses self to explain compile errors, so an instance without a window will do.
    return InteractiveLearningApp.__new__(InteractiveLearningApp).execute_cpp_code(code, CONTEXT)


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
    message = InteractiveLearningApp._parse_compiler_errors(None, "/tmp/x/temp_code.cpp:1:1: error: 'x' was not declared in this scope", CONTEXT)
    assert "行附近" not in message


def test_hint_and_line_come_from_the_same_error():
    # Line 2 misspells myScore, line 3 lacks ';': the first error's hint, with its own line.
    error = run('int myScore = 95;\nstd::cout << myscore << std::endl;\nstd::cout << "done" << std::endl')["error"]
    assert error.startswith("提示：在第 2 行附近，" + COMPILER_ERROR_HINTS["was not declared in this scope"])


def test_errors_inside_system_headers_do_not_give_the_line():
    # #include inside main makes <cmath> report errors at its own lines (/usr/include/math.h:34).
    error = run("#include <cmath>\nstd::cout << sqrt(4);")["error"]
    assert error.startswith("提示：在第 2 行附近，")


IME_PUNCTUATION = r"extended character|\\U0000(ff|20[12]|30[0-3])"

# A real mistake for every COMPILER_ERROR_HINTS row: rows written from memory never matched g++ (#7, #12).
MISTAKES = [
    ('std::cout << "小华" << std::endl；', IME_PUNCTUATION),  # Chinese IME punctuation
    ('std::cout << “小华” << std::endl;', IME_PUNCTUATION),
    ("int x = 1;\nif （x > 0） {}", IME_PUNCTUATION),
    ('std::cout << "a"；\nstd::cout << "b";', IME_PUNCTUATION),  # not the ';' hint
    ('#include <iostream>\nint main() {\n    std::cout << "hi";\n    return 0;\n}', r"a function-definition is not allowed here"),
    ("int x = 5\nstd::cout << x;", r"expected (',' or )?';' before"),
    ("std::cout << y;", r"was not declared in this scope"),
    ("int x = 3 + ;", r"expected primary-expression before '.*' token"),
    ('std::cout << "a" << \\n;', r"stray '\\[0-9]*' in program"),
    ("int foo();\nfoo();", r"undefined reference to"),
    ("if (1) {", r"expected '}' at end of input"),
    ("}", r"expected declaration before '}' token"),
    ("int x = 1;\ndouble x = 2;", r"conflicting declaration '.*'"),
    ("int x = 5;\nint x = 6;", r"redeclaration of '.*'"),
    ("std::cout << std::cout;", r"no match for 'operator<<'"),
    ("int x; std::cin >> 5;", r"no match for 'operator>>'"),
    ("int 5x = 3;", r"expected unqualified-id before numeric constant"),
    ("do { } (1);", r"expected 'while' before '\('"),
    ("int x = (3 + 4;", r"expected '\)' before ';' token"),
    ("else { }", r"'else' without a previous 'if'"),
    ("return;", r"return-statement with no value, in function returning 'int'"),
    ("int x = abs();", r"too few arguments to function"),
    ("int x = abs(1, 2);", r"too many arguments to function"),
]


@pytest.mark.parametrize("code, pattern", MISTAKES)
def test_common_mistakes_get_a_friendly_hint(code, pattern):
    error = run(code)["error"]
    assert error.startswith("提示：") and COMPILER_ERROR_HINTS[pattern] in error


def test_every_compiler_hint_has_a_real_mistake():
    assert set(COMPILER_ERROR_HINTS) == {pattern for _, pattern in MISTAKES}
