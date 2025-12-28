import sys
from PyQt5.QtWidgets import QWidget, QRubberBand, QApplication
from PyQt5.QtCore import Qt, QPoint, QRect
from PyQt5.QtGui import QPainter, QColor, QPen

class ScreenCapture:
    @staticmethod
    def capture_rect(rect, save_path=None):
        screen = QApplication.primaryScreen()
        # 直接抓取指定区域
        pixmap = screen.grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height())
        
        if not save_path:
            import tempfile
            import os
            temp_dir = tempfile.gettempdir()
            save_path = os.path.join(temp_dir, "screenshot_temp.png")
        
        pixmap.save(save_path, "png")
        return save_path

class ScreenSelector(QWidget):
    """
    全屏遮罩窗口，用于选择区域
    """
    selection_done = None

    def __init__(self):
        super().__init__()
        # 设置窗口标志
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        # 背景透明
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        
        # 获取当前鼠标所在屏幕的几何信息（逻辑坐标）
        cursor_pos = QApplication.desktop().cursor().pos()
        screen_number = QApplication.desktop().screenNumber(cursor_pos)
        screen_rect = QApplication.desktop().screenGeometry(screen_number)
        self.setGeometry(screen_rect)
        
        self.begin = QPoint()
        self.end = QPoint()
        self.rubber_band = QRubberBand(QRubberBand.Rectangle, self)
        
        # 设置橡皮筋样式
        self.rubber_band.setStyleSheet("""
            QRubberBand {
                border: 2px dashed red;
                background-color: rgba(255, 255, 255, 50);
            }
        """)

    def showEvent(self, event):
        super().showEvent(event)
        self.activateWindow()
        self.raise_()
        self.setFocus()

    def paintEvent(self, event):
        # 绘制半透明黑色背景
        painter = QPainter(self)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 100))
        painter.drawRect(self.rect())

    def mousePressEvent(self, event):
        self.begin = event.pos()
        self.rubber_band.setGeometry(QRect(self.begin, self.begin))
        self.rubber_band.show()

    def mouseMoveEvent(self, event):
        if self.rubber_band.isVisible():
            self.rubber_band.setGeometry(QRect(self.begin, event.pos()).normalized())

    def mouseReleaseEvent(self, event):
        if self.rubber_band.isVisible():
            self.rubber_band.hide()
            rect = self.rubber_band.geometry()
            # 忽略太小的误触
            if rect.width() < 5 or rect.height() < 5:
                self.close()
                return
            
            self.close()
            if ScreenSelector.selection_done:
                ScreenSelector.selection_done(rect)