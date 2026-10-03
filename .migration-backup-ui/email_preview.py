"""Edge/Chromium-backed HTML email preview for the Tkinter editor."""
from __future__ import annotations

from io import BytesIO
import html
import os
from pathlib import Path
import queue
import shutil
import threading
import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageTk


class EmailBrowserPreview(ctk.CTkFrame):
    """Show full-page browser renders in a scrollable Tk canvas."""

    def __init__(self, master):
        super().__init__(master, fg_color="#F2F4F7", corner_radius=7)
        self.canvas = tk.Canvas(self, bg="#F2F4F7", bd=0, highlightthickness=0)
        self.scrollbar = ctk.CTkScrollbar(self, command=self.canvas.yview, width=9)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y", padx=(0, 3), pady=4)
        self.canvas.bind("<Configure>", self._on_resize, add="+")
        self.canvas.bind("<MouseWheel>", self._on_mousewheel, add="+")

        self._requests: queue.Queue = queue.Queue(maxsize=1)
        self._results: queue.Queue = queue.Queue()
        self._stopped = threading.Event()
        self._latest_request = 0
        self._resize_after = None
        self._poll_after = None
        self._document = ""
        self._source_image = None
        self._photo = None
        self._image_item = None
        self._worker = threading.Thread(target=self._browser_worker,
                                        name="email-preview-browser", daemon=True)
        self._worker.start()
        self._poll_after = self.after(80, self._poll_results)

    def set_document(self, document: str) -> None:
        resolved = document if document.strip() else (
            "<!doctype html><html><head><meta charset='utf-8'></head><body></body></html>"
        )
        if resolved == self._document:
            return
        self._document = resolved
        self.canvas.yview_moveto(0)
        self._queue_render()

    def _on_resize(self, _event=None):
        if not self._document or self._stopped.is_set():
            return
        self._latest_request += 1
        self._scale_current_image()
        if self._resize_after:
            try:
                self.after_cancel(self._resize_after)
            except tk.TclError:
                pass
        self._resize_after = self.after(120, self._queue_render)

    def _queue_render(self):
        self._resize_after = None
        if self._stopped.is_set() or not self._document:
            return
        width = max(280, self.canvas.winfo_width())
        height = max(320, self.canvas.winfo_height())
        self._latest_request += 1
        request = (self._latest_request, self._document, width, height)
        try:
            self._requests.put_nowait(request)
        except queue.Full:
            try:
                self._requests.get_nowait()
            except queue.Empty:
                pass
            self._requests.put_nowait(request)

    def _poll_results(self):
        self._poll_after = None
        if self._stopped.is_set():
            return
        while True:
            try:
                result = self._results.get_nowait()
            except queue.Empty:
                break
            kind = result[0]
            if kind == "image":
                _kind, request_id, png = result
                if request_id != self._latest_request:
                    continue
                self._source_image = Image.open(BytesIO(png)).convert("RGB")
                self._scale_current_image()
            elif kind == "error":
                if result[1] is None or result[1] == self._latest_request:
                    self._show_error(result[2])
        self._poll_after = self.after(80, self._poll_results)

    def _scale_current_image(self):
        if self._source_image is None or not self.winfo_exists():
            return
        width = max(1, self.canvas.winfo_width())
        source = self._source_image
        if source.width != width:
            height = max(1, round(source.height * width / source.width))
            image = source.resize((width, height), Image.Resampling.BILINEAR)
        else:
            image = source
        self._photo = ImageTk.PhotoImage(image)
        if self._image_item is None:
            self._image_item = self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
        else:
            self.canvas.itemconfigure(self._image_item, image=self._photo)
        self.canvas.configure(scrollregion=(0, 0, image.width, image.height))

    def _show_error(self, message: str):
        self.canvas.delete("all")
        self._image_item = None
        self._source_image = None
        self._photo = None
        self.canvas.configure(scrollregion=(0, 0, max(self.canvas.winfo_width(), 1),
                                            max(self.canvas.winfo_height(), 1)))
        self.canvas.create_text(
            max(self.canvas.winfo_width() // 2, 140), max(self.canvas.winfo_height() // 2, 100),
            text=message, width=max(self.canvas.winfo_width() - 48, 220),
            justify="center", fill="#667085", font=("Segoe UI", 10),
        )

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    @staticmethod
    def _edge_path():
        edge = shutil.which("msedge")
        if edge:
            return edge
        for root in (os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES")):
            if root:
                candidate = Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
                if candidate.is_file():
                    return str(candidate)
        return None

    @staticmethod
    def _preview_shell(source: str) -> str:
        # Keep the template document unchanged inside an isolated, script-disabled
        # iframe. The outer document supplies only the email-client viewport.
        safe_source = html.escape(source, quote=True)
        return f'''<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
html,body{{margin:0;min-height:100%;background:#F2F4F7}}
body{{font-family:Arial,sans-serif}}
#mail{{display:block;width:calc(100% - 28px);max-width:900px;min-height:calc(100vh - 28px);
       height:calc(100vh - 28px);margin:14px auto;border:0;background:#fff}}
</style></head><body>
<iframe id="mail" title="Email template preview" sandbox="allow-same-origin" srcdoc="{safe_source}"></iframe>
<script>
const mail=document.getElementById('mail');
function fitMail(){{
  try{{
    const doc=mail.contentDocument;
    if(!doc)return;
    const body=doc.body, root=doc.documentElement;
    const height=Math.max(window.innerHeight-28,root.scrollHeight,body?body.scrollHeight:0);
    mail.style.height=height+'px';
    document.documentElement.dataset.previewReady='1';
  }}catch(_error){{document.documentElement.dataset.previewReady='1';}}
}}
mail.addEventListener('load',()=>{{fitMail();setTimeout(fitMail,80);setTimeout(fitMail,350);}});
window.addEventListener('resize',fitMail);
</script></body></html>'''

    def _browser_worker(self):
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                edge_path = self._edge_path()
                launch_options = {"headless": True, "args": ["--disable-gpu"]}
                if edge_path:
                    launch_options["executable_path"] = edge_path
                browser = playwright.chromium.launch(**launch_options)
                page = browser.new_page(viewport={"width": 640, "height": 720}, device_scale_factor=1)
                rendered_document = None
                while not self._stopped.is_set():
                    try:
                        request = self._requests.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    if request is None:
                        break
                    request_id, document, width, height = request
                    try:
                        page.set_viewport_size({"width": width, "height": height})
                        if document != rendered_document:
                            page.set_content(self._preview_shell(document), wait_until="domcontentloaded",
                                             timeout=12000)
                            rendered_document = document
                            try:
                                page.wait_for_function(
                                    "document.documentElement.dataset.previewReady === '1'", timeout=2500
                                )
                            except Exception:
                                pass
                        else:
                            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => "
                                          "requestAnimationFrame(resolve)))")
                        png = page.screenshot(type="png", full_page=True, animations="disabled",
                                              timeout=12000)
                        self._results.put(("image", request_id, png))
                    except Exception as error:
                        self._results.put(("error", request_id,
                                           f"Không thể render HTML bằng Edge: {error}"))
                browser.close()
        except Exception as error:
            if not self._stopped.is_set():
                self._results.put((
                    "error",
                    None,
                    "Không khởi chạy được Edge/Chromium. Cài dependency của ứng dụng và bảo đảm "
                    f"Microsoft Edge hoặc Chromium có sẵn. ({error})",
                ))

    def dispose(self):
        if self._stopped.is_set():
            return
        self._stopped.set()
        for callback in (self._resize_after, self._poll_after):
            if callback:
                try:
                    self.after_cancel(callback)
                except tk.TclError:
                    pass
        try:
            self._requests.put_nowait(None)
        except queue.Full:
            try:
                self._requests.get_nowait()
            except queue.Empty:
                pass
            try:
                self._requests.put_nowait(None)
            except queue.Full:
                pass
