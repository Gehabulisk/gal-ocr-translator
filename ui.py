import sys
import os
import json
import time
import keyboard
import threading
import copy
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QTextEdit, 
                             QSystemTrayIcon, QMenu, QAction, QInputDialog, 
                             QFormLayout, QLineEdit, QComboBox, QSpinBox, 
                             QDoubleSpinBox, QCheckBox, QDialog, QTabWidget,
                             QFileDialog, QSplitter, QFrame, QSizeGrip, QGroupBox, QMessageBox, QColorDialog, QGraphicsOpacityEffect)
from PyQt5.QtCore import (Qt, QPoint, QTimer, pyqtSignal, QObject, QSettings, QUrl, QRect, Q_ARG, QMetaObject, QSize)
from PyQt5.QtGui import (QIcon, QPixmap, QFont, QColor, QCursor, QDesktopServices, QPalette, QPainter, QPen)

# 导入本地模块
from config import SettingsManager, DEFAULT_GLOBAL_CONFIG, DEFAULT_WINDOW_CONFIG
from ai_api import AIChatAPI
from ocr import OCREngine
from screenshot import ScreenCapture, ScreenSelector

# --- UI Components ---

class IndicatorWindow(QWidget):
    def __init__(self, rect, window_name, parent=None):
        super().__init__(None)
        self.window_name = window_name
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setGeometry(rect)
        self.setVisible(True)
        self.raise_()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(Qt.red,3)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self.rect())
        painter.setPen(Qt.red)
        font = QFont("Arial", 12)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(10, 25, self.window_name)

# --- 后台工作线程 ---
class TranslationWorker(QObject):
    sig_status = pyqtSignal(str)
    sig_result = pyqtSignal(str)
    sig_error = pyqtSignal(str)

    def __init__(self, config, ocr_engine, ai_engine):
        super().__init__()
        self.config = config
        self.ocr = ocr_engine
        self.ai = ai_engine

    def run_task(self, mode, path, ocr_text):
        try:
            self.sig_status.emit("正在处理...")
            self.ocr.set_engine(self.config['ocr_engine'], self.config['ocr_lang'], self.config['tesseract_path'])
            if mode == 'ocr_to_ai' and path:
                self.sig_status.emit("正在进行OCR...")
                ocr_text = self.ocr.run_ocr(path)
            self.sig_status.emit("正在翻译...")
            self.ai.set_config(
                self.config['api_url'], self.config['api_key'], self.config['model'],
                self.config['prompt'], self.config['proxy'], 
                json.loads(self.config['custom_params'])
            )
            if mode == 'ocr_to_ai':
                res = self.ai.call_api(text_content=ocr_text)
            else:
                res = self.ai.call_api(image_path=path)
            self.sig_result.emit(res)
        except Exception as e:
            self.sig_error.emit(f"发生错误:\n{str(e)}")

