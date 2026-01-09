import logging
from PyQt6.QtWidgets import QDockWidget, QFileDialog
from PyQt6.QtGui import QAction, QTransform
from PyQt6.QtCore import pyqtSignal, QRectF
from PyQt6.QtGui import QImage
import pyqtgraph as pg
import numpy as np

from utils.utils import fmt_hybrid

class PlotDock(QDockWidget):
    closed = pyqtSignal(object)

    def __init__(self, title, parent):
        super().__init__(title, parent)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        self.plotWidget = pg.PlotWidget()
        self.setWidget(self.plotWidget)
        self.plotWidget.setBackground((255, 255, 255))
        self.setFloating(False)

        self.plotColors = ['r', 'g', 'b', 'c', 'm', 'y', 'w']
        self.plotColorsIndex = 0
        self.legend = self.plotWidget.addLegend()

        self.setPlotStyle()

        # data 포맷(예시):
        # self.data[interface_id] = {
        #   "title": "Interface A",
        #   "x": x_series,
        #   "ys": { "voltage": y_series, "current": y_series2, ... },
        # }
        self.data: dict[object, dict] = {}

        # 마우스를 따라다니는 라벨: TextItem
        self.tip = pg.TextItem(
            text="",
            anchor=(0, 1),   # (x,y) 기준점: 왼쪽-위
            border=pg.mkPen(width=1),
            fill=pg.mkBrush(255, 255, 255, 200),
            color=(0, 0, 0)
        )
        self.tip.setZValue(10)
        self.plotWidget.addItem(self.tip, ignoreBounds=True)

        # mouse move 이벤트
        self.proxy = pg.SignalProxy(
            self.plotWidget.scene().sigMouseMoved,
            rateLimit=60,
            slot=self.on_mouse_moved
        )

        self.hoverEnabled = True

        # 우클 메뉴 항목 추가
        self.setExtraMenuItems()

        # 이미지 overlay
        self._img_item: pg.ImageItem = None
        self._overlayPath: str = None

    def showImageOverlayArray(
        self,
        img: np.ndarray,
        x0: float = 0.0,
        y0: float = 0.0,
        x1: float = None,
        y1: float = None,
        opacity: float = 1.0
    ):
        """
        ✅ 좌측 하단 (x0,y0) + 우측 상단 (x1,y1) 기준으로 이미지 오버레이
        """
        if img is None:
            return
        if x1 is None or y1 is None:
            raise ValueError("showImageOverlayArray requires x1 and y1 (top-right corner).")

        opacity = max(0.0, min(1.0, float(opacity)))

        arr = np.asarray(img)
        if arr.ndim == 2:
            arr = np.stack([arr, arr, arr, np.full_like(arr, 255)], axis=-1)
        if arr.ndim != 3 or arr.shape[2] not in (3, 4):
            raise ValueError(f"Unsupported image shape: {arr.shape}")
        if arr.dtype != np.uint8:
            arr = arr.astype(np.uint8, copy=False)
        if arr.shape[2] == 3:
            alpha = np.full((arr.shape[0], arr.shape[1], 1), 255, dtype=np.uint8)
            arr = np.concatenate([arr, alpha], axis=2)

        arr = arr.copy()
        H, W = arr.shape[0], arr.shape[1]

        # clear()로 씬에서 빠질 수 있으니 항상 재-add 보장
        if self._img_item is None:
            self._img_item = pg.ImageItem(axisOrder="row-major")
            self._img_item.setZValue(-10)
        if self._img_item.scene() is None:
            self.plotWidget.addItem(self._img_item, ignoreBounds=True)

        self._img_item.setOpacity(opacity)

        self._img_item.setImage(arr, autoLevels=False, axisOrder="row-major")

        # (x0,y0)~(x1,y1) -> w,h
        x0 = float(x0)
        y0 = float(y0)
        x1 = float(x1)
        y1 = float(y1)
        w = x1 - x0
        h = y1 - y0

        # 음수도 정규화
        if w < 0:
            x0, x1 = x1, x0
            w = -w
        if h < 0:
            y0, y1 = y1, y0
            h = -h

        sx = w / float(W)
        sy = -h / float(H)   # 이미지 row-major를 plot y-up으로 맞추기 위해 y 뒤집기
        dx = x0
        dy = y1              # ✅ top(y1)에 맞춤 (뒤집었기 때문)

        tr = QTransform()
        tr.setMatrix(
            sx, 0.0, 0.0,
            0.0, sy, 0.0,
            dx, dy, 1.0
        )
        self._img_item.setTransform(tr)

    def clearImageOverlay(self):
        if self._img_item is not None:
            try:
                self.plotWidget.removeItem(self._img_item)
            except Exception:
                pass
            self._img_item = None

    def setExtraMenuItems(self):
        vb = self.plotWidget.getPlotItem().getViewBox()
        menu = vb.menu  # pyqtgraph 기본 메뉴 객체 (ViewBoxMenu)
        if menu is None:
            return

        # -----------------------------
        # Hover 토글
        # -----------------------------
        act = QAction("Hover Mouse Position", self)
        act.setCheckable(True)
        act.setChecked(True)

        def _toggle(checked: bool):
            self.hoverEnabled = checked
            if not checked:
                try:
                    self.plotWidget.removeItem(self.tip)
                except Exception:
                    pass
            else:
                if self.tip.scene() is None:
                    self.plotWidget.addItem(self.tip, ignoreBounds=True)

        act.toggled.connect(_toggle)
        menu.addSeparator()
        menu.addAction(act)
        self._toggleHoverAction = act  # GC 방지/상태 유지용

        # -----------------------------
        # Image overlay 메뉴 추가
        # -----------------------------
        openAct = QAction("Overlay Image...", self)

        def _openOverlay():
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Select image to overlay",
                "",
                "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff);;All Files (*.*)",
            )
            if not path:
                return

            self._overlayPath = path

            # 기본 배치: 현재 보이는 뷰 영역에 꽉 차게
            vb2 = self.plotWidget.getPlotItem().getViewBox()
            (x0, x1), (y0, y1) = vb2.viewRange()
            self.showImageOverlay(path, x0=x0, y0=y0, w=(x1 - x0), h=(y1 - y0))

        openAct.triggered.connect(_openOverlay)
        menu.addAction(openAct)

        clearAct = QAction("Clear Overlay Image", self)

        def _clearOverlay():
            self._overlayPath = None
            self.clearImageOverlay()

        clearAct.triggered.connect(_clearOverlay)
        menu.addAction(clearAct)

        self._overlayOpenAction = openAct   # GC 방지
        self._overlayClearAction = clearAct # GC 방지

    def on_mouse_moved(self, evt):
        if not self.hoverEnabled: return

        pos = evt[0]
        pi = self.plotWidget.getPlotItem()
        vb = pi.getViewBox()

        if not vb.sceneBoundingRect().contains(pos):
            self.tip.setText("")
            return

        p = vb.mapSceneToView(pos)
        x, y = p.x(), p.y()
        x, y = float(p.x()), float(p.y())
        self.tip.setText(f"x: {fmt_hybrid(x)}\ny: {fmt_hybrid(y)}")

        # 위치는 View 좌표계 그대로 (항상 안전)
        xr, yr = vb.viewRange()
        dx = (xr[1] - xr[0]) * 0.02
        dy = (yr[1] - yr[0]) * 0.02
        self.tip.setPos(x + dx, y + dy)

    def setPlotStyle(self):
        self.legend.setLabelTextSize('25pt')
        self._x0_line = pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen((200, 200, 200), width=2))
        self._y0_line = pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen((200, 200, 200), width=2))
        self.plotWidget.addItem(self._x0_line, ignoreBounds=True)
        self.plotWidget.addItem(self._y0_line, ignoreBounds=True)

    def refreshPlot(self):
        self.clearImageOverlay()
        self.plotWidget.clear()
        self.legend = self.plotWidget.addLegend()
        self.plotColorsIndex = 0

        self.setPlotStyle()
        if self.hoverEnabled: self.plotWidget.addItem(self.tip, ignoreBounds=True)

        for interface_id, plot_data in self.data.items():

            # png 데이터일 경우 overlay로 처리
            if plot_data.get('file_type') == 'png':
                img = plot_data.get('image')
                pos = plot_data.get('image_pos', (0.0, 0.0, 10.0, 10.0))
                opacity = plot_data.get('image_opacity', 1.0)
                if img is not None:
                    self.showImageOverlayArray(
                        img,
                        x0=pos[0],
                        y0=pos[1],
                        x1=pos[2],
                        y1=pos[3],
                        opacity=opacity
                    )

                logging.info(f"Plotted PNG overlay for interface {interface_id}, position={pos}, opacity={opacity}")

            elif plot_data.get('file_type') in ['csv', 'lis']:
                x = plot_data.get("x")
                ys = plot_data.get("ys", {}) or {}
                title = plot_data.get("title", f"Interface {interface_id}")

                if x is None or not ys:
                    continue

                for series_name, y in ys.items():
                    color = self.plotColors[self.plotColorsIndex % len(self.plotColors)]
                    pen = pg.mkPen(color, width=2)

                    # 범례에 표시될 이름
                    legend_name = f"{title}: {series_name}"

                    self.plotWidget.plot(x, y, pen=pen, name=legend_name)
                    self.plotColorsIndex += 1

    def clearInterface(self, interface_id: object):

        """특정 interface의 레이어를 제거하고 다시 그림."""

        if interface_id in self.data:
            self.data.pop(interface_id, None)
            self.refreshPlot()

    def closeEvent(self, event):
        logging.info(f"Closing dock widget: {self.windowTitle()}")
        self.closed.emit(self)
        super().closeEvent(event)