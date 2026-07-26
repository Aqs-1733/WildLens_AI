from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QMainWindow, QMessageBox, QPushButton, QSplitter, QTextEdit, QVBoxLayout, QWidget,
)


@dataclass
class ApiClient:
    base_url: str
    token: str = ""

    def request(self, path: str, method: str = "GET", payload: dict | None = None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.base_url.rstrip("/") + path,
            data=body,
            method=method,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))


class ReviewWindow(QMainWindow):
    def __init__(self, api_url: str):
        super().__init__()
        self.api = ApiClient(api_url)
        self.items: list[dict] = []
        self.setWindowTitle("WildLens 人工复核辅助工具")
        self.resize(980, 640)

        root = QWidget()
        layout = QVBoxLayout(root)
        auth = QHBoxLayout()
        auth.addWidget(QLabel("访问令牌"))
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        auth.addWidget(self.token)
        load = QPushButton("加载待复核项")
        load.clicked.connect(self.load_queue)
        auth.addWidget(load)
        layout.addLayout(auth)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self.show_item)
        splitter.addWidget(self.list_widget)

        panel = QWidget()
        form = QFormLayout(panel)
        self.label = QLineEdit()
        self.scientific = QLineEdit()
        self.category = QLineEdit()
        self.note = QTextEdit()
        self.raw = QTextEdit()
        self.raw.setReadOnly(True)
        form.addRow("中文名", self.label)
        form.addRow("学名", self.scientific)
        form.addRow("类别", self.category)
        form.addRow("复核说明", self.note)
        form.addRow("原始记录", self.raw)
        actions = QHBoxLayout()
        confirm = QPushButton("确认并提交")
        confirm.clicked.connect(lambda: self.submit("confirmed"))
        training = QPushButton("加入训练集")
        training.clicked.connect(lambda: self.submit("needs_training"))
        dismiss = QPushButton("标记误报")
        dismiss.clicked.connect(lambda: self.submit("dismissed"))
        actions.addWidget(confirm)
        actions.addWidget(training)
        actions.addWidget(dismiss)
        form.addRow(actions)
        splitter.addWidget(panel)
        splitter.setSizes([330, 650])
        layout.addWidget(splitter)
        self.setCentralWidget(root)

    def load_queue(self):
        self.api.token = self.token.text().strip()
        try:
            data = self.api.request("/api/review/queue")
            self.items = data if isinstance(data, list) else data.get("items", [])
            self.list_widget.clear()
            for item in self.items:
                self.list_widget.addItem(
                    f"#{item.get('id')} {item.get('label')} · {item.get('confidence', 0):.0%}"
                )
        except Exception as exc:
            QMessageBox.critical(self, "加载失败", str(exc))

    def show_item(self, row: int):
        if row < 0 or row >= len(self.items):
            return
        item = self.items[row]
        self.label.setText(str(item.get("label", "")))
        self.scientific.setText(str(item.get("scientific_name", "")))
        self.category.setText(str(item.get("category", "unknown")))
        self.note.clear()
        self.raw.setPlainText(json.dumps(item, ensure_ascii=False, indent=2))

    def submit(self, status: str):
        row = self.list_widget.currentRow()
        if row < 0:
            return
        item = self.items[row]
        payload = {
            "species_id": item.get("species_id"),
            "label": self.label.text().strip() or "待确认目标",
            "scientific_name": self.scientific.text().strip(),
            "category": self.category.text().strip() or "unknown",
            "status": status,
            "note": self.note.toPlainText().strip(),
        }
        try:
            self.api.request(f"/api/review/detections/{item['id']}", "PATCH", payload)
            QMessageBox.information(self, "提交成功", "复核结果已写回平台。")
            self.load_queue()
        except Exception as exc:
            QMessageBox.critical(self, "提交失败", str(exc))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8010")
    args = parser.parse_args()
    app = QApplication(sys.argv)
    window = ReviewWindow(args.api)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