class TranslationWindow(QMainWindow):
    def __init__(self, window_index, settings_manager, tray_icon_manager):
        super().__init__()
        self.window_index = window_index
        self.sm = settings_manager
        self.tim = tray_icon_manager # TrayIconManager instance
        
        self.config = self.sm.data['windows'][self.window_index] if self.window_index < len(self.sm.data['windows']) else copy.deepcopy(DEFAULT_WINDOW_CONFIG)
        self.global_config = self.sm.data['global']
        
        self.ai = AIChatAPI()
        self.ocr = OCREngine()
        self.worker = TranslationWorker(self.global_config, self.ocr, self.ai)
        self.worker.sig_status.connect(self.update_text_content)
        self.worker.sig_result.connect(self.on_translation_result)
        self.worker.sig_error.connect(self.on_translation_error)
        
        self.indicator = None
        self.last_image_path = None
        self.last_ocr_text = ""
        self.auto_timer = QTimer()
        self.auto_timer.timeout.connect(self.run_auto_mode)
        self.drag_position = None
        
        self.init_ui()
        self.apply_style()
        self.update_indicator()
        self.register_shortcuts()

    def init_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground) 
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)
        
        # 右键菜单
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        
        # --- 标题栏 ---
        title_bar = QWidget()
        title_bar.setObjectName("TitleBar")
        title_bar.setAutoFillBackground(True)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(5,0,5,0)
        title_lbl = QLabel(f"窗口 {self.window_index + 1}")
        title_lbl.setObjectName("TitleLabel")
        title_layout.addWidget(title_lbl)
        title_layout.addStretch()
        
        # --- 拖动大小句柄 (右上角) ---
        self.sizegrip = QSizeGrip(self)
        self.sizegrip.setVisible(True)
        title_layout.addWidget(self.sizegrip)
        
        layout.addWidget(title_bar)
        
        # 标题栏透明度效果
        self.titlebar_effect = QGraphicsOpacityEffect(title_bar)
        title_bar.setGraphicsEffect(self.titlebar_effect)
        
        # --- 按钮栏 ---
        toolbar = QWidget()
        toolbar.setObjectName("ToolBar")
        toolbar.setAutoFillBackground(True)
        self.layout_toolbar = QHBoxLayout(toolbar)
        self.layout_toolbar.addStretch(1) # 居中开始
        
        # 修正：按钮尺寸改回 32x32
        def create_btn(name, tooltip, callback, icon_file=None):
            btn = QPushButton("") # 无文字
            btn.setToolTip(tooltip) # 悬停显示文字
            btn.clicked.connect(callback)
            if icon_file:
                path = os.path.join("assets/ui", icon_file)
                if os.path.exists(path):
                    btn.setIcon(QIcon(path))
            btn.setFixedSize(32, 32) # 修正：尺寸改回32
            btn.setIconSize(QSize(24, 24)) # 修正：图标调整为24
            return btn
            
        self.btn_screenshot = create_btn("截图", "画框截屏并翻译", self.start_selection, "camera.png")
        self.btn_translate = create_btn("翻译", "翻译当前标定区域", self.capture_and_translate, "translate.png")
        self.btn_reselect = create_btn("选区", "修改截屏区域(不翻译)", self.start_selection_only, "screenshot.png")
        self.btn_toggle_ind = create_btn("指示", "显示/隐藏指示器", self.toggle_indicator, "eye.png")
        self.btn_retry = create_btn("重试", "使用旧图重新翻译", self.retry_translation, "retry.png")
        self.btn_auto = create_btn("自动", "开启/关闭自动模式", self.toggle_auto, "auto.png")
        self.btn_settings = create_btn("设置", "打开设置", self.open_settings, "settings.png")
        
        self.layout_toolbar.addWidget(self.btn_screenshot)
        self.layout_toolbar.addWidget(self.btn_translate)
        self.layout_toolbar.addWidget(self.btn_reselect)
        self.layout_toolbar.addWidget(self.btn_toggle_ind)
        self.layout_toolbar.addWidget(self.btn_retry)
        self.layout_toolbar.addWidget(self.btn_auto)
        self.layout_toolbar.addWidget(self.btn_settings)
        self.layout_toolbar.addStretch(1) # 居中结束
        
        # 按钮栏透明度效果
        self.toolbar_effect = QGraphicsOpacityEffect(toolbar)
        toolbar.setGraphicsEffect(self.toolbar_effect)
        
        layout.addWidget(toolbar)
        
        # --- 翻译文本区 ---
        self.text_edit = QTextEdit()
        self.text_edit.setObjectName("TransText")
        self.text_edit.setReadOnly(True)
        self.text_edit.setFrameShape(QFrame.NoFrame)
        self.text_edit.setAutoFillBackground(True)
        layout.addWidget(self.text_edit)

    def show_context_menu(self, pos):
        menu = QMenu(self)
        action_close = QAction("关闭窗口", self)
        action_close.triggered.connect(self.close_window)
        menu.addAction(action_close)
        menu.exec_(self.mapToGlobal(pos))

    def resizeEvent(self, event):
        lock_size = self.config.get('window_style', {}).get('lock_size', False)
        if not lock_size:
            ws = self.config.setdefault('window_style', {})
            ws['width'] = self.width()
            ws['height'] = self.height()
            self.sm.save()
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.drag_position:
            self.move(event.globalPos() - self.drag_position)
            self.save_current_position()
            event.accept()

    def save_current_position(self):
        p = self.pos()
        self.config['win_pos'] = {"x": p.x(), "y": p.y()}
        self.sm.save()

    def showEvent(self, event):
        super().showEvent(event)
        self.update_indicator()

    def enterEvent(self, event):
        self.apply_style(is_hover=True)

    def leaveEvent(self, event):
        self.apply_style(is_hover=False)

    def apply_style(self, is_hover=False):
        if self.window_index < len(self.sm.data['windows']):
            self.config = self.sm.data['windows'][self.window_index]
        
        style = self.global_config['window_style']
        local_ws = self.config.get('window_style', {})
        final_style = copy.deepcopy(DEFAULT_GLOBAL_CONFIG['window_style'])
        final_style.update(style)
        final_style.update(local_ws)
        
        self.resize(final_style['width'], final_style['height'])
        
        win_pos = self.config.get('win_pos', {"x": 100, "y": 100})
        if self.pos() == QPoint(0,0):
            self.move(win_pos['x'], win_pos['y'])
        
        font = QFont()
        font.setPointSize(final_style['font_size'])
        self.text_edit.setFont(font)
        
        # --- 样式应用 ---
        top_op_val = final_style['hover_opacity'] if is_hover else final_style['top_opacity']
        top_bg_c = QColor(final_style.get('top_bg_color', '#2B2B2B'))
        
        self.titlebar_effect.setOpacity(top_op_val)
        self.toolbar_effect.setOpacity(top_op_val)
        
        self.findChild(QWidget, "TitleBar").setStyleSheet(f"""
            QWidget#TitleBar {{
                background-color: rgb({top_bg_c.red()}, {top_bg_c.green()}, {top_bg_c.blue()});
                height: 30px;
            }}
            QLabel#TitleLabel {{ background-color: transparent; color: black; font-weight: bold; }} 
        """)
        
        self.findChild(QWidget, "ToolBar").setStyleSheet(f"""
            QWidget#ToolBar {{
                background-color: rgb({top_bg_c.red()}, {top_bg_c.green()}, {top_bg_c.blue()});
            }}
            QPushButton {{
                background-color: #E0E0E0;
                border: 1px solid #AAAAAA;
                border-radius: 4px;
                padding: 2px;
            }}
            QPushButton:hover {{
                background-color: #D0D0D0;
            }}
        """)
        
        # 翻译框样式
        bg_c = QColor(final_style.get('text_bg_color', '#FFFFFFCC'))
        text_c = QColor(final_style.get('text_color', '#000000'))
        
        border_style = ""
        enable_border = final_style.get('enable_text_border', False)
        if enable_border:
            border_c = QColor(final_style.get('text_border_color', '#FF0000'))
            border_style = f"border: 2px solid rgba({border_c.red()}, {border_c.green()}, {border_c.blue()}, {border_c.alpha()});"
        
        self.text_edit.setStyleSheet(f"""
            QTextEdit#TransText {{
                background-color: rgba({bg_c.red()}, {bg_c.green()}, {bg_c.blue()}, {bg_c.alpha()}); 
                color: rgba({text_c.red()}, {text_c.green()}, {text_c.blue()}, {text_c.alpha()});
                border: none;
                {border_style}
            }}
        """)
        
        # --- 锁定大小逻辑 ---
        lock_size = final_style.get('lock_size', False)
        if lock_size:
            self.sizegrip.hide()
            self.sizegrip.setEnabled(False)
        else:
            self.sizegrip.show()
            self.sizegrip.setEnabled(True)
            
        t_path = self.global_config.get('tesseract_path', '')
        self.ocr.set_engine(self.global_config['ocr_engine'], self.global_config['ocr_lang'], t_path)

    # --- 信号槽 ---
    def update_text_content(self, text):
        self.text_edit.setText(text)
    def on_translation_result(self, res):
        self.setWindowOpacity(1.0)
        self.text_edit.setText(res)
        self.apply_style()
    def on_translation_error(self, err):
        self.text_edit.setTextColor(QColor("red"))
        self.text_edit.setText(err)

    # --- 指示器 ---
    def update_indicator(self):
        if self.indicator:
            self.indicator.close()
            self.indicator = None
        if self.config.get('show_indicator', True):
            r = self.config['region']
            rect = QRect(r['x'], r['y'], r['w'], r['h'])
            self.indicator = IndicatorWindow(rect, f"窗口 {self.window_index + 1}")
            self.indicator.raise_()

    def toggle_indicator(self):
        self.config['show_indicator'] = not self.config.get('show_indicator', True)
        self.sm.save()
        self.update_indicator()

    def start_selection(self):
        self.stop_auto()
        self.hide() 
        if self.indicator: 
            self.indicator.close()
            self.indicator = None
        self.selector = ScreenSelector()
        ScreenSelector.selection_done = self.on_area_selected_then_translate
        self.selector.show()

    def start_selection_only(self):
        self.stop_auto()
        self.hide() 
        if self.indicator: 
            self.indicator.close()
            self.indicator = None
        self.selector = ScreenSelector()
        ScreenSelector.selection_done = self.on_area_selected_only
        self.selector.show()

    def on_area_selected_then_translate(self, rect):
        self.config['region'] = {"x": rect.x(), "y": rect.y(), "w": rect.width(), "h": rect.height()}
        self.sm.save()
        self.show()
        self.update_indicator()
        self.capture_and_translate()
        if hasattr(self, 'selector'): self.selector = None

    def on_area_selected_only(self, rect):
        self.config['region'] = {"x": rect.x(), "y": rect.y(), "w": rect.width(), "h": rect.height()}
        self.sm.save()
        self.show()
        self.update_indicator()
        if hasattr(self, 'selector'): self.selector = None

    def capture_and_translate(self):
        interrupt = self.global_config['auto_mode'].get('interrupt_on_manual', True)
        if self.auto_timer.isActive():
            if interrupt:
                self.stop_auto()
            else: pass 
        self.do_process_async()
        if not interrupt and self.global_config['auto_mode'].get('enabled', False):
            interval = self.global_config['auto_mode']['interval'] * 1000
            self.auto_timer.start(interval)

    def retry_translation(self):
        interrupt = self.global_config['auto_mode'].get('interrupt_on_manual', True)
        if self.auto_timer.isActive():
            if interrupt:
                self.stop_auto()
            else: pass
        if self.last_image_path and os.path.exists(self.last_image_path):
            self.update_text_content("正在重试...")
            mode = self.global_config.get('mode', 'ocr_to_ai')
            threading.Thread(target=self.worker.run_task, args=(mode, self.last_image_path, self.last_ocr_text)).start()
        if not interrupt and self.global_config['auto_mode'].get('enabled', False):
            interval = self.global_config['auto_mode']['interval'] * 1000
            self.auto_timer.start(interval)

    def do_process_async(self):
        try:
            r = self.config['region']
            screen = QApplication.primaryScreen()
            logical_rect = QRect(r['x'], r['y'], r['w'], r['h'])
            path = ScreenCapture.capture_rect(logical_rect)
            self.last_image_path = path
            mode = self.global_config.get('mode', 'ocr_to_ai')
            threading.Thread(target=self.worker.run_task, args=(mode, path, "")).start()
        except Exception as e:
            self.text_edit.setTextColor(QColor("red"))
            self.text_edit.setText(f"发生错误:\n{str(e)}")

    def translate_result(self, img_path, ocr_text):
        self.setWindowOpacity(1.0)
        mode = self.global_config.get('mode', 'ocr_to_ai')
        threading.Thread(target=self.worker.run_task, args=(mode, img_path, ocr_text)).start()

    def toggle_auto(self):
        if self.auto_timer.isActive(): self.stop_auto()
        else: self.start_auto()

    def start_auto(self):
        self.global_config['auto_mode']['enabled'] = True
        self.sm.save()
        self.btn_auto.setText("停止")
        self.run_auto_mode()

    def stop_auto(self):
        self.auto_timer.stop()
        self.global_config['auto_mode']['enabled'] = False
        self.sm.save()
        self.btn_auto.setText("自动")

    def run_auto_mode(self):
        try:
            r = self.config['region']
            screen = QApplication.primaryScreen()
            logical_rect = QRect(r['x'], r['y'], r['w'], r['h'])
            path = ScreenCapture.capture_rect(logical_rect)
            self.last_image_path = path
            current_ocr_text = ""
            mode = self.global_config.get('mode', 'ocr_to_ai')
            if mode == 'ocr_to_ai':
                current_ocr_text = self.ocr.run_ocr(path)
            content_changed = False
            if mode == 'ocr_to_ai':
                if current_ocr_text != self.last_ocr_text:
                    content_changed = True
                    self.last_ocr_text = current_ocr_text
            else:
                content_changed = True
            if content_changed:
                self.translate_result(path if mode=='direct_ai' else None, 
                                      current_ocr_text if mode=='ocr_to_ai' else None)
            interval = self.global_config['auto_mode']['interval'] * 1000
            self.auto_timer.start(interval)
        except Exception as e:
            print(f"Auto loop error: {e}")
            interval = self.global_config['auto_mode']['interval'] * 1000
            self.auto_timer.start(interval)

    def register_shortcuts(self):
        sk = self.config.get('shortcuts', DEFAULT_WINDOW_CONFIG['shortcuts'])
        def add_hotkey(key, func):
            try: keyboard.add_hotkey(key, func)
            except Exception as e: print(f"Hotkey {key} failed: {e}")
        add_hotkey(sk['screenshot'], self.start_selection)
        add_hotkey(sk['translate_area'], self.capture_and_translate)
        add_hotkey(sk['retry'], self.retry_translation)
        add_hotkey(sk['toggle_indicator'], self.toggle_indicator)
        add_hotkey(sk['select_area'], self.start_selection_only)

    def open_settings(self):
        # 从 ui.py 导入 SettingsDialog，但需要传入 tim
        # 为避免循环引用，SettingsDialog 定义在 ui.py 内部是没问题的，因为它接收外部对象
        dlg = SettingsDialog(self.tim)
        dlg.exec_()
        for win in self.tim.windows:
            win.apply_style()

    def closeEvent(self, event):
        if self.indicator: self.indicator.close()
        if self.global_config.get('paddle', {}).get('close_on_exit', True):
            if self.ocr.engine_type == 'paddle':
                self.ocr.stop_paddle()
        if self.global_config.get('close_to_tray', True):
            self.hide()
            event.ignore()
        else:
            self.tim.on_window_closed(self.window_index)
            event.accept()

    def close_window(self):
        self.close()


