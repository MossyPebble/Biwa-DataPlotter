import sys, os, subprocess, json, time, math
from datetime import datetime
import pyqtgraph as pg
import pandas as pd
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout, QLabel, QDockWidget, QTabWidget, QLineEdit, QFormLayout, QPushButton, QMenu, QCheckBox, QGridLayout, QComboBox, QFrame, QTextEdit, QToolTip, QLabel, QSlider
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QEvent, QTimer, QObject
from PyQt6.QtGui import QFont, QShortcut, QKeySequence

from utils.SSHManager import SSHManager

import logging

# 로거 기본 설정
logging.basicConfig(
    level=logging.INFO,                        # INFO 이상 레벨만 기록
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("log.txt", mode="a", encoding="utf-8"),  # 파일에 append
        logging.StreamHandler()                                       # 콘솔에도 출력
    ]
)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Biwa-DataPlotter")

        # 필요 변수 선언
        self.ssh = None
        self.serverFileWatcherThread = None
        self.data = None
        self.dataColumnNames = None
        self.plotInterfaces = []  # PlotInterface 객체를 저장할 리스트
        self.lastUpdatedTime = None

        # *************** 메뉴바 설정 **************
        menuBar = self.menuBar()
        settingsMenu = QMenu("Settings", self)
        menuBar.addMenu(settingsMenu)

        saveAction = QAction("Save Settings", self)
        saveAction.triggered.connect(self.saveSettings)
        settingsMenu.addAction(saveAction)

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

        # 왼쪽에 도크된 임시 그래프 A, B (A 위에 B가 쌓임)
        dock_a = QDockWidget("Graph A", leftWidget)
        plot_a = pg.PlotWidget()
        dock_a.setWidget(plot_a)
        dock_a.setFloating(False)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock_a)

        dock_b = QDockWidget("Graph B", leftWidget)
        plot_b = pg.PlotWidget()
        dock_b.setWidget(plot_b)
        dock_b.setFloating(False)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock_b)

        # *************** 오른쪽 도킹 위젯 설정 **************
        rightTabWidget = QDockWidget("Settings", rightWidget)
        self.tabWidget = QTabWidget(rightTabWidget)
        rightTabWidget.setWidget(self.tabWidget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, rightTabWidget)
        rightTabWidget.setFloating(False)

        # ************** SSH 설정 탭 **************
        # component 선언
        tab1Widget = QWidget()
        self.tabWidget.addTab(tab1Widget, "SSH Settings")

        formLayout1 = QFormLayout(tab1Widget)
        formLayout1.addRow("Host:", hostLineEdit := QLineEdit())
        formLayout1.addRow("Port:", portLineEdit := QLineEdit())
        formLayout1.addRow("User ID:", userIdLineEdit := QLineEdit())
        formLayout1.addRow("Key Path:", keyPathLineEdit := QLineEdit())
        formLayout1.addRow(QLabel(""))
        formLayout1.addRow(QLabel("Path of .lis file"))
        formLayout1.addRow("File Path:", filePathLineEdit := QLineEdit())
        formLayout1.addRow(QLabel(""))
        formLayout1.addRow(QLabel("Connect and Get"))
        formLayout1.addRow("Connect:", connectButton := QPushButton("Connect"))
        formLayout1.addRow("Get File:", getButton := QPushButton("Get File"))

        # 필요한 components에 접근을 용이하게 하기 위해 인스턴스 변수로 저장
        self.hostLineEdit = hostLineEdit
        self.portLineEdit = portLineEdit
        self.userIdLineEdit = userIdLineEdit
        self.keyPathLineEdit = keyPathLineEdit
        self.filePathLineEdit = filePathLineEdit
        self.connectButton = connectButton
        self.getButton = getButton

        # 핸들러와 component 연결
        connectButton.clicked.connect(self.connectButtonHandler)
        getButton.clicked.connect(self.getButtonHandler)

        # ************** Plot Settings 탭 **************
        # component 선언
        tab2Widget = QWidget()
        self.tabWidget.addTab(tab2Widget, "Plot Settings")

       
        formLayout2 = QFormLayout(tab2Widget)

        # 마지막 갱신 시간 표시
        self.lastUpdatedLabel = QLabel("Never")
        formLayout2.addRow("Last Updated:", self.lastUpdatedLabel)

        # Add Graph 버튼
        formLayout2.addRow("", addGraphButton := QPushButton("Add Graph"))
        addGraphButton.clicked.connect(self.createPlotWidget)
        self.formLayout2 = formLayout2

        # 예시 데이터
        x = [1, 2, 3, 4, 5]
        plot_a.plot(x, [1, 4, 9, 16, 25], pen='b')
        plot_b.plot(x, [25, 16, 9, 4, 1], pen='r')

        self.resize(1000, 600)

        # ************** quickChange 탭 **************
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

        # *************** 단축키 설정 **************
        self.shellCommandShortcut = QShortcut(QKeySequence("F6"), self)
        self.shellCommandShortcut.activated.connect(self.executeShellCommand)

        self.editorSaveShortcut = QShortcut(QKeySequence("Ctrl+S"), self.editorTextEdit)
        self.editorSaveShortcut.activated.connect(self.editorSaveHotkeyHandler)
        self.editorSaveShortcut.setContext(Qt.ShortcutContext.WidgetShortcut)

        # *************** 초기 설정 로드 **************
        self.loadSettings()

    def showTooltip(self, message):
        QToolTip.showText(self.mapToGlobal(self.rect().center()), message, self)

    def editorGetButtonHandler(self):

        """
            Built-in Editor에서 Get File 버튼 클릭 시 호출되는 핸들러 함수
        """

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

    def editorSaveHotkeyHandler(self):

        """
            Built-in Editor에서 Ctrl+S 단축키로 파일 저장 시 호출되는 핸들러 함수
        """

        file_path = self.editorFilePathLineEdit.text().strip()
        content = self.editorTextEdit.toPlainText()
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

    def executeShellCommand(self):

        """
            Shell Command를 실행하는 메서드
        """

        commands = self.shellCommandTextEdit.toPlainText().split('\n')
        if not commands:
            logging.info("Shell Command is empty.")
            return
        if not self.ssh:
            logging.info("SSH connection is not established.")
            return
        
        self.showTooltip("Executing shell command...")

        try:
            channel = self.ssh.invoke_shell()
            self.ssh.execute_commands_over_shell(channel, commands, no_output=True)
            channel.close()
        except Exception as e:
            logging.info(f"Error executing shell command: {e}")

    def connectButtonHandler(self):

        """
            SSH 연결 버튼 클릭 시 호출되는 핸들러 함수
        """

        host = self.hostLineEdit.text()
        port = int(self.portLineEdit.text())
        userId = self.userIdLineEdit.text()
        key_path = self.keyPathLineEdit.text()

        # SSHManager를 사용하여 SSH 연결을 시도
        try:
            self.ssh = SSHManager(host, port, userId, key_path)
            logging.info("SSH 연결 성공")

            
        except Exception as e:
            logging.info(f"SSH 연결 실패: {e}")

        # connect 버튼 비활성화
        self.connectButton.setEnabled(False)

    def getButtonHandler(self):

        """
            Get File 버튼 클릭 시 호출되는 핸들러 함수
        """

        file_path = self.filePathLineEdit.text()

        if not self.ssh: 
            logging.info("SSH 연결이 되어 있지 않습니다.")
            return
        if not file_path:
            logging.info(f"파일 경로가 비어 있습니다: {file_path}")
            return

        # 파일 감시 스레드 시작
        self.serverFileWatcherThread = ServerFileWatcherThread(self.ssh, file_path)
        self.serverFileWatcherThread.file_updated.connect(self.onFileUpdated)
        self.serverFileWatcherThread.start()

        # 첫 파일 업데이트
        self.onFileUpdated(file_path)

        # 탭을 두 번째 것으로 변경
        self.tabWidget.setCurrentIndex(1)

    def onFileUpdated(self, remote_file_path):

        """
            파일이 업데이트되었을 때 호출되는 함수
        """

        logging.info(f"파일이 업데이트되었습니다: {remote_file_path}")

        # 마지막 갱신 시간 기록
        self.lastUpdatedTime = datetime.now()
        self.lastUpdatedLabel.setText(self.lastUpdatedTime.strftime("%Y-%m-%d %H:%M:%S"))

        # 파일 다운로드 후 CSV 변환
        local_file_path = './temp/output.lis'
        self.ssh.get_file(remote_file_path, local_file_path)
        lisToCSV(local_file_path)

        # data, dataColumnNames 업데이트
        try:
            self.data = pd.read_csv(local_file_path.replace('.lis', '.csv'))
            self.dataColumnNames = self.data.columns.tolist()
            logging.info(f"Data loaded successfully. Columns: {self.dataColumnNames}")
        except Exception as e:
            logging.info(f"Error loading data: {e}")
            self.data = None
            self.dataColumnNames = None

        # Plot 업데이트 호출
        for plotInterface in self.plotInterfaces:
            plotInterface.data = self.data  # 데이터 전달
            plotInterface.dataColumnNames = self.dataColumnNames  # 컬럼 이름 전달
            plotInterface.updatePlot()

        # 갱신 완료 알림
        self.showTooltip("Data updated and plots refreshed.")

    def createPlotWidget(self):

        """
            새로운 PlotDock과 그 PlotDock을 다루기 위한 interface를 만드는 함수
        """

        # PlotDock 생성
        dock = PlotDock(f"Graph {len(self.plotInterfaces) + 1}", self.leftWidget, self.data, self.dataColumnNames)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

        # PlotInterface 관리
        self.formLayout2.addRow("", dock.plotInterface.frame)  # QFormLayout에 PlotInterface의 frame 추가
        self.plotInterfaces.append(dock.plotInterface)        # PlotInterface를 리스트에 저장

        return dock.plotInterface

    def loadSettings(self):

        # 만약, ssh_config.json 파일이 존재하지 않는다면, 생성
        if not os.path.exists("./ssh_config.json"):
            with open("./ssh_config.json", "w") as config_file:
                json.dump({
                    "host": "",
                    "port": 22,
                    "userId": "",
                    "key_path": "",
                    "file_path": "",
                    "shell_command": "",
                    "editor_file_path": ""
                }, config_file, indent=4)

        # ssh_config.json 파일에서 SSH 설정을 로드
        config_path = "./ssh_config.json"
        if os.path.exists(config_path):
            with open(config_path, "r") as config_file:
                ssh_config = json.load(config_file)
                self.hostLineEdit.setText(ssh_config.get("host", ""))
                self.portLineEdit.setText(str(ssh_config.get("port", "")))
                self.userIdLineEdit.setText(ssh_config.get("userId", ""))
                self.keyPathLineEdit.setText(ssh_config.get("key_path", ""))
                self.filePathLineEdit.setText(ssh_config.get("file_path", ""))
                self.shellCommandTextEdit.setPlainText(ssh_config.get("shell_command", ""))
                self.editorFilePathLineEdit.setText(ssh_config.get("editor_file_path", ""))

    def saveSettings(self):

        """
            SSH 설정을 ssh_config.json 파일에 저장하는 함수
        """

        ssh_config = {
            "host": self.hostLineEdit.text(),
            "port": int(self.portLineEdit.text()),
            "userId": self.userIdLineEdit.text(),
            "key_path": self.keyPathLineEdit.text(),
            "file_path": self.filePathLineEdit.text(),
            "shell_command": self.shellCommandTextEdit.toPlainText(),
            "editor_file_path": self.editorFilePathLineEdit.text()
        }
        with open("./ssh_config.json", "w") as config_file:
            json.dump(ssh_config, config_file, indent=4)
        logging.info("SSH 설정 저장 완료")

