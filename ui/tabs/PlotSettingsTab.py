from PyQt6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QFormLayout, QPushButton, QHBoxLayout, QLabel, QGroupBox
from PyQt6.QtCore import Qt

import logging

# ui에서 import
from ui.PlotDock import PlotDock
from ui.DataInterface import DataInterface

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from main import MainWindow

def createPlotSettingsTab(self: "MainWindow"):

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
    addPlotButton.clicked.connect(lambda: createPlotDock(self))
    addDataButton.clicked.connect(lambda: createDataInterface(self))
    self.formLayout2.addRow("", btnRow)

def createPlotDock(self: "MainWindow"):

    """
        새로운 PlotDock을 생성하는 메서드
    """

    # PlotDock 생성
    dock = PlotDock(f"Graph {self.plotIndex}", self.leftWidget)
    self.plotIndex += 1
    self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
    self.plotDocks.append(dock)

    # 닫혀서 delete될 때 리스트에서 제거되도록 연결
    dock.closed.connect(lambda obj=dock: destroyPlotDock(self, obj))

    # 각 DataInterface의 plotSelectComboBox에 새 PlotDock 추가
    for data_interface in self.plotInterfaces: data_interface.refreshPlotSelectComboBox()

def createDataInterface(self: "MainWindow"):

    """
        새로운 DataInterface를 생성하는 메서드
    """

    data_interface = DataInterface(self.ssh, self.plotDocks, self.dataPathHistory)

    # 접이식 컨테이너
    group = QGroupBox(f'{data_interface.interface_id}')
    group.setCheckable(True)
    group.setChecked(True)

    v = QVBoxLayout(group)
    v.setContentsMargins(8, 8, 8, 8)
    v.addWidget(data_interface.frame)

    # 체크 상태로 내부 show/hide
    group.toggled.connect(data_interface.frame.setVisible)

    # 기존 formLayout2에 넣되, label은 없애자(남는 문제 줄임)
    self.formLayout2.addRow(group)

    # delete 때 group까지 지우도록 참조 저장
    data_interface._container = group

    self.plotInterfaces.append(data_interface)
    logging.info(f"DataInterface created. Total interfaces: {len(self.plotInterfaces)}")

def destroyPlotDock(self: "MainWindow", dock_obj: PlotDock):

    """
        PlotDock이 close되어 삭제되면 호출됨.
        self.plotDocks에서 제거 + UI 갱신.

        Args:
            dock_obj (PlotDock): 삭제될 PlotDock 객체
    """

    # destroyed 시점엔 이미 QObject만 남을 수 있어서, id 기반으로 제거
    before = len(self.plotDocks)
    self.plotDocks.remove(dock_obj)
    after = len(self.plotDocks)
    logging.info(f"PlotDock destroyed. plotDocks: {before} -> {after}")

    # DataInterface 콤보박스 갱신
    for data_interface in self.plotInterfaces:
        data_interface.refreshDataUI()