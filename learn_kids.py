import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog, filedialog
import json
import subprocess
import tempfile
import os
import re # Added for error parsing and syntax highlighting
from tkinter import font as tk_font # Import the font module
import shutil
import datetime

# --- 全局常量 ---
COURSES_BASE_DIR = os.path.join(os.path.dirname(__file__), "courses")

# --- 函数：获取课程列表 ---
def get_courses():
    """Scans the courses directory and returns a list of available courses."""
    if not os.path.exists(COURSES_BASE_DIR) or not os.path.isdir(COURSES_BASE_DIR):
        return []
    return sorted([d for d in os.listdir(COURSES_BASE_DIR) if os.path.isdir(os.path.join(COURSES_BASE_DIR, d))])

# --- 函数：从课程文件夹加载单元数据 ---
def load_units_from_course(course_name):
    """
    Loads all .json unit files from a specific course directory.
    """
    course_path = os.path.join(COURSES_BASE_DIR, course_name)
    all_units_data = {}
    if not os.path.isdir(course_path):
        messagebox.showerror("错误", f"课程目录 '{course_path}' 不存在！")
        return {}

    json_files = sorted([f for f in os.listdir(course_path) if f.endswith('.json')])

    if not json_files:
        messagebox.showwarning("警告", f"课程 '{course_name}' 中没有找到任何单元JSON文件。")
        return {}

    for filename in json_files:
        filepath = os.path.join(course_path, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict) and len(data) == 1:
                all_units_data.update(data)
            else:
                messagebox.showwarning("格式警告", f"单元文件 '{filename}' 格式不符合预期，已跳过。")
        except Exception as e:
            messagebox.showerror("加载错误", f"加载单元文件 '{filepath}' 时出错: {e}")
            continue

    return all_units_data

# --- 数据占位符 ---
# LESSONS_DATA is now loaded dynamically after a course is selected.
LESSONS_DATA = {}

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

        def _on_mousewheel(event):
            if event.num == 4: canvas.yview_scroll(-1, "units")
            elif event.num == 5: canvas.yview_scroll(1, "units")
            else: canvas.yview_scroll(int(-1*(event.delta/120)), "units")

        def _on_shift_mousewheel(event):
            if event.num == 4: canvas.xview_scroll(-1, "units")
            elif event.num == 5: canvas.xview_scroll(1, "units")
            else: canvas.xview_scroll(int(-1*(event.delta/120)), "units")

        if container.tk.call('tk', 'windowingsystem') == 'aqua':
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
            canvas.bind_all("<Shift-MouseWheel>", _on_shift_mousewheel)
        else:
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
            canvas.bind_all("<Shift-MouseWheel>", _on_shift_mousewheel)
            canvas.bind_all("<Button-4>", _on_mousewheel)
            canvas.bind_all("<Button-5>", _on_mousewheel)

