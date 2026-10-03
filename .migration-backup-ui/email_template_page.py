"""Email template editor and a small, non-executing HTML preview."""
from __future__ import annotations

import re
import tkinter as tk
from tkinter import font as tkfont
from html.parser import HTMLParser
import customtkinter as ctk

from .email_preview import EmailBrowserPreview
from .email_templates import (
    EmailTemplateRepository,
    TemplateVariableResolver,
)


SAMPLE_VALUES = {
    "name": "Nguyễn Văn A",
    "email": "example@email.com",
    "report_date": "03/10/2026",
    "workspace_name": "SPX October Report",
    "record_count": "12,480",
}
VARIABLES = ("name", "email", "report_date", "workspace_name", "record_count")
BLOCK_TAGS = {"address", "article", "blockquote", "div", "h1", "h2", "h3", "h4",
              "li", "ol", "p", "section", "table", "tr", "ul", "tbody", "thead", "tfoot"}


class CodeEditor(tk.Frame):
    """Lightweight HTML/CSS editor built from Tk Text with a code-editor layout."""

    COLORS = {
        "background": "#FFFFFF", "header": "#F8FAFC", "gutter": "#F5F7FA",
        "border": "#D0D5DD", "text": "#344054", "muted": "#98A2B3",
        "active_line": "#EEF4FF", "tag": "#175CD3", "attribute": "#7A3E9D",
        "string": "#B54708", "comment": "#667085", "selector": "#175CD3",
        "property": "#7A3E9D", "value": "#027A48", "variable": "#C11574",
        "bracket": "#667085", "accent": "#E94F2E",
    }

    def __init__(self, master, *, on_change, on_save):
        super().__init__(master, bg=self.COLORS["background"], bd=0,
                         highlightthickness=1, highlightbackground=self.COLORS["border"])
        self.on_change = on_change
        self.on_save = on_save
        self._highlight_after = None
        self._redraw_after = None
        available_fonts = set(tkfont.families(self))
        self.code_font = next((name for name in ("Consolas", "JetBrains Mono", "Fira Code",
                                                  "Cascadia Code", "Courier New")
                               if name in available_fonts), "Courier New")
        self.tab_width = tkfont.Font(self, family=self.code_font, size=11).measure("    ")
        self._build()

    def _build(self):
        header = ctk.CTkFrame(self, height=38, fg_color=self.COLORS["header"], corner_radius=0)
        header.pack(fill="x", padx=1, pady=(1, 0))
        header.pack_propagate(False)
        ctk.CTkLabel(header, text="●", font=ctk.CTkFont(size=10),
                     text_color=self.COLORS["accent"]).pack(side="left", padx=(12, 7))
        ctk.CTkLabel(header, text="template.html", font=ctk.CTkFont(family=self.code_font, size=10),
                     text_color="#344054").pack(side="left")
        ctk.CTkLabel(header, text="HTML  ·  CSS", font=ctk.CTkFont(size=9, weight="bold"),
                     text_color="#667085").pack(side="left", padx=(10, 0))
        tools = ctk.CTkFrame(header, fg_color="transparent")
        tools.pack(side="right", padx=6)
        self._tool_button(tools, "Undo", self._undo).pack(side="left", padx=2)
        self._tool_button(tools, "Redo", self._redo).pack(side="left", padx=2)
        ctk.CTkFrame(self, height=1, fg_color=self.COLORS["border"]).pack(fill="x", padx=1)

        body = tk.Frame(self, bg=self.COLORS["background"], bd=0, highlightthickness=0)
        body.pack(fill="both", expand=True, padx=1, pady=(0, 1))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        gutter_wrap = tk.Frame(body, bg=self.COLORS["gutter"], width=52,
                               highlightbackground=self.COLORS["border"], highlightthickness=1)
        gutter_wrap.grid(row=0, column=0, sticky="nsew")
        gutter_wrap.grid_propagate(False)
        self.gutter = tk.Text(gutter_wrap, width=4, wrap="none", state="disabled", takefocus=False,
                              bg=self.COLORS["gutter"], fg=self.COLORS["muted"], relief="flat", bd=0,
                              highlightthickness=0, padx=8, pady=12, font=(self.code_font, 11),
                              spacing1=2, spacing3=2)
        self.gutter.pack(fill="both", expand=True)
        self.gutter.tag_configure("active_number", foreground=self.COLORS["accent"],
                                  background=self.COLORS["active_line"],
                                  font=(self.code_font, 11, "bold"))
        self.text = tk.Text(
            body, wrap="none", state="normal", undo=True, maxundo=-1, autoseparators=True,
            bg=self.COLORS["background"], fg=self.COLORS["text"],
            insertbackground=self.COLORS["accent"], insertwidth=2, selectbackground="#DCEBFF",
            selectforeground="#17212F", relief="flat", bd=0, highlightthickness=0, takefocus=True,
            padx=14, pady=12, font=(self.code_font, 11), spacing1=2, spacing3=2,
            tabs=(self.tab_width,),
        )
        self.text.grid(row=0, column=1, sticky="nsew")
        self._textbox = self.text
        self.vscroll = ctk.CTkScrollbar(body, width=9, command=self.text.yview,
                                        fg_color=self.COLORS["background"],
                                        button_color="#C7CED8", button_hover_color="#AAB4C1")
        self.vscroll.grid(row=0, column=2, sticky="ns", padx=(2, 3), pady=4)
        self.hscroll = ctk.CTkScrollbar(self, orientation="horizontal", height=9,
                                        command=self.text.xview, fg_color=self.COLORS["background"],
                                        button_color="#C7CED8", button_hover_color="#AAB4C1")
        self.hscroll.pack(fill="x", padx=4, pady=(0, 3))
        self.text.configure(yscrollcommand=self._on_yview, xscrollcommand=self.hscroll.set)
        self._configure_syntax_tags()
        self.text.bind("<KeyRelease>", self._on_key_release, add="+")
        self.text.bind("<ButtonRelease-1>", self._refresh_cursor, add="+")
        self.text.bind("<Button-1>", self._ensure_text_focus, add="+")
        self.text.bind("<<Paste>>", self._on_key_release, add="+")
        self.text.bind("<<Cut>>", self._on_key_release, add="+")
        self.text.bind("<FocusIn>", self._refresh_cursor, add="+")
        self.text.bind("<Configure>", self._schedule_gutter, add="+")
        self.text.bind("<Tab>", self._insert_indent)
        self.text.bind("<Control-s>", self.on_save)
        self.text.bind("<Control-Shift-z>", self._redo)
        self.text.bind("<Control-y>", self._redo)
        self.gutter.bind("<Button-1>", self._gutter_click)

    def _tool_button(self, parent, text, command):
        return ctk.CTkButton(parent, text=text, command=command, width=48, height=25,
                             fg_color="transparent", hover_color="#EAECF0",
                             text_color="#475467", corner_radius=5,
                             font=ctk.CTkFont(size=9))

    def _configure_syntax_tags(self):
        self.text.tag_configure("current_line", background=self.COLORS["active_line"])
        for name in ("html_tag", "css_selector"):
            self.text.tag_configure(name, foreground=self.COLORS["tag"])
        self.text.tag_configure("html_attribute", foreground=self.COLORS["attribute"])
        self.text.tag_configure("code_string", foreground=self.COLORS["string"])
        self.text.tag_configure("code_comment", foreground=self.COLORS["comment"])
        self.text.tag_configure("css_property", foreground=self.COLORS["property"])
        self.text.tag_configure("css_value", foreground=self.COLORS["value"])
        self.text.tag_configure("code_variable", foreground=self.COLORS["variable"])
        self.text.tag_configure("html_bracket", foreground=self.COLORS["bracket"])

    def get(self, start, end=None):
        return self.text.get(start, end)

    def insert(self, index, value):
        self.text.insert(index, value)
        self.schedule_highlight()

    def delete(self, start, end=None):
        self.text.delete(start, end)
        self.schedule_highlight()

    def focus_set(self):
        self.text.focus_set()

    def _insert_indent(self, _event=None):
        self.text.insert(tk.INSERT, "    ")
        self.on_change()
        self.schedule_highlight()
        return "break"

    def _undo(self):
        try:
            self.text.edit_undo()
        except tk.TclError:
            pass
        self.on_change()
        self.schedule_highlight()

    def _redo(self, _event=None):
        try:
            self.text.edit_redo()
        except tk.TclError:
            pass
        self.on_change()
        self.schedule_highlight()
        return "break"

    def _on_key_release(self, _event=None):
        self.on_change()
        self.schedule_highlight()

    def _refresh_cursor(self, _event=None):
        self._highlight_current_line()
        self._schedule_gutter()

    def _on_yview(self, first, last):
        self.vscroll.set(first, last)
        self._schedule_gutter()

    def _schedule_gutter(self, _event=None):
        if self._redraw_after:
            try:
                self.after_cancel(self._redraw_after)
            except tk.TclError:
                pass
        self._redraw_after = self.after_idle(self._draw_gutter)

    def _draw_gutter(self):
        self._redraw_after = None
        if not self.winfo_exists():
            return
        try:
            current = int(self.text.index("insert").split(".", 1)[0])
            line_count = int(self.text.index("end-1c").split(".", 1)[0])
            first, _last = self.text.yview()
            self.gutter.configure(state="normal")
            self.gutter.delete("1.0", "end")
            self.gutter.insert("1.0", "\n".join(str(number) for number in range(1, line_count + 1)))
            self.gutter.tag_remove("active_number", "1.0", "end")
            self.gutter.tag_add("active_number", f"{current}.0", f"{current}.end +1c")
            self.gutter.configure(state="disabled")
            self.gutter.yview_moveto(first)
        except tk.TclError:
            return

    def _highlight_current_line(self):
        self.text.tag_remove("current_line", "1.0", "end")
        line = self.text.index("insert").split(".", 1)[0]
        self.text.tag_add("current_line", f"{line}.0", f"{line}.end +1c")
        self.text.tag_lower("current_line")
        self._schedule_gutter()

    def _gutter_click(self, event):
        line = self.gutter.index(f"@0,{event.y}").split(".", 1)[0]
        self.text.mark_set("insert", f"{line}.0")
        self.text.focus_set()
        self._refresh_cursor()

    def _ensure_text_focus(self, _event=None):
        if self.text.cget("state") != "normal":
            self.text.configure(state="normal")
        self.text.focus_set()

    def schedule_highlight(self):
        if self._highlight_after:
            try:
                self.after_cancel(self._highlight_after)
            except tk.TclError:
                pass
        self._highlight_after = self.after(75, self._highlight_syntax)
        self._highlight_current_line()

    def dispose(self):
        for attr in ("_highlight_after", "_redraw_after"):
            callback_id = getattr(self, attr)
            if callback_id:
                try:
                    self.after_cancel(callback_id)
                except tk.TclError:
                    pass
                setattr(self, attr, None)

    def _highlight_syntax(self):
        self._highlight_after = None
        source = self.text.get("1.0", "end-1c")
        names = ("html_tag", "html_attribute", "code_string", "code_comment", "css_selector",
                 "css_property", "css_value", "code_variable", "html_bracket")
        for name in names:
            self.text.tag_remove(name, "1.0", "end")

        def color(tag, start, end):
            if end > start:
                self.text.tag_add(tag, f"1.0 + {start} chars", f"1.0 + {end} chars")

        for match in re.finditer(r"<!--.*?-->|<![^>]*>|</?\s*[A-Za-z][\w:-]*|</?>", source, re.DOTALL):
            token = match.group(0)
            if token.startswith("<!--"):
                color("code_comment", match.start(), match.end())
                continue
            name = re.search(r"[A-Za-z][\w:-]*", token)
            if name:
                color("html_tag", match.start() + name.start(), match.start() + name.end())
            for bracket in re.finditer(r"[<>]", token):
                color("html_bracket", match.start() + bracket.start(), match.start() + bracket.end())
        for match in re.finditer(r"\b[\w:-]+(?=\s*=)", source):
            color("html_attribute", match.start(), match.end())
        for match in re.finditer(r"(?:\"[^\"]*\"|'[^']*')", source):
            color("code_string", match.start(), match.end())
        for match in re.finditer(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}", source):
            color("code_variable", match.start(), match.end())

        for style in re.finditer(r"<\s*style\b[^>]*>(.*?)<\s*/\s*style\s*>", source,
                                 re.IGNORECASE | re.DOTALL):
            css = style.group(1)
            offset = style.start(1)
            for match in re.finditer(r"/\*.*?\*/", css, re.DOTALL):
                color("code_comment", offset + match.start(), offset + match.end())
            for match in re.finditer(r"([^{};]+)(?=\s*\{)", css):
                selector = match.group(1).strip()
                start = match.start(1) + len(match.group(1)) - len(match.group(1).lstrip())
                color("css_selector", offset + start, offset + start + len(selector))
            for match in re.finditer(r"([\w-]+)(\s*:)([^;{}]+)", css):
                color("css_property", offset + match.start(1), offset + match.end(1))
                value_start = match.start(3) + len(match.group(3)) - len(match.group(3).lstrip())
                color("css_value", offset + value_start, offset + match.end(3))
        self._highlight_current_line()


