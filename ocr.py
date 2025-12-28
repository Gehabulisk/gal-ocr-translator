import pytesseract
from paddleocr import PaddleOCR
import os
import shutil
import sys

class OCREngine:
    def __init__(self):
        self.engine_type = 'tesseract' # 'tesseract' or 'paddle'
        self.lang = 'eng+chi_sim'
        self.paddle_ocr = None
        self.tesseract_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        
        # 检测 tesseract 是否存在于环境变量或指定路径
        self.tesseract_available = self.check_tesseract()

    def set_engine(self, engine_type, lang=None, tesseract_path=None):
        self.engine_type = engine_type
        if lang:
            self.lang = lang
        if tesseract_path:
            self.tesseract_path = tesseract_path
            if os.path.exists(tesseract_path):
                pytesseract.pytesseract.tesseract_cmd = tesseract_path
                self.tesseract_available = True
            else:
                self.tesseract_available = False

    @staticmethod
    def check_tesseract(custom_path=None):
        """检查 Tesseract 是否可用"""
        if custom_path and os.path.exists(custom_path):
            return True
        if shutil.which("tesseract"):
            return True
        return False

    def start_paddle(self):
        """显式启动 PaddleOCR"""
        if self.paddle_ocr is not None:
            return "PaddleOCR 已经在运行"
        try:
            # 初始化 PaddleOCR，这里会自动下载模型如果不存在
            self.paddle_ocr = PaddleOCR(use_angle_cls=True, lang=self.lang, show_log=False)
            return "PaddleOCR 启动成功"
        except Exception as e:
            self.paddle_ocr = None
            return f"PaddleOCR 启动失败: {str(e)}"

    def stop_paddle(self):
        """停止 PaddleOCR，释放内存"""
        if self.paddle_ocr:
            del self.paddle_ocr
            self.paddle_ocr = None
            return "PaddleOCR 已停止"
        return "PaddleOCR 未运行"

    def run_ocr(self, image_path):
        if not os.path.exists(image_path):
            raise Exception(f"错误: 图片文件不存在 {image_path}")

        try:
            if self.engine_type == 'tesseract':
                if not self.tesseract_available:
                    # 尝试再次检测，以防用户刚安装了
                    if os.path.exists(self.tesseract_path):
                        self.tesseract_available = True
                        pytesseract.pytesseract.tesseract_cmd = self.tesseract_path
                    else:
                        raise Exception("Tesseract 未配置或路径错误，请在设置中检查。")
                
                text = pytesseract.image_to_string(image_path, lang=self.lang)
                return text
                
            elif self.engine_type == 'paddle':
                if self.paddle_ocr is None:
                    # 如果未手动启动，尝试按需自动启动一次
                    msg = self.start_paddle()
                    if "失败" in msg:
                        raise Exception(msg)
                
                result = self.paddle_ocr.ocr(image_path, cls=True)
                if not result or not result[0]:
                    return ""
                txt_list = [line[1][0] for line in result[0]]
                return "\n".join(txt_list)
        except Exception as e:
            # 抛出异常以便在上层显示
            raise Exception(f"OCR Error: {str(e)}")