class CodeEditor(tk.Frame):
    def __init__(self, master, font=None, **kwargs):
        super().__init__(master, **kwargs)
        kwargs.pop('height', None)

        self.line_numbers = tk.Text(self, width=4, padx=4, takefocus=0, border=0,
                                    background='lightgrey', state='disabled', wrap='none', font=font)
        self.code_area = tk.Text(self, wrap='word', undo=True, padx=5, pady=5, font=font)

        self.scrollbar_y = ttk.Scrollbar(self, orient="vertical", command=self._on_scrollbar)
        self.code_area.configure(yscrollcommand=self.scrollbar_y.set)

        self.line_numbers.pack(side="left", fill="y")
        self.scrollbar_y.pack(side="right", fill="y")
        self.code_area.pack(side="right", fill="both", expand=True)

        self.code_area.bind("<KeyRelease>", self._on_key_release)
        self.code_area.bind("<MouseWheel>", self._on_scroll)
        self.code_area.bind("<Button-4>", self._on_scroll)
        self.code_area.bind("<Button-5>", self._on_scroll)
        self.code_area.bind("<Return>", self._on_enter_key)
        self.code_area.bind("<Configure>", self._on_key_release)

        self._update_line_numbers()
        self._configure_tags()

    def _on_scrollbar(self, *args):
        self.code_area.yview(*args)
        self.line_numbers.yview(*args)
        self._update_line_numbers()

    def _on_scroll(self, event=None):
        self.line_numbers.yview_moveto(self.code_area.yview()[0])
        self._update_line_numbers()
        return "break"

    def _on_enter_key(self, event=None):
        self._apply_indentation()
        self._on_key_release()
        return "break"

    def _apply_indentation(self):
        current_line_number_str = self.code_area.index(tk.INSERT).split('.')[0]
        if current_line_number_str == "1": prev_line_content = ""
        else:
            prev_line_number = int(current_line_number_str) - 1
            prev_line_content = self.code_area.get(f"{prev_line_number}.0", f"{prev_line_number}.end")

        indentation = "".join(char for char in prev_line_content if char in ' \t')
        if prev_line_content.strip().endswith('{'): indentation += "    "
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
        master.title("互动学习平台")
        master.geometry("1100x800")

        # --- 字体定义 ---
        self.font_title = ("Arial", 22, "bold")
        self.font_subtitle = ("Arial", 18, "bold")
        self.font_normal_text = ("Arial", 15)
        self.font_normal_bold = ("Arial", 15, "bold")
        self.font_italic_text = ("Arial", 15, "italic")
        self.font_code_text = ("Courier New", 14)
        self.font_button = ("Arial", 14)

        # --- 状态变量 ---
        self.courses = get_courses()
        self.current_course_name = None
        self.current_topic_key = None # "Topic" is now a "Unit"
        self.current_lesson_index = 0
        self.scores = {}
        self.max_scores = {}
        self.lesson_points_awarded = {}
        self.total_score = 0
        self.total_max_score = 0
        self.failed_attempts = {}
        self.MAX_FAILED_ATTEMPTS = 5

        # --- 主窗口布局 ---
        self.main_paned_window = ttk.PanedWindow(master, orient=tk.HORIZONTAL)
        self.main_paned_window.pack(fill=tk.BOTH, expand=True)

        # --- 左侧面板 (课程/单元列表) ---
        self.left_panel_container = ttk.Frame(self.main_paned_window, width=280, height=700)
        self.left_panel_container.pack_propagate(False)
        self.main_paned_window.add(self.left_panel_container, weight=0)

        self.left_panel_title = ttk.Label(self.left_panel_container, text="课程列表", font=self.font_subtitle)
        self.left_panel_title.pack(pady=10)

        # --- 课程/单元按钮的容器 ---
        self.buttons_frame = ttk.Frame(self.left_panel_container)
        self.buttons_frame.pack(fill=tk.BOTH, expand=True)
        self.course_buttons = {}
        self.topic_buttons = {} # For units within a course

        # --- 右侧主内容区 ---
        self.scrollable_lesson_outer_frame = ScrollableFrame(self.main_paned_window)
        self.main_paned_window.add(self.scrollable_lesson_outer_frame, weight=1)
        self.lesson_frame = self.scrollable_lesson_outer_frame.scrollable_content_frame

        self.lesson_title_label = ttk.Label(self.lesson_frame, text="请从左侧选择一个课程开始学习", font=self.font_title)
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

        self.score_label = ttk.Label(master, text="总得分: 0 / 0", font=self.font_subtitle)
        self.score_label.pack(side=tk.BOTTOM, pady=10)

        self.display_courses()

    def display_courses(self):
        """Clears the left panel and shows the list of available courses."""
        for widget in self.buttons_frame.winfo_children():
            widget.destroy()
        self.left_panel_title.config(text="课程列表")
        self.course_buttons = {}

        if not self.courses:
            ttk.Label(self.buttons_frame, text="没有找到课程。\n请在 'courses' 文件夹中\n创建课程子目录。", justify=tk.CENTER).pack(pady=20)
            return

        for course_name in self.courses:
            btn = ttk.Button(self.buttons_frame, text=course_name, command=lambda c=course_name: self.select_course(c), width=25, style="Large.TButton")
            btn.pack(pady=5, padx=5, fill=tk.X)
            self.course_buttons[course_name] = btn

        # --- 添加管理按钮 ---
        manage_btn = ttk.Button(self.buttons_frame, text="⚙️ 课程管理", command=self.open_management_window)
        manage_btn.pack(side=tk.BOTTOM, pady=20, padx=5, fill=tk.X)

    def open_management_window(self):
        """Opens the course management window."""
        management_win = CourseManagementWindow(self.master, self)
        management_win.grab_set() # Modal-like behavior

    def select_course(self, course_name):
        """Loads a course and displays its units."""
        global LESSONS_DATA
        self.current_course_name = course_name
        LESSONS_DATA = load_units_from_course(course_name)

        if not LESSONS_DATA:
            self.lesson_title_label.config(text=f"课程 '{course_name}' 为空")
            self._clear_input_widgets()
            self.explanation_text.config(state=tk.NORMAL); self.explanation_text.delete('1.0', tk.END)
            self.explanation_text.insert(tk.END, "这个课程里还没有任何学习单元。"); self.explanation_text.config(state=tk.DISABLED)
            return

        # Reset scores and state for the new course
        self.scores = {topic: 0 for topic in LESSONS_DATA}
        self.max_scores = {topic: sum(l.get('points', 0) for l in lessons) for topic, lessons in LESSONS_DATA.items()}
        self.lesson_points_awarded = {}
        self.total_score = 0
        self.total_max_score = sum(self.max_scores.values())
        self.current_topic_key = None
        self.current_lesson_index = 0

        self.display_units()
        self.update_score_display()
        # Select the first unit automatically
        first_unit_key = next(iter(LESSONS_DATA), None)
        if first_unit_key:
            self.select_topic(first_unit_key)

    def display_units(self):
        """Displays the units for the currently selected course."""
        for widget in self.buttons_frame.winfo_children():
            widget.destroy()
        self.left_panel_title.config(text=f"课程: {self.current_course_name}")
        self.topic_buttons = {}

        # Add a "Back to Courses" button
        back_btn = ttk.Button(self.buttons_frame, text="« 返回课程列表", command=self.display_courses)
        back_btn.pack(pady=(5, 10), padx=5, fill=tk.X)

        for topic_key in LESSONS_DATA.keys():
            btn = ttk.Button(self.buttons_frame, text=topic_key, command=lambda k=topic_key: self.select_topic(k), width=25, style="Large.TButton")
            btn.pack(pady=5, padx=5, fill=tk.X)
            self.topic_buttons[topic_key] = btn
            self.update_topic_button_text(topic_key) # Update with initial score

    def select_topic(self, topic_key):
        self.current_topic_key = topic_key
        self.current_lesson_index = 0
        self.lesson_title_label.config(text=f"单元: {topic_key}")
        self.load_lesson()
        self.update_score_display()

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
            # ... (completion message logic)
            return

        self.skip_button.config(state=tk.NORMAL)
        self.next_button.config(state=tk.NORMAL)
        lesson = topic_lessons[self.current_lesson_index]
        lesson_id = (self.current_topic_key, self.current_lesson_index)
        points_already_awarded = self.lesson_points_awarded.get(lesson_id, False)

        self.explanation_text.config(state=tk.NORMAL); self.explanation_text.delete('1.0', tk.END)
        self.explanation_text.insert(tk.END, lesson.get("text", "")); self.explanation_text.config(state=tk.DISABLED)
        self.code_display_text.config(state=tk.NORMAL); self.code_display_text.delete('1.0', tk.END)
        self.code_display_text.insert(tk.END, lesson.get("code", "")); self.code_display_text.config(state=tk.DISABLED)

        lesson_type = lesson["type"]
        if not points_already_awarded and lesson_type != "explanation":
            self.submit_button.config(state=tk.NORMAL)
        else: self.submit_button.config(state=tk.DISABLED)

        if lesson_type == "code_challenge":
            self.question_label.config(text=lesson.get("question", "请根据说明编写代码："))
            self.code_input_area = CodeEditor(self.input_frame, font=self.font_code_text) # Removed height=10
            self.code_input_area.pack(pady=5, fill=tk.BOTH, expand=True)
            if not points_already_awarded:
                self.format_code_button.config(state=tk.NORMAL) # Enable format button

            self.output_title_label.pack(pady=(10,0), anchor="w", before=self.action_buttons_frame) # Adjusted packing order
            self.output_display_area.pack(pady=5, fill=tk.X, before=self.action_buttons_frame)   # Adjusted packing order

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
                self.answer_entry.insert(0, str(lesson["answer"]))
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

    def _parse_compiler_errors(self, stderr):
        """Attempts to parse g++ errors and provide friendlier messages."""
        # Simple error mapping (can be expanded)
        error_map = {
            r"expected ';' before": "哎呀，好像在某行的末尾忘记了分号 ';' 哦！C++中很多语句需要用它来结束。",
            r"was not declared in this scope": "嗯，你用了一个变量或者函数，但是好像忘记先告诉电脑它是什么了（忘记声明了）。",
            r"expected primary-expression before '.*' token": "这里似乎有点小问题，电脑不太明白你想做什么。检查一下是不是有奇怪的符号或者漏了东西？",
            r"stray '\\[0-9]*' in program": "代码里好像有一些奇怪的、看不懂的符号，检查一下是不是不小心打错了？",
            r"undefined reference to": "电脑找到了一个名字，但是找不到它具体代表什么（比如一个函数）。是不是忘记写这个函数了，或者链接的时候出错了？",
            r"expected '}' at end of input": "代码的最后好像少了一个大括号 '}' 来收尾哦。",
            r"expected declaration before '}' token": "这个大括号 '}' 前面是不是少了点什么代码呢？",
            r"conflicting declaration '.*'": "这个名字好像之前用过了，但是这次用它的方式和之前不一样哦。",
            r"redeclaration of '.*'": "这个名字你好像声明过两次了，检查一下是不是写多了？",
            r"no match for 'operator<<'": "使用 `cout << ...` 的时候，`<<` 右边的东西电脑不认识，看看是不是类型不对？",
            r"no match for 'operator>>'": "使用 `cin >> ...` 的时候，`>>` 右边的变量电脑不认识，看看是不是类型不对或者没声明？",
            r"expected unqualified-id before numeric constant": "数字前面是不是不小心写了什么不该写的东西？",
            r"expected 'while' before '('": "for或者do-while循环是不是少了 `while` 关键字？",
            r"expected expression before ')' token": "括号 `()` 里面好像少了点东西，或者括号不匹配哦。",
            r"expected ')' before ';' token": "是不是有一行代码的括号 `(` 没有对应的 `)` 就直接写分号了？",
            r"else without a previous if": "`else` 是跟着 `if` 用的，这里好像没有找到前面的 `if` 呀。",
            r"return-statement with no value, in function returning 'int'": "这个函数应该返回一个整数，但是 `return;` 后面忘记写返回值了。",
            r"note: expected 'int' but argument is of type": "函数需要的参数类型和你给的不一样哦，检查一下参数类型吧。",
            r"too few arguments to function": "调用函数的时候，给的参数数量不够哦。",
            r"too many arguments to function": "调用函数的时候，给的参数数量太多了哦。",
            r"error: (ld returned 1 exit status|linker command failed)": "代码编译好了，但是在最后组合（链接）的时候出错了。通常是找不到 main 函数或者某些库函数。"
        }
        # More specific error patterns can be added above less specific ones.
        for pattern, friendly_message in error_map.items():
            if re.search(pattern, stderr, re.IGNORECASE):
                # Try to extract line number if possible
                line_match = re.search(r":(\d+):\d+:", stderr)
                if line_match:
                    return f"提示：在第 {line_match.group(1)} 行附近，{friendly_message}\n\n原始错误片段：\n{stderr[:300]}" # Show a snippet
                return f"提示：{friendly_message}\n\n原始错误片段：\n{stderr[:300]}"

        return f"原始编译错误：\n{stderr}" # Fallback to original error if no match

    def execute_cpp_code(self, user_code_snippet, context_template):
        try:
            subprocess.run(['g++', '--version'], check=True, capture_output=True, text=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return {'success': False, 'output': '', 'error': "C++编译器 (g++) 未找到或无法执行。\n请确保已安装g++并将其添加到系统PATH中。"}

        full_code = context_template.replace("{user_code}", user_code_snippet)
        temp_dir = tempfile.mkdtemp()
        cpp_file_path = os.path.join(temp_dir, "temp_code.cpp")
        exe_file_name = "temp_code.exe" if os.name == 'nt' else "temp_code"
        exe_file_path = os.path.join(temp_dir, exe_file_name)

        try:
            with open(cpp_file_path, 'w', encoding='utf-8') as f: f.write(full_code)
            compile_process = subprocess.run(
                ['g++', cpp_file_path, '-o', exe_file_path, '-std=c++11'],
                capture_output=True, text=True, timeout=10
            )
            if compile_process.returncode != 0:
                friendly_error = self._parse_compiler_errors(compile_process.stderr)
                return {'success': False, 'output': '', 'error': friendly_error} # Use friendly error

            run_process = subprocess.run([exe_file_path], capture_output=True, text=True, timeout=5)
            runtime_error_info = f"\n运行时信息/错误:\n{run_process.stderr}" if run_process.stderr else ""
            return {'success': True, 'output': run_process.stdout, 'error': runtime_error_info}
        except subprocess.TimeoutExpired as te:
            error_type = "编译" if 'compile_process' not in locals() or te is compile_process else "执行"
            return {'success': False, 'output': '', 'error': f"{error_type}超时！代码可能进入了无限循环或运行时间过长。"}
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
            return f"“{lesson['answer']}”"
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

        if not self.lesson_points_awarded.get(lesson_id, False) and points > 0:
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
                self.feedback_label.config(text=f"{cpp_error_message}\n剩余尝试次数: {remaining_attempts}", foreground="red")
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
                user_answer = self.answer_entry.get().strip()
                is_correct = (user_answer.lower() == str(lesson["answer"]).lower())
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
                user_code = self.code_input_area.get("1.0", "end-1c").strip()
                if not user_code:
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

                result = self.execute_cpp_code(user_code, context)
                self.output_display_area.config(state=tk.NORMAL)
                self.output_display_area.delete('1.0', tk.END)

                if result['success']:
                    actual_output_trimmed = result['output'].strip()
                    expected_output_trimmed = expected_out_str.strip()
                    is_correct = (actual_output_trimmed == expected_output_trimmed)
                    display_text = f"你的程序输出:\n---\n{result['output']}\n---"
                    if result['error']: display_text += f"\n运行时信息/错误:\n{result['error']}\n---"
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
        # ... (no changes)
        self.feedback_label.config(text="已跳过当前关卡。", foreground="blue")
        self.next_lesson()

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


class CourseManagementWindow(tk.Toplevel):
    def __init__(self, parent, app_instance):
        super().__init__(parent)
        self.app = app_instance
        self.title("课程与单元管理")
        self.geometry("900x600")

        # --- Main Paned Window ---
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- Courses Panel (Left) ---
        courses_frame = ttk.LabelFrame(main_pane, text="课程管理", padding=10)
        main_pane.add(courses_frame, weight=1)

        self.course_listbox = tk.Listbox(courses_frame, font=self.app.font_normal_text)
        self.course_listbox.pack(fill=tk.BOTH, expand=True)
        self.course_listbox.bind("<<ListboxSelect>>", self.on_course_select)

        courses_btn_frame = ttk.Frame(courses_frame)
        courses_btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(courses_btn_frame, text="添加课程", command=self.add_course).pack(side=tk.LEFT, expand=True, padx=2)
        ttk.Button(courses_btn_frame, text="重命名", command=self.rename_course).pack(side=tk.LEFT, expand=True, padx=2)
        ttk.Button(courses_btn_frame, text="删除课程", command=self.delete_course).pack(side=tk.LEFT, expand=True, padx=2)

        # --- Units Panel (Right) ---
        units_frame = ttk.LabelFrame(main_pane, text="单元管理 (请先选择左侧课程)", padding=10)
        main_pane.add(units_frame, weight=2)

        self.unit_listbox = tk.Listbox(units_frame, font=self.app.font_normal_text)
        self.unit_listbox.pack(fill=tk.BOTH, expand=True)

        units_btn_frame = ttk.Frame(units_frame)
        units_btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(units_btn_frame, text="添加单元", command=self.add_unit).pack(side=tk.LEFT, expand=True, padx=2)
        ttk.Button(units_btn_frame, text="编辑单元", command=self.edit_unit).pack(side=tk.LEFT, expand=True, padx=2)
        ttk.Button(units_btn_frame, text="删除单元", command=self.delete_unit).pack(side=tk.LEFT, expand=True, padx=2)

        # --- Import/Export Frame ---
        io_frame = ttk.LabelFrame(self, text="导入 / 导出", padding=10)
        io_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Button(io_frame, text="导入课程(.zip)", command=self.import_courses).pack(side=tk.LEFT, expand=True, padx=5)
        ttk.Button(io_frame, text="导出所有课程", command=self.export_all_courses).pack(side=tk.LEFT, expand=True, padx=5)

        self.populate_course_list()

    def populate_course_list(self):
        self.course_listbox.delete(0, tk.END)
        courses = get_courses()
        for course in courses:
            self.course_listbox.insert(tk.END, course)
        self.on_course_select() # Clear unit list if no course is selected

    def on_course_select(self, event=None):
        self.unit_listbox.delete(0, tk.END)
        selected_indices = self.course_listbox.curselection()
        if not selected_indices:
            return

        course_name = self.course_listbox.get(selected_indices[0])
        course_path = os.path.join(COURSES_BASE_DIR, course_name)

        if os.path.isdir(course_path):
            units = sorted([f for f in os.listdir(course_path) if f.endswith('.json')])
            for unit in units:
                self.unit_listbox.insert(tk.END, unit)

    def _refresh_all_lists(self):
        """Refreshes the course lists in both the management window and the main app."""
        self.populate_course_list()
        self.app.courses = get_courses()
        self.app.display_courses()

    def add_course(self):
        new_course_name = simpledialog.askstring("添加新课程", "请输入新课程的名称:", parent=self)
        if not new_course_name or not new_course_name.strip():
            return

        new_course_name = new_course_name.strip()
        # Basic validation for directory names
        if any(c in r'<>:"/\|?*' for c in new_course_name):
            messagebox.showerror("错误", "课程名称包含无效字符。", parent=self)
            return

        new_course_path = os.path.join(COURSES_BASE_DIR, new_course_name)
        if os.path.exists(new_course_path):
            messagebox.showerror("错误", "该课程名称已存在。", parent=self)
            return

        try:
            os.makedirs(new_course_path)
            messagebox.showinfo("成功", f"课程 '{new_course_name}' 已成功创建。", parent=self)
            self._refresh_all_lists()
        except Exception as e:
            messagebox.showerror("创建失败", f"创建课程目录时出错: {e}", parent=self)

    def rename_course(self):
        selected_indices = self.course_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("无选择", "请先在列表中选择一个要重命名的课程。", parent=self)
            return

        old_name = self.course_listbox.get(selected_indices[0])
        new_name = simpledialog.askstring("重命名课程", f"请输入 '{old_name}' 的新名称:", initialvalue=old_name, parent=self)

        if not new_name or not new_name.strip() or new_name.strip() == old_name:
            return

        new_name = new_name.strip()
        if any(c in r'<>:"/\|?*' for c in new_name):
            messagebox.showerror("错误", "课程名称包含无效字符。", parent=self)
            return

        old_path = os.path.join(COURSES_BASE_DIR, old_name)
        new_path = os.path.join(COURSES_BASE_DIR, new_name)

        if os.path.exists(new_path):
            messagebox.showerror("错误", "该课程名称已存在。", parent=self)
            return

        try:
            os.rename(old_path, new_path)
            messagebox.showinfo("成功", "课程已成功重命名。", parent=self)
            self._refresh_all_lists()
        except Exception as e:
            messagebox.showerror("重命名失败", f"重命名课程时出错: {e}", parent=self)

    def delete_course(self):
        selected_indices = self.course_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("无选择", "请先在列表中选择一个要删除的课程。", parent=self)
            return

        course_name = self.course_listbox.get(selected_indices[0])

        if not messagebox.askyesno("确认删除", f"您确定要永久删除课程 '{course_name}' 吗？\n此操作将删除其包含的所有单元，且无法撤销！", parent=self):
            return

        course_path = os.path.join(COURSES_BASE_DIR, course_name)
        try:
            shutil.rmtree(course_path)
            messagebox.showinfo("成功", f"课程 '{course_name}' 已被删除。", parent=self)
            self._refresh_all_lists()
        except Exception as e:
            messagebox.showerror("删除失败", f"删除课程时出错: {e}", parent=self)

    def add_unit(self):
        selected_course_indices = self.course_listbox.curselection()
        if not selected_course_indices:
            messagebox.showwarning("无选择", "请先在左侧选择一个要添加单元的课程。", parent=self)
            return

        course_name = self.course_listbox.get(selected_course_indices[0])
        unit_title = simpledialog.askstring("添加新单元", "请输入新单元的标题 (这将是文件名和课程标题):", parent=self)

        if not unit_title or not unit_title.strip():
            return

        unit_title = unit_title.strip()
        # A simple filename from title
        filename = f"{unit_title.replace(' ', '_').lower()}.json"
        filepath = os.path.join(COURSES_BASE_DIR, course_name, filename)

        if os.path.exists(filepath):
            messagebox.showerror("错误", "一个使用类似标题的单元文件已存在。", parent=self)
            return

        # Default template for a new unit
        template = {
            unit_title: [
                {
                    "type": "explanation",
                    "text": "这是新单元的介绍。",
                    "code": "// 在这里写一些示例代码",
                    "points": 0
                }
            ]
        }

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(template, f, ensure_ascii=False, indent=4)
            messagebox.showinfo("成功", f"单元 '{filename}' 已成功创建。", parent=self)
            self.on_course_select() # Refresh unit list
        except Exception as e:
            messagebox.showerror("创建失败", f"创建单元文件时出错: {e}", parent=self)

    def edit_unit(self):
        selected_course_indices = self.course_listbox.curselection()
        selected_unit_indices = self.unit_listbox.curselection()

        if not selected_course_indices or not selected_unit_indices:
            messagebox.showwarning("无选择", "请先选择一个课程和要编辑的单元。", parent=self)
            return

        course_name = self.course_listbox.get(selected_course_indices[0])
        unit_filename = self.unit_listbox.get(selected_unit_indices[0])
        filepath = os.path.join(COURSES_BASE_DIR, course_name, unit_filename)

        try:
            # Open the file with the default system editor
            if os.name == 'nt': # For Windows
                os.startfile(filepath)
            elif os.name == 'posix': # For macOS, Linux
                subprocess.call(('open', filepath) if sys.platform == 'darwin' else ('xdg-open', filepath))
            else:
                messagebox.showinfo("提示", f"请手动打开文件进行编辑:\n{filepath}", parent=self)
        except Exception as e:
            messagebox.showerror("打开失败", f"无法打开文件: {e}", parent=self)

    def delete_unit(self):
        selected_course_indices = self.course_listbox.curselection()
        selected_unit_indices = self.unit_listbox.curselection()

        if not selected_course_indices or not selected_unit_indices:
            messagebox.showwarning("无选择", "请先选择一个课程和要删除的单元。", parent=self)
            return

        course_name = self.course_listbox.get(selected_course_indices[0])
        unit_filename = self.unit_listbox.get(selected_unit_indices[0])

        if not messagebox.askyesno("确认删除", f"您确定要永久删除单元 '{unit_filename}' 吗？\n此操作无法撤销！", parent=self):
            return

        filepath = os.path.join(COURSES_BASE_DIR, course_name, unit_filename)
        try:
            os.remove(filepath)
            messagebox.showinfo("成功", f"单元 '{unit_filename}' 已被删除。", parent=self)
            self.on_course_select() # Refresh unit list
        except Exception as e:
            messagebox.showerror("删除失败", f"删除单元时出错: {e}", parent=self)

    def import_courses(self):
        filepath = filedialog.askopenfilename(
            title="选择要导入的课程压缩包",
            filetypes=[("Zip files", "*.zip")],
            parent=self
        )
        if not filepath:
            return

        if not messagebox.askyesno("确认导入", "导入将合并课程，同名课程中的同名单元文件将被覆盖。\n确定要继续吗？", parent=self):
            return

        try:
            shutil.unpack_archive(filepath, COURSES_BASE_DIR, 'zip')
            messagebox.showinfo("成功", "课程已成功导入并合并。", parent=self)
            self._refresh_all_lists()
        except Exception as e:
            messagebox.showerror("导入失败", f"导入课程时出错: {e}", parent=self)

    def export_all_courses(self):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        suggested_filename = f"courses_backup_{timestamp}.zip"

        filepath = filedialog.asksaveasfilename(
            title="选择导出位置",
            initialfile=suggested_filename,
            defaultextension=".zip",
            filetypes=[("Zip files", "*.zip")],
            parent=self
        )
        if not filepath:
            return

        # The path given to make_archive should not include the extension.
        archive_path_base = filepath.rsplit('.', 1)[0]

        try:
            shutil.make_archive(archive_path_base, 'zip', COURSES_BASE_DIR)
            messagebox.showinfo("成功", f"所有课程已成功导出到:\n{filepath}", parent=self)
        except Exception as e:
            messagebox.showerror("导出失败", f"导出课程时出错: {e}", parent=self)


if __name__ == "__main__":
    if not os.path.exists(COURSES_BASE_DIR):
        print(f"创建课程目录: {COURSES_BASE_DIR}")
        os.makedirs(COURSES_BASE_DIR)

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
