from __future__ import annotations

import uuid
from typing import Any

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from runner_client.app.store import BUILTIN_SERVER_IDS, save_servers


class ServerManageDialog(QDialog):
    """增删改服务器环境列表。"""

    def __init__(self, servers: list[dict[str, Any]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("管理服务器环境")
        self.resize(480, 360)
        self._servers = [dict(s) for s in servers]

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("默认提供「本地开发」(localhost)，可添加或编辑自定义环境地址。"))

        self._list = QListWidget()
        self._refresh_list()
        layout.addWidget(self._list, stretch=1)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("添加")
        edit_btn = QPushButton("编辑")
        remove_btn = QPushButton("删除")
        add_btn.clicked.connect(self._add_server)
        edit_btn.clicked.connect(self._edit_server)
        remove_btn.clicked.connect(self._remove_server)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _refresh_list(self) -> None:
        self._list.clear()
        for item in self._servers:
            label = item.get("label") or item.get("url", "")
            url = item.get("url", "")
            self._list.addItem(f"{label}  —  {url}")

    def _selected_index(self) -> int | None:
        row = self._list.currentRow()
        return row if row >= 0 else None

    def _add_server(self) -> None:
        label, ok = QInputDialog.getText(self, "添加环境", "显示名称：", text="自定义环境")
        if not ok or not label.strip():
            return
        url, ok2 = QInputDialog.getText(self, "添加环境", "服务器地址：", text="http://")
        if not ok2 or not url.strip():
            return
        self._servers.append(
            {
                "id": f"custom_{uuid.uuid4().hex[:8]}",
                "label": label.strip(),
                "url": url.strip().rstrip("/"),
            }
        )
        self._refresh_list()
        self._list.setCurrentRow(len(self._servers) - 1)

    def _edit_server(self) -> None:
        idx = self._selected_index()
        if idx is None:
            QMessageBox.information(self, "提示", "请先选择一项")
            return
        item = self._servers[idx]
        label, ok = QInputDialog.getText(self, "编辑环境", "显示名称：", text=item.get("label", ""))
        if not ok or not label.strip():
            return
        url, ok2 = QInputDialog.getText(self, "编辑环境", "服务器地址：", text=item.get("url", ""))
        if not ok2 or not url.strip():
            return
        item["label"] = label.strip()
        item["url"] = url.strip().rstrip("/")
        self._refresh_list()
        self._list.setCurrentRow(idx)

    def _remove_server(self) -> None:
        idx = self._selected_index()
        if idx is None:
            QMessageBox.information(self, "提示", "请先选择一项")
            return
        sid = str(self._servers[idx].get("id", ""))
        if sid in BUILTIN_SERVER_IDS:
            QMessageBox.warning(self, "无法删除", "内置环境不能删除，可编辑其地址。")
            return
        answer = QMessageBox.question(
            self,
            "确认删除",
            f"删除环境「{self._servers[idx].get('label')}」？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._servers.pop(idx)
        self._refresh_list()

    def _accept(self) -> None:
        save_servers(self._servers)
        self.accept()

    def result_servers(self) -> list[dict[str, Any]]:
        return self._servers