# --- Settings Dialog ---
class SettingsDialog(QDialog):
    def __init__(self, tray_icon_manager):
        super().__init__()
        self.tim = tray_icon_manager
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.current_text = '#000000'
        self.current_bg = '#FFFFFFCC'
        self.current_border = '#FF0000'
        self.current_top_bg = '#2B2B2B'
        self.setWindowTitle("设置")
        self.resize(750, 650)
        self.setStyleSheet("""
            QDialog, QWidget, QLabel, QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QGroupBox {
                background-color: white; color: black; border:1px solid #cccccc;
            }
            QPushButton { background-color: #f0f0f0; color: black; border:1px solid #aaaaaa; padding: 5px; }
            QPushButton:hover { background-color: #e0e0e0; }
            QTabWidget::pane { border: 1px solid #cccccc; }
        """)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.build_general_tab()
        self.window_widgets = {}
        self.build_window_tabs()
        btn_box = QHBoxLayout()
        btn_save = QPushButton("保存")
        btn_save.clicked.connect(self.save_settings)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_save)
        btn_box.addWidget(btn_cancel)
        layout.addLayout(btn_box)
        self.load_data()

    def build_general_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        grp_api = QGroupBox("API 设置")
        form_api = QFormLayout(grp_api)
        self.input_url = QLineEdit()
        form_api.addRow("API域名:", self.input_url)
        self.input_key = QLineEdit()
        form_api.addRow("API Key:", self.input_key)
        self.input_model = QLineEdit()
        form_api.addRow("模型名称:", self.input_model)
        self.input_prompt = QTextEdit()
        self.input_prompt.setMaximumHeight(100)
        form_api.addRow("提示词:", self.input_prompt)
        self.input_proxy = QLineEdit()
        form_api.addRow("代理地址:", self.input_proxy)
        self.input_params = QLineEdit()
        self.input_params.setPlaceholderText('{"temperature": 0.7}')
        form_api.addRow("自定义参数:", self.input_params)
        layout.addWidget(grp_api)
        grp_ocr = QGroupBox("OCR & 模式")
        form_ocr = QFormLayout(grp_ocr)
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["ocr_to_ai", "direct_ai"])
        form_ocr.addRow("翻译模式:", self.combo_mode)
        self.combo_ocr = QComboBox()
        self.combo_ocr.addItems(["tesseract", "paddle"])
        form_ocr.addRow("OCR引擎:", self.combo_ocr)
        self.input_ocr_lang = QLineEdit()
        form_ocr.addRow("OCR语言:", self.input_ocr_lang)
        self.input_tess_path = QLineEdit()
        btn_browse = QPushButton("...")
        btn_browse.setMaximumWidth(30)
        btn_browse.clicked.connect(self.browse_tesseract)
        h_tess = QHBoxLayout()
        h_tess.addWidget(self.input_tess_path); h_tess.addWidget(btn_browse)
        form_ocr.addRow("Tesseract路径:", h_tess)
        self.btn_check_tess = QPushButton("检测")
        self.btn_check_tess.clicked.connect(self.check_tess)
        form_ocr.addRow(self.btn_check_tess)
        h_paddle = QHBoxLayout()
        self.btn_start_paddle = QPushButton("启动Paddle")
        self.btn_start_paddle.clicked.connect(self.start_paddle)
        self.btn_stop_paddle = QPushButton("停止Paddle")
        self.btn_stop_paddle.clicked.connect(self.stop_paddle)
        self.check_paddle_close = QCheckBox("关闭程序时停止Paddle")
        h_paddle.addWidget(self.btn_start_paddle)
        h_paddle.addWidget(self.btn_stop_paddle)
        form_ocr.addRow("PaddleOCR:", h_paddle)
        form_ocr.addRow(self.check_paddle_close)
        layout.addWidget(grp_ocr)
        grp_style = QGroupBox("窗口外观 (全局)")
        form_style = QFormLayout(grp_style)
        self.btn_top_bg_color = QPushButton("顶部背景色")
        self.btn_top_bg_color.clicked.connect(self.choose_top_bg)
        form_style.addRow(self.btn_top_bg_color)
        self.spin_top_opacity = QDoubleSpinBox()
        self.spin_top_opacity.setRange(0.0, 1.0)
        self.spin_top_opacity.setSingleStep(0.1)
        self.spin_top_opacity.setValue(0.9)
        self.spin_top_opacity.setToolTip("控制按钮、图标、标题的显示程度")
        form_style.addRow("顶部透明度:", self.spin_top_opacity)
        self.spin_hover = QDoubleSpinBox()
        self.spin_hover.setRange(0.0, 1.0)
        self.spin_hover.setSingleStep(0.1)
        self.spin_hover.setValue(1.0)
        form_style.addRow("悬停透明度:", self.spin_hover)
        self.btn_border_color = QPushButton("翻译框描边色")
        self.btn_border_color.clicked.connect(self.choose_border)
        form_style.addRow(self.btn_border_color)
        self.check_border_enable = QCheckBox("启用描边")
        form_style.addRow(self.check_border_enable)
        self.btn_bg_color = QPushButton("翻译框背景色")
        self.btn_bg_color.clicked.connect(self.choose_bg)
        form_style.addRow(self.btn_bg_color)
        self.btn_text_color = QPushButton("文字颜色")
        self.btn_text_color.clicked.connect(self.choose_text)
        form_style.addRow(self.btn_text_color)
        self.spin_font = QSpinBox()
        form_style.addRow("字号:", self.spin_font)
        self.check_auto_save_state = QCheckBox("拖动后自动保存位置")
        self.check_auto_save_state.setChecked(True)
        form_style.addRow(self.check_auto_save_state)
        layout.addWidget(grp_style)
        grp_auto = QGroupBox("自动模式")
        form_auto = QFormLayout(grp_auto)
        self.check_auto_enable = QCheckBox("启用自动")
        form_auto.addRow(self.check_auto_enable)
        self.spin_interval = QSpinBox()
        form_auto.addRow("间隔(秒):", self.spin_interval)
        layout.addWidget(grp_auto)
        layout.addStretch()
        self.tabs.addTab(tab, "通用设置")

    def build_window_tabs(self):
        while self.tabs.count() > 1:
            self.tabs.removeTab(1)
        self.window_widgets.clear()
        for i in range(len(self.tim.sm.data['windows'])):
            self.add_window_tab(i)

    def add_window_tab(self, index):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        grp_size = QGroupBox(f"窗口 {index+1} - 大小与锁定")
        form_size = QFormLayout(grp_size)
        self.spin_width = QSpinBox()
        self.spin_width.setRange(200, 4000)
        form_size.addRow("窗口宽度:", self.spin_width)
        self.spin_height = QSpinBox()
        self.spin_height.setRange(100, 3000)
        form_size.addRow("窗口高度:", self.spin_height)
        # 修正：去掉括号里的描述
        self.check_lock_size = QCheckBox("锁定窗口大小")
        form_size.addRow(self.check_lock_size)
        layout.addWidget(grp_size)
        grp_win_pos = QGroupBox(f"窗口 {index+1} - 启动位置")
        form_win_pos = QFormLayout(grp_win_pos)
        spin_win_x = QSpinBox(); spin_win_x.setRange(0, 9999)
        spin_win_y = QSpinBox(); spin_win_y.setRange(0, 9999)
        pos_layout = QHBoxLayout()
        pos_layout.addWidget(spin_win_x); pos_layout.addWidget(QLabel("X"))
        pos_layout.addWidget(spin_win_y); pos_layout.addWidget(QLabel("Y"))
        form_win_pos.addRow(pos_layout)
        layout.addWidget(grp_win_pos)
        grp_region = QGroupBox(f"窗口 {index+1} - 截屏区域")
        form_region = QFormLayout(grp_region)
        spin_x = QSpinBox(); spin_x.setRange(0, 10000)
        spin_y = QSpinBox(); spin_y.setRange(0, 10000)
        spin_w = QSpinBox(); spin_w.setRange(0, 10000)
        spin_h = QSpinBox(); spin_h.setRange(0, 10000)
        reg_layout = QHBoxLayout()
        reg_layout.addWidget(spin_x); reg_layout.addWidget(QLabel("X"))
        reg_layout.addWidget(spin_y); reg_layout.addWidget(QLabel("Y"))
        reg_layout.addWidget(spin_w); reg_layout.addWidget(QLabel("W"))
        reg_layout.addWidget(spin_h); reg_layout.addWidget(QLabel("H"))
        form_region.addRow(reg_layout)
        layout.addWidget(grp_region)
        grp_keys = QGroupBox(f"窗口 {index+1} - 快捷键")
        form_keys = QFormLayout(grp_keys)
        sk_shot = QLineEdit()
        sk_trans = QLineEdit()
        sk_retry = QLineEdit()
        sk_ind = QLineEdit()
        sk_sel = QLineEdit()
        form_keys.addRow("截图(选区):", sk_shot)
        form_keys.addRow("翻译(当前):", sk_trans)
        form_keys.addRow("重试:", sk_retry)
        form_keys.addRow("指示器:", sk_ind)
        form_keys.addRow("选区(改区):", sk_sel)
        layout.addWidget(grp_keys)
        btn_del = QPushButton(f"删除窗口 {index+1}")
        btn_del.setStyleSheet("color: red;")
        btn_del.clicked.connect(lambda checked, idx=index: self.delete_window(idx))
        layout.addWidget(btn_del)
        layout.addStretch()
        self.tabs.addTab(tab, f"窗口 {index+1}")
        self.window_widgets[index] = {
            'win_x': spin_win_x, 'win_y': spin_win_y,
            'width': self.spin_width, 'height': self.spin_height,
            'lock_size': self.check_lock_size,
            'x': spin_x, 'y': spin_y, 'w': spin_w, 'h': spin_h,
            'screenshot': sk_shot, 'translate': sk_trans,
            'retry': sk_retry, 'indicator': sk_ind, 'select': sk_sel
        }

    def delete_window(self, index):
        reply = QMessageBox.question(self, '确认', f'确定要删除窗口 {index+1} 吗？', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            if index < len(self.tim.sm.data['windows']):
                del self.tim.sm.data['windows'][index]
                self.tim.sm.save()
            self.build_window_tabs()
            self.load_data()

    def load_data(self):
        g = self.tim.sm.data['global']
        self.input_url.setText(g.get('api_url', ''))
        self.input_key.setText(g.get('api_key', ''))
        self.input_model.setText(g.get('model', ''))
        self.input_prompt.setPlainText(g.get('prompt', ''))
        self.input_proxy.setText(g.get('proxy', ''))
        self.input_params.setText(g.get('custom_params', '{}'))
        self.combo_mode.setCurrentText(g.get('mode', 'ocr_to_ai'))
        self.combo_ocr.setCurrentText(g.get('ocr_engine', 'tesseract'))
        self.input_ocr_lang.setText(g.get('ocr_lang', ''))
        self.input_tess_path.setText(g.get('tesseract_path', ''))
        ws = g.get('window_style', {})
        self.spin_font.setValue(ws.get('font_size', 12))
        self.spin_top_opacity.setValue(ws.get('top_opacity', 0.9))
        self.spin_hover.setValue(ws.get('hover_opacity', 1.0))
        self.check_auto_save_state.setChecked(ws.get('auto_save_state', True))
        self.check_border_enable.setChecked(ws.get('enable_text_border', False))
        self.current_top_bg = ws.get('top_bg_color', '#2B2B2B')
        self.current_bg = ws.get('text_bg_color', '#FFFFFFCC')
        self.current_border = ws.get('text_border_color', '#FF0000')
        self.current_text = ws.get('text_color', '#000000')
        self.update_color_btns()
        am = g.get('auto_mode', {})
        self.check_auto_enable.setChecked(am.get('enabled', False))
        self.spin_interval.setValue(am.get('interval', 5))
        self.check_paddle_close.setChecked(g.get('paddle', {}).get('close_on_exit', True))
        for i, win_data in enumerate(self.tim.sm.data['windows']):
            if i in self.window_widgets:
                wgts = self.window_widgets[i]
                local_ws = win_data.get('window_style', {})
                wgts['width'].setValue(local_ws.get('width', 400))
                wgts['height'].setValue(local_ws.get('height', 300))
                wgts['lock_size'].setChecked(local_ws.get('lock_size', False))
                win_pos = win_data.get('win_pos', {'x': 100, 'y': 100})
                wgts['win_x'].setValue(win_pos.get('x', 100))
                wgts['win_y'].setValue(win_pos.get('y', 100))
                reg = win_data.get('region', {})
                wgts['x'].setValue(reg.get('x', 0))
                wgts['y'].setValue(reg.get('y', 0))
                wgts['w'].setValue(reg.get('w', 0))
                wgts['h'].setValue(reg.get('h', 0))
                sks = win_data.get('shortcuts', {})
                wgts['screenshot'].setText(sks.get('screenshot', ''))
                wgts['translate'].setText(sks.get('translate_area', ''))
                wgts['retry'].setText(sks.get('retry', ''))
                wgts['indicator'].setText(sks.get('toggle_indicator', ''))
                wgts['select'].setText(sks.get('select_area', ''))

    def save_settings(self):
        g = self.tim.sm.data['global']
        g['api_url'] = self.input_url.text()
        g['api_key'] = self.input_key.text()
        g['model'] = self.input_model.text()
        g['prompt'] = self.input_prompt.toPlainText()
        g['proxy'] = self.input_proxy.text()
        g['custom_params'] = self.input_params.text()
        g['mode'] = self.combo_mode.currentText()
        g['ocr_engine'] = self.combo_ocr.currentText()
        g['ocr_lang'] = self.input_ocr_lang.text()
        g['tesseract_path'] = self.input_tess_path.text()
        g['window_style'] = {
            'font_size': self.spin_font.value(),
            'top_opacity': self.spin_top_opacity.value(),
            'hover_opacity': self.spin_hover.value(),
            'top_bg_color': self.current_top_bg,
            'text_color': self.current_text,
            'text_bg_color': self.current_bg,
            'text_border_color': self.current_border,
            'enable_text_border': self.check_border_enable.isChecked(),
            'auto_save_state': self.check_auto_save_state.isChecked()
        }
        g['auto_mode'] = {
            'enabled': self.check_auto_enable.isChecked(),
            'interval': self.spin_interval.value(),
            'interrupt_on_manual': True
        }
        g['paddle']['close_on_exit'] = self.check_paddle_close.isChecked()
        g['close_to_tray'] = True
        for i in range(len(self.tim.sm.data['windows'])):
            if i in self.window_widgets:
                wgts = self.window_widgets[i]
                win_data = self.tim.sm.data['windows'][i]
                win_data.setdefault('window_style', {})
                win_data['window_style']['width'] = wgts['width'].value()
                win_data['window_style']['height'] = wgts['height'].value()
                win_data['window_style']['lock_size'] = wgts['lock_size'].isChecked()
                win_data['win_pos'] = {
                    'x': wgts['win_x'].value(), 'y': wgts['win_y'].value()
                }
                win_data['region'] = {
                    'x': wgts['x'].value(), 'y': wgts['y'].value(),
                    'w': wgts['w'].value(), 'h': wgts['h'].value()
                }
                win_data['shortcuts'] = {
                    'screenshot': wgts['screenshot'].text(),
                    'translate_area': wgts['translate'].text(),
                    'retry': wgts['retry'].text(),
                    'toggle_indicator': wgts['indicator'].text(),
                    'select_area': wgts['select'].text()
                }
        self.tim.sm.save()
        self.accept()

    def browse_tesseract(self):
        path, _ = QFileDialog.getOpenFileName(self, "Tesseract", "", "Exe (*.exe)")
        if path: self.input_tess_path.setText(path)

    def check_tess(self):
        from ocr import OCREngine # Local import to ensure it's available
        if OCREngine.check_tesseract(self.input_tess_path.text()):
            QMessageBox.information(self, "Success", "Tesseract found!")
        else:
            QMessageBox.warning(self, "Fail", "Tesseract not found.")

    def start_paddle(self):
        if self.tim.windows:
            self.tim.windows[0].ocr.lang = self.input_ocr_lang.text()
            msg = self.tim.windows[0].ocr.start_paddle()
            QMessageBox.information(self, "Paddle", msg)

    def stop_paddle(self):
        if self.tim.windows:
            msg = self.tim.windows[0].ocr.stop_paddle()
            QMessageBox.information(self, "Paddle", msg)

    def choose_bg(self):
        c = QColorDialog.getColor(QColor(self.current_bg), self, "Bg", QColorDialog.ShowAlphaChannel)
        if c.isValid():
            self.current_bg = c.name(QColor.HexArgb)
            self.update_color_btns()

    def choose_top_bg(self):
        c = QColorDialog.getColor(QColor(self.current_top_bg), self, "TopBg", QColorDialog.ShowAlphaChannel)
        if c.isValid():
            self.current_top_bg = c.name(QColor.HexArgb)
            self.update_color_btns()

    def choose_text(self):
        c = QColorDialog.getColor(QColor(self.current_text), self, "Text", QColorDialog.ShowAlphaChannel)
        if c.isValid():
            self.current_text = c.name(QColor.HexArgb)
            self.update_color_btns()

    def choose_border(self):
        c = QColorDialog.getColor(QColor(self.current_border), self, "Border", QColorDialog.ShowAlphaChannel)
        if c.isValid():
            self.current_border = c.name(QColor.HexArgb)
            self.update_color_btns()

    def update_color_btns(self):
        self.btn_top_bg_color.setStyleSheet(f"background-color:{self.current_top_bg}")
        self.btn_border_color.setStyleSheet(f"background-color:{self.current_border}")
        self.btn_bg_color.setStyleSheet(f"background-color:{self.current_bg}")
        self.btn_text_color.setStyleSheet(f"background-color:{self.current_text}")