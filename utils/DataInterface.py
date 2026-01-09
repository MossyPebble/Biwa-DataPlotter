import logging, math, os, time
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QGridLayout, QLabel, QCheckBox, QComboBox, QSlider, QWidget, QLineEdit, QPushButton, QFormLayout, QToolTip, QApplication
from PyQt6.QtCore import QEvent, QObject, Qt
import pyqtgraph as pg
import pandas as pd, numpy as np

# utils
from utils.utils import lisToCSV, clear_layout, qimage_to_rgba_numpy
from utils.FileWatcherThread import FileWatcherThread
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from utils.SSHManager import SSHManager

class DataInterface:

    def __init__(self, ssh: "SSHManager", plotDocks: list[pg.PlotWidget], dataPathHistory: list[str]):
        
        """
            DataInterface 초기화 메서드

            Args:
                ssh (SSHManager): SSHManager 인스턴스 (서버와 통신용)
                plotDocks (list[pg.PlotWidget]): 데이터를 표시할 PlotDock 위젯 리스트
                dataPathHistory (list[str]): 이전에 사용된 데이터 파일 경로 히스토리 리스트
        """

        self.ssh = ssh
        self.plotDocks = plotDocks
        self.lastRefreshTime = None
        self.dataPathHistory = dataPathHistory
        self.fileType = None

        # UI 변수
        self.path = ''

        # frame 생성 및 frame 내부 root layout 생성
        self.frame = QFrame()
        self.frame.setFrameShape(QFrame.Shape.Box)
        self.frame.setLineWidth(2)
        self.rootLayout = QVBoxLayout(self.frame)

        self.createGetDataInterface()

    def createGetDataInterface(self):

        """
            init에서 data 경로를 받는 UI 생성 함수
            생성하는 것:
                - .lis 또는 .csv 파일 경로 입력란
                - "Get File" 버튼
                - local 파일 사용 체크박스
        """
        
        # form layout 생성
        formLayout1 = QFormLayout()
        self.rootLayout.addLayout(formLayout1)

        formLayout1.addRow(QLabel(""))
        formLayout1.addRow(QLabel("Path of .lis file (or .csv)"))
        formLayout1.addRow("File Path:", filePathComboBox := QComboBox())
        self.filePathComboBox = filePathComboBox
        self.filePathComboBox.setMinimumContentsLength(30)  # 표시 문자 길이
        self.filePathComboBox.setEditable(True)
        self.filePathComboBox.addItems(self.dataPathHistory)
        formLayout1.addRow(QLabel(""), getButton := QPushButton("Get File"))
        getButton.clicked.connect(self.getButtonHandler)

        # 또는, local 경로를 사용할 수도 있음
        self.useLocalFileButton = QCheckBox("Select Local File")
        formLayout1.addRow("... or use local file!  ", self.useLocalFileButton)

        # margin
        formLayout1.addRow(QLabel(""))

    def getButtonHandler(self):

        """
            "Get File" 버튼 핸들러.
            이 함수가 실행되면 path를 받아 저장한 후, 파일 감시 스레드를 시작함.
        """

        # 기존의 파일 감시 스레드가 있으면 종료
        if hasattr(self, "serverFileWatcherThread"):
            self.serverFileWatcherThread.stop()
            self.serverFileWatcherThread.wait()

        self.path = self.filePathComboBox.currentText().strip()

        # 만약 path가 비어있지 않고, 히스토리에 없으면 히스토리에 추가
        # 만약 히스토리에 이미 있으면, 가장 최근으로 이동
        if self.path:
            exists = any(self.filePathComboBox.itemText(i) == self.path
                         for i in range(self.filePathComboBox.count()))
            if exists:
                idx = self.dataPathHistory.index(self.path)
                self.dataPathHistory.pop(idx)
            self.dataPathHistory.insert(0, self.path)
        logging.info(f"DataInterface: history updated with path: {self.dataPathHistory}")

        # error 체크
        if not self.ssh: logging.info("DataInterface: SSH not connected."); return
        if not self.path: logging.info(f"파일 경로가 비어 있습니다: {self.path}"); return

        # file path 저장
        logging.info(f"DataInterface: File path set to: {self.path}")
        self.serverFileWatcherThread = FileWatcherThread(self.ssh, self.path)
        self.serverFileWatcherThread.file_updated.connect(self.updateData)
        self.serverFileWatcherThread.start()

    def updateData(self, file_path):

        """
            파일이 업데이트되었을 때 호출되는 함수.
            호출 시, 파일을 다운로드하고 데이터를 로드한 후 refreshDataUI와 updatePlot을 호출해 UI, 플롯을 갱신함.
        """

        logging.info(f"DataInterface: File updated signal received for: {file_path}")

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        # 파일 다운로드
        local_path = './temp/' + os.path.basename(file_path)
        try:
            self.ssh.get_file(file_path, local_path)
            logging.info(f"DataInterface: File downloaded to: {local_path}")
        except Exception as e:
            logging.info(f"DataInterface: Failed to download file: {e}")
            return
        self.lastRefreshTime = time.time()

        # 데이터 로드
        try:
            if local_path.lower().endswith(".csv"):
                self.fileType = "csv"
                self.data = pd.read_csv(local_path)
                self.dataColumnNames = self.data.columns.tolist()
                logging.info(f"DataInterface: Data loaded with columns: {self.dataColumnNames}")
            elif local_path.lower().endswith(".lis"):
                self.fileType = "lis"
                lisToCSV(local_path)
                self.data = pd.read_csv(local_path[:-4] + ".csv")
                self.dataColumnNames = self.data.columns.tolist()
                logging.info(f"DataInterface: Data loaded with columns: {self.dataColumnNames}")

            # png 지원
            elif local_path.lower().endswith(".png"):
                self.fileType = "png"

                # np로 읽어 저장
                self.data = qimage_to_rgba_numpy(local_path)

            else: 
                logging.info(f"DataInterface: Unsupported file type: {local_path}")
                return
            
        except Exception as e: 
            logging.info(f"DataInterface: Failed to load data file: {e}")
            return
        
        # UI 및 플롯 갱신
        self.refreshDataUI()
        self.updatePlot(setSliderMax=True)

        QApplication.restoreOverrideCursor()
        self.showTooltip("Data updated and UI refreshed.")

    def _captureUIState(self) -> dict:
        state = {
            "selected_dock_title": None,
            "selected_dock_obj": None,
            "x_column": None,
            "checked_y": set(),
            "show_past": True,
            "slider_value": None,

            # ✅ PNG용 상태
            "img_x0": None,
            "img_y0": None,
            "img_x1": None,
            "img_y1": None,
            "img_opacity": None,
        }

        if hasattr(self, "plotSelectComboBox") and self.plotSelectComboBox is not None:
            state["selected_dock_obj"] = self.plotSelectComboBox.currentData()
            state["selected_dock_title"] = self.plotSelectComboBox.currentText()

        if hasattr(self, "xAxisComboBox") and self.xAxisComboBox is not None:
            state["x_column"] = self.xAxisComboBox.currentText()

        if hasattr(self, "yAxisCheckBoxes") and self.yAxisCheckBoxes is not None:
            state["checked_y"] = {cb.text() for cb in self.yAxisCheckBoxes if cb.isChecked()}

        if hasattr(self, "showPastDataCheckBox") and self.showPastDataCheckBox is not None:
            state["show_past"] = self.showPastDataCheckBox.isChecked()

        if hasattr(self, "lengthSlider") and self.lengthSlider is not None:
            state["slider_value"] = self.lengthSlider.value()

        # ✅ PNG 입력값 저장(문자열 그대로 저장하면 round-trip이 쉬움)
        if hasattr(self, "x0PosLineEdit") and self.x0PosLineEdit is not None:
            state["img_x0"] = self.x0PosLineEdit.text()
        if hasattr(self, "y0PosLineEdit") and self.y0PosLineEdit is not None:
            state["img_y0"] = self.y0PosLineEdit.text()
        if hasattr(self, "x1PosLineEdit") and self.x1PosLineEdit is not None:
            state["img_x1"] = self.x1PosLineEdit.text()
        if hasattr(self, "opacityLineEdit") and self.opacityLineEdit is not None:
            state["img_opacity"] = self.opacityLineEdit.text()

        return state

    def _restoreUIState(self, state: dict):

        """
            refreshDataUI 이후 새로 만들어진 UI에 저장된 상태를 복원
        """

        # PlotDock 선택 복원(가능하면 객체로, 아니면 title로)
        if hasattr(self, "plotSelectComboBox") and self.plotSelectComboBox is not None:
            self.plotSelectComboBox.blockSignals(True)
            try:
                restored = False
                prev_obj = state.get("selected_dock_obj")
                if prev_obj is not None:
                    for i in range(self.plotSelectComboBox.count()):
                        if self.plotSelectComboBox.itemData(i) is prev_obj:
                            self.plotSelectComboBox.setCurrentIndex(i)
                            restored = True
                            break

                if not restored:
                    prev_title = state.get("selected_dock_title")
                    if prev_title:
                        idx = self.plotSelectComboBox.findText(prev_title)
                        if idx >= 0:
                            self.plotSelectComboBox.setCurrentIndex(idx)
            finally:
                self.plotSelectComboBox.blockSignals(False)

        # X 축 복원
        if hasattr(self, "xAxisComboBox") and self.xAxisComboBox is not None:
            prev_x = state.get("x_column")
            if prev_x:
                idx = self.xAxisComboBox.findText(prev_x)
                if idx >= 0:
                    self.xAxisComboBox.blockSignals(True)
                    self.xAxisComboBox.setCurrentIndex(idx)
                    self.xAxisComboBox.blockSignals(False)

        # Show past 복원
        if hasattr(self, "showPastDataCheckBox") and self.showPastDataCheckBox is not None:
            self.showPastDataCheckBox.blockSignals(True)
            self.showPastDataCheckBox.setChecked(bool(state.get("show_past", True)))
            self.showPastDataCheckBox.blockSignals(False)

        # Y 체크박스 복원 (이름 매칭)
        checked_y = state.get("checked_y") or set()
        if hasattr(self, "yAxisCheckBoxes") and self.yAxisCheckBoxes is not None:
            for cb in self.yAxisCheckBoxes:
                cb.blockSignals(True)
                cb.setChecked(cb.text() in checked_y)
                cb.blockSignals(False)

        # 슬라이더 값 복원(새 max 범위 내로 clamp)
        if hasattr(self, "lengthSlider") and self.lengthSlider is not None:
            prev_val = state.get("slider_value")
            if prev_val is not None:
                maxv = self.lengthSlider.maximum()
                minv = self.lengthSlider.minimum()
                v = max(minv, min(maxv, int(prev_val)))
                self.lengthSlider.blockSignals(True)
                self.lengthSlider.setValue(v)
                self.lengthSlider.blockSignals(False)

        # ✅ PNG 입력값 복원
        if hasattr(self, "x0PosLineEdit") and self.x0PosLineEdit is not None and state.get("img_x0") is not None:
            self.x0PosLineEdit.setText(str(state["img_x0"]))
        if hasattr(self, "y0PosLineEdit") and self.y0PosLineEdit is not None and state.get("img_y0") is not None:
            self.y0PosLineEdit.setText(str(state["img_y0"]))
        if hasattr(self, "x1PosLineEdit") and self.x1PosLineEdit is not None and state.get("img_x1") is not None:
            self.x1PosLineEdit.setText(str(state["img_x1"]))
        if hasattr(self, "y1PosLineEdit") and self.y1PosLineEdit is not None and state.get("img_y1") is not None:
            self.y1PosLineEdit.setText(str(state["img_y1"]))
        if hasattr(self, "opacityLineEdit") and self.opacityLineEdit is not None and state.get("img_opacity") is not None:
            self.opacityLineEdit.setText(str(state["img_opacity"]))

    def refreshDataUI(self):

        """
            데이터 갱신 후 UI 요소(콤보박스, 체크박스 등)를 갱신하는 메서드
        """

        if not self.path: return

        # 현재 UI 상태 저장
        prev_state = self._captureUIState()

        # 기존 UI 요소 제거
        clear_layout(self.rootLayout)

        # frame 내부 레이아웃 설정
        self.interfaceLayout = QVBoxLayout()
        self.rootLayout.addLayout(self.interfaceLayout)

        # 종료 버튼 생성
        closeButton = QPushButton("Close This Data Interface")
        closeButton.clicked.connect(self.delete)
        self.interfaceLayout.addWidget(closeButton)

        # 데이터 파일 경로 표시
        dataFilePathLineEdit = QLineEdit()
        dataFilePathLineEdit.setReadOnly(True)
        dataFilePathLineEdit.setText(self.path)
        self.interfaceLayout.addWidget(dataFilePathLineEdit)

        # 마지막 갱신 시간 표시
        if self.lastRefreshTime:
            last_refresh_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.lastRefreshTime))
            lastRefreshLabel = QLabel(f"Last Refreshed: {last_refresh_str}")
            self.interfaceLayout.addWidget(lastRefreshLabel)
        self.interfaceLayout.addWidget(QLabel(''))

        # 표시할 PlotWidget 선택 콤보박스 생성
        self.interfaceLayout.addWidget(QLabel("Select Plot to Display Data"))
        self.plotSelectComboBox = QComboBox()
        for dock in self.plotDocks:
            title = dock.windowTitle() if hasattr(dock, "windowTitle") else str(dock)
            self.plotSelectComboBox.addItem(title, dock)
        self.plotSelectComboBox.currentIndexChanged.connect(self.updatePlot)
        self.interfaceLayout.addWidget(self.plotSelectComboBox)

        if self.fileType == "png":
            
            # 위치 및 크기 입력란 생성
            self.interfaceLayout.addWidget(QLabel("Image Position and Size"))
            formLayout = QFormLayout()

            self.x0PosLineEdit = QLineEdit('0')
            formLayout.addRow('좌 하단 x 위치:', self.x0PosLineEdit)
            self.y0PosLineEdit = QLineEdit('0')
            formLayout.addRow('좌 하단 y 위치:', self.y0PosLineEdit)
            self.x1PosLineEdit = QLineEdit(str(self.data.shape[1]))
            formLayout.addRow('우 상단 x 위치:', self.x1PosLineEdit)
            self.y1PosLineEdit = QLineEdit(str(self.data.shape[0]))
            formLayout.addRow('우 상단 y 위치:', self.y1PosLineEdit)

            # 투명도 조절
            self.opacityLineEdit = QLineEdit("1.0")
            formLayout.addRow("Opacity (0.0 - 1.0):", self.opacityLineEdit)

            self.interfaceLayout.addLayout(formLayout)

            # 입력 종료 시 플롯 갱신
            for le in (self.x0PosLineEdit, self.y0PosLineEdit, self.x1PosLineEdit, self.y1PosLineEdit, self.opacityLineEdit):
                le.editingFinished.connect(lambda _le=le: self.updatePlot(setSliderMax=False))

        elif self.fileType == "csv" or self.fileType == "lis":

            # 과거 데이터 보이기 체크박스 생성
            self.showPastDataCheckBox = QCheckBox("Show Past Data")
            self.showPastDataCheckBox.setChecked(True)
            self.interfaceLayout.addWidget(self.showPastDataCheckBox)

            # y축 데이터 체크박스 생성
            self.yAxisCheckBoxes = []
            self.yAxisCheckBoxLayout = QGridLayout()
            self.interfaceLayout.addWidget(QLabel("Y-Axis Data"))
            self.interfaceLayout.addLayout(self.yAxisCheckBoxLayout)

            for i, column in enumerate(self.dataColumnNames):
                checkbox = QCheckBox(column)
                checkbox.stateChanged.connect(self.updatePlot)
                self.yAxisCheckBoxLayout.addWidget(checkbox, i // 3, i % 3)
                self.yAxisCheckBoxes.append(checkbox)

            # x축 데이터 콤보박스 생성
            self.interfaceLayout.addWidget(QLabel("X-Axis Data"))
            self.xAxisComboBox = QComboBox()
            self.xAxisComboBox.addItems(self.dataColumnNames)
            self.xAxisComboBox.currentIndexChanged.connect(self.updatePlot)
            self.interfaceLayout.addWidget(self.xAxisComboBox)

            # 데이터 슬라이더 생성
            self.interfaceLayout.addWidget(QLabel("Data Length"))
            self.lengthSlider = QSlider(Qt.Orientation.Horizontal)
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
            for w in self.frame.findChildren(QWidget): w.installEventFilter(self._wheelFilter)

        # 이전 UI 상태 복원
        self._restoreUIState(prev_state)

    def refreshPlotSelectComboBox(self):

        """
            Plot 선택 콤보박스를 갱신하는 메서드
        """

        self.plotSelectComboBox.blockSignals(True)
        self.plotSelectComboBox.clear()
        for dock in self.plotDocks:
            title = dock.windowTitle() if hasattr(dock, "windowTitle") else str(dock)
            self.plotSelectComboBox.addItem(title, dock)
        self.plotSelectComboBox.blockSignals(False)

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

    def updatePlot(self, setSliderMax=True):

        """
            Plot을 업데이트하는 메서드
        """

        # 선택된 PlotDock 가져오기
        selected_dock = self.plotSelectComboBox.currentData()
        if selected_dock is None or not hasattr(selected_dock, "plotWidget"):
            logging.info("Error: No PlotDock selected (or invalid dock).")
            return
        
        interface_id = id(self)
        sendingData = {'title': f"IF {interface_id}"}

        if self.fileType == 'png':
            sendingData['file_type'] = self.fileType

            # 이미지 데이터 전송
            sendingData['image'] = self.data
            selected_dock.data[interface_id] = sendingData

            # 이미지 위치 및 크기 설정
            try:
                x0 = float(self.x0PosLineEdit.text())
                y0 = float(self.y0PosLineEdit.text())
                x1 = float(self.x1PosLineEdit.text())
                y1 = float(self.y1PosLineEdit.text())
                opacity = float(self.opacityLineEdit.text())
                sendingData['image_pos'] = (x0, y0, x1, y1)
                sendingData['image_opacity'] = opacity
            except ValueError:
                logging.info("Error: Invalid image position/size values.")
                return
        
        elif self.fileType in ['csv', 'lis']:
            sendingData['file_type'] = self.fileType

            # x축 데이터 가져오기
            x_data = self.xAxisComboBox.currentText()
            if x_data not in self.dataColumnNames:
                logging.info(f"Error: X-axis data '{x_data}' not found in columns.")
                return

            # y축 데이터 가져오기
            y_data_columns = [cb.text() for cb in self.yAxisCheckBoxes if cb.isChecked()]
            
            # 슬라이더 최대치 데이터 길이에 맞추기
            max_len = len(self.data)
            if self.lengthSlider.maximum() != max_len:
                self.lengthSlider.blockSignals(True)
                self.lengthSlider.setMaximum(max_len)
                if self.lengthSlider.value() > max_len: self.lengthSlider.setValue(max_len)
                self.lengthSlider.blockSignals(False)

            n = min(self.lengthSlider.value(), max_len)
            if n <= 0: return
            if setSliderMax:
                self.lengthSlider.setValue(max_len)
                n = max_len
            
            # n, % 라벨 갱신
            self.updateLengthLabel(n, max_len)

            x = self.data[x_data].iloc[:n]
            ys = {y_name: self.data[y_name].iloc[:n] for y_name in y_data_columns}

            sendingData['x'] = x
            sendingData['ys'] = ys

        # PlotDock에 내 데이터 저장 후, PlotDock이 통합 렌더링
        selected_dock.data[interface_id] = sendingData
        selected_dock.refreshPlot()

    def delete(self):

        """
            PlotWidget과 인터페이스를 삭제하는 메서드
        """

        # PlotDock에서 데이터 제거 및 갱신
        for dock in self.plotDocks:
            interface_id = id(self)
            if interface_id in dock.data:
                dock.data.pop(interface_id, None)
                dock.refreshPlot()

        self.frame.deleteLater()  # QFrame 삭제
        logging.info("Plot deleted.")

    def showTooltip(self, message):
        
        # DataInterface는 QWidget이 아니므로, 실제 위젯(frame)을 기준으로 툴팁 표시
        anchor = getattr(self, "frame", None)
        if anchor is None:
            logging.info(f"Tooltip: {message}")
            return

        global_pos = anchor.mapToGlobal(anchor.rect().center())
        QToolTip.showText(global_pos, message, anchor)

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