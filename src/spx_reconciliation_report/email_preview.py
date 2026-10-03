"""Qt WebEngine based HTML email preview widget."""
from PySide6.QtWebEngineWidgets import QWebEngineView


class EmailBrowserPreview(QWebEngineView):
    def set_document(self, document: str) -> None:
        self.setHtml(document)
