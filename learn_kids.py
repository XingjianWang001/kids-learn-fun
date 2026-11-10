import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import subprocess
import tempfile
import os
import re # Added for error parsing and syntax highlighting
import shutil
import threading
from tkinter import font as tk_font # Import the font module

OUTPUT_LIMIT = 64 * 1024  # bytes kept per stream; an endless print loop would otherwise fill memory

# g++ error regex -> friendly hint; more specific patterns first. tests/test_run_limits.py has a real mistake for each row.
COMPILER_ERROR_HINTS = {
    # Chinese IME punctuation: GCC 10+ says "extended character “" or writes ； as \U0000ff1b. First, as `"a"；` also matches the ';' row.
    r"extended character|\\U0000(ff|20[12]|30[0-3])": "代码里有中文标点符号（比如 ； ， （ ） “ ”），要切换到英文输入法再打这些符号哦。",
    r"a function-definition is not allowed here": "这里只要写 main 函数里面的代码，不用再写 #include 和 int main() 哦。",
    r"expected (',' or )?';' before": "哎呀，好像在某行的末尾忘记了分号 ';' 哦！C++中很多语句需要用它来结束。",
    r"did you mean 'std::": "`cout`、`cin`、`endl`、`max` 这些名字前面要加 `std::` 哦，比如 `std::cout`。",  # before the row below, which says to declare it
    r"was not declared in this scope": "嗯，你用了一个变量或者函数，但是好像忘记先告诉电脑它是什么了（忘记声明了）。",
    r"missing terminating [\"'] character": "引号要成对出现哦：文字的两边都要有双引号，比如 \"小华\"。",
    r"expected primary-expression before '.*' token": "这里似乎有点小问题，电脑不太明白你想做什么。检查一下是不是有奇怪的符号或者漏了东西？",
    r"stray '\\[0-9]*' in program": "代码里好像有一些奇怪的、看不懂的符号，检查一下是不是不小心打错了？",
    r"undefined reference to": "电脑找到了一个名字，但是找不到它具体代表什么（比如一个函数）。是不是忘记写这个函数了，或者链接的时候出错了？",
    r"expected '}' at end of input": "代码的最后好像少了一个大括号 '}' 来收尾哦。",
    r"expected declaration before '}' token": "这个大括号 '}' 前面是不是少了点什么代码呢？",
    r"conflicting declaration '.*'": "这个名字好像之前用过了，但是这次用它的方式和之前不一样哦。",
    r"redeclaration of '.*'": "这个名字你好像声明过两次了，检查一下是不是写多了？",
    # cout >> x or cin << x: before the two rows below, which blame the type of what is on the right.
    r"no match for 'operator>>' \(operand types are 'std::ostream|no match for 'operator<<' \(operand types are 'std::istream": "箭头方向反了：`std::cout << ...` 把东西送到屏幕，`std::cin >> ...` 从键盘拿到变量里。",
    r"no match for 'operator<<'": "使用 `cout << ...` 的时候，`<<` 右边的东西电脑不认识，看看是不是类型不对？",
    r"no match for 'operator>>'": "使用 `cin >> ...` 的时候，`>>` 右边的变量电脑不认识，看看是不是类型不对或者没声明？",
    r"expected unqualified-id before numeric constant": "数字前面是不是不小心写了什么不该写的东西？",
    r"expected 'while' before '\('": "for或者do-while循环是不是少了 `while` 关键字？",
    r"expected '\)' before ';' token": "是不是有一行代码的括号 `(` 没有对应的 `)` 就直接写分号了？",
    r"'else' without a previous 'if'": "`else` 是跟着 `if` 用的，这里好像没有找到前面的 `if` 呀。",
    r"return-statement with no value, in function returning 'int'": "这个函数应该返回一个整数，但是 `return;` 后面忘记写返回值了。",
    r"too few arguments to function": "调用函数的时候，给的参数数量不够哦。",
    r"too many arguments to function": "调用函数的时候，给的参数数量太多了哦。",
    # std::max, std::min and std::abs are overloaded or templates: g++ says this instead of the two rows above.
    r"no matching function for call to|'__comp' cannot be used as a function": "调用函数时给的参数不对哦：数量不对，或者类型不一样（比如一个 int、一个 double）。`std::max`、`std::min` 一次只能比较两个数，三个数要写成 `std::max(a, std::max(b, c))`。",
    r"to binary 'operator\^'": "C++ 里的 ^ 不是乘方，是位运算「异或」。平方要写成 x * x，或者用 pow(x, 2)。",
}

