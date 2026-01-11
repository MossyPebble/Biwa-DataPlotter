from PyQt6.QtWidgets import QWidget, QFormLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QCheckBox

import os, logging

# utils에서 import
from utils.utils import parseParamsFile

# ui에서 import
from ui.ParamRowWidget import ParamRowWidget

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from main import MainWindow

def createQuickParamsTab(self: "MainWindow"):

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

    initializeQuickParamsTab(self)

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
    loadParamsButton.clicked.connect(lambda: loadParamsFileHandler(self))

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
    updateParamsDisplay(self, self.params)

def initializeQuickParamsTab(self: "MainWindow"):

    """
        Quick Params 탭 초기화
    """

    self.params = {'sample1': {'value': 10, 'favorite': False}, 'sample2': {'value': 20, 'favorite': True}}
    self.fav_params = {}

def loadParamsFileHandler(self: "MainWindow"):

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

        # Params 디스플레이 갱신
        updateParamsDisplay(self, self.params)

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

        Args:
            params (dict): 파라미터 딕셔너리
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
        row = ParamRowWidget(key, params, lambda: updateParamsDisplay(self, self.params))
        self.paramsDisplayLayout.addRow(row)