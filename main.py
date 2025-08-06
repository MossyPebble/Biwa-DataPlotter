import sys, os, subprocess, json, time
from datetime import datetime
import pyqtgraph as pg
import pandas as pd
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout, QLabel, QDockWidget, QTabWidget, QHBoxLayout, QLineEdit, QFormLayout, QPushButton, QMenu, QCheckBox, QRadioButton, QGridLayout, QComboBox, QFrame
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QEvent
from PyQt6.QtGui import QFont

from utils.SSHManager import SSHManager

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
        formLayout1.addRow(QLabel("    "))
        formLayout1.addRow(QLabel("Path of .lis file"))
        formLayout1.addRow("File Path:", filePathLineEdit := QLineEdit())
        formLayout1.addRow(QLabel("    "))
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
        formLayout2.addRow("", addGraphButton := QPushButton("Add Graph"))
        addGraphButton.clicked.connect(self.createPlotWidget)
        self.formLayout2 = formLayout2

        self.loadSettings()

        # 예시 데이터
        x = [1, 2, 3, 4, 5]
        plot_a.plot(x, [1, 4, 9, 16, 25], pen='b')
        plot_b.plot(x, [25, 16, 9, 4, 1], pen='r')

        self.resize(1000, 600)

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
            print("SSH 연결 성공")

            
        except Exception as e:
            print(f"SSH 연결 실패: {e}")

        # connect 버튼 비활성화
        self.connectButton.setEnabled(False)

    def getButtonHandler(self):

        """
            Get File 버튼 클릭 시 호출되는 핸들러 함수
        """

        file_path = self.filePathLineEdit.text()

        if not self.ssh: 
            print("SSH 연결이 되어 있지 않습니다.")
            return
        if not file_path:
            print("파일 경로가 비어 있습니다.")
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

        print(f"파일이 업데이트되었습니다: {remote_file_path}")

        # 파일 다운로드 후 CSV 변환
        local_file_path = './temp/output.lis'
        self.ssh.get_file(remote_file_path, local_file_path)
        lisToCSV(local_file_path)

        # data, dataColumnNames 업데이트
        try:
            self.data = pd.read_csv(local_file_path.replace('.lis', '.csv'))
            self.dataColumnNames = self.data.columns.tolist()
            print(f"Data loaded successfully. Columns: {self.dataColumnNames}")
        except Exception as e:
            print(f"Error loading data: {e}")
            self.data = None
            self.dataColumnNames = None

        # Plot 업데이트 호출
        for plotInterface in self.plotInterfaces:
            plotInterface.data = self.data  # 데이터 전달
            plotInterface.dataColumnNames = self.dataColumnNames  # 컬럼 이름 전달
            plotInterface.updatePlot()

    def createPlotWidget(self):

        """
            새로운 PlotWidget과 그 PlotWidget을 다루기 위한 interface를 만드는 함수
        """

        # PlotWidget 생성
        dock = QDockWidget(f"Graph {len(self.plotInterfaces) + 1}", self.leftWidget)
        plot = pg.PlotWidget()
        dock.setWidget(plot)
        dock.setFloating(False)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

        # PlotInterface 객체 생성 및 관리
        plotInterface = PlotInterface(plot, self.dataColumnNames)
        plotInterface.data = self.data  # 데이터 전달
        self.formLayout2.addRow("", plotInterface.frame)  # QFormLayout에 PlotInterface의 frame 추가
        plotInterface.data = self.data  # 데이터 전달
        self.plotInterfaces.append(plotInterface)  # PlotInterface를 리스트에 저장

        # Dock이 닫힐 때 PlotInterface 삭제
        dock.visibilityChanged.connect(lambda visible: self.handleDockVisibilityChange(visible, plotInterface, dock))

        return plotInterface
    
    def handleDockVisibilityChange(self, visible, plotInterface, dock):

        """
            QDockWidget의 가시성 변경을 처리하는 메서드
        """

        # Dock이 닫혔을 때, dock 스스로와 PlotInterface를 삭제
        if not visible:
            print("Dock is closing, deleting PlotInterface...")
            self.deletePlot(plotInterface)
            dock.deleteLater()
    
    def deletePlot(self, plotInterface):

        """
            특정 PlotInterface를 삭제하는 메서드
        """

        if plotInterface in self.plotInterfaces:
            print(f"Attempting to delete PlotInterface: {plotInterface}")
            # QFormLayout에서 frame 제거
            self.formLayout2.removeWidget(plotInterface.frame)
            plotInterface.delete()  # PlotInterface의 delete 메서드 호출
            self.plotInterfaces.remove(plotInterface)  # 리스트에서 제거
            print(f"Deleted PlotInterface: {plotInterface}")
        else:
            print("PlotInterface not found.")

    def updatePlot(self, state=None, column=None):

        """
            Plot을 업데이트하는 메서드
        """

        # x축 데이터 가져오기
        x_data = self.xAxisComboBox.currentText()
        if x_data not in self.dataColumnNames:
            print(f"Error: X-axis data '{x_data}' not found in columns.")
            return

        # y축 데이터 가져오기
        y_data_columns = [cb.text() for cb in self.yAxisCheckBoxes if cb.isChecked()]
        if not y_data_columns:
            print("Warning: No Y-axis data selected.")
            return

        # PlotWidget 초기화
        self.plot.clear()

        # 선택된 데이터를 기반으로 그래프 그리기
        for y_data in y_data_columns:
            self.plot.plot(
                self.data[x_data],  # X축 데이터
                self.data[y_data],  # Y축 데이터
                pen=pg.mkPen(color=(255, 0, 0), width=2)  # 스타일 설정
            )
        print(f"Updating plot with X: {x_data}, Y: {y_data_columns}")

    def loadSettings(self):

        # 만약, ssh_config.json 파일이 존재하지 않는다면, 생성
        if not os.path.exists("./ssh_config.json"):
            with open("./ssh_config.json", "w") as config_file:
                json.dump({
                    "host": "",
                    "port": 22,
                    "userId": "",
                    "key_path": "",
                    "file_path": ""
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

    def saveSettings(self):

        """
            SSH 설정을 ssh_config.json 파일에 저장하는 함수
        """

        ssh_config = {
            "host": self.hostLineEdit.text(),
            "port": int(self.portLineEdit.text()),
            "userId": self.userIdLineEdit.text(),
            "key_path": self.keyPathLineEdit.text(),
            "file_path": self.filePathLineEdit.text()
        }
        with open("./ssh_config.json", "w") as config_file:
            json.dump(ssh_config, config_file, indent=4)
        print("SSH 설정 저장 완료")

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
                command = f"stat -c %Y {self.remote_file_path}"  # 파일의 마지막 수정 시간 가져오기
                stdin, stdout, stderr = self.ssh_manager.ssh.exec_command(command)
                current_modified_time = int(stdout.read().strip())

                if last_modified_time is None or current_modified_time != last_modified_time:
                    last_modified_time = current_modified_time
                    print(f"마지막 수정 시간: {datetime.fromtimestamp(last_modified_time)}")
                    print(f"파일이 변경되었습니다: {self.remote_file_path}")
                    self.file_updated.emit(self.remote_file_path)  # 파일 변경 신호 전송
            except Exception as e:
                print(f"Error watching file: {e}")
            time.sleep(1)  # 1초 간격으로 파일 감시

class PlotInterface:
    def __init__(self, plot, dataColumnNames):
        self.plot = plot
        self.dataColumnNames = dataColumnNames

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

    def updatePlot(self, state=None, column=None):

        """
            Plot을 업데이트하는 메서드
        """

        # x축 데이터 가져오기
        x_data = self.xAxisComboBox.currentText()
        if x_data not in self.dataColumnNames:
            print(f"Error: X-axis data '{x_data}' not found in columns.")
            return

        # y축 데이터 가져오기
        y_data_columns = [cb.text() for cb in self.yAxisCheckBoxes if cb.isChecked()]
        if not y_data_columns:
            print("Warning: No Y-axis data selected.")
            return

        # PlotWidget 초기화
        self.plot.clear()

        # 선택된 데이터를 기반으로 그래프 그리기
        for y_data in y_data_columns:
            self.plot.plot(
                self.data[x_data],  # X축 데이터
                self.data[y_data],  # Y축 데이터
                pen=pg.mkPen(color=(255, 0, 0), width=2)  # 스타일 설정
            )
        print(f"Updating plot with X: {x_data}, Y: {y_data_columns}")

    def delete(self):

        """
            PlotWidget과 인터페이스를 삭제하는 메서드
        """

        self.plot.deleteLater()  # PlotWidget 삭제
        self.frame.deleteLater()  # QFrame 삭제
        print("Plot and interface deleted.")

def lisToCSV(path) -> None:

    """
        .lis 파일을 CSV로 변환하는 함수입니다.

        Args:
            path (str): 변환할 .lis 파일의 경로
    """

    # eishin을 실행해 .lis를 CSV로. "Usage: " << argv[0] << " <input_lis_file> <output_csv_file>"
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return
    
    output_path = path.replace('.lis', '.csv')
    command = f"eishin {path} {output_path}"
    try:
        subprocess.run(command, shell=True, check=True)
        print(f"Converted {path} to {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error converting {path} to CSV: {e}")

def getFileAndPlot():pass

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Arial", 20))
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
