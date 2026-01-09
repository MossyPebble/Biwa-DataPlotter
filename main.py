import sys, os, json, logging
from datetime import datetime
import pandas as pd
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter,QLabel, QDockWidget, QTabWidget, QLineEdit, QFormLayout, QPushButton, QMenu, QCheckBox, QTextEdit, QToolTip, QLabel, QScrollArea, QHBoxLayout, QVBoxLayout, QDialog, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QShortcut, QKeySequence, QAction, QPixmap, QIcon

# utils에서 import
from utils.SSHManager import SSHManager
from utils.utils import lisToCSV, parseParamsFile, patch_modelcard_content_inplace
from utils.PlotDock import PlotDock
from utils.DataInterface import DataInterface
from utils.ParamRowWidget import ParamRowWidget

# 로거 기본 설정
logging.basicConfig(
    level=logging.INFO,                                             # INFO 이상 레벨만 기록
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("log.txt", mode="a", encoding="utf-8"), # 파일에 append
        logging.StreamHandler()                                     # 콘솔에도 출력
    ]
)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Biwa-DataPlotter")
        icon_path = os.path.join(os.path.dirname(__file__), "img", "biwahayahide_list.png")
        self.setWindowIcon(QIcon(icon_path))

        version = 1.1

        # 필요 변수 선언
        self.ssh = None
        self.serverFileWatcherThread = None
        self.data = None
        self.data_history = []
        self.plotIndex = 0
        self.fav_params = set()
        self.config_path = "./config.json"
        self.dataPathHistory = []

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
        self.createSSHSettingsTab()
        self.createPlotSettingsTab()
        self.createQuickChangeTab()
        self.createQuickParamsTab()

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
            self.connectButtonHandler()
        except Exception as e:
            logging.info(f"Initial SSH connection failed: {e}")
            self.showTooltip("Initial SSH connection failed.")

    def createSSHSettingsTab(self):

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

        # 또는, local 경로를 사용할 수도 있음
        self.useLocalFileButton = QCheckBox("Select Local File")
        self.useLocalFileButton.toggled.connect(self.useLocalFileButtonHandler)  # 핸들러 연결
        formLayout1.addRow("... or use local file!  ", self.useLocalFileButton)

        # 필요한 components에 접근을 용이하게 하기 위해 인스턴스 변수로 저장
        self.hostLineEdit = hostLineEdit
        self.portLineEdit = portLineEdit
        self.userIdLineEdit = userIdLineEdit
        self.keyPathLineEdit = keyPathLineEdit
        self.connectButton = connectButton

        # 핸들러와 component 연결
        connectButton.clicked.connect(self.connectButtonHandler)

    def createPlotSettingsTab(self):

        # component 선언
        tab2Widget = QWidget()
        self.tabWidget.addTab(tab2Widget, "Plot Settings")
        outerLayout = QVBoxLayout(tab2Widget)

        # 스크롤 영역
        self.plotSettingsScrollArea = QScrollArea()
        self.plotSettingsScrollArea.setWidgetResizable(True)
        outerLayout.addWidget(self.plotSettingsScrollArea)

        # 스크롤 내부 컨텐츠 + 여기에 formLayout2를 붙임
        self.plotSettingsContent = QWidget()
        self.formLayout2 = QFormLayout(self.plotSettingsContent)
        self.plotSettingsScrollArea.setWidget(self.plotSettingsContent)

        # Add Plot, Add Data로 분리
        btnRow = QHBoxLayout()
        btnRow.addWidget(addPlotButton := QPushButton("Add Plot"))
        btnRow.addWidget(addDataButton := QPushButton("Add Data"))
        addPlotButton.clicked.connect(self.createPlotDock)
        addDataButton.clicked.connect(self.createDataInterface)
        self.formLayout2.addRow("", btnRow)

    def createQuickChangeTab(self):

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
        getFileButton.clicked.connect(self.editorGetButtonHandler)
        self.editorTextEdit = QTextEdit()
        formLayout3.addRow("", self.editorTextEdit)

    def createQuickParamsTab(self):

        """
            Params 파일의 값을 빠르게 변경할 수 있는 탭 구현
            파일은 다음과 같은 형식이 라고 가정:
                +version = 4.3             binunit = 1               paramchk= 1               mobmod  = 0
                +capmod  = 0             igcmod  = 0               igbmod  = 0               geomod  = 0
            저런 형식을 파싱하여, 각 파라미터를 체크박스나 콤보박스로 빠르게 변경할 수 있도록 함
            현재 목표는 
                {Favorite} {param_name}: {current_value}  {-10% Button} {-5% Button} {+5% Button} {+10% Button}
            을 한 줄에 넣은 UI로 구성하는 것
        """

        tab4Widget = QWidget()
        self.tabWidget.addTab(tab4Widget, "Quick Params")

        formLayout4 = QFormLayout(tab4Widget)

        # 간단히 이 탭의 사용법 안내
        formLayout4.addRow("", QLabel("파라미터 파일 경로를 입력하고, 파일을 로드하세요."))
        formLayout4.addRow("", QLabel("수정 후 저장하면, 해당 파일을 기반으로 한 새 파일이 생성됩니다."))

        # Ctrl+S, F6 통합 여부 체크박스
        # 이 옵션 활성화 시, Ctrl+S가 눌리면 저장 후 F6도 함께 호출됨
        self.useCtrlSForParamsCheckBox = QCheckBox("Use Ctrl+S to Save Params and Execute Shell Command (F6)")
        formLayout4.addRow("", self.useCtrlSForParamsCheckBox)

        # 가져올 Params 파일 경로 입력란
        formLayout4.addRow("", QLabel("Params File Path"))
        self.paramsFilePathLineEdit = QLineEdit()
        formLayout4.addRow("File Path:", self.paramsFilePathLineEdit)
        formLayout4.addRow("", loadParamsButton := QPushButton("Load Params"))
        loadParamsButton.clicked.connect(self.loadParamsFileHandler)

        # 생성할 파일 이름 입력란
        formLayout4.addRow("", QLabel("Output File Name"))
        self.outputParamsFileNameLineEdit = QLineEdit("output_params.txt")
        formLayout4.addRow("File Name:", self.outputParamsFileNameLineEdit)

        # Params 파라미터들을 표시할 영역
        self.paramsScrollArea = QScrollArea()
        self.paramsScrollArea.setWidgetResizable(True)
        self.paramsDisplayArea = QWidget()
        self.paramsDisplayLayout = QFormLayout(self.paramsDisplayArea)
        self.paramsScrollArea.setWidget(self.paramsDisplayArea)
        formLayout4.addRow("", self.paramsScrollArea)

        # 견본 파라미터 표시
        self.params = {'sample1': {'value': 10, 'favorite': False}, 'sample2': {'value': 20, 'favorite': True}}
        self.updateParamsDisplay(self.params)

    def loadParamsFileHandler(self):

        """
            Params 파일 로드 핸들러 (원격 전용).
            - SSH로 원격 파일을 내려받아 ./temp/params_file.txt 로 저장한 뒤 파싱합니다.
            - SSH 연결이 없으면 로드하지 않습니다.
        """

        # 파일 경로 가져오기
        file_path = self.paramsFilePathLineEdit.text().strip()
        if not file_path:
            logging.info("Params file path is empty.")
            self.showTooltip("Params file path is empty.")
            return

        # SSH 연결 확인
        if self.ssh is None:
            logging.info("SSH connection is not established.")
            self.showTooltip("SSH 연결이 되어 있지 않습니다.")
            return

        # 파일 다운로드 및 파싱
        try:
            os.makedirs("./temp", exist_ok=True)
            local_tmp = "./temp/params_file.txt"

            # 원격 파일 다운로드
            self.ssh.get_file(file_path, local_tmp)

            # 로컬 임시 파일 읽기
            with open(local_tmp, "r", encoding="utf-8") as f:
                content = f.read()

            params = parseParamsFile(content)
            self.params = params

            # favorite params 복원
            for key in self.fav_params:
                if key in self.params:
                    self.params[key]["favorite"] = True

            self.updateParamsDisplay(params)

            logging.info(f"Params loaded (remote): {file_path}")
            self.showTooltip("Params file loaded successfully. (remote)")

        except Exception as e:
            logging.info(f"Error loading params file (remote): {e}")
            self.showTooltip(f"Params load failed: {e}")

    def updateParamsDisplay(self, params: dict):

        """
            Params 파라미터들을 self.paramsDisplayLayout에 표시하는 함수
            UI 구성:
                {Favorite} {param_name}  {value_edit}  {-10%} {-5%} {+5%} {+10%}
        """

        # 기존 행/위젯 정리 (removeRow만 하면 위젯이 남아 UI가 꼬일 수 있음)
        while self.paramsDisplayLayout.rowCount() > 0:
            item = self.paramsDisplayLayout.itemAt(0, QFormLayout.ItemRole.LabelRole)
            if item is not None and item.widget() is not None: item.widget().deleteLater()
            item = self.paramsDisplayLayout.itemAt(0, QFormLayout.ItemRole.FieldRole)
            if item is not None and item.widget() is not None: item.widget().deleteLater()
            self.paramsDisplayLayout.removeRow(0)

        # params를 key 기준으로 정렬, favorite이 True인 항목이 위로 오도록
        def _sort_key(k: str):
            fav = bool(params.get(k, {}).get("favorite", False))
            return (0 if fav else 1, k.lower())
        for key in sorted(params.keys(), key=_sort_key):
            row = ParamRowWidget(key, params, lambda: self.updateParamsDisplay(self.params))
            self.paramsDisplayLayout.addRow(row)

    def useLocalFileButtonHandler(self):

        """
            로컬 파일 사용 버튼 핸들러
        """

        if self.useLocalFileButton.isChecked():
            self.useLocalFile = True
            self.showTooltip("Using local file for data.")
            logging.info("Using local file for data.")
        else:
            self.useLocalFile = False
            self.showTooltip("Using remote file for data.")
            logging.info("Using remote file for data.")

    def showTooltip(self, message): QToolTip.showText(self.mapToGlobal(self.rect().center()), message, self)

    def editorGetButtonHandler(self):

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

        try:
            channel = self.ssh.invoke_shell()
            self.ssh.execute_commands_over_shell(channel, commands, no_output=True)
            channel.close()
        except Exception as e: logging.info(f"Error executing shell command: {e}")

    def connectButtonHandler(self):

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

    def createPlotDock(self):

        """
            새로운 PlotDock을 생성하는 메서드
        """

        # PlotDock 생성
        dock = PlotDock(f"Graph {self.plotIndex}", self.leftWidget)
        self.plotIndex += 1
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self.plotDocks.append(dock)

        # 닫혀서 delete될 때 리스트에서 제거되도록 연결
        dock.closed.connect(self.destroyPlotDock)

        # 각 DataInterface의 plotSelectComboBox에 새 PlotDock 추가
        for data_interface in self.plotInterfaces: data_interface.refreshPlotSelectComboBox()

    def destroyPlotDock(self, dock_obj):

        """
            PlotDock이 close되어 삭제되면 호출됨.
            self.plotDocks에서 제거 + UI 갱신
        """

        # destroyed 시점엔 이미 QObject만 남을 수 있어서, id 기반으로 제거
        before = len(self.plotDocks)
        self.plotDocks.remove(dock_obj)
        after = len(self.plotDocks)
        logging.info(f"PlotDock destroyed. plotDocks: {before} -> {after}")

        # DataInterface 콤보박스 갱신
        for data_interface in self.plotInterfaces:
            data_interface.refreshDataUI()

    def createDataInterface(self):

        """
            새로운 DataInterface를 생성하는 메서드
        """

        data_interface = DataInterface(self.ssh, self.plotDocks, self.dataPathHistory)
        self.formLayout2.addRow(QLabel(""), data_interface.frame)
        self.plotInterfaces.append(data_interface)
        logging.info(f"DataInterface created. Total interfaces: {len(self.plotInterfaces)}")

    def loadSettings(self):

        # 만약, ssh_config.json 파일이 존재하지 않는다면, 생성
        if not os.path.exists(self.config_path):
            with open(self.config_path, "w") as config_file:
                json.dump({
                    "host": "",
                    "port": 22,
                    "userId": "",
                    "key_path": "",
                    "shell_command": "",
                    "editor_file_path": "",
                    "use_local_file": False,
                    "params_file_path": "",
                    "params_output_file_name": "",
                    "use_ctrl_s_for_params": False,
                    "favorite_params": [],
                    "data_path_history": [],
                }, config_file, indent=4)

        # ssh_config.json 파일에서 SSH 설정을 로드
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as config_file:
                ssh_config = json.load(config_file)
                self.hostLineEdit.setText(ssh_config.get("host", ""))
                self.portLineEdit.setText(str(ssh_config.get("port", "")))
                self.userIdLineEdit.setText(ssh_config.get("userId", ""))
                self.keyPathLineEdit.setText(ssh_config.get("key_path", ""))
                self.shellCommandTextEdit.setPlainText(ssh_config.get("shell_command", ""))
                self.editorFilePathLineEdit.setText(ssh_config.get("editor_file_path", ""))
                self.useLocalFileButton.setChecked(ssh_config.get("use_local_file", False))
                self.paramsFilePathLineEdit.setText(ssh_config.get("params_file_path", ""))
                self.outputParamsFileNameLineEdit.setText(ssh_config.get("params_output_file_name", "output_params.txt"))
                self.useCtrlSForParamsCheckBox.setChecked(ssh_config.get("use_ctrl_s_for_params", False))
                self.fav_params = set(ssh_config.get("favorite_params", []))
                self.dataPathHistory = ssh_config.get("data_path_history", [])

    def saveSettings(self):

        """
            설정을 config.json 파일에 저장하는 함수
        """

        ssh_config = {
            "host": self.hostLineEdit.text(),
            "port": int(self.portLineEdit.text()),
            "userId": self.userIdLineEdit.text(),
            "key_path": self.keyPathLineEdit.text(),
            "shell_command": self.shellCommandTextEdit.toPlainText(),
            "editor_file_path": self.editorFilePathLineEdit.text(),
            "use_local_file": self.useLocalFile,
            "params_file_path": self.paramsFilePathLineEdit.text(),
            "params_output_file_name": self.outputParamsFileNameLineEdit.text(),
            "use_ctrl_s_for_params": self.useCtrlSForParamsCheckBox.isChecked(),
            "favorite_params": list(self.fav_params),
            "data_path_history": self.dataPathHistory,
        }
        with open(self.config_path, "w") as config_file:
            json.dump(ssh_config, config_file, indent=4)
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