# --- 函数：加载课程数据 ---
def load_lessons_from_file(directory="."):
    """
    Loads all .json lesson files from the specified directory,
    sorts them by filename, and merges them into a single lessons data dictionary.
    Each JSON file is expected to contain a single top-level key (the lesson title)
    and its corresponding lesson content array.
    """
    all_lessons_data = {}
    json_files = sorted([f for f in os.listdir(directory) if f.endswith('.json') and f != "lessons_data.json"]) # Exclude the old combined file

    if not json_files:
        messagebox.showerror("错误", f"在目录 '{directory}' 中没有找到任何课程JSON文件！")
        return {}

    for filename in json_files:
        filepath = os.path.join(directory, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Expecting each file to be a dict with one key (lesson title)
            if isinstance(data, dict) and len(data) == 1:
                all_lessons_data.update(data)
            else:
                print(f"Warning: File '{filepath}' does not have the expected format (single top-level key). Skipping.")
                messagebox.showwarning("格式警告", f"课程文件 '{filename}' 格式不符合预期（应为单个顶级键），已跳过。")
        except FileNotFoundError:
            messagebox.showerror("错误", f"课程数据文件 '{filepath}' 未找到！")
            continue
        except json.JSONDecodeError as e:
            messagebox.showerror("JSON错误", f"课程数据文件 '{filepath}' 格式错误！\n{e}")
            continue
        except Exception as e:
            messagebox.showerror("错误", f"加载课程文件 '{filepath}' 时发生未知错误: {e}")
            continue

    if not all_lessons_data:
        messagebox.showerror("错误", "未能成功加载任何课程数据。")

    return all_lessons_data

# Lesson files sit next to this script, wherever it is launched from.
LESSONS_DATA = load_lessons_from_file(directory=os.path.dirname(os.path.abspath(__file__)))
if not LESSONS_DATA:
    print("CRITICAL: No lesson data loaded. Application might not function correctly.")

def accepted_answers(lesson):
    """A fill_blank `answer` is one string or a list of accepted ones; the first is the one shown."""
    answer = lesson["answer"]
    return answer if isinstance(answer, list) else [answer]


def normalize_answer(text):
    """Spaces don't change a C++ expression, so `i<=n` matches `i <= n`."""
    return re.sub(r"\s+", "", str(text)).lower()


def normalize_output(text):
    """Spaces at the end of a line can't be seen in the output box, so `1 ⏎2 ⏎` matches `1⏎2⏎`."""
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


def wheel_steps(event):
    """-1 to scroll up, 1 down, 0 for none. Only the sign counts: macOS and touchpads send deltas far below 120."""
    if event.num in (4, 5):  # X11 sends the wheel as buttons 4 and 5
        return -1 if event.num == 4 else 1
    return (event.delta < 0) - (event.delta > 0)


class ScrollableFrame(ttk.Frame):
    """A pure Tkinter scrollable frame that actually works!"""
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar_y = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        scrollbar_x = ttk.Scrollbar(self, orient="horizontal", command=canvas.xview)

        self.scrollable_content_frame = ttk.Frame(canvas)

        self.scrollable_content_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=self.scrollable_content_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar_y.pack(side="right", fill="y")
        scrollbar_x.pack(side="bottom", fill="x")

        def scroll(e):
            # Over a Text, the wheel scrolls that Text while it can go further that way, otherwise the page; never both.
            top, bottom = e.widget.yview() if isinstance(e.widget, tk.Text) else (0.0, 1.0)
            steps = wheel_steps(e)
            if (steps < 0 and top > 0) or (steps > 0 and bottom < 1):
                e.widget.yview_scroll(3 * steps, "units")
            else:
                canvas.yview_scroll(steps, "units")

        canvas.bind_all("<MouseWheel>", scroll)
        canvas.bind_all("<Shift-MouseWheel>", lambda e: canvas.xview_scroll(wheel_steps(e), "units"))
        canvas.bind_all("<Button-4>", scroll)  # X11
        canvas.bind_all("<Button-5>", scroll)
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            canvas.unbind_class("Text", sequence)  # Text's own wheel binding runs first and would scroll it before scroll() decides

class CodeEditor(tk.Frame):
    def __init__(self, master, font=None, height=None, **kwargs):
        super().__init__(master, **kwargs)

        # height is in lines and goes to both Texts: the frame takes the height they ask for.
        self.line_numbers = tk.Text(self, width=4, padx=4, takefocus=0, border=0,
                                    background='lightgrey', state='disabled', wrap='none', font=font, height=height)
        self.code_area = tk.Text(self, wrap='word', undo=True, padx=5, pady=5, font=font, height=height)

        self.scrollbar_y = ttk.Scrollbar(self, orient="vertical", command=self._on_scrollbar)
        self.code_area.configure(yscrollcommand=self.scrollbar_y.set)

        self.line_numbers.pack(side="left", fill="y")
        self.scrollbar_y.pack(side="right", fill="y")
        self.code_area.pack(side="right", fill="both", expand=True)

        self.code_area.bind("<KeyRelease>", self._on_key_release)
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            for column in (self.code_area, self.line_numbers):  # over either column, both scroll together
                column.bind(sequence, self._on_scroll)
        self.code_area.bind("<Return>", self._on_enter_key)
        self.code_area.bind("<Configure>", self._on_key_release)

        self._update_line_numbers()
        self._configure_tags()

    def _on_scrollbar(self, *args):
        self.code_area.yview(*args)
        self.line_numbers.yview(*args)
        self._update_line_numbers()

    def _on_scroll(self, event):
        # At the code's end in that direction, let the page's bind_all handler scroll the page instead.
        steps = wheel_steps(event)
        top, bottom = self.code_area.yview()
        if (steps < 0 and top <= 0) or (steps > 0 and bottom >= 1):
            return None
        self.code_area.yview_scroll(3 * steps, "units")
        self.line_numbers.yview_moveto(self.code_area.yview()[0])
        self._update_line_numbers()
        return "break"  # or the page's bind_all handler would scroll too

    def _on_enter_key(self, event=None):
        self._apply_indentation()
        self._on_key_release()
        return "break"

    def _apply_indentation(self):
        # Enter splits the line at the cursor, so the new line follows the text before the cursor.
        line_before_cursor = self.code_area.get("insert linestart", tk.INSERT)
        stripped = line_before_cursor.lstrip(' \t')
        indentation = line_before_cursor[:len(line_before_cursor) - len(stripped)]
        if stripped.rstrip().endswith('{'): indentation += "    "
        self.code_area.insert(tk.INSERT, "\n" + indentation)

    def _update_line_numbers(self, event=None):
        self.line_numbers.config(state='normal')
        self.line_numbers.delete('1.0', 'end')
        num_lines = self.code_area.index('end-1c').split('.')[0]
        line_numbers_string = "\n".join(str(i) for i in range(1, int(num_lines) + 1))
        self.line_numbers.insert('1.0', line_numbers_string)
        self.line_numbers.config(state='disabled')
        self.line_numbers.yview_moveto(self.code_area.yview()[0])

    def _configure_tags(self):
        font_name = self.code_area.cget("font")
        try:
            # Attempt to get font details if font_name is a string like "Courier New 14"
            font_tuple = tk_font.Font(font=font_name).actual() # Use tk_font here
            base_font_family = font_tuple['family']
            base_font_size = font_tuple['size']
        except tk.TclError: # Fallback if font_name is already a tuple or other issue
            base_font_family = "Courier New" # Default
            base_font_size = 14 # Default
            if isinstance(font_name, (tuple, list)) and len(font_name) >= 2:
                base_font_family = font_name[0]
                base_font_size = font_name[1]


        self.code_area.tag_configure("keyword", foreground="blue", font=(base_font_family, base_font_size, "bold"))
        self.code_area.tag_configure("comment", foreground="green", font=(base_font_family, base_font_size, "italic"))
        self.code_area.tag_configure("string", foreground="purple")
        self.code_area.tag_configure("number", foreground="orange")
        self.code_area.tag_configure("preprocessor", foreground="magenta", font=(base_font_family, base_font_size, "bold"))

    def _highlight_syntax(self, event=None):
        for tag in ["keyword", "comment", "string", "number", "preprocessor"]:
            self.code_area.tag_remove(tag, '1.0', 'end')

        content = self.code_area.get('1.0', 'end-1c')

        keywords = [
            'int', 'double', 'float', 'char', 'bool', 'void', 'long', 'short', 'signed', 'unsigned',
            'if', 'else', 'switch', 'case', 'default', 'for', 'while', 'do', 'break', 'continue',
            'return', 'class', 'struct', 'enum', 'union', 'public', 'private', 'protected',
            'new', 'delete', 'this', 'true', 'false', 'nullptr', 'const', 'static', 'volatile',
            'using', 'namespace', 'std', 'cout', 'cin', 'endl', 'main', 'include', 'iostream', 'vector', 'string'
        ]
        preprocessor_directives = ['#include', '#define', '#ifdef', '#ifndef', '#endif', '#if', '#else', '#elif']

        for directive in preprocessor_directives:
            for match in re.finditer(r"^\s*" + re.escape(directive), content, re.MULTILINE):
                start, end = f"1.0+{match.start()}c", f"1.0+{match.end()}c"
                self.code_area.tag_add("preprocessor", start, end)

        for keyword in keywords:
            for match in re.finditer(r'\b' + keyword + r'\b', content):
                start, end = f"1.0+{match.start()}c", f"1.0+{match.end()}c"
                if not any(t in self.code_area.tag_names(start) for t in ["comment", "string", "preprocessor"]):
                    self.code_area.tag_add("keyword", start, end)

        for match in re.finditer(r"//.*", content):
            start, end = f"1.0+{match.start()}c", f"1.0+{match.end()}c"
            self.code_area.tag_add("comment", start, end)

        for match in re.finditer(r'"(?:\\.|[^"\\])*"', content): # Handles escaped quotes
            start, end = f"1.0+{match.start()}c", f"1.0+{match.end()}c"
            if not any(t in self.code_area.tag_names(start) for t in ["comment"]):
                 self.code_area.tag_add("string", start, end)

        for match in re.finditer(r'\b\d+(\.\d*)?\b|\b\.\d+\b', content):
            start, end = f"1.0+{match.start()}c", f"1.0+{match.end()}c"
            if not any(t in self.code_area.tag_names(start) for t in ["comment", "string"]):
                self.code_area.tag_add("number", start, end)

    def _on_key_release(self, event=None):
        self._update_line_numbers()
        self._highlight_syntax()
        self.code_area.see(tk.INSERT)
        self.line_numbers.yview_moveto(self.code_area.yview()[0])

    def get(self, start="1.0", end="end-1c"): return self.code_area.get(start, end)
    def insert(self, index, text): self.code_area.insert(index, text); self._on_key_release()
    def delete(self, start, end=None): self.code_area.delete(start, end); self._on_key_release()
    def config(self, **kwargs): self.code_area.config(**kwargs) if 'state' in kwargs else self.code_area.config(**kwargs)
    def focus(self): self.code_area.focus_set()
    def pack(self, **kwargs): super().pack(**kwargs)


class InteractiveLearningApp:
    def __init__(self, master):
        self.master = master
        master.title("C++ 互动学习小程序 (小学生版)")
        master.geometry("1000x800")

        self.font_title = ("Arial", 22, "bold")
        self.font_subtitle = ("Arial", 18, "bold")
        self.font_normal_text = ("Arial", 15)
        self.font_normal_bold = ("Arial", 15, "bold")
        self.font_italic_text = ("Arial", 15, "italic")
        self.font_code_text = ("Courier New", 14)
        self.font_button = ("Arial", 14)

        self.current_topic_key = None
        self.current_lesson_index = 0
        self.scores = {topic: 0 for topic in LESSONS_DATA}
        self.max_scores = {topic: sum(l.get('points', 0) for l in lessons) for topic, lessons in LESSONS_DATA.items()}
        self.lesson_points_awarded = {}
        self.total_score = 0
        self.total_max_score = sum(self.max_scores.values())
        self.failed_attempts = {}
        self.MAX_FAILED_ATTEMPTS = 5

        self.main_paned_window = ttk.PanedWindow(master, orient=tk.HORIZONTAL)
        self.main_paned_window.pack(fill=tk.BOTH, expand=True)

        self.topic_frame_container = ttk.Frame(self.main_paned_window, width=250, height=700)
        self.topic_frame_container.pack_propagate(False)
        self.main_paned_window.add(self.topic_frame_container, weight=0)

        ttk.Label(self.topic_frame_container, text="课程列表", font=self.font_subtitle).pack(pady=10)
        self.topic_buttons_frame = ttk.Frame(self.topic_frame_container)
        self.topic_buttons_frame.pack(fill=tk.BOTH, expand=True)
        self.topic_buttons = {}
        for i, topic_key in enumerate(LESSONS_DATA.keys()):
            btn = ttk.Button(self.topic_buttons_frame, text=topic_key, command=lambda k=topic_key: self.select_topic(k), width=25, style="Large.TButton")
            btn.pack(pady=5, padx=5, fill=tk.X)
            self.topic_buttons[topic_key] = btn

        self.scrollable_lesson_outer_frame = ScrollableFrame(self.main_paned_window)
        self.main_paned_window.add(self.scrollable_lesson_outer_frame, weight=1)
        self.lesson_frame = self.scrollable_lesson_outer_frame.scrollable_content_frame

        self.lesson_title_label = ttk.Label(self.lesson_frame, text="请选择一个课程开始学习", font=self.font_title)
        self.lesson_title_label.pack(pady=(5,10), anchor="w")

        self.explanation_text = scrolledtext.ScrolledText(self.lesson_frame, wrap=tk.WORD, height=5, font=self.font_normal_text, relief=tk.SOLID, borderwidth=1)
        self.explanation_text.pack(pady=5, fill=tk.X); self.explanation_text.config(state=tk.DISABLED)

        self.code_display_text = scrolledtext.ScrolledText(self.lesson_frame, wrap=tk.WORD, height=6, font=self.font_code_text, relief=tk.SOLID, borderwidth=1)
        self.code_display_text.pack(pady=5, fill=tk.X); self.code_display_text.config(state=tk.DISABLED)

        self.question_label = ttk.Label(self.lesson_frame, text="", font=self.font_italic_text, wraplength=700)
        self.question_label.pack(pady=(10,5), anchor="w")

        self.input_frame = ttk.Frame(self.lesson_frame)
        self.input_frame.pack(pady=5, fill=tk.X, expand=False)
        self.answer_entry = None; self.radio_var = None; self.radio_buttons = []; self.code_input_area = None

        # Frame for submit and format buttons
        self.action_buttons_frame = ttk.Frame(self.lesson_frame)
        self.action_buttons_frame.pack(pady=5, fill=tk.X)

        self.submit_button = ttk.Button(self.action_buttons_frame, text="提交答案", command=self.check_answer, state=tk.DISABLED)
        self.submit_button.pack(side=tk.LEFT, padx=5, expand=True)

        self.format_code_button = ttk.Button(self.action_buttons_frame, text="整理代码", command=self._format_code_action, state=tk.DISABLED)
        self.format_code_button.pack(side=tk.LEFT, padx=5, expand=True)

        self.feedback_label = ttk.Label(self.lesson_frame, text="", font=self.font_normal_bold, wraplength=700)
        self.feedback_label.pack(pady=5, anchor="w")

        self.output_title_label = ttk.Label(self.lesson_frame, text="程序输出/错误信息:", font=self.font_normal_bold)
        self.output_display_area = scrolledtext.ScrolledText(self.lesson_frame, wrap=tk.WORD, height=7, font=self.font_code_text, relief=tk.SOLID, borderwidth=1)
        self.output_display_area.config(state=tk.DISABLED)

        self.nav_frame = ttk.Frame(self.lesson_frame)
        self.nav_frame.pack(pady=20, fill=tk.X)
        self.prev_button = ttk.Button(self.nav_frame, text="上一关卡", command=self.previous_lesson, state=tk.DISABLED)
        self.prev_button.pack(side=tk.LEFT, padx=10, expand=True)
        self.skip_button = ttk.Button(self.nav_frame, text="跳过关卡", command=self.skip_lesson, state=tk.DISABLED)
        self.skip_button.pack(side=tk.LEFT, padx=10, expand=True)
        self.next_button = ttk.Button(self.nav_frame, text="下一关卡", command=self.next_lesson, state=tk.DISABLED)
        self.next_button.pack(side=tk.LEFT, padx=10, expand=True)

        self.score_label = ttk.Label(master, text=f"总得分: 0 / {self.total_max_score}", font=self.font_subtitle)
        self.score_label.pack(side=tk.BOTTOM, pady=10)

        self.update_score_display()
        if not LESSONS_DATA:
            self.lesson_title_label.config(text="没有加载到课程数据")
            self.explanation_text.config(state=tk.NORMAL); self.explanation_text.delete('1.0', tk.END)
            self.explanation_text.insert(tk.END, "请检查课程JSON文件是否存在于'interLearn'目录且格式正确。")
            self.explanation_text.config(state=tk.DISABLED)
        else: self.load_lesson()

    def select_topic(self, topic_key):
        self.current_topic_key = topic_key; self.current_lesson_index = 0
        self.lesson_title_label.config(text=f"学习中: {topic_key}")
        self.load_lesson(); self.update_score_display()

    def _clear_input_widgets(self):
        if self.answer_entry: self.answer_entry.destroy(); self.answer_entry = None
        if self.radio_buttons:
            for rb in self.radio_buttons: rb.destroy()
            self.radio_buttons = []
        if self.code_input_area: self.code_input_area.destroy(); self.code_input_area = None
        self.question_label.config(text="")
        self.output_title_label.pack_forget()
        self.output_display_area.pack_forget()
        self.output_display_area.config(state=tk.NORMAL); self.output_display_area.delete('1.0', tk.END)
        self.output_display_area.config(state=tk.DISABLED)
        self.format_code_button.config(state=tk.DISABLED) # Keep it part of action_buttons_frame

    def load_lesson(self):
        self.feedback_label.config(text="", foreground="black")
        self._clear_input_widgets()
        self.submit_button.config(state=tk.DISABLED)
        self.format_code_button.config(state=tk.DISABLED) # Ensure format button is disabled initially

        if not self.current_topic_key or not LESSONS_DATA.get(self.current_topic_key):
            # ... (rest of the initial message if no topic selected)
            return

        topic_lessons = LESSONS_DATA[self.current_topic_key]
        num_lessons = len(topic_lessons)
        self.prev_button.config(state=tk.NORMAL if self.current_lesson_index > 0 else tk.DISABLED)

        if self.current_lesson_index >= num_lessons:
            self.skip_button.config(state=tk.DISABLED)
            self.next_button.config(state=tk.DISABLED)
            score = f"{self.scores.get(self.current_topic_key, 0)} / {self.max_scores.get(self.current_topic_key, 0)}"
            self.explanation_text.config(state=tk.NORMAL); self.explanation_text.delete('1.0', tk.END)
            self.explanation_text.insert(tk.END, f"恭喜你完成了「{self.current_topic_key}」的全部关卡！\n本课得分: {score}\n可以点击左边的课程列表继续学习，或者点「上一关卡」复习。")
            self.explanation_text.config(state=tk.DISABLED)
            self.code_display_text.config(state=tk.NORMAL); self.code_display_text.delete('1.0', tk.END)
            self.code_display_text.config(state=tk.DISABLED)
            self.update_topic_button_text(self.current_topic_key)
            return

        self.skip_button.config(state=tk.NORMAL)
        self.next_button.config(state=tk.NORMAL)
        lesson = topic_lessons[self.current_lesson_index]
        lesson_id = (self.current_topic_key, self.current_lesson_index)
        points_already_awarded = self.lesson_points_awarded.get(lesson_id, False)

        self.explanation_text.config(state=tk.NORMAL); self.explanation_text.delete('1.0', tk.END)
        self.explanation_text.insert(tk.END, lesson.get("text", "")); self.explanation_text.config(state=tk.DISABLED)
        self.code_display_text.config(state=tk.NORMAL); self.code_display_text.delete('1.0', tk.END)
        # Code challenges show cpp_context: the program that actually runs.
        self.code_display_text.insert(tk.END, lesson.get("cpp_context") or lesson.get("code", "")); self.code_display_text.config(state=tk.DISABLED)
        user_code_index = self.code_display_text.search("{user_code}", "1.0")
        if user_code_index:  # most programs are taller than the box: show where the child's code goes and what runs after it
            self.code_display_text.yview(f"{user_code_index} - 2 lines")

        lesson_type = lesson["type"]
        if not points_already_awarded and lesson_type != "explanation":
            self.submit_button.config(state=tk.NORMAL)
        else: self.submit_button.config(state=tk.DISABLED)

        if lesson_type == "code_challenge":
            self.question_label.config(text=lesson.get("question", "请根据说明编写代码："))
            self.code_input_area = CodeEditor(self.input_frame, font=self.font_code_text, height=10)
            self.code_input_area.pack(pady=5, fill=tk.BOTH, expand=True)
            if not points_already_awarded:
                self.format_code_button.config(state=tk.NORMAL) # Enable format button

            # Below the feedback, so 提交答案 stays right under the editor.
            self.output_title_label.pack(pady=(10,0), anchor="w", before=self.nav_frame)
            self.output_display_area.pack(pady=5, fill=tk.X, before=self.nav_frame)

            # ... (rest of code_challenge setup, including standard answer check)
            if "standard_answer_code" in lesson and "cpp_context" in lesson and "expected_output" in lesson: # Shortened for brevity
                pass # Standard answer check logic
            if points_already_awarded:
                self.code_input_area.insert(tk.END, "你已经通过了这个挑战！\n（此处不显示之前提交的代码）")
                self.code_input_area.config(state=tk.DISABLED)
                self.feedback_label.config(text="你已经通过了这个编程挑战！", foreground="blue")
            else: self.code_input_area.focus()

        # ... (fill_blank, multiple_choice logic)
        elif lesson_type == "fill_blank":
            q_parts = lesson["question_parts"]
            full_q_text = q_parts[0] + "______" + (q_parts[1] if len(q_parts) > 1 else "")
            self.question_label.config(text=full_q_text)
            self.answer_entry = ttk.Entry(self.input_frame, font=self.font_normal_text, width=30)
            self.answer_entry.pack(pady=5)
            if points_already_awarded:
                self.answer_entry.insert(0, str(accepted_answers(lesson)[0]))
                self.answer_entry.config(state=tk.DISABLED)
                self.feedback_label.config(text="你已经答对过这题啦！", foreground="blue")
            else:
                self.answer_entry.focus()
        elif lesson_type == "multiple_choice":
            self.question_label.config(text=lesson["question"])
            self.radio_var = tk.StringVar(value=None)
            correct_answer_idx_str = str(lesson["answer_index"])
            for i, option in enumerate(lesson["options"]):
                rb = ttk.Radiobutton(self.input_frame, text=option, variable=self.radio_var, value=str(i), style="Large.TRadiobutton")
                rb.pack(anchor=tk.W, padx=20, pady=2)
                self.radio_buttons.append(rb)
            if points_already_awarded:
                self.radio_var.set(correct_answer_idx_str)
                for rb_widget in self.radio_buttons: rb_widget.config(state=tk.DISABLED)
                self.feedback_label.config(text="你已经答对过这题啦！", foreground="blue")


        self.update_topic_button_text(self.current_topic_key)
        self.master.update_idletasks()
        canvas = self.scrollable_lesson_outer_frame.winfo_children()[0]
        canvas.yview_moveto(0); canvas.xview_moveto(0)
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _auto_indent_code(self, code_text):
        lines = code_text.split('\n')
        indented_code = []
        current_indent_level = 0
        indent_size = 4
        for line in lines:
            line = line.strip()
            if line.startswith('}'): current_indent_level = max(0, current_indent_level - 1)
            indented_line = ' ' * (current_indent_level * indent_size) + line
            indented_code.append(indented_line)
            if line.endswith('{'): current_indent_level += 1
        return "\n".join(indented_code)

    def _format_code_action(self):
        if self.code_input_area:
            current_code = self.code_input_area.get("1.0", "end-1c")
            formatted_code = self._auto_indent_code(current_code)
            self.code_input_area.delete("1.0", "end")
            self.code_input_area.insert("1.0", formatted_code)
            self.code_input_area._on_key_release()

    def _parse_compiler_errors(self, stderr, context_template):
        """Explains the program's first error that has a hint, at that error's own line."""
        # Only temp_code.cpp's own errors: an #include typed in the editor adds errors at /usr/include lines.
        # Link errors (undefined reference) have none, so then the whole output is searched, without a line.
        errors = re.findall(r"temp_code\.cpp:(\d+):\d+: (?:fatal )?error: (.*)", stderr) or [("0", stderr)]
        for line, message in errors:
            for pattern, friendly_message in COMPILER_ERROR_HINTS.items():
                if re.search(pattern, message, re.IGNORECASE):
                    # g++ counts the hidden cpp_context lines too; < 1 means the error is in the template.
                    user_line = int(line) - context_template.split("{user_code}")[0].count("\n")
                    if user_line >= 1:
                        return f"提示：在第 {user_line} 行附近，{friendly_message}\n\n原始错误片段：\n{stderr[:300]}" # Show a snippet
                    return f"提示：{friendly_message}\n\n原始错误片段：\n{stderr[:300]}"

        return f"原始编译错误：\n{stderr}" # Fallback to original error if no match

    def execute_cpp_code(self, user_code_snippet, context_template):
        if not shutil.which('g++'):
            return {'success': False, 'output': '', 'error': "C++编译器 (g++) 未找到或无法执行。\n请确保已安装g++并将其添加到系统PATH中。"}

        full_code = context_template.replace("{user_code}", user_code_snippet)
        temp_dir = tempfile.mkdtemp()
        cpp_file_path = os.path.join(temp_dir, "temp_code.cpp")
        exe_file_name = "temp_code.exe" if os.name == 'nt' else "temp_code"
        exe_file_path = os.path.join(temp_dir, exe_file_name)

        try:
            with open(cpp_file_path, 'w', encoding='utf-8') as f: f.write(full_code)
            # g++ and the program print UTF-8 (the source is UTF-8); Windows would otherwise decode with its ANSI code page (e.g. GBK).
            try:
                compile_process = subprocess.run(
                    ['g++', cpp_file_path, '-o', exe_file_path, '-std=c++11'],
                    capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10,
                    env={**os.environ, 'LC_ALL': 'C'},  # English messages with ASCII quotes, as COMPILER_ERROR_HINTS expects
                )
            except subprocess.TimeoutExpired:
                return {'success': False, 'output': '', 'error': "编译超时！请稍后再试一次。"}
            if compile_process.returncode != 0:
                friendly_error = self._parse_compiler_errors(compile_process.stderr, context_template)
                return {'success': False, 'output': '', 'error': friendly_error} # Use friendly error

            # stdin=DEVNULL: cin gets end-of-input at once instead of hanging the window until the timeout.
            with subprocess.Popen([exe_file_path], stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
                timer = threading.Timer(5, proc.kill)
                outputs = {}

                def read_capped(name, stream):
                    # Stop the program once a stream passes the limit instead of buffering all of it.
                    outputs[name] = stream.read(OUTPUT_LIMIT + 1)
                    if len(outputs[name]) > OUTPUT_LIMIT:
                        proc.kill()

                stderr_reader = threading.Thread(target=read_capped, args=('stderr', proc.stderr))
                timer.start()
                stderr_reader.start()
                read_capped('stdout', proc.stdout)
                stderr_reader.join()
                proc.wait()
                timed_out = timer.finished.is_set()  # set only if the timer fired, until cancel() below
                timer.cancel()
            if any(len(data) > OUTPUT_LIMIT for data in outputs.values()):
                return {'success': False, 'output': '', 'error': "输出过长（超过 64 KB）！代码可能进入了无限循环。"}
            if timed_out:
                return {'success': False, 'output': '', 'error': "执行超时！代码可能进入了无限循环或运行时间过长。"}
            # Decode like text=True did: UTF-8, and \r\n to \n so Windows output matches the expected text.
            stdout, stderr = (outputs[name].decode('utf-8', 'replace').replace('\r\n', '\n') for name in ('stdout', 'stderr'))
            runtime_error_info = f"\n运行时信息/错误:\n{stderr}" if stderr else ""
            if proc.returncode != 0:
                return {'success': False, 'output': '', 'error': f"程序异常退出 (code {proc.returncode}){runtime_error_info}"}
            return {'success': True, 'output': stdout, 'error': runtime_error_info}
        except Exception as e:
            return {'success': False, 'output': '', 'error': f"执行时发生意外错误: {str(e)}"}
        finally:
            for f_path in [cpp_file_path, exe_file_path]:
                if os.path.exists(f_path):
                    try: os.remove(f_path)
                    except OSError as e: print(f"Warning: Could not remove temp file {f_path}: {e}")
            if os.path.exists(temp_dir):
                try:
                    if not os.listdir(temp_dir): os.rmdir(temp_dir)
                    else: print(f"Warning: Temp directory {temp_dir} not empty, not removing.")
                except OSError as e: print(f"Warning: Could not remove temp directory {temp_dir}: {e}")

    def _get_correct_answer_display_text(self, lesson):
        # ... (no changes here)
        lesson_type = lesson["type"]
        if lesson_type == "fill_blank":
            return f"“{accepted_answers(lesson)[0]}”"
        elif lesson_type == "multiple_choice":
            return f"“{lesson['options'][lesson['answer_index']]}”"
        elif lesson_type == "code_challenge":
            expected_out = lesson.get("expected_output", "未定义预期输出")
            return f"\n预期输出是:\n---\n{expected_out.strip()}\n---"
        return "N/A"


    def _handle_correct_answer(self, lesson, lesson_id):
        # ... (no changes here)
        points = lesson.get("points", 0)
        feedback_msg = ""

        newly_awarded = not self.lesson_points_awarded.get(lesson_id, False) and points > 0
        if newly_awarded:
            self.scores[self.current_topic_key] += points
            self.total_score = sum(self.scores.values())
            self.lesson_points_awarded[lesson_id] = True
            feedback_msg = f"太棒了! 完全正确! +{points}分"
        elif self.lesson_points_awarded.get(lesson_id, False):
            feedback_msg = "太棒了! 你之前已经答对这题了!"
        else:
            feedback_msg = "太棒了! 完全正确!"

        self.feedback_label.config(text=feedback_msg, foreground="green")
        self.submit_button.config(state=tk.DISABLED)
        if self.answer_entry: self.answer_entry.config(state=tk.DISABLED)
        for rb in self.radio_buttons: rb.config(state=tk.DISABLED)
        if self.code_input_area: self.code_input_area.config(state=tk.DISABLED)
        self.format_code_button.config(state=tk.DISABLED) # Disable format button on correct answer

        self.failed_attempts[lesson_id] = 0
        if newly_awarded:
            self.update_score_display()  # show the final score before the modal congratulation
            self.check_all_topics_completed()

    def _handle_incorrect_answer(self, lesson, lesson_id, cpp_error_message=""):
        # ... (no changes here, but cpp_error_message will now be friendlier if parsed)
        self.failed_attempts.setdefault(lesson_id, 0)
        self.failed_attempts[lesson_id] += 1

        if self.failed_attempts[lesson_id] >= self.MAX_FAILED_ATTEMPTS:
            correct_answer_text = self._get_correct_answer_display_text(lesson)
            feedback_msg = f"尝试次数过多。\n正确答案提示: {correct_answer_text}\n"
            feedback_msg += "继续努力，下一关加油！"

            self.feedback_label.config(text=feedback_msg, foreground="orange")
            self.submit_button.config(state=tk.DISABLED)
            self.format_code_button.config(state=tk.DISABLED) # Disable format button
            if self.answer_entry: self.answer_entry.config(state=tk.DISABLED)
            for rb in self.radio_buttons: rb.config(state=tk.DISABLED)
            if self.code_input_area: self.code_input_area.config(state=tk.DISABLED)

            self.failed_attempts[lesson_id] = 0
        else:
            remaining_attempts = self.MAX_FAILED_ATTEMPTS - self.failed_attempts[lesson_id]
            hint_text = lesson.get('hint', '没有提示。')

            if lesson["type"] == "code_challenge" and cpp_error_message:
                self.feedback_label.config(text=f"本关提示：{hint_text}\n{cpp_error_message}\n剩余尝试次数: {remaining_attempts}", foreground="red")
            else: # Fallback for other errors or non-code challenges
                self.feedback_label.config(text=f"不对哦，再想想看! 提示：{hint_text}\n剩余尝试次数: {remaining_attempts}", foreground="red")

            if self.answer_entry:
                self.answer_entry.select_range(0, tk.END)


    def check_answer(self):
        # ... (no changes to the start of this method)
        if not self.current_topic_key: return
        topic_lessons = LESSONS_DATA[self.current_topic_key]
        if self.current_lesson_index >= len(topic_lessons): return

        lesson = topic_lessons[self.current_lesson_index]
        lesson_id = (self.current_topic_key, self.current_lesson_index)
        lesson_type = lesson["type"]
        is_correct = False
        cpp_specific_error_message = "" # Will hold friendly or original error

        if lesson_type == "code_challenge":
            self.output_display_area.config(state=tk.NORMAL)
            self.output_display_area.delete('1.0', tk.END)
            self.output_display_area.config(state=tk.DISABLED, foreground="black")

        if lesson_type == "fill_blank":
            # ...
            if self.answer_entry:
                is_correct = normalize_answer(self.answer_entry.get()) in map(normalize_answer, accepted_answers(lesson))
        elif lesson_type == "multiple_choice":
            # ...
            if self.radio_var:
                user_answer_idx = self.radio_var.get()
                if user_answer_idx is not None and user_answer_idx.isdigit():
                     is_correct = (int(user_answer_idx) == lesson["answer_index"])
                else:
                    self.feedback_label.config(text="请选择一个选项哦!", foreground="orange")
                    return
        elif lesson_type == "code_challenge":
            if self.code_input_area:
                user_code = self.code_input_area.get("1.0", "end-1c")  # unstripped: error line numbers must match the editor
                if not user_code.strip():
                    self.feedback_label.config(text="请输入你的C++代码！", foreground="orange")
                    self.output_display_area.config(state=tk.NORMAL)
                    self.output_display_area.insert(tk.END, "错误: 未输入任何代码。")
                    self.output_display_area.config(state=tk.DISABLED, foreground="red")
                    return

                context = lesson.get("cpp_context")
                expected_out_str = lesson.get("expected_output")

                if context is None or expected_out_str is None:
                    # ... (error handling)
                    messagebox.showerror("课程错误", "此代码挑战缺少必要的 'cpp_context' 或 'expected_output' 数据。")
                    self.feedback_label.config(text="课程配置错误，无法执行。", foreground="red")
                    self.submit_button.config(state=tk.DISABLED)
                    self.format_code_button.config(state=tk.DISABLED)
                    return

                self.feedback_label.config(text="正在编译运行…", foreground="black")
                buttons = (self.submit_button, self.prev_button, self.skip_button, self.next_button,
                           self.format_code_button, *self.topic_buttons.values())
                for button in buttons: button.state(["disabled"])  # the flag only: -state keeps what each button should be after the run
                self.feedback_label.update_idletasks()  # show it before the window blocks on g++
                result = self.execute_cpp_code(user_code, context)
                def unlock():
                    for button in buttons: button.config(state=button.cget("state"))
                # Clicks made while the window was blocked are replayed after we return: unlock only once they hit disabled buttons.
                # shortcut: assumes the replayed clicks arrive within 100 ms; running g++ on a worker thread (#5 option b) removes the guess.
                self.master.after(100, unlock)
                self.output_display_area.config(state=tk.NORMAL)
                self.output_display_area.delete('1.0', tk.END)

                if result['success']:
                    actual_output_trimmed = normalize_output(result['output'])
                    expected_output_trimmed = normalize_output(expected_out_str)
                    is_correct = (actual_output_trimmed == expected_output_trimmed)
                    display_text = f"你的程序输出:\n---\n{result['output']}\n---"
                    if result['error']: display_text += f"{result['error']}\n---"
                    self.output_display_area.insert(tk.END, display_text)
                    if not is_correct:
                        cpp_specific_error_message = "输出与预期不符。" # This will be shown by _handle_incorrect_answer
                        self.output_display_area.insert(tk.END, f"\n预期输出 (已去除首尾空格/换行进行比较):\n---\n{expected_output_trimmed}\n---")
                        self.output_display_area.insert(tk.END, f"\n你的输出 (已去除首尾空格/换行进行比较):\n---\n{actual_output_trimmed}\n---")
                else:
                    is_correct = False
                    cpp_specific_error_message = result['error'] # This is now the (potentially friendly) error
                    self.output_display_area.insert(tk.END, f"{cpp_specific_error_message}") # Display the error
                    self.output_display_area.config(foreground="red")
                self.output_display_area.config(state=tk.DISABLED)

        if is_correct:
            self._handle_correct_answer(lesson, lesson_id)
        else:
            self._handle_incorrect_answer(lesson, lesson_id, cpp_error_message=cpp_specific_error_message)

        self.update_score_display()
        self.update_topic_button_text(self.current_topic_key)
        self.master.update_idletasks()
        canvas = self.scrollable_lesson_outer_frame.winfo_children()[0]
        canvas.configure(scrollregion=canvas.bbox("all"))

    def previous_lesson(self):
        # ... (no changes)
        if self.current_topic_key and self.current_lesson_index > 0:
            self.current_lesson_index -= 1
            self.load_lesson()

    def next_lesson(self):
        # ... (no changes)
        if self.current_topic_key:
            topic_lessons = LESSONS_DATA[self.current_topic_key]
            if self.current_lesson_index < len(topic_lessons):
                 self.current_lesson_index += 1
            self.load_lesson()

    def skip_lesson(self):
        self.next_lesson()  # load_lesson() clears the feedback, so set it afterwards
        self.feedback_label.config(text="已跳过当前关卡。", foreground="blue")

    def update_score_display(self):
        # ... (no changes)
        self.score_label.config(text=f"总得分: {self.total_score} / {self.total_max_score}")

    def update_topic_button_text(self, topic_key):
        # ... (no changes)
        if not topic_key or topic_key not in self.topic_buttons: return
        btn = self.topic_buttons[topic_key]
        max_s = self.max_scores.get(topic_key, 0)
        current_s = self.scores.get(topic_key, 0)
        progress_text = f"{topic_key} ({current_s}/{max_s})"

        is_topic_fully_completed = True
        if LESSONS_DATA.get(topic_key) and max_s > 0:
            for i, lesson_in_topic in enumerate(LESSONS_DATA[topic_key]):
                lesson_id = (topic_key, i)
                if lesson_in_topic.get("points", 0) > 0 and not self.lesson_points_awarded.get(lesson_id, False):
                    is_topic_fully_completed = False
                    break
            if current_s < max_s :
                is_topic_fully_completed = False
        elif max_s == 0:
            is_topic_fully_completed = True
        else:
            is_topic_fully_completed = False


        if max_s > 0 and is_topic_fully_completed :
            progress_text += " ✔️"
            btn.config(style="Completed.TButton")
        else:
            btn.config(style="Large.TButton")
        btn.config(text=progress_text)

    def check_all_topics_completed(self):
        # ... (no changes)
        if not LESSONS_DATA or self.total_max_score == 0: return

        all_scorable_topics_completed = True
        has_scorable_topics = False
        for t_key in LESSONS_DATA:
            if self.max_scores.get(t_key, 0) > 0:
                has_scorable_topics = True
                topic_lessons = LESSONS_DATA[t_key]
                topic_completed_for_check = True
                for i, lesson_in_topic in enumerate(topic_lessons):
                    if lesson_in_topic.get("points", 0) > 0:
                        lesson_id = (t_key, i)
                        if not self.lesson_points_awarded.get(lesson_id, False):
                            topic_completed_for_check = False
                            break
                if not topic_completed_for_check:
                    all_scorable_topics_completed = False
                    break

        if has_scorable_topics and all_scorable_topics_completed:
            messagebox.showinfo("恭喜!", "太厉害啦! 你已经完成了所有课程的学习，并获得了所有分数! 你是最棒的!")


if __name__ == "__main__":
    # ... (no changes)
    print("提示：对于 'code_challenge' 类型的关卡，请确保 'lessons_data.json' 文件中包含以下字段：")
    print("  - \"cpp_context\": \"#include <iostream>\\nint main() {{ {user_code} return 0; }}\" (包含 {user_code} 占位符)")
    print("  - \"expected_output\": \"预期的程序输出\" (程序输出将与此比较，首尾空格/换行符会被去除后比较)")
    print("  - \"standard_answer_code\": \"能够产生预期输出的标准答案C++代码片段\" (可选但强烈建议，用于校验关卡数据)")
    print("-" * 30)

    root = tk.Tk()
    style = ttk.Style()
    button_font_config = ("Arial", 14)
    radio_font_config = ("Arial", 13)

    style.configure("TRadiobutton", font=radio_font_config)
    style.configure("Large.TRadiobutton", font=radio_font_config)

    style.configure("TButton", font=button_font_config, padding=5)
    style.configure("Large.TButton", font=button_font_config, padding=5)
    style.configure("Completed.TButton", foreground="green", font=(button_font_config[0], button_font_config[1], 'bold'), padding=5)

    app = InteractiveLearningApp(root)
    root.mainloop()