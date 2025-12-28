import sys
import os
import copy
import keyboard
from PyQt5.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, QAction)
from PyQt5.QtCore import (Qt, QPoint, QObject) # 修正：添加了 QObject
from PyQt5.QtGui import (QIcon, QPixmap, QColor, QCursor, QPalette)

# 导入本地模块
from config import SettingsManager, DEFAULT_WINDOW_CONFIG
from ui import TranslationWindow, SettingsDialog

# --- System Tray & Main Management ---

class TrayIconManager(QObject):
    def __init__(self, app, sm):
        super().__init__()
        self.app = app
        self.sm = sm
        self.windows = []
        self.tray_icon = QSystemTrayIcon()
        icon_path = os.path.join("assets/ui", "app_icon.png")
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else:
            pixmap = QPixmap(64, 64)
            pixmap.fill(Qt.blue)
            self.tray_icon.setIcon(QIcon(pixmap))
        menu = QMenu()
        action_restore = QAction("还原所有窗口", self)
        action_restore.triggered.connect(self.restore_all)
        menu.addAction(action_restore)
        action_new_win = QAction("新建翻译窗口", self)
        action_new_win.triggered.connect(self.create_new_window)
        menu.addAction(action_new_win)
        action_settings = QAction("设置", self)
        action_settings.triggered.connect(self.open_global_settings)
        menu.addAction(action_settings)
        menu.addSeparator()
        action_exit = QAction("关闭程序", self)
        action_exit.triggered.connect(self.quit_app)
        menu.addAction(action_exit)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def create_new_window(self):
        new_win_config = copy.deepcopy(DEFAULT_WINDOW_CONFIG)
        self.sm.data['windows'].append(new_win_config)
        self.sm.save()
        idx = len(self.sm.data['windows']) - 1
        win = TranslationWindow(idx, self.sm, self)
        win.show()
        self.windows.append(win)
        # 更新设置对话框（如果打开着）
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, SettingsDialog):
                widget.build_window_tabs()
                widget.load_data()

    def restore_all(self):
        for win in self.windows:
            if not win.isVisible():
                win.show()
                win.raise_()
                win.activateWindow()

    def open_global_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec_()
        for win in self.windows:
            win.apply_style()

    def on_window_closed(self, index):
        self.windows = [w for w in self.windows if w.window_index != index]
        if not self.windows:
            if self.sm.data['global'].get('close_to_tray', True):
                pass 
            else:
                self.quit_app()

    def quit_app(self):
        self.tray_icon.hide()
        keyboard.unhook_all()
        self.app.quit()

if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    QApplication.setQuitOnLastWindowClosed(False)
    app = QApplication(sys.argv)
    
    # 初始化资源目录
    if not os.path.exists("assets/ui"):
        os.makedirs("assets/ui")
        
    # 加载配置并初始化管理器
    sm = SettingsManager()
    tim = TrayIconManager(app, sm)
    
    # 启动现有窗口
    if not sm.data.get('windows'):
        sm.data['windows'] = [copy.deepcopy(DEFAULT_WINDOW_CONFIG)]
        sm.save()
        
    for i in range(len(sm.data['windows'])):
        win = TranslationWindow(i, sm, tim)
        win.show()
        tim.windows.append(win)
        
    sys.exit(app.exec_())