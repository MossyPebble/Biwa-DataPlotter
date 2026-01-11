from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QLineEdit, QMenu
from PyQt6.QtCore import Qt

class ParamRowWidget(QWidget):

    """
        params 구조: params[key] == {"value": ..., "favorite": bool}

        Args:
            key (str): 파라미터 이름
            params_ref (dict): 파라미터 사전 참조
            on_fav_changed (callable, optional): favorite 상태 변경 시 호출할 콜백 함수
            parent (QWidget, optional): 부모 위젯
    """

    def __init__(
            self, 
            key: str, 
            params_ref: dict, 
            on_fav_changed: 
            callable=None, 
            parent=None
        ):

        super().__init__(parent)
        self.key = key
        self.params_ref = params_ref
        self.on_fav_changed = on_fav_changed  # favorite 바뀌면 재정렬용 콜백

        # 초기값 저장
        self.initValue = params_ref.get(key, {}).get("value", "")

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.favBtn = QPushButton()
        self.favBtn.setFixedWidth(40)
        self.favBtn.setCheckable(True)
        self.favBtn.toggled.connect(self._toggle_fav)

        self.keyLabel = QLabel(key)
        self.keyLabel.setMinimumWidth(140)

        self.valueEdit = QLineEdit()
        self.valueEdit.setMinimumWidth(120)
        self.valueEdit.editingFinished.connect(self._commit_value)

        self.b_m10 = QPushButton("-10%"); self.b_m10.setFixedWidth(70)
        self.b_m5  = QPushButton("-5%");  self.b_m5.setFixedWidth(70)
        self.b_p5  = QPushButton("+5%");  self.b_p5.setFixedWidth(70)
        self.b_p10 = QPushButton("+10%"); self.b_p10.setFixedWidth(70)

        self.b_m10.clicked.connect(lambda: self._apply_percent(-0.10))
        self.b_m5.clicked.connect(lambda: self._apply_percent(-0.05))
        self.b_p5.clicked.connect(lambda: self._apply_percent(+0.05))
        self.b_p10.clicked.connect(lambda: self._apply_percent(+0.10))

        self.layout.addWidget(self.favBtn)
        self.layout.addWidget(self.keyLabel)
        self.layout.addWidget(self.valueEdit, 1)
        self.layout.addWidget(self.b_m10)
        self.layout.addWidget(self.b_m5)
        self.layout.addWidget(self.b_p5)
        self.layout.addWidget(self.b_p10)

        # 우클릭 메뉴
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.showMouseRightClickMenu)

        self.refresh_from_model()

    def showMouseRightClickMenu(self, pos): 
        menu = QMenu(self)

        menu.addAction('Reset to Reference', lambda: self.valueEdit.setText(str(self.initValue)))
        menu.addSeparator()
        menu.addAction("Set as Favorite", lambda: self.favBtn.setChecked(True))
        menu.addAction("Unset Favorite", lambda: self.favBtn.setChecked(False))

        menu.exec(self.mapToGlobal(pos))

    def refresh_from_model(self):
        entry = self.params_ref.get(self.key, {})
        fav = bool(entry.get("favorite", False))
        val = entry.get("value", "")
        self.favBtn.blockSignals(True)
        self.favBtn.setChecked(fav)
        self.favBtn.blockSignals(False)
        self.favBtn.setText("★" if fav else "☆")
        self.valueEdit.setText(str(val))

    def _toggle_fav(self, checked: bool):
        self.params_ref[self.key]["favorite"] = bool(checked)
        if callable(self.on_fav_changed): self.on_fav_changed()

    def _commit_value(self): self.params_ref[self.key]["value"] = self.valueEdit.text().strip()

    def _apply_percent(self, percent: float):
        raw = self.valueEdit.text().strip()
        try: x = float(raw)
        except ValueError: return
        new_x = x * (1.0 + percent)
        out = str(int(round(new_x))) if abs(new_x - round(new_x)) < 1e-12 else f"{new_x:.6g}"
        self.valueEdit.setText(out)
        self.params_ref[self.key]["value"] = out