from PyQt6.QtWidgets import QWidget, QFormLayout, QLabel, QTextEdit, QLineEdit, QPushButton

import logging

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from main import MainWindow

def createQuickChangeTab(self: "MainWindow"):

    tab3Widget = QWidget()
    self.tabWidget.addTab(tab3Widget, "Quick Change")

    formLayout3 = QFormLayout(tab3Widget)
    formLayout3.addRow("", QLabel("Shell Command (F6)"))
    self.shellCommandTextEdit = QTextEdit()
    self.shellCommandTextEdit.setFixedHeight(150)
    formLayout3.addRow("Command:", self.shellCommandTextEdit)
    formLayout3.addRow("", QLabel(""))
    
    # built-in editor 구현
    formLayout3.addRow("", QLabel("Built-in Editor (Save with Ctrl+S)"))
    self.editorFilePathLineEdit = QLineEdit()
    formLayout3.addRow("File Path:", self.editorFilePathLineEdit)
    formLayout3.addRow("", getFileButton := QPushButton("Get File"))
    getFileButton.clicked.connect(lambda: editorGetButtonHandler(self))
    self.editorTextEdit = QTextEdit()
    formLayout3.addRow("", self.editorTextEdit)

def editorGetButtonHandler(self: "MainWindow"):

    """
        Built-in Editor에서 Get File 버튼 클릭 시 호출되는 핸들러 함수
    """

    if self.useLocalFile:
        logging.info("Using local file for editor.")
        self.showTooltip("Using local file for editor.")
        return

    file_path = self.editorFilePathLineEdit.text().strip()
    if not file_path:
        logging.info("File path is empty.")
        return

    if not self.ssh:
        logging.info("SSH connection is not established.")
        self.showTooltip("SSH 연결이 되어 있지 않습니다.")
        return

    try:
        self.showTooltip("Getting file...")

        # 파일 다운로드
        local_file_path = './temp/editor_file.txt'
        self.ssh.get_file(file_path, local_file_path)

        # 파일 내용을 읽어서 에디터에 표시
        with open(local_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            self.editorTextEdit.setPlainText(content)
        logging.info(f"File loaded successfully: {file_path}")
        self.showTooltip("File loaded successfully.")
    except Exception as e:
        logging.info(f"Error getting file: {e}")