class ServerFileWatcherThread(QThread):
    file_updated = pyqtSignal(str)  # 파일 변경 시 신호를 보냄

    def __init__(self, ssh_manager, remote_file_path):
        super().__init__()
        self.ssh_manager = ssh_manager
        self.remote_file_path = remote_file_path
        self.running = True

    def run(self):
        last_modified_time = None
        while self.running:
            try:
            
                # 서버에서 파일의 수정 시간 확인
                command = f"stat -c %Y \"{self.remote_file_path}\""  # 파일의 마지막 수정 시간 가져오기
                stdin, stdout, stderr = self.ssh_manager.ssh.exec_command(command)
                current_modified_time = int(stdout.read().strip())

                if last_modified_time is None or current_modified_time != last_modified_time:
                    last_modified_time = current_modified_time
                    logging.info(f"마지막 수정 시간: {datetime.fromtimestamp(last_modified_time)}")
                    logging.info(f"파일이 변경되었습니다: {self.remote_file_path}")
                    self.file_updated.emit(self.remote_file_path)  # 파일 변경 신호 전송
            except Exception as e:
                logging.info(f"Error watching file: {e}")
            time.sleep(1)  # 1초 간격으로 파일 감시

class WheelToSliderFilter(QObject):
    def __init__(self, slider: QSlider):
        super().__init__()
        self.slider = slider

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel and self.slider is not None:
            delta = event.angleDelta().y()
            if delta == 0:
                return False
            notches = int(delta / 120)  # 1 notch = 120
            minv = self.slider.minimum()
            maxv = self.slider.maximum()
            rng = max(1, maxv - minv)

            # 기본 스텝: 범위의 1%
            step = max(1, math.ceil(rng * 0.01))

            # 가속도: Shift=5%, Ctrl=10%
            mods = event.modifiers()
            if mods & Qt.KeyboardModifier.ControlModifier:
                step *= 10
            elif mods & Qt.KeyboardModifier.ShiftModifier:
                step *= 5

            new_val = max(minv, min(maxv, self.slider.value() + notches * step))
            if new_val != self.slider.value():
                self.slider.setValue(new_val)
            event.accept()
            return True
        return False

class PlotInterface:
    def __init__(self, plot, dataColumnNames):
        self.plot = plot
        self.dataColumnNames = dataColumnNames
        self.plotColors = ['r', 'g', 'b', 'c', 'm', 'y', 'w']
        self.plotColorsIndex = 0

        # frame 생성
        self.frame = QFrame()
        self.frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame.setLineWidth(2)

        # frame 내부 레이아웃 설정
        self.interfaceLayout = QVBoxLayout(self.frame)

        # y축 데이터 체크박스 생성
        self.yAxisCheckBoxes = []
        self.yAxisCheckBoxLayout = QGridLayout()
        self.interfaceLayout.addWidget(QLabel("Y-Axis Data"))
        self.interfaceLayout.addLayout(self.yAxisCheckBoxLayout)

        for i, column in enumerate(dataColumnNames):
            checkbox = QCheckBox(column)
            checkbox.stateChanged.connect(lambda state, col=column: self.updatePlot(state, col))
            self.yAxisCheckBoxLayout.addWidget(checkbox, i // 3, i % 3)
            self.yAxisCheckBoxes.append(checkbox)

        # x축 데이터 콤보박스 생성
        self.interfaceLayout.addWidget(QLabel("X-Axis Data"))
        self.xAxisComboBox = QComboBox()
        self.xAxisComboBox.addItems(dataColumnNames)
        self.xAxisComboBox.currentIndexChanged.connect(self.updatePlot)
        self.interfaceLayout.addWidget(self.xAxisComboBox)

        # 데이터 길이 수동 설정
        self.interfaceLayout.addWidget(QLabel("Data Length"))
        self.lengthSlider = QSlider(Qt.Orientation.Horizontal)
        self.lengthSlider.setMinimum(1)
        self.lengthSlider.setMaximum(1)  # 데이터 로드 후 갱신
        self.lengthSlider.setValue(1)
        self.lengthSlider.setTickPosition(QSlider.TickPosition.NoTicks)

        # 슬라이더 변경 시 라벨/플롯 갱신
        self.lengthSlider.valueChanged.connect(self.onLengthSliderChanged)
        self.interfaceLayout.addWidget(self.lengthSlider)

        # 현재 n과 % 표시 라벨
        self.lengthInfoLabel = QLabel("1 / 1 (100%)")
        self.lengthInfoLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.interfaceLayout.addWidget(self.lengthInfoLabel)

        # 추가: PlotInterface 영역(프레임과 모든 자식)에서 휠 => 슬라이더 제어
        self._wheelFilter = WheelToSliderFilter(self.lengthSlider)
        self.frame.installEventFilter(self._wheelFilter)
        for w in self.frame.findChildren(QWidget):
            w.installEventFilter(self._wheelFilter)

    # 슬라이더 변경 핸들러
    def onLengthSliderChanged(self, value: int):
        max_len = len(self.data) if getattr(self, "data", None) is not None else self.lengthSlider.maximum()
        max_len = max(max_len, 1)
        n = min(value, max_len)
        self.updateLengthLabel(n, max_len)
        self.updatePlot(setSliderMax=False)

    # n, % 라벨 갱신
    def updateLengthLabel(self, n: int, max_len: int):
        pct = int(n / max_len * 100) if max_len > 0 else 0
        self.lengthInfoLabel.setText(f"{n} / {max_len} ({pct}%)")

    def updatePlot(self, state=None, column=None, setSliderMax=True):

        """
            Plot을 업데이트하는 메서드
        """

        # x축 데이터 가져오기
        x_data = self.xAxisComboBox.currentText()
        if x_data not in self.dataColumnNames:
            logging.info(f"Error: X-axis data '{x_data}' not found in columns.")
            return

        # y축 데이터 가져오기
        y_data_columns = [cb.text() for cb in self.yAxisCheckBoxes if cb.isChecked()]
        if not y_data_columns:
            logging.info("Warning: No Y-axis data selected.")
            return
        
        # 슬라이더 최대치 데이터 길이에 맞추기
        max_len = len(self.data)
        if self.lengthSlider.maximum() != max_len:
            self.lengthSlider.blockSignals(True)
            self.lengthSlider.setMaximum(max_len)
            if self.lengthSlider.value() > max_len:
                self.lengthSlider.setValue(max_len)
            self.lengthSlider.blockSignals(False)

        n = min(self.lengthSlider.value(), max_len)
        if n <= 0:
            return
        if setSliderMax:
            self.lengthSlider.setValue(max_len)
            n = max_len
        
        # n, % 라벨 갱신
        self.updateLengthLabel(n, max_len)

        # PlotWidget 초기화
        self.plot.clear()

        # 선택된 데이터를 기반으로 그래프 그리기
        self.plotColorsIndex = 0
        for y_data in y_data_columns:
            self.plot.plot(
                self.data[x_data].iloc[:n],
                self.data[y_data].iloc[:n],
                pen=pg.mkPen(self.plotColors[self.plotColorsIndex % len(self.plotColors)], width=2),
                name=y_data
            )
            self.plotColorsIndex += 1
        logging.info(f"Updating plot with X: {x_data}, Y: {y_data_columns}")

    def delete(self):

        """
            PlotWidget과 인터페이스를 삭제하는 메서드
        """

        self.plot.deleteLater()  # PlotWidget 삭제
        self.frame.deleteLater()  # QFrame 삭제
        logging.info("Plot and interface deleted.")

class PlotDock(QDockWidget):
    def __init__(self, title, parent=None, data=None, dataColumnNames=None):
        super().__init__(title, parent)
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable | QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.plotWidget = pg.PlotWidget()  # PlotWidget 생성
        self.setWidget(self.plotWidget)   # PlotWidget을 도킹 위젯에 설정
        self.setFloating(False)           # 도킹 위젯 고정

        # PlotInterface 생성 및 연결
        self.plotInterface = PlotInterface(self.plotWidget, dataColumnNames)
        self.plotInterface.data = data  # 데이터 전달

        # linkedInterface 속성 추가
        self.linkedInterface = self.plotInterface

    def closeEvent(self, event):
        logging.info(f"Closing dock widget: {self.windowTitle()}")

        # 연동된 PlotInterface가 있다면 삭제
        if self.linkedInterface:
            self.linkedInterface.delete()
        super().closeEvent(event)

def lisToCSV(path) -> None:

    """
        .lis 파일을 CSV로 변환하는 함수입니다.

        Args:
            path (str): 변환할 .lis 파일의 경로
    """

    # eishin을 실행해 .lis를 CSV로. "Usage: " << argv[0] << " <input_lis_file> <output_csv_file>"
    if not os.path.exists(path):
        logging.info(f"File not found: {path}")
        return
    
    output_path = path.replace('.lis', '.csv')
    command = f"eishin {path} {output_path}"
    try:
        subprocess.run(command, shell=True, check=True)
        logging.info(f"Converted {path} to {output_path}")
    except subprocess.CalledProcessError as e:
        logging.info(f"Error converting {path} to CSV: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Arial", 20))
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