def _css_rules(content: str) -> dict[str, dict[str, str]]:
    rules: dict[str, dict[str, str]] = {}
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    for selectors, declarations in re.findall(r"([^{}]+)\{([^{}]*)\}", content):
        styles = {}
        for declaration in declarations.split(";"):
            if ":" not in declaration:
                continue
            key, value = declaration.split(":", 1)
            key, value = key.strip().lower(), value.strip()
            value = re.sub(r"\s*!important\s*$", "", value, flags=re.IGNORECASE).strip()
            if key == "background":
                color = re.search(r"#[0-9a-f]{3,8}\b|\b(?:white|black|transparent|[a-z]{3,20})\b",
                                  value, re.IGNORECASE)
                if color:
                    styles["background-color"] = color.group(0)
            if key in {"padding-top", "padding-right", "padding-bottom", "padding-left",
                       "margin-top", "margin-right", "margin-bottom", "margin-left"}:
                base, edge = key.split("-", 1)
                values = styles.get(base, "0 0 0 0").split()
                while len(values) < 4:
                    values.append(values[-1] if values else "0")
                values[{"top": 0, "right": 1, "bottom": 2, "left": 3}[edge]] = value
                styles[base] = " ".join(values)
            if key in {"color", "background-color", "font-size", "font-weight", "font-style",
                       "font-family", "text-align", "padding", "margin", "line-height",
                       "width", "max-width", "border", "border-color", "border-width",
                       "border-radius", "display"}:
                styles[key] = value
        for selector in selectors.split(","):
            rules[selector.strip().lower()] = styles
    return rules


class _PreviewNode:
    def __init__(self, tag="root", attrs=None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children = []


class _PreviewDOMParser(HTMLParser):
    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
                 "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _PreviewNode()
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "iframe", "object", "embed", "style"}:
            return
        node = _PreviewNode(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in self.VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in self.VOID_TAGS and len(self.stack) > 1:
            self.stack.pop()

    def handle_endtag(self, tag):
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if data:
            self.stack[-1].children.append(data)


class EmailPreviewRenderer:
    """Render the common email HTML/CSS box model with native Tk widgets."""

    BLOCK_TAGS = BLOCK_TAGS | {"body", "center", "td", "th", "tr", "pre", "figure", "blockquote"}
    INHERITED = {"color", "font-family", "font-size", "font-weight", "font-style",
                 "text-align", "line-height"}
    SKIP_TAGS = {"html", "head", "title", "meta", "link", "style", "script", "iframe", "object", "embed"}
    DEFAULTS = {"color": "#344054", "font-family": "Arial", "font-size": "11pt",
                "font-weight": "normal", "font-style": "normal", "text-align": "left"}

    def __init__(self, parent, content: str, css_rules: dict[str, dict[str, str]]):
        self.parent = parent
        self.css_rules = css_rules
        self.parser = _PreviewDOMParser()
        self.parser.feed(content)
        self.parser.close()
        self.body_background = "#F8FAFC"
        self._render()

    def _render(self):
        for child in self.parent.winfo_children():
            child.destroy()
        root = ctk.CTkFrame(self.parent, fg_color=self.body_background, corner_radius=0)
        root.pack(fill="x", expand=True, padx=8, pady=8)
        self.root_frame = root
        self._render_children(root, self.parser.root, self.DEFAULTS.copy(), [], self.body_background)
        root.configure(fg_color=self.body_background)
        self.parent.configure(fg_color=self.body_background)

    def _matches_simple(self, selector: str, node: _PreviewNode) -> bool:
        selector = selector.strip().lower()
        if not selector or any(char in selector for char in ":[]>+~"):
            return False
        tag_match = re.match(r"^[a-z][\w-]*", selector)
        if tag_match and tag_match.group(0) != node.tag:
            return False
        if not tag_match and not selector.startswith((".", "#")):
            return False
        classes = node.attrs.get("class", "").lower().split()
        if any(name not in classes for name in re.findall(r"\.([\w-]+)", selector)):
            return False
        id_match = re.search(r"#([\w-]+)", selector)
        return not id_match or id_match.group(1) == node.attrs.get("id", "").lower()

    def _matches_selector(self, selector: str, ancestry: list[_PreviewNode]) -> bool:
        parts = selector.split()
        if not parts or not self._matches_simple(parts[-1], ancestry[-1]):
            return False
        candidates = ancestry[:-1]
        for part in reversed(parts[:-1]):
            for index in range(len(candidates) - 1, -1, -1):
                if self._matches_simple(part, candidates[index]):
                    candidates = candidates[:index]
                    break
            else:
                return False
        return True

    def _styles(self, node, inherited, ancestry):
        styles = {key: value for key, value in inherited.items() if key in self.INHERITED}
        chain = [*ancestry, node]
        for selector, declarations in self.css_rules.items():
            if self._matches_selector(selector, chain):
                styles.update(declarations)
        inline = _css_rules(f"x {{{node.attrs.get('style', '')}}}").get("x", {})
        styles.update(inline)
        if "background" in inline and "background-color" not in inline:
            styles["background-color"] = inline["background"]
        if node.tag in {"b", "strong"}:
            styles["font-weight"] = "bold"
        if node.tag in {"i", "em"}:
            styles["font-style"] = "italic"
        if re.fullmatch(r"h[1-6]", node.tag):
            has_explicit_size = any(
                "font-size" in declarations and self._matches_selector(selector, chain)
                for selector, declarations in self.css_rules.items()
            ) or "font-size" in inline
            if not has_explicit_size:
                styles["font-size"] = f"{28 - int(node.tag[1]) * 3}px"
            if styles.get("font-weight") in {None, "", "normal"}:
                styles["font-weight"] = "bold"
        if node.tag in {"b", "strong"}:
            styles.setdefault("font-weight", "bold")
        return styles

    def _color(self, value, fallback):
        if not value:
            return fallback
        rgb = re.fullmatch(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})(?:\s*,\s*[\d.]+)?\s*\)", value, re.IGNORECASE)
        if rgb:
            value = "#" + "".join(f"{max(0, min(255, int(channel))):02X}" for channel in rgb.groups())
        try:
            self.parent.winfo_rgb(value)
            return value
        except tk.TclError:
            return fallback

    @staticmethod
    def _length(value, fallback=0):
        match = re.search(r"(-?\d+(?:\.\d+)?)\s*(px|pt)?", value or "", re.IGNORECASE)
        if not match:
            return fallback
        result = float(match.group(1)) * (4 / 3 if match.group(2) and match.group(2).lower() == "pt" else 1)
        return max(0, min(80, round(result)))

    def _box(self, value):
        parts = value.split()
        sizes = [self._length(part) for part in parts[:4]]
        if not sizes:
            return (0, 0, 0, 0)
        if len(sizes) == 1:
            top = right = bottom = left = sizes[0]
        elif len(sizes) == 2:
            top = bottom = sizes[0]
            right = left = sizes[1]
        elif len(sizes) == 3:
            top, right, bottom = sizes
            left = right
        else:
            top, right, bottom, left = sizes
        return top, right, bottom, left

    def _font(self, styles, node):
        family = styles.get("font-family", "Arial").split(",", 1)[0].strip(" \'\"`")
        if not re.fullmatch(r"[\w -]{1,40}", family):
            family = "Arial"
        size = self._length(styles.get("font-size", "11pt"), 11)
        size = max(8, min(34, round(size * 0.75)))
        if re.fullmatch(r"h[1-6]", node.tag):
            size = max(size, 22 - int(node.tag[1]) * 2)
        weight = styles.get("font-weight", "").lower()
        style = styles.get("font-style", "").lower()
        flags = []
        if weight in {"bold", "600", "700", "800", "900"}:
            flags.append("bold")
        if style == "italic":
            flags.append("italic")
        return (family, size, *flags)

    def _inline_runs(self, node, inherited, ancestry):
        runs = []
        for child in node.children:
            if isinstance(child, str):
                if child:
                    runs.append((child, inherited))
                continue
            if child.tag in self.BLOCK_TAGS:
                continue
            if child.tag == "br":
                runs.append(("\n", inherited))
                continue
            if child.tag == "img":
                alt = child.attrs.get("alt", "")
                if alt:
                    runs.append((f"[{alt}]", inherited))
                continue
            styles = self._styles(child, inherited, ancestry + [node])
            runs.extend(self._inline_runs(child, styles, ancestry + [node, child]))
        return runs

    def _append_rich_text(self, parent, runs, styles, background):
        text = "".join(value for value, _style in runs)
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        if not text.strip():
            return
        fg = self._color(styles.get("color"), "#344054")
        widget = tk.Text(parent, wrap="word", height=1, bd=0, relief="flat",
                         highlightthickness=0, padx=0, pady=0, takefocus=False,
                         bg=background, fg=fg, font=self._font(styles, _PreviewNode("p")),
                         spacing1=0, spacing2=0, spacing3=0)
        widget.pack(fill="x", expand=True)
        tag_cache = {}
        for value, run_styles in runs:
            if not value:
                continue
            font = self._font(run_styles, _PreviewNode("span"))
            color = self._color(run_styles.get("color"), fg)
            key = (font, color, run_styles.get("text-decoration", ""))
            tag = tag_cache.get(key)
            if tag is None:
                tag = f"run_{len(tag_cache)}"
                tag_cache[key] = tag
                options = {"font": font, "foreground": color}
                if "underline" in key[2]:
                    options["underline"] = True
                widget.tag_configure(tag, **options)
            widget.insert("end", value, (tag,))
        widget.configure(state="disabled")
        widget.bind("<Configure>", lambda _event, target=widget: self._fit_text(target), add="+")
        widget.after_idle(lambda target=widget: self._fit_text(target))

    @staticmethod
    def _fit_text(widget):
        try:
            lines = widget.count("1.0", "end-1c", "displaylines")
            if lines and lines[0] > 0:
                widget.configure(height=lines[0])
        except (tk.TclError, TypeError):
            pass

    def _render_children(self, parent, node, styles, ancestry, background, *, side="top"):
        runs = []
        for child in node.children:
            if isinstance(child, str):
                if child:
                    runs.append((child, styles))
                continue
            if child.tag == "html":
                self._render_children(parent, child, styles, ancestry + [node], background, side=side)
                continue
            if child.tag in self.SKIP_TAGS:
                continue
            if child.tag in self.BLOCK_TAGS:
                self._append_rich_text(parent, runs, styles, background)
                runs.clear()
                self._render_node(parent, child, styles, ancestry + [node], background,
                                  side="left" if node.tag == "tr" else "top")
            else:
                child_styles = self._styles(child, styles, ancestry + [node])
                runs.extend(self._inline_runs(child, child_styles, ancestry + [node, child]))
        self._append_rich_text(parent, runs, styles, background)

    def _render_node(self, parent, node, inherited, ancestry, parent_bg, *, side="top"):
        if node.tag in self.SKIP_TAGS or node.tag in {"html"}:
            self._render_children(parent, node, inherited, ancestry + [node], parent_bg, side=side)
            return
        styles = self._styles(node, inherited, ancestry)
        if styles.get("display", "").lower() == "none":
            return
        if node.tag == "body":
            self.body_background = self._color(styles.get("background-color"), parent_bg)
            parent.configure(fg_color=self.body_background)
            self._render_children(parent, node, styles, ancestry + [node], self.body_background)
            return
        if node.tag == "img":
            alt = node.attrs.get("alt", "Image")
            ctk.CTkLabel(parent, text=f"[{alt}]", anchor="w", text_color=self._color(styles.get("color"), "#667085"),
                         font=ctk.CTkFont(size=10), fg_color="transparent").pack(anchor="w", pady=4)
            return

        bg = self._color(styles.get("background-color"), parent_bg)
        has_background = "background-color" in styles
        border = styles.get("border", "")
        border_match = re.match(r"(?:\d+(?:\.\d+)?px\s+)?(?:solid|dashed|dotted)?\s*(#[0-9a-f]{3,8}|[a-z]+)?",
                                border, re.IGNORECASE)
        border_color = self._color(styles.get("border-color") or (border_match.group(1) if border_match else None), "#E4E7EC")
        border_width = self._length(styles.get("border-width", ""))
        if border and border_width == 0:
            width_match = re.match(r"\s*(\d+(?:\.\d+)?)px", border)
            border_width = self._length(width_match.group(0)) if width_match else 1
        radius = self._length(styles.get("border-radius", ""))
        top, right, bottom, left = self._box(styles.get("margin", ""))
        padding_top, padding_right, padding_bottom, padding_left = self._box(styles.get("padding", ""))
        if node.tag in {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li"}:
            bottom = max(bottom, 5 if node.tag == "p" else 7)
        frame = ctk.CTkFrame(parent, fg_color=bg if has_background else "transparent",
                             corner_radius=min(radius, 18), border_width=min(border_width, 3),
                             border_color=border_color)
        pack_options = {"side": side, "fill": "both" if side == "left" else "x",
                        "expand": side == "left", "padx": (left, right), "pady": (top, bottom)}
        frame.pack(**pack_options)
        inner = ctk.CTkFrame(frame, fg_color="transparent", corner_radius=0)
        inner.pack(fill="both" if side == "left" else "x", expand=side == "left",
                   padx=(padding_left, padding_right), pady=(padding_top, padding_bottom))
        if node.tag in {"ul", "ol"}:
            for index, child in enumerate(node.children):
                if isinstance(child, _PreviewNode) and child.tag == "li":
                    if node.tag == "ol":
                        child.attrs = {**child.attrs, "data-preview-marker": f"{index + 1}."}
                    self._render_node(inner, child, styles, ancestry + [node], bg)
                elif isinstance(child, str) and child.strip():
                    self._append_rich_text(inner, [(child, styles)], styles, bg)
            return
        if node.tag == "li":
            marker = node.attrs.get("data-preview-marker", "•")
            marker_label = ctk.CTkLabel(inner, text=marker, width=24, anchor="w",
                                        text_color=self._color(styles.get("color"), "#344054"),
                                        font=ctk.CTkFont(size=11))
            marker_label.pack(side="left", anchor="n")
            content = ctk.CTkFrame(inner, fg_color="transparent")
            content.pack(side="left", fill="x", expand=True)
            self._render_children(content, node, styles, ancestry + [node], bg)
            return
        self._render_children(inner, node, styles, ancestry + [node], bg)


class _EmailTextParser(HTMLParser):
    """Render readable HTML and basic CSS in a Tk Text widget; never execute code."""

    def __init__(self, widget: tk.Text, rules: dict[str, dict[str, str]]):
        super().__init__(convert_charrefs=True)
        self.widget = widget
        self.rules = rules
        self.stack: list[tuple[str, dict[str, str], list[str]]] = []
        self.tag_counter = 0
        self.last_was_break = True
        widget.tag_configure("body", font=("Arial", 11), foreground="#344054", spacing1=2, spacing3=2)
        widget.tag_configure("bold", font=("Arial", 11, "bold"))
        widget.tag_configure("italic", font=("Arial", 11, "italic"))
        widget.tag_configure("link", foreground="#175CD3", underline=True)
        for level, size in ((1, 22), (2, 18), (3, 15), (4, 13)):
            widget.tag_configure(f"heading{level}", font=("Arial", size, "bold"),
                                 foreground="#17212F", spacing1=8, spacing3=6)

    def _style_for(self, tag: str, attrs: dict[str, str]) -> list[str]:
        styles: dict[str, str] = {}
        for selector, declarations in self.rules.items():
            if self._selector_matches(selector, tag, attrs):
                styles.update(declarations)
        styles.update(dict(
            (key.strip().lower(), re.sub(r"\s*!important\s*$", "", value.strip(), flags=re.IGNORECASE))
            for key, value in re.findall(r"([\w-]+)\s*:\s*([^;]+)", attrs.get("style", ""))
        ))
        if "background" in styles and "background-color" not in styles:
            background_match = re.search(
                r"#[0-9a-f]{3,8}\b|\b(?:white|black|transparent|[a-z]{3,20})\b",
                styles["background"], re.IGNORECASE,
            )
            if background_match:
                styles["background-color"] = background_match.group(0)
        if tag in {"b", "strong"}:
            styles["font-weight"] = "bold"
        if tag in {"i", "em"}:
            styles["font-style"] = "italic"
        tag_names = []
        self.tag_counter += 1
        tag_name = f"email_style_{self.tag_counter}"
        options = {}
        color = styles.get("color", "")
        background = styles.get("background-color", "")
        valid_color = re.compile(r"^(#[0-9a-f]{3,8}|[a-z]{3,20})$", re.IGNORECASE)
        if self._valid_color(color, valid_color):
            options["foreground"] = color
        if self._valid_color(background, valid_color):
            options["background"] = background
        size = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(px|pt)?", styles.get("font-size", ""), re.IGNORECASE)
        font_size = 11
        if size:
            points = float(size.group(1)) * (0.75 if size.group(2) == "px" else 1)
            font_size = max(8, min(34, round(points)))
        font_family = styles.get("font-family", "Arial").split(",", 1)[0].strip(" \'\"`")
        if not re.fullmatch(r"[\w -]{1,40}", font_family):
            font_family = "Arial"
        font_flags = []
        if styles.get("font-weight", "").lower() in {"bold", "600", "700", "800", "900"}:
            font_flags.append("bold")
        if styles.get("font-style", "").lower() == "italic":
            font_flags.append("italic")
        if "font-size" in styles or "font-family" in styles or font_flags:
            options["font"] = (font_family, font_size, *font_flags)
        if styles.get("text-align", "").lower() in {"left", "center", "right"}:
            options["justify"] = styles["text-align"].lower()
        for box_property in ("padding", "margin"):
            dimensions = re.findall(r"(\d+(?:\.\d+)?)\s*(px|pt)?", styles.get(box_property, ""), re.IGNORECASE)
            if not dimensions:
                continue
            values = [max(0, min(48, round(float(amount) * (4 / 3 if unit.lower() == "pt" else 1))))
                      for amount, unit in dimensions[:4]]
            if len(values) == 1:
                top = right = bottom = left = values[0]
            elif len(values) == 2:
                top = bottom = values[0]
                right = left = values[1]
            elif len(values) == 3:
                top, right, bottom = values
                left = right
            else:
                top, right, bottom, left = values
            options["lmargin1"] = options["lmargin2"] = options.get("lmargin1", 0) + left
            options["rmargin"] = options.get("rmargin", 0) + right
            options["spacing1"] = options.get("spacing1", 0) + top
            options["spacing3"] = options.get("spacing3", 0) + bottom
        if options:
            self.widget.tag_configure(tag_name, **options)
            tag_names.append(tag_name)
        if tag in {"b", "strong"}:
            tag_names.append("bold")
        if tag in {"i", "em"}:
            tag_names.append("italic")
        if tag == "a":
            tag_names.append("link")
        heading = re.fullmatch(r"h([1-4])", tag)
        if heading:
            tag_names.append(f"heading{heading.group(1)}")
        return tag_names

    def _selector_matches(self, selector: str, tag: str, attrs: dict[str, str]) -> bool:
        parts = selector.split()
        if not parts or not self._simple_selector_matches(parts[-1], tag, attrs):
            return False
        ancestors = self.stack[:]
        for part in reversed(parts[:-1]):
            while ancestors:
                ancestor_tag, ancestor_attrs, _ancestor_styles = ancestors.pop()
                if self._simple_selector_matches(part, ancestor_tag, ancestor_attrs):
                    break
            else:
                return False
        return True

    @staticmethod
    def _simple_selector_matches(selector: str, tag: str, attrs: dict[str, str]) -> bool:
        selector = selector.strip().lower()
        if not selector or any(char in selector for char in ":[]>+~"):
            return False
        tag_match = re.match(r"^[a-z][\w-]*", selector)
        if tag_match and tag_match.group(0) != tag:
            return False
        if not tag_match and not selector.startswith((".", "#")):
            return False
        if any(name not in attrs.get("class", "").lower().split()
               for name in re.findall(r"\.([\w-]+)", selector)):
            return False
        id_match = re.search(r"#([\w-]+)", selector)
        return not id_match or id_match.group(1) == attrs.get("id", "").lower()

    def _valid_color(self, value: str, pattern: re.Pattern) -> bool:
        if not pattern.fullmatch(value):
            return False
        try:
            self.widget.winfo_rgb(value)
            return True
        except tk.TclError:
            return False

    def _break(self, count: int = 1) -> None:
        active = [name for _tag, _attrs, names in self.stack for name in names]
        for index in range(count):
            if not self.last_was_break or index > 0:
                self.widget.insert("end", "\n", tuple(["body", *active]))
                self.last_was_break = True

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in {"script", "iframe", "object", "embed", "style", "head", "meta", "link", "title"}:
            return
        if tag in BLOCK_TAGS:
            self._break(2 if tag.startswith("h") else 1)
        if tag == "br":
            self._break()
            return
        if tag == "img":
            alt = dict(attrs).get("alt", "")
            if alt:
                self.handle_data(f"[{alt}]")
            return
        if tag in {"hr"}:
            self._break()
            self.widget.insert("end", "────────────────────────\n", ("body",))
            self.last_was_break = True
            return
        tags = self._style_for(tag, dict(attrs))
        self.stack.append((tag, dict(attrs), tags))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in BLOCK_TAGS:
            self._break()
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        text = re.sub(r"\s+", " ", data)
        if not text or text.isspace():
            return
        active = [name for _tag, _attrs, names in self.stack for name in names]
        self.widget.insert("end", text, tuple(["body", *active]))
        self.last_was_break = False


class EmailTemplatePage:
    def __init__(self, app):
        self.app = app
        self.colors = {
            "surface": "#FFFFFF", "canvas": "#F4F6F8", "surface_alt": "#F8FAFC",
            "line": "#E5E9EF", "line_strong": "#D5DCE5", "text": "#17212F",
            "muted": "#667384", "accent": "#E94F2E", "accent_soft": "#FFF2ED",
        }
        self.repository = EmailTemplateRepository(app.db)
        self.records: list[dict] = []
        self.selected_id: str | None = None
        self.base_values = {"name": "", "subject": "", "html": ""}
        self._loading = False
        self._preview_after = None
        self._preview_document = ""
        self._preview_subject_text = "Subject email"
        self._expanded_window = None
        self._expanded_preview = None
        self._expanded_subject = None
        self.frame = ctk.CTkFrame(app.shell, fg_color="transparent", corner_radius=0)
        self.frame.pack(fill="both", expand=True)
        self._build()
        self.reload()

    def _build(self) -> None:
        top = ctk.CTkFrame(self.frame, fg_color="transparent")
        top.pack(fill="x", pady=(3, 13))
        title_group = ctk.CTkFrame(top, fg_color="transparent")
        title_group.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(title_group, text="EMAIL TEMPLATE", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=self.colors["accent"]).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(title_group, text="Email Template", font=ctk.CTkFont(family="Segoe UI", size=25, weight="bold"),
                     text_color=self.colors["text"]).pack(anchor="w")
        ctk.CTkLabel(title_group, text="Tạo và quản lý các mẫu email dùng trong hệ thống.",
                     font=ctk.CTkFont(size=12), text_color=self.colors["muted"]).pack(anchor="w", pady=(3, 0))
        top_actions = ctk.CTkFrame(top, fg_color="transparent")
        top_actions.pack(side="right", anchor="s")
        self.app._secondary(top_actions, "+  Template mới", self.new_template,
                            width=132, height=38).pack(side="left", padx=(0, 8))
        self.app._secondary(top_actions, "Hoàn tác", self.cancel_changes,
                            width=92, height=38).pack(side="left", padx=(0, 8))
        self.app._primary(top_actions, "Lưu template", self.save_template,
                          width=136, height=38).pack(side="left")

        content = ctk.CTkFrame(self.frame, fg_color="transparent")
        content.pack(fill="both", expand=True)
        self.sidebar = ctk.CTkFrame(content, width=245, fg_color=self.colors["surface"],
                                    corner_radius=10, border_width=1, border_color=self.colors["line"])
        self.sidebar.pack(side="left", fill="y", padx=(0, 12))
        self.sidebar.pack_propagate(False)
        ctk.CTkLabel(self.sidebar, text="TEMPLATE ĐÃ LƯU", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=self.colors["muted"]).pack(anchor="w", padx=14, pady=(14, 8))
        self.search = ctk.CTkEntry(self.sidebar, height=36, placeholder_text="Tìm template...",
                                   border_color=self.colors["line_strong"], corner_radius=8,
                                   font=ctk.CTkFont(size=11))
        self.search.pack(fill="x", padx=12, pady=(0, 10))
        self.search.bind("<KeyRelease>", lambda _event: self._render_list())
        self.list_frame = ctk.CTkScrollableFrame(self.sidebar, fg_color="transparent",
                                                 scrollbar_button_color="#D0D5DD")
        self.list_frame.pack(fill="both", expand=True, padx=5, pady=(0, 8))
        self.sidebar_actions = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.sidebar_actions.pack(fill="x", padx=10, pady=(0, 11))
        self.rename_button = self.app._secondary(self.sidebar_actions, "Đổi tên", self.rename_template,
                                                  width=68, height=30, font=ctk.CTkFont(size=10))
        self.rename_button.pack(side="left", expand=True, fill="x", padx=(0, 4))
        self.duplicate_button = self.app._secondary(self.sidebar_actions, "Nhân bản", self.duplicate_template,
                                                     width=68, height=30, font=ctk.CTkFont(size=10))
        self.duplicate_button.pack(side="left", expand=True, fill="x", padx=4)
        self.delete_button = ctk.CTkButton(self.sidebar_actions, text="Xóa", command=self.delete_template,
                                           width=48, height=30, fg_color=self.colors["surface"],
                                           hover_color="#FEE4E2", text_color="#B42318",
                                           border_width=1, border_color=self.colors["line"],
                                           corner_radius=7, font=ctk.CTkFont(size=10))
        self.delete_button.pack(side="left", padx=(4, 0))

        self.editor_panel = ctk.CTkFrame(content, fg_color=self.colors["surface"], corner_radius=10,
                                         border_width=1, border_color=self.colors["line"])
        self.editor_panel.pack(side="left", fill="both", expand=True)
        self._build_editor()

    def _build_editor(self) -> None:
        form = ctk.CTkFrame(self.editor_panel, fg_color="transparent")
        form.pack(fill="x", padx=16, pady=(14, 8))
        ctk.CTkLabel(form, text="TÊN TEMPLATE", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=self.colors["muted"]).pack(anchor="w", pady=(0, 5))
        self.name_entry = ctk.CTkEntry(form, height=36, placeholder_text="Ví dụ: Báo cáo reconciliation",
                                       border_color=self.colors["line_strong"], corner_radius=8)
        self.name_entry.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(form, text="SUBJECT EMAIL", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=self.colors["muted"]).pack(anchor="w", pady=(0, 5))
        self.subject_entry = ctk.CTkEntry(form, height=36,
                                          placeholder_text="Báo cáo ngày {report_date}",
                                          border_color=self.colors["line_strong"], corner_radius=8)
        self.subject_entry.pack(fill="x")
        self.name_entry.bind("<KeyRelease>", self._on_form_change)
        self.subject_entry.bind("<KeyRelease>", self._on_form_change)
        self.name_entry.bind("<Control-s>", self._save_shortcut)
        self.subject_entry.bind("<Control-s>", self._save_shortcut)

        variable_row = ctk.CTkFrame(self.editor_panel, fg_color="transparent")
        variable_row.pack(fill="x", padx=16, pady=(0, 9))
        ctk.CTkLabel(variable_row, text="Biến có sẵn", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=self.colors["text"]).pack(side="left", padx=(0, 8))
        for variable in VARIABLES:
            chip_width = max(52, int(len(variable) * 7.2 + 18))
            ctk.CTkButton(variable_row, text="{" + variable + "}", width=chip_width, height=26,
                          fg_color="#F2F4F7", hover_color="#E9EDF2", text_color="#475467",
                          corner_radius=6, font=ctk.CTkFont(family="Consolas", size=10),
                          command=lambda item=variable: self.insert_variable(item)).pack(side="left", padx=3)

        panes = ctk.CTkFrame(self.editor_panel, fg_color="transparent")
        panes.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        panes.grid_columnconfigure(0, weight=52, uniform="email_pane")
        panes.grid_columnconfigure(1, weight=48, uniform="email_pane")
        panes.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(panes, text="HTML / CSS", anchor="w", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=self.colors["text"]).grid(row=0, column=0, sticky="ew", padx=(2, 7), pady=(0, 6))
        preview_heading = ctk.CTkFrame(panes, fg_color="transparent")
        preview_heading.grid(row=0, column=1, sticky="ew", padx=(7, 2), pady=(0, 6))
        ctk.CTkLabel(preview_heading, text="LIVE PREVIEW", anchor="w",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=self.colors["text"]).pack(side="left")
        ctk.CTkButton(
            preview_heading, text="↗  Mở rộng", command=self._open_expanded_preview,
            width=92, height=27, corner_radius=7, border_width=1,
            border_color=self.colors["line_strong"], fg_color=self.colors["surface"],
            hover_color=self.colors["surface_alt"], text_color=self.colors["text"],
            font=ctk.CTkFont(size=10, weight="bold"),
        ).pack(side="right")
        edit_wrap = ctk.CTkFrame(panes, fg_color=CodeEditor.COLORS["background"], corner_radius=8,
                                 border_width=1, border_color=CodeEditor.COLORS["border"])
        edit_wrap.grid(row=1, column=0, sticky="nsew", padx=(0, 7))
        self.editor = CodeEditor(edit_wrap, on_change=self._on_editor_change,
                                 on_save=self._save_shortcut)
        self.editor.pack(fill="both", expand=True, padx=1, pady=1)
        preview_wrap = ctk.CTkFrame(panes, fg_color=self.colors["surface_alt"], corner_radius=8,
                                    border_width=1, border_color=self.colors["line"])
        preview_wrap.grid(row=1, column=1, sticky="nsew", padx=(7, 0))
        self.preview_subject = ctk.CTkLabel(preview_wrap, text="Subject email", anchor="w", justify="left",
                                            wraplength=300, font=ctk.CTkFont(size=11, weight="bold"),
                                            text_color=self.colors["text"])
        self.preview_subject.pack(fill="x", padx=12, pady=(10, 7))
        preview_body = ctk.CTkFrame(preview_wrap, fg_color=self.colors["surface"], corner_radius=7,
                                    border_width=1, border_color=self.colors["line"])
        preview_body.pack(fill="both", expand=True, padx=9, pady=(0, 9))
        self.preview_render_area = EmailBrowserPreview(preview_body)
        self.preview_render_area.pack(fill="both", expand=True, padx=1, pady=1)

        footer = ctk.CTkFrame(self.editor_panel, fg_color="transparent")
        footer.pack(fill="x", padx=16, pady=(0, 13))
        self.save_state = ctk.CTkLabel(footer, text="", font=ctk.CTkFont(size=11),
                                       text_color=self.colors["muted"])
        self.save_state.pack(side="left")

    def reload(self) -> None:
        self.records = self.repository.get_all()
        self._render_list()
        if self.records:
            self._load_record(self.records[0])
        else:
            self._load_record(None)

    def _render_list(self) -> None:
        for child in self.list_frame.winfo_children():
            child.destroy()
        query = self.search.get().strip().casefold()
        records = [item for item in self.records
                   if query in item["name"].casefold() or query in item["subject"].casefold()]
        if not records:
            text = "Chưa có email template\nTạo template đầu tiên để dùng khi gửi email." if not self.records else "Không tìm thấy template phù hợp."
            ctk.CTkLabel(self.list_frame, text=text, justify="left", wraplength=205,
                         font=ctk.CTkFont(size=11), text_color=self.colors["muted"]).pack(anchor="w", padx=9, pady=14)
        for item in records:
            selected = item["id"] == self.selected_id
            card = ctk.CTkFrame(
                self.list_frame,
                fg_color="#FFF7F4" if selected else self.colors["surface"],
                border_width=1,
                border_color="#F2B5A5" if selected else self.colors["line"],
                corner_radius=9,
            )
            card.pack(fill="x", padx=4, pady=4)
            content = ctk.CTkFrame(card, fg_color="transparent")
            content.pack(fill="x", padx=11, pady=(9, 8))
            name_label = ctk.CTkLabel(
                content, text=item["name"], anchor="w", justify="left", wraplength=180,
                font=ctk.CTkFont(size=11, weight="bold"), text_color=self.colors["text"],
            )
            name_label.pack(fill="x")
            subject_label = ctk.CTkLabel(
                content, text=item["subject"], anchor="w", justify="left", wraplength=180,
                font=ctk.CTkFont(size=10), text_color=self.colors["muted"],
            )
            subject_label.pack(fill="x", pady=(3, 0))
            updated_label = ctk.CTkLabel(
                content, text=f'Cập nhật {item["updated_at"][:10]}', anchor="w",
                font=ctk.CTkFont(size=9), text_color=self.colors["muted"],
            )
            updated_label.pack(fill="x", pady=(7, 0))
            select_item = lambda _event=None, current=item: self.select_template(current)
            for widget in (card, content, name_label, subject_label, updated_label):
                widget.bind("<Button-1>", select_item, add="+")
        state = "normal" if self.selected_id else "disabled"
        for control in (self.rename_button, self.duplicate_button, self.delete_button):
            control.configure(state=state)

    def _values(self) -> dict[str, str]:
        return {"name": self.name_entry.get().strip(), "subject": self.subject_entry.get().strip(),
                "html": self.editor.get("1.0", "end-1c")}

    def _is_dirty(self) -> bool:
        return self._values() != self.base_values

    def _update_dirty_state(self) -> None:
        dirty = self._is_dirty()
        self.save_state.configure(text="● Chưa lưu" if dirty else "Đã lưu",
                                  text_color=self.colors["accent"] if dirty else self.colors["muted"])

    def _load_record(self, item: dict | None) -> None:
        self._loading = True
        self.selected_id = item["id"] if item else None
        values = {"name": item["name"], "subject": item["subject"], "html": item["html_content"]} if item else {
            "name": "", "subject": "", "html": ""}
        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, values["name"])
        self.subject_entry.delete(0, "end")
        self.subject_entry.insert(0, values["subject"])
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", values["html"])
        self.base_values = values.copy()
        self._loading = False
        self._render_list()
        self._update_dirty_state()
        self._schedule_preview()

    def _confirm_discard(self) -> bool:
        if not self._is_dirty():
            return True
        return self.app._dialog(
            "Thay đổi chưa được lưu", "Bạn có thay đổi chưa được lưu. Nếu tiếp tục, các thay đổi này sẽ bị bỏ.",
            parent=self.app, confirm=True, confirm_text="Bỏ thay đổi", kind="warning",
        )

    def select_template(self, item: dict) -> None:
        if item["id"] == self.selected_id:
            return
        if not self._confirm_discard():
            return
        fresh = self.repository.get_by_id(item["id"])
        if fresh:
            self._load_record(fresh)

    def new_template(self) -> None:
        if not self._confirm_discard():
            return
        self._load_record(None)
        self.name_entry.focus_set()

    def _on_form_change(self, _event=None) -> None:
        if self._loading:
            return
        self._update_dirty_state()
        self._schedule_preview()

    def _on_editor_change(self, _event=None) -> None:
        if self._loading:
            return
        self._update_dirty_state()
        self._schedule_preview()

    def _insert_indent(self, _event=None):
        self.editor._textbox.insert(tk.INSERT, "    ")
        self._on_editor_change()
        return "break"

    def insert_variable(self, variable: str) -> None:
        self.editor._textbox.insert(tk.INSERT, "{" + variable + "}")
        self.editor.focus_set()
        self._on_editor_change()
        self.editor.schedule_highlight()

    def _save_shortcut(self, _event=None):
        self.save_template()
        return "break"

    def _schedule_preview(self) -> None:
        if self._preview_after:
            try:
                self.frame.after_cancel(self._preview_after)
            except tk.TclError:
                pass
        self._preview_after = self.frame.after(400, self._render_preview)

    def dispose(self) -> None:
        if self._preview_after:
            try:
                self.frame.after_cancel(self._preview_after)
            except tk.TclError:
                pass
            self._preview_after = None
        self.editor.dispose()
        self._close_expanded_preview()
        self.preview_render_area.dispose()

    def _open_expanded_preview(self) -> None:
        if self._expanded_window is not None:
            try:
                if self._expanded_window.winfo_exists():
                    self._expanded_window.deiconify()
                    self._expanded_window.lift()
                    return
            except tk.TclError:
                pass

        window = ctk.CTkToplevel(self.app)
        self.app._apply_window_icon(window)
        window.title("Xem trước email")
        window.geometry("1180x820")
        window.minsize(760, 540)
        window.configure(fg_color=self.colors["canvas"])
        self._expanded_window = window

        card = ctk.CTkFrame(window, fg_color=self.colors["surface"], corner_radius=12,
                            border_width=1, border_color=self.colors["line"])
        card.pack(fill="both", expand=True, padx=18, pady=18)
        heading = ctk.CTkFrame(card, fg_color="transparent")
        heading.pack(fill="x", padx=18, pady=(14, 10))
        ctk.CTkLabel(heading, text="LIVE PREVIEW", anchor="w",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=self.colors["muted"]).pack(side="left")
        subject = ctk.CTkLabel(card, text=self._preview_subject_text, anchor="w",
                               font=ctk.CTkFont(size=13, weight="bold"),
                               text_color=self.colors["text"])
        subject.pack(fill="x", padx=18, pady=(0, 10))
        preview_frame = ctk.CTkFrame(card, fg_color=self.colors["surface_alt"], corner_radius=9,
                                     border_width=1, border_color=self.colors["line"])
        preview_frame.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self._expanded_subject = subject
        self._expanded_preview = EmailBrowserPreview(preview_frame)
        self._expanded_preview.pack(fill="both", expand=True, padx=1, pady=1)
        window.protocol("WM_DELETE_WINDOW", self._close_expanded_preview)
        window.update_idletasks()
        self._expanded_preview.set_document(self._preview_document)
        window.lift()

    def _close_expanded_preview(self) -> None:
        window = self._expanded_window
        preview = self._expanded_preview
        self._expanded_window = None
        self._expanded_preview = None
        self._expanded_subject = None
        if preview is not None:
            preview.dispose()
        if window is not None:
            try:
                if window.winfo_exists():
                    window.destroy()
            except tk.TclError:
                pass

    def _render_preview(self) -> None:
        self._preview_after = None
        values = self._values()
        resolved_subject = TemplateVariableResolver.resolve(values["subject"] or "Subject email", SAMPLE_VALUES,
                                                            escape_html=False)
        self._preview_subject_text = resolved_subject
        self.preview_subject.configure(text=resolved_subject)
        if self._expanded_subject is not None:
            try:
                self._expanded_subject.configure(text=resolved_subject)
            except tk.TclError:
                pass
        self._preview_document = TemplateVariableResolver.resolve(
            values["html"], SAMPLE_VALUES, escape_html=True
        )
        self.preview_render_area.set_document(self._preview_document)
        if self._expanded_preview is not None:
            self._expanded_preview.set_document(self._preview_document)

    def save_template(self) -> None:
        values = self._values()
        missing = [label for key, label in (("name", "Tên template"), ("subject", "Subject"), ("html", "HTML"))
                   if not values[key].strip()]
        if missing:
            self.app._dialog("Thiếu thông tin", "Vui lòng nhập: " + ", ".join(missing) + ".", kind="warning")
            return
        if self.selected_id:
            self.repository.update(self.selected_id, values["name"], values["subject"], values["html"])
        else:
            self.selected_id = self.repository.create(values["name"], values["subject"], values["html"])
        self.records = self.repository.get_all()
        selected = self.repository.get_by_id(self.selected_id)
        self._load_record(selected)
        self.app._toast("Template đã được lưu thành công.")

    def cancel_changes(self) -> None:
        if self.selected_id:
            record = self.repository.get_by_id(self.selected_id)
            self._load_record(record)
        else:
            self._load_record(None)

    def rename_template(self) -> None:
        self.name_entry.focus_set()
        self.name_entry.select_range(0, "end")

    def duplicate_template(self) -> None:
        record = self.repository.get_by_id(self.selected_id) if self.selected_id else None
        if not record:
            return
        if self._is_dirty() and not self._confirm_discard():
            return
        new_id = self.repository.create(record["name"] + " (bản sao)", record["subject"], record["html_content"])
        self.records = self.repository.get_all()
        self._load_record(self.repository.get_by_id(new_id))
        self.app._toast("Đã tạo bản sao template.")

    def delete_template(self) -> None:
        record = self.repository.get_by_id(self.selected_id) if self.selected_id else None
        if not record:
            return
        if not self.app._dialog("Xóa template?", "Template này sẽ bị xóa khỏi hệ thống.",
                                parent=self.app, confirm=True, confirm_text="Xóa template", kind="warning"):
            return
        self.repository.delete(record["id"])
        self.records = self.repository.get_all()
        next_record = self.records[0] if self.records else None
        self._load_record(next_record)
        self.app._toast("Đã xóa template.")
