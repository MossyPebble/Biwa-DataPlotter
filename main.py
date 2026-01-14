import sys, os, json, logging
from datetime import datetime
import pandas as pd
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter,QLabel, QDockWidget, QTabWidget, QLineEdit, QFormLayout, QPushButton, QMenu, QCheckBox, QTextEdit, QToolTip, QLabel, QScrollArea, QHBoxLayout, QVBoxLayout, QDialog, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QShortcut, QKeySequence, QAction, QPixmap, QIcon

# utils에서 import
from utils.utils import lisToCSV, patch_modelcard_content_inplace
from utils.HSPICEParser import HSPICEParser

# ui에서 import
from ui.ParamRowWidget import ParamRowWidget
from ui.tabs.SSHSettingsTab import createSSHSettingsTab, connectButtonHandler
from ui.tabs.PlotSettingsTab import createPlotSettingsTab
from ui.tabs.QuickChangeTab import createQuickChangeTab
from ui.tabs.QuickParamsTab import createQuickParamsTab

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from utils.SSHManager import SSHManager

    # ui에서 import
    from ui.PlotDock import PlotDock
    from ui.DataInterface import DataInterface

# 로거 기본 설정
logging.basicConfig(
    level=logging.INFO,                                          
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f'./log/{datetime.now().strftime("%Y%m%d_%H%M%S")}_log.txt', mode="a", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Biwa-DataPlotter")
        icon_path = os.path.join(os.path.dirname(__file__), "img", "biwahayahide_list.png")
        self.setWindowIcon(QIcon(icon_path))

        version = 1.11

        # 필요 변수 선언
        self.ssh: SSHManager = None
        self.serverFileWatcherThread = None
        self.data = None
        self.data_history = []
        self.plotIndex = 0
        self.fav_params = set()
        self.config_path = "./config.json"
        self.dataPathHistory = []

        self.lineEditComponents = [
            'hostLineEdit',
            'portLineEdit',
            'userIdLineEdit',
            'keyPathLineEdit',
            'editorFilePathLineEdit',
            'paramsFilePathLineEdit',
            'outputParamsFileNameLineEdit'
        ]

        self.textEditComponents = [
            'shellCommandTextEdit'
        ]

        self.checkBoxComponents = [
            'useCtrlSForParamsCheckBox'
        ]

        # UI 요소 관리
        self.plotDocks: list[PlotDock] = []
        self.plotInterfaces: list[DataInterface] = []

        self.lastUpdatedTime = None
        self.useLocalFile = False

        # *************** 메뉴바 설정 **************
        menuBar = self.menuBar()
        settingsMenu = QMenu("Settings", self)
        menuBar.addMenu(settingsMenu)

        saveAction = QAction("Save Settings", self)
        saveAction.triggered.connect(self.saveSettings)
        settingsMenu.addAction(saveAction)

        saveParamsAction = QAction("Save Params File", self)
        def _saveParamsAndRun(checked):
            self.fav_params = {k for k, v in self.params.items() if v.get("favorite", False)}
            self.saveSettings()
        saveParamsAction.triggered.connect(_saveParamsAndRun)
        settingsMenu.addAction(saveParamsAction)

        biwaInfoAction = QAction("About Biwa", self)
        def _showBiwaInfo(checked: bool = False):
            img_path = os.path.join(os.path.dirname(__file__), "img", "biwahayahide_01.png")

            pix = QPixmap(img_path)

            dlg = QDialog(self)
            dlg.setWindowTitle("About Biwa")

            text_label = QLabel(dlg)
            text_label.setText("Biwa-DataPlotter\n" + f"Version {str(version)}\n" + "\n")

            img_label = QLabel(dlg)
            pix2 = pix.scaled(
                pix.width() // 2,
                pix.height() // 2,
                Qt.AspectRatioMode.IgnoreAspectRatio,  # 정확히 반반(가로/세로 각각)
                Qt.TransformationMode.SmoothTransformation,
            )
            img_label.setPixmap(pix2)
            dlg.setFixedSize(pix2.size())

            dlg.show()
            self._aboutDialog = dlg  # GC 방지
        biwaInfoAction.triggered.connect(_showBiwaInfo)
        settingsMenu.addAction(biwaInfoAction)

        # *************** 좌측 도킹 위젯 설정 **************
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(5)
        splitter.setChildrenCollapsible(False)
        leftWidget = QWidget(splitter)
        rightWidget = QWidget(splitter)
        self.setCentralWidget(splitter)

        # component에 접근을 용이하게 하기 위해 인스턴스 변수로 저장
        self.leftWidget = leftWidget
        self.rightWidget = rightWidget

        # *************** 오른쪽 도킹 위젯 설정 **************
        rightTabWidget = QDockWidget("Settings", rightWidget)
        self.tabWidget = QTabWidget(rightTabWidget)
        rightTabWidget.setWidget(self.tabWidget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, rightTabWidget)
        rightTabWidget.setFloating(False)

        # ************** 탭 생성 **************
        createSSHSettingsTab(self)
        createPlotSettingsTab(self)
        createQuickChangeTab(self)
        createQuickParamsTab(self)

        # *************** 단축키 설정 **************
        self.shellCommandShortcut = QShortcut(QKeySequence("F6"), self)
        self.shellCommandShortcut.activated.connect(self.executeShellCommand)

        self.editorSaveShortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        self.editorSaveShortcut.activated.connect(self.onCtrlSPressed)

        # *************** 초기 설정 로드 **************
        self.loadSettings()
        self.resize(1000, 600)

        # 자체 connect 시도, 실패 시 툴팁 표시
        try:
            connectButtonHandler(self)
        except Exception as e:
            logging.info(f"Initial SSH connection failed: {e}")
            self.showTooltip("Initial SSH connection failed.")

    def showTooltip(self, message): QToolTip.showText(self.mapToGlobal(self.rect().center()), message, self)

    def onCtrlSPressed(self):

        """
            Built-in Editor에서 Ctrl+S 단축키로 파일 저장 시 호출되는 핸들러 함수
        """

        tab_idx = self.tabWidget.currentIndex()
        tab_name = self.tabWidget.tabText(tab_idx)

        print(f"Current Tab: {tab_name}")

        # 현재 탭이 "Quick Change"일 떄의 동작
        if tab_name == "Quick Change":
            file_path = self.editorFilePathLineEdit.text().strip()
            content = self.editorTextEdit.toPlainText()
            if not content: 
                logging.info("Editor content is empty.")
                self.showTooltip("Editor content is empty.")
                return
            try:

                # 현재 에디터 내용을 읽어 서버 측 경로로 저장
                self.showTooltip("Saving file...")
                logging.info(f"Saving file to: {file_path}")
                local_file_path = './temp/editor_file.txt'
                with open(local_file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.ssh.put_file(local_file_path, file_path)
                self.showTooltip("File saved successfully.")
                logging.info(f"File saved successfully: {file_path}")
            except Exception as e:
                logging.info(f"Error saving file: {e}")

        # 현재 탭이 "Quick Params"일 때의 동작
        elif tab_name == "Quick Params":
            output_file_name = self.outputParamsFileNameLineEdit.text().strip()
            if not output_file_name:
                logging.info("Output file name is empty.")
                self.showTooltip("Output file name is empty.")
                return

            try:
                # Params 내용을 서버로 저장
                self.showTooltip("Saving params file...")
                logging.info(f"Saving params to: {output_file_name}")

                # 템플릿 파일 로드
                templateFilePath = './temp/params_file.txt'
                with open(templateFilePath, 'r', encoding='utf-8') as f:
                    template_content = f.read()

                # 오직 key:value 쌍만 추출된 dict 생성
                params_simple = {key: entry.get("value", "") for key, entry in self.params.items()}

                # 모델 카드 생성
                content = patch_modelcard_content_inplace(template_content, params_simple, section=None, insert_missing=True)

                # 로컬 임시 파일에 작성
                local_file_path = './temp/params_output.txt'
                with open(local_file_path, 'w', encoding='utf-8') as f:
                    f.write(content)

                # 서버로 업로드
                self.ssh.put_file(local_file_path, output_file_name)

                self.showTooltip("Params file saved successfully.")
                logging.info(f"Params file saved successfully: {output_file_name}")
            except Exception as e:
                logging.info(f"Error saving params file: {e}")

        if self.useCtrlSForParamsCheckBox.isChecked():
            self.executeShellCommand()

    def executeShellCommand(self):

        """
            Shell Command를 실행하는 메서드
        """

        commands = self.shellCommandTextEdit.toPlainText().split('\n')
        if not commands: logging.info("Shell Command is empty.")           ; return
        if not self.ssh: logging.info("SSH connection is not established."); return
        
        self.showTooltip("Executing shell command...")

        channel = self.ssh.invoke_shell()
        # self.ssh.execute_commands_over_shell(channel, commands, no_output=False)
        self.ssh.send_command(commands[0])
        channel.close()

    def onFileUpdated(self, remote_file_path: str):

        """
            파일이 업데이트되었을 때 호출되는 함수
        """

        logging.info(f"파일이 업데이트되었습니다: {remote_file_path}")

        # 데이터 히스토리에 현재 데이터 추가
        if self.data is not None:
            self.data_history.append(self.data.copy())
            logging.info(f"Data history updated. Total entries: {len(self.data_history)}")

        # 마지막 갱신 시간 기록
        self.lastUpdatedTime = datetime.now()
        self.lastUpdatedLabel.setText(self.lastUpdatedTime.strftime("%Y-%m-%d %H:%M:%S"))

        # 만약, 파일의 확장자가 lis라면, csv로 변환
        if remote_file_path.endswith('.lis'):
            local_file_path = './temp/output.lis'

            if self.useLocalFile:

                # 로컬 파일 사용 시, 경로만 변경 후 CSV 변환
                local_file_path = remote_file_path
                lisToCSV(local_file_path)
            else:

                # 서버 파일 사용 시, 파일 다운로드 후 CSV 변환
                self.ssh.get_file(remote_file_path, local_file_path)
                lisToCSV(local_file_path)
        
        # csv라면, 경로 및 이름만 변경
        elif remote_file_path.endswith('.csv'):
            local_file_path = './temp/output.csv'

            if self.useLocalFile:
                local_file_path = remote_file_path
            else:
                self.ssh.get_file(remote_file_path, local_file_path)

        # 이외의 파일이라면, 툴팁으로 알림 후 return
        else:
            logging.info(f"지원하지 않는 파일 형식입니다: {remote_file_path}")
            self.showTooltip("지원하지 않는 파일 형식입니다 (.lis, .csv 만 지원).")
            return

        # data, dataColumnNames 업데이트
        try:
            self.data = pd.read_csv(local_file_path.replace('.lis', '.csv'))
            logging.info(f"Data loaded successfully. Columns: {self.dataColumnNames}")
        except Exception as e:
            logging.info(f"Error loading data: {e}")
            self.data = None
            self.dataColumnNames = None

        # Plot 업데이트 호출
        for plotInterface in self.plotInterfaces:
            plotInterface.data = self.data  # 데이터 전달
            plotInterface.data_history = self.data_history
            plotInterface.updatePlot()

        # 갱신 완료 알림
        self.showTooltip("Data updated and plots refreshed.")

    def loadSettings(self):

        """config.json 파일에서 설정을 불러오는 함수"""

        # 만약, ssh_config.json 파일이 존재하지 않는다면, 생성
        if not os.path.exists(self.config_path):
            config_dict = {}
            for comp in self.lineEditComponents: config_dict[comp] = ""
            for comp in self.textEditComponents: config_dict[comp] = ""
            for comp in self.checkBoxComponents: config_dict[comp] = False
            config_dict["favorite_params"] = []
            config_dict["data_path_history"] = []

            with open(self.config_path, "w") as config_file:
                json.dump(config_dict, config_file, indent=4)
            logging.info("설정 파일이 존재하지 않아 새로 생성하였습니다.")

        # ssh_config.json 파일에서 SSH 설정을 로드
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as config_file:
                config_dict: dict = json.load(config_file)

                for comp in self.lineEditComponents: getattr(self, comp).setText(config_dict.get(comp, ""))
                for comp in self.textEditComponents: getattr(self, comp).setPlainText(config_dict.get(comp, ""))
                for comp in self.checkBoxComponents: getattr(self, comp).setChecked(config_dict.get(comp, False))
                self.fav_params = set(config_dict.get("favorite_params", []))
                self.dataPathHistory = list(config_dict.get("data_path_history", []))

    def saveSettings(self):

        """설정을 config.json 파일에 저장하는 함수"""

        config_dict = {}
        for comp in self.lineEditComponents: config_dict[comp] = getattr(self, comp).text()
        for comp in self.textEditComponents: config_dict[comp] = getattr(self, comp).toPlainText()
        for comp in self.checkBoxComponents: config_dict[comp] = getattr(self, comp).isChecked()
        config_dict["favorite_params"] = list(self.fav_params)
        config_dict["data_path_history"] = self.dataPathHistory

        with open(self.config_path, "w") as config_file:
            json.dump(config_dict, config_file, indent=4)
        logging.info("설정 저장 완료")

    def closeEvent(self, a0):
        self.saveSettings()
        super().closeEvent(a0)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("경기천년제목", 20))
    w = MainWindow()
    w.show()
    sys.exit(app.exec())