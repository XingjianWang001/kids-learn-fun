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
