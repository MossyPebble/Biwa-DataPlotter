from PyQt6.QtWidgets import QWidget, QFormLayout, QLineEdit, QLabel, QPushButton
from utils.SSHManager import SSHManager
import logging

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from main import MainWindow

def createSSHSettingsTab(self: "MainWindow"):

    # component 선언
    tab1Widget = QWidget()
    self.tabWidget.addTab(tab1Widget, "SSH Settings")

    formLayout1 = QFormLayout(tab1Widget)
    formLayout1.addRow("Host:", hostLineEdit := QLineEdit())
    formLayout1.addRow("Port:", portLineEdit := QLineEdit())
    formLayout1.addRow("User ID:", userIdLineEdit := QLineEdit())
    formLayout1.addRow("Key Path:", keyPathLineEdit := QLineEdit())
    formLayout1.addRow(QLabel(""))
    formLayout1.addRow("Connect:", connectButton := QPushButton("Connect"))

    # 필요한 components에 접근을 용이하게 하기 위해 인스턴스 변수로 저장
    self.hostLineEdit = hostLineEdit
    self.portLineEdit = portLineEdit
    self.userIdLineEdit = userIdLineEdit
    self.keyPathLineEdit = keyPathLineEdit
    self.connectButton = connectButton

    # 핸들러와 component 연결
    connectButton.clicked.connect(lambda: connectButtonHandler(self))

def connectButtonHandler(self: "MainWindow"):

    """
        SSH 연결 버튼 클릭 시 호출되는 핸들러 함수
    """

    if self.useLocalFile:
        logging.info("Using local file for data.")
        self.showTooltip("Using local file for data.")
        return

    host = self.hostLineEdit.text()
    port = int(self.portLineEdit.text())
    userId = self.userIdLineEdit.text()
    key_path = self.keyPathLineEdit.text()

    # SSHManager를 사용하여 SSH 연결을 시도
    try:
        self.ssh = SSHManager(host, port, userId, key_path)
        logging.info("SSH 연결 성공")
    except Exception as e: logging.info(f"SSH 연결 실패: {e}")

    # connect 버튼 비활성화
    self.connectButton.setEnabled(False)

    # 탭을 두 번째 것으로 변경
    self.tabWidget.setCurrentIndex(1)