import os
import sys
import json
import winreg
import requests
import traceback
import datetime as dt
import base64
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QMessageBox, QTextEdit,
    QListWidget, QListWidgetItem, QSplitter, QFrame,
    QMenu, QAction, QInputDialog, QGroupBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtGui import QFont, QIcon, QColor, QPalette, QTextCursor

# 直接导入自动化模块（打包时会包含）
import pyautogui
import pyperclip
import keyboard
import bs4
import datetime


# 图像识别函数
def recognize_image(prompt='请识别图片中的内容', image_path='image.png'):
    """
    识别图像内容
    参数:
        prompt: 提示词
        image_path: 图像文件路径
    返回:
        str: 图像识别结果
    """
    try:
        # API配置
        api_key = "sk-hoospyciwnztwjzricfhonbbsbhcrodjdsxidbzyogpzqeqh"
        api_url = "https://api.siliconflow.cn/v1/chat/completions"

        headers = {
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json"
        }

        # 图片编码函数
        def encode_image_to_base64(image_path):
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')

        # 调用示例
        base64_image = encode_image_to_base64(image_path)

        data = {
            "model": "THUDM/GLM-4.1V-9B-Thinking",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/jpeg;base64," + base64_image
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 300
        }

        response = requests.post(api_url, headers=headers, json=data)
        result = response.json()
        return result['choices'][0]['message']['content']
    except Exception as e:
        return f"识别失败: {str(e)}"


# 语音识别函数
def recognize_audio(audio_path='audio.mp3'):
    """
    识别音频内容
    参数:
        audio_path: 音频文件路径
    返回:
        str: 语音识别结果
    """
    try:
        # API配置
        api_key = "sk-hoospyciwnztwjzricfhonbbsbhcrodjdsxidbzyogpzqeqh"
        api_url = "https://api.siliconflow.cn/v1/audio/transcriptions"

        headers = {
            "Authorization": "Bearer " + api_key
        }

        # 检查文件是否存在
        if not os.path.exists(audio_path):
            # 尝试在当前目录查找
            current_dir = os.path.dirname(os.path.abspath(__file__))
            audio_path = os.path.join(current_dir, audio_path)
            if not os.path.exists(audio_path):
                # 尝试在桌面查找
                desktop = os.path.join(os.path.expanduser("~"), "Desktop")
                audio_path = os.path.join(desktop, audio_path)
                if not os.path.exists(audio_path):
                    return f"错误: 找不到文件 '{audio_path}'"

        # 调用语音识别API
        with open(audio_path, "rb") as audio_file:
            files = {
                "file": ("audio.mp3", audio_file),
                "model": (None, "FunAudioLLM/SenseVoiceSmall")
            }
            response = requests.post(api_url, headers=headers, files=files)

        result = response.json()
        return result.get('text', '识别失败: 未返回识别结果')
    except Exception as e:
        return f"识别失败: {str(e)}"


# 发送文件函数
def send_file(file_path, target_user_id=None):
    """
    发送文件给用户（通过chat_bot中转）
    参数:
        file_path: 文件路径
        target_user_id: 目标用户ID
    返回:
        str: 发送结果
    """
    try:
        # 检查文件是否存在
        if not os.path.exists(file_path):
            # 尝试在当前目录查找
            current_dir = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(current_dir, file_path)
            if not os.path.exists(file_path):
                # 尝试在桌面查找
                desktop = os.path.join(os.path.expanduser("~"), "Desktop")
                file_path = os.path.join(desktop, file_path)
                if not os.path.exists(file_path):
                    return f"错误: 找不到文件 '{file_path}'"

        # 读取文件内容
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        # 编码为base64
        file_b64 = base64.b64encode(file_data).decode('utf-8')
        file_name = os.path.basename(file_path)
        file_size = len(file_data)
        
        # 发送到chat_bot（端口 5004）
        chat_bot_url = "http://127.0.0.1:5004/api/receive_file_from_execute"
        data = {
            'target_user_id': target_user_id,
            'file_path': file_path,
            'file_name': file_name,
            'file_data': file_b64,
            'file_size': file_size
        }
        
        response = requests.post(chat_bot_url, json=data, timeout=30)
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                return f"成功: 文件 '{file_name}' 已发送给用户 {target_user_id}"
            else:
                return f"失败: {result.get('message', '未知错误')}"
        else:
            return f"失败: chat_bot响应错误 {response.status_code}"
            
    except requests.exceptions.ConnectionError:
        return "失败: 无法连接到chat_bot (端口 5004)，请确保chat_bot已启动"
    except Exception as e:
        return f"错误: {str(e)}"


class ExecutionThread(QThread):
    """代码执行线程"""
    output_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)  # success, result_message

    def __init__(self, code, file_path, parent=None):
        super().__init__(parent)
        self.code = code
        self.file_path = file_path
        self.is_running = True

    def run(self):
        """执行代码"""
        success = False
        result_message = ""

        try:
            # 重定向print输出
            import sys
            from io import StringIO

            # 捕获标准输出
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = StringIO()
            sys.stderr = StringIO()

            try:
                # 创建执行环境
                exec_globals = {
                    'pyautogui': pyautogui,
                    'pyperclip': pyperclip,
                    'keyboard': keyboard,
                    'recognize_image': recognize_image,
                    'recognize_audio': recognize_audio,
                    'send_file': send_file,
                    '__file__': self.file_path,
                    '__name__': '__main__'
                }

                # 执行代码
                exec(self.code, exec_globals)

                # 获取输出
                output = sys.stdout.getvalue()
                error = sys.stderr.getvalue()

                if output:
                    self.output_signal.emit(output)
                if error:
                    self.error_signal.emit(error)

                success = True
                result_message = f"✅ 代码执行成功！\n\n执行时间: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                if output:
                    result_message += f"\n\n输出:\n{output}"

            except Exception as e:
                error_msg = traceback.format_exc()
                self.error_signal.emit(f"\n❌ 执行出错:\n{error_msg}")
                result_message = f"❌ 代码执行失败！\n\n错误信息:\n{error_msg}"
                success = False

            finally:
                # 恢复标准输出
                sys.stdout = old_stdout
                sys.stderr = old_stderr

        except Exception as e:
            result_message = f"❌ 执行器内部错误: {str(e)}"
            success = False

        finally:
            self.finished_signal.emit(success, result_message)

    def stop(self):
        """停止执行"""
        self.is_running = False
        # 注意：无法真正停止正在执行的代码，只能设置标志


class DoFileExecutor(QMainWindow):
    # 定义信号用于更新UI
    execution_output = pyqtSignal(str)
    execution_error = pyqtSignal(str)
    execution_finished = pyqtSignal(bool)

    def __init__(self, file_to_execute=None):
        super().__init__()
        self.file_to_execute = file_to_execute
        self.current_file = None
        self.execution_history = []
        self.execution_thread = None
        self.last_execution_success = False
        self.last_execution_result = ""

        # 获取程序所在目录
        if getattr(sys, 'frozen', False):
            # 如果是打包后的exe
            self.app_dir = os.path.dirname(sys.executable)
        else:
            # 如果是python脚本
            self.app_dir = os.path.dirname(os.path.abspath(__file__))

        # 配置文件
        self.config_file = Path(self.app_dir) / '.assistant_config.json'
        self.assistant_config = self.load_assistant_config()

        # 历史记录文件保存在程序目录
        self.history_file = Path(self.app_dir) / '.do_executor_history.json'

        self.is_executing = False
        self.load_history()

        self.init_ui()
        self.setup_file_association()

        # 连接信号
        self.execution_output.connect(self.append_output)
        self.execution_error.connect(self.append_error)
        self.execution_finished.connect(self.on_execution_finished)

        # 如果是通过文件关联启动，直接执行文件
        if file_to_execute and os.path.exists(file_to_execute):
            QTimer.singleShot(100, lambda: self.execute_do_file(file_to_execute))

    def load_assistant_config(self):
        """加载助手配置"""
        default_config = {
            'assistant_id': '',
            'chat_port': 5001,  # 云聊默认端口
            'enabled': True  # 默认启用
        }

        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # 确保enabled字段存在，如果不存在则设为True
                    if 'enabled' not in config:
                        config['enabled'] = True
                    return {**default_config, **config}
            except:
                pass

        return default_config

    def save_assistant_config(self):
        """保存助手配置"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.assistant_config, f, ensure_ascii=False, indent=2)
        except:
            pass

    def send_result_to_assistant(self, success, result_message, file_path):
        """发送执行结果给灵犀助手和灵犀云聊"""
        if not self.assistant_config.get('enabled'):
            return

        # 构建结果消息
        file_name = os.path.basename(file_path) if file_path else "未知文件"
        status = "成功" if success else "失败"

        message = f"""📋 自动化脚本执行报告

文件: {file_name}
状态: {status}
时间: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{result_message}"""

        # 发送给chat_bot.py，让它转发到灵犀云聊
        try:
            # chat_bot.py运行在本地5004端口
            chat_bot_url = "http://127.0.0.1:5004/api/receive_execution_result"
            response = requests.post(chat_bot_url, json={
                'result': message,
                'success': success,
                'file': file_name,
                'timestamp': dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }, timeout=3)
            print(f"结果已发送给chat_bot.py: {response.status_code}")
        except Exception as e:
            print(f"发送给chat_bot.py失败: {e}")

    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("灵犀副驾驶 - .do文件执行器")
        self.setGeometry(300, 300, 1100, 750)

        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(10)

        # ========== 左侧面板 ==========
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_panel.setMaximumWidth(350)
        left_panel.setMinimumWidth(300)
        left_layout.setSpacing(8)

        # 文件操作区域
        file_group = QGroupBox("文件操作")
        file_layout = QVBoxLayout(file_group)
        file_layout.setSpacing(8)

        # 第一行按钮
        btn_row1 = QHBoxLayout()
        select_file_btn = QPushButton("📂 选择.do文件")
        select_file_btn.clicked.connect(self.select_do_file)
        select_file_btn.setMinimumHeight(35)
        btn_row1.addWidget(select_file_btn)

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(self.refresh_file_list)
        refresh_btn.setMinimumHeight(35)
        btn_row1.addWidget(refresh_btn)
        file_layout.addLayout(btn_row1)

        # 第二行按钮
        btn_row2 = QHBoxLayout()
        config_btn = QPushButton("⚙️ 助手配置")
        config_btn.clicked.connect(self.show_config_dialog)
        config_btn.setMinimumHeight(35)
        btn_row2.addWidget(config_btn)

        clear_history_btn = QPushButton("🗑️ 清除历史")
        clear_history_btn.clicked.connect(self.clear_all_history)
        clear_history_btn.setMinimumHeight(35)
        btn_row2.addWidget(clear_history_btn)
        file_layout.addLayout(btn_row2)

        left_layout.addWidget(file_group)

        # 文件列表
        file_label = QLabel("📁 最近使用的.do文件")
        file_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #81A1C1; padding: 5px;")
        left_layout.addWidget(file_label)

        self.file_list = QListWidget()
        self.file_list.setMinimumHeight(150)
        self.file_list.itemDoubleClicked.connect(self.on_file_double_clicked)
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self.show_file_context_menu)
        left_layout.addWidget(self.file_list)

        # 历史记录
        history_label = QLabel("📜 执行历史")
        history_label.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #81A1C1; padding: 5px; margin-top: 10px;")
        left_layout.addWidget(history_label)

        self.history_list = QListWidget()
        self.history_list.setMinimumHeight(200)
        self.history_list.itemDoubleClicked.connect(self.on_history_double_clicked)
        self.history_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.history_list.customContextMenuRequested.connect(self.show_history_context_menu)
        left_layout.addWidget(self.history_list)

        # ========== 右侧面板 ==========
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(8)

        # 当前文件信息和状态
        info_group = QGroupBox("执行状态")
        info_layout = QVBoxLayout(info_group)
        info_layout.setSpacing(5)

        # 文件信息行
        file_info_row = QHBoxLayout()
        self.file_info_label = QLabel("未选择文件")
        self.file_info_label.setStyleSheet(
            "background-color: #1a3a5a; padding: 8px; border-radius: 3px; font-weight: bold;")
        file_info_row.addWidget(self.file_info_label, 3)

        # 助手状态指示器
        self.assistant_status = QLabel("⚪ 未连接")
        self.assistant_status.setStyleSheet(
            "background-color: #2a3a4a; padding: 5px 10px; border-radius: 3px; font-size: 12px;")
        self.assistant_status.setAlignment(Qt.AlignCenter)
        self.assistant_status.setFixedWidth(100)
        file_info_row.addWidget(self.assistant_status, 1)

        info_layout.addLayout(file_info_row)

        # 执行控制按钮行
        control_row = QHBoxLayout()
        control_row.setSpacing(8)

        self.execute_btn = QPushButton("▶ 执行")
        self.execute_btn.clicked.connect(self.execute_current_file)
        self.execute_btn.setEnabled(False)
        self.execute_btn.setMinimumHeight(40)
        self.execute_btn.setStyleSheet("QPushButton { background-color: #2a5a7a; }")
        control_row.addWidget(self.execute_btn)

        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.clicked.connect(self.stop_execution)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setMinimumHeight(40)
        self.stop_btn.setStyleSheet("QPushButton { background-color: #8b3a4a; }")
        control_row.addWidget(self.stop_btn)

        self.clear_btn = QPushButton("🗑 清空输出")
        self.clear_btn.clicked.connect(self.clear_output)
        self.clear_btn.setMinimumHeight(40)
        control_row.addWidget(self.clear_btn)

        self.send_btn = QPushButton("📤 发送结果")
        self.send_btn.clicked.connect(self.send_current_result)
        self.send_btn.setEnabled(False)
        self.send_btn.setMinimumHeight(40)
        self.send_btn.setStyleSheet("QPushButton { background-color: #3a5a7a; }")
        control_row.addWidget(self.send_btn)

        info_layout.addLayout(control_row)
        right_layout.addWidget(info_group)

        # 输出区域
        output_label = QLabel("📤 执行输出:")
        output_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #81A1C1; padding: 5px;")
        right_layout.addWidget(output_label)

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setFont(QFont("Consolas", 10))
        self.output_text.setMinimumHeight(200)
        right_layout.addWidget(self.output_text)

        # 代码预览区域
        code_label = QLabel("📄 代码预览:")
        code_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #81A1C1; padding: 5px;")
        right_layout.addWidget(code_label)

        self.code_preview = QTextEdit()
        self.code_preview.setReadOnly(True)
        self.code_preview.setFont(QFont("Consolas", 10))
        self.code_preview.setMaximumHeight(180)
        right_layout.addWidget(self.code_preview)

        # 添加左右面板到主布局
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel, 1)

        # 应用主题样式
        self.apply_theme()

        # 更新助手状态显示
        self.update_assistant_status()

        # 刷新文件列表
        self.refresh_file_list()

    def update_assistant_status(self):
        """更新助手连接状态显示"""
        if self.assistant_config.get('enabled'):
            if self.assistant_config.get('assistant_id'):
                self.assistant_status.setText(f"🟢 已连接")
                self.assistant_status.setStyleSheet(
                    "background-color: #1a5a3a; padding: 5px 10px; border-radius: 3px; font-size: 12px; color: #aaffaa;")
                self.assistant_status.setToolTip(
                    f"助手ID: {self.assistant_config['assistant_id']}\n端口: {self.assistant_config.get('chat_port', 5001)}")
            else:
                self.assistant_status.setText("🟡 未配置ID")
                self.assistant_status.setStyleSheet(
                    "background-color: #5a4a1a; padding: 5px 10px; border-radius: 3px; font-size: 12px; color: #ffffaa;")
        else:
            self.assistant_status.setText("⚪ 已禁用")
            self.assistant_status.setStyleSheet(
                "background-color: #2a3a4a; padding: 5px 10px; border-radius: 3px; font-size: 12px;")

    def show_config_dialog(self):
        """显示配置对话框"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLineEdit, QCheckBox, QDialogButtonBox, \
            QHBoxLayout

        dialog = QDialog(self)
        dialog.setWindowTitle("助手配置")
        dialog.setMinimumWidth(450)
        layout = QVBoxLayout(dialog)

        # 说明文字
        info_label = QLabel("配置助手反馈功能，执行结果将自动发送给灵犀助手和灵犀云聊")
        info_label.setStyleSheet("color: #81A1C1; padding: 5px;")
        layout.addWidget(info_label)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        # 启用助手反馈
        enabled_check = QCheckBox()
        enabled_check.setChecked(self.assistant_config.get('enabled', True))
        enabled_check.setText("启用自动反馈")
        form_layout.addRow("", enabled_check)

        # 助手ID
        assistant_id_edit = QLineEdit(self.assistant_config.get('assistant_id', ''))
        assistant_id_edit.setPlaceholderText("输入灵犀助手ID")
        assistant_id_edit.setMinimumWidth(250)
        form_layout.addRow("助手ID:", assistant_id_edit)

        # 云聊端口
        chat_port_edit = QLineEdit(str(self.assistant_config.get('chat_port', 5001)))
        chat_port_edit.setPlaceholderText("灵犀云聊端口")
        chat_port_edit.setMaximumWidth(100)
        form_layout.addRow("灵犀云聊端口:", chat_port_edit)

        layout.addLayout(form_layout)

        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(dialog.reject)
        cancel_btn.setFixedWidth(100)

        save_btn = QPushButton("保存")
        save_btn.clicked.connect(dialog.accept)
        save_btn.setFixedWidth(100)
        save_btn.setDefault(True)

        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(save_btn)
        layout.addLayout(button_layout)

        if dialog.exec_() == QDialog.Accepted:
            self.assistant_config['enabled'] = enabled_check.isChecked()
            self.assistant_config['assistant_id'] = assistant_id_edit.text().strip()
            try:
                self.assistant_config['chat_port'] = int(chat_port_edit.text())
            except:
                self.assistant_config['chat_port'] = 5001

            self.save_assistant_config()
            self.update_assistant_status()

            if self.assistant_config['enabled'] and self.assistant_config['assistant_id']:
                QMessageBox.information(self, "配置完成", "助手反馈功能已启用！\n执行结果将自动发送给助手和云聊。")
            elif self.assistant_config['enabled']:
                QMessageBox.warning(self, "提示", "请填写助手ID以启用反馈功能")
            else:
                QMessageBox.information(self, "配置完成", "配置已保存，反馈功能已禁用")

    def send_current_result(self):
        """发送当前执行结果"""
        if not self.last_execution_result:
            QMessageBox.warning(self, "警告", "没有可发送的执行结果")
            return

        if not self.assistant_config.get('enabled'):
            reply = QMessageBox.question(
                self,
                "确认",
                "反馈功能未启用，是否现在配置？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.show_config_dialog()
            return

        if not self.assistant_config.get('assistant_id'):
            QMessageBox.warning(self, "提示", "请先在配置中设置助手ID")
            self.show_config_dialog()
            return

        # 发送结果
        self.send_result_to_assistant(
            self.last_execution_success,
            self.last_execution_result,
            self.current_file
        )

        QMessageBox.information(self, "发送完成", "执行结果已发送给助手和云聊")

    def apply_theme(self):
        """应用深色主题"""
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #0a1428, stop:0.5 #1a3a5a, stop:1 #0a1428);
            }
            QWidget {
                background: transparent;
                color: #ECEFF4;
            }
            QGroupBox {
                background-color: rgba(26, 43, 58, 0.7);
                border: 1px solid #5E81AC;
                border-radius: 5px;
                margin-top: 10px;
                font-weight: bold;
                color: #81A1C1;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QPushButton {
                background-color: #1a3a5a;
                color: #81A1C1;
                border-radius: 3px;
                padding: 8px 12px;
                font-size: 13px;
                border: 1px solid #5E81AC;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #2a5a7a;
            }
            QPushButton:pressed {
                background-color: #0a1a2a;
            }
            QPushButton:disabled {
                background-color: #2a3a4a;
                color: #5a6a7a;
                border: 1px solid #3a4a5a;
            }
            QListWidget {
                background-color: rgba(26, 43, 58, 0.9);
                border: 1px solid #5E81AC;
                border-radius: 3px;
                padding: 5px;
                font-size: 13px;
                color: #ECEFF4;
            }
            QListWidget::item {
                padding: 5px;
                border-bottom: 1px solid #3a5a7a;
            }
            QListWidget::item:selected {
                background-color: #2a5a7a;
            }
            QListWidget::item:hover {
                background-color: #1a4a6a;
            }
            QTextEdit {
                background-color: rgba(16, 26, 36, 0.95);
                border: 1px solid #5E81AC;
                border-radius: 3px;
                padding: 8px;
                font-size: 13px;
                color: #ECEFF4;
                selection-background-color: #2a5a7a;
            }
            QLabel {
                color: #ECEFF4;
            }
            QScrollBar:vertical {
                background: #1a2a3a;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #3a5a7a;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #4a6a8a;
            }
        """)

    def setup_file_association(self):
        """设置.do文件关联到本程序"""
        try:
            # 获取当前执行文件的路径
            if getattr(sys, 'frozen', False):
                # 如果是打包后的exe
                exe_path = f'"{sys.executable}" "%1"'
            else:
                # 如果是python脚本
                exe_path = f'"{sys.executable}" "{os.path.abspath(__file__)}" "%1"'

            # 注册.do文件关联
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.do") as key:
                winreg.SetValue(key, "", winreg.REG_SZ, "DoFile")

            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\DoFile") as key:
                winreg.SetValue(key, "", winreg.REG_SZ, "灵犀副驾驶自动化脚本")

            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\DoFile\shell\open\command") as key:
                winreg.SetValue(key, "", winreg.REG_SZ, exe_path)

            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\DoFile\DefaultIcon") as key:
                icon_path = sys.executable if getattr(sys, 'frozen', False) else sys.executable
                winreg.SetValue(key, "", winreg.REG_SZ, f"{icon_path},0")

            print(".do文件关联设置成功")
        except Exception as e:
            print(f"设置文件关联时出错: {e}")

    def load_history(self):
        """加载执行历史"""
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.execution_history = json.load(f)
        except:
            self.execution_history = []

    def save_history(self):
        """保存执行历史"""
        try:
            # 只保存最近50条记录
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.execution_history[:50], f, ensure_ascii=False, indent=2)
        except:
            pass

    def refresh_file_list(self):
        """刷新文件列表"""
        self.file_list.clear()

        # 从历史记录中获取最近使用的文件
        recent_files = []
        for item in self.execution_history:
            if item.get('file') and item['file'] not in recent_files and os.path.exists(item['file']):
                recent_files.append(item['file'])

        # 添加最近使用的文件
        for file_path in recent_files[:10]:
            item = QListWidgetItem(os.path.basename(file_path))
            item.setData(Qt.UserRole, file_path)
            item.setToolTip(file_path)
            self.file_list.addItem(item)

        # 刷新历史记录列表
        self.refresh_history_list()

    def refresh_history_list(self):
        """刷新历史记录列表"""
        self.history_list.clear()

        for item in self.execution_history[:20]:
            time_str = item.get('time', '')[:16]  # 只显示日期和时间到分钟
            file_name = os.path.basename(item.get('file', '未知文件'))
            status = "✅" if item.get('success') else "❌"
            display_text = f"{status} {time_str} - {file_name}"

            list_item = QListWidgetItem(display_text)
            list_item.setData(Qt.UserRole, item)
            list_item.setToolTip(
                f"文件: {item.get('file')}\n时间: {item.get('time')}\n状态: {'成功' if item.get('success') else '失败'}")
            self.history_list.addItem(list_item)

    def select_do_file(self):
        """选择.do文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择.do文件", str(Path.home()), "DO文件 (*.do);;所有文件 (*.*)"
        )

        if file_path:
            self.load_do_file(file_path)

    def load_do_file(self, file_path):
        """加载.do文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()

            self.current_file = file_path
            self.file_info_label.setText(f"当前文件: {os.path.basename(file_path)}")
            self.file_info_label.setToolTip(file_path)
            self.code_preview.setText(code)
            self.execute_btn.setEnabled(True)

            # 添加到最近使用列表
            self.add_to_recent(file_path)

        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法读取文件: {str(e)}")

    def add_to_recent(self, file_path):
        """添加到最近使用文件列表"""
        # 检查是否已在列表中
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.data(Qt.UserRole) == file_path:
                self.file_list.takeItem(i)
                break

        # 添加到顶部
        item = QListWidgetItem(os.path.basename(file_path))
        item.setData(Qt.UserRole, file_path)
        item.setToolTip(file_path)
        self.file_list.insertItem(0, item)

        # 限制列表长度
        while self.file_list.count() > 15:
            self.file_list.takeItem(self.file_list.count() - 1)

    def on_file_double_clicked(self, item):
        """双击文件列表项"""
        file_path = item.data(Qt.UserRole)
        if file_path and os.path.exists(file_path):
            self.load_do_file(file_path)

    def on_history_double_clicked(self, item):
        """双击历史记录项"""
        history_item = item.data(Qt.UserRole)
        if history_item and history_item.get('file') and os.path.exists(history_item['file']):
            self.load_do_file(history_item['file'])

    def show_file_context_menu(self, pos):
        """显示文件列表右键菜单"""
        item = self.file_list.itemAt(pos)
        if not item:
            return

        menu = QMenu()

        execute_action = QAction("执行", self)
        execute_action.triggered.connect(lambda: self.execute_do_file(item.data(Qt.UserRole)))
        menu.addAction(execute_action)

        open_folder_action = QAction("打开所在文件夹", self)
        open_folder_action.triggered.connect(lambda: self.open_file_folder(item.data(Qt.UserRole)))
        menu.addAction(open_folder_action)

        remove_action = QAction("从列表移除", self)
        remove_action.triggered.connect(lambda: self.file_list.takeItem(self.file_list.row(item)))
        menu.addAction(remove_action)

        menu.exec_(self.file_list.mapToGlobal(pos))

    def show_history_context_menu(self, pos):
        """显示历史记录右键菜单"""
        item = self.history_list.itemAt(pos)
        if not item:
            return

        history_item = item.data(Qt.UserRole)
        menu = QMenu()

        if history_item and history_item.get('file') and os.path.exists(history_item['file']):
            execute_action = QAction("执行", self)
            execute_action.triggered.connect(lambda: self.execute_do_file(history_item['file']))
            menu.addAction(execute_action)

            open_folder_action = QAction("打开所在文件夹", self)
            open_folder_action.triggered.connect(lambda: self.open_file_folder(history_item['file']))
            menu.addAction(open_folder_action)

        delete_action = QAction("从历史删除", self)
        delete_action.triggered.connect(lambda: self.delete_history_item(item))
        menu.addAction(delete_action)

        menu.exec_(self.history_list.mapToGlobal(pos))

    def delete_history_item(self, item):
        """删除单条历史记录"""
        history_item = item.data(Qt.UserRole)
        if history_item in self.execution_history:
            self.execution_history.remove(history_item)
            self.save_history()
            self.refresh_history_list()
            self.refresh_file_list()

    def open_file_folder(self, file_path):
        """打开文件所在文件夹"""
        if os.path.exists(file_path):
            os.startfile(os.path.dirname(file_path))

    def execute_current_file(self):
        """执行当前选中的文件"""
        if self.current_file and os.path.exists(self.current_file):
            self.execute_do_file(self.current_file)

    def execute_do_file(self, file_path):
        """执行.do文件"""
        if self.is_executing:
            QMessageBox.warning(self, "警告", "已有任务正在执行，请等待完成或点击停止")
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()

            self.current_file = file_path
            self.file_info_label.setText(f"正在执行: {os.path.basename(file_path)}")
            self.code_preview.setText(code)

            # 清空输出
            self.clear_output()

            # 更新按钮状态
            self.execute_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.send_btn.setEnabled(False)
            self.is_executing = True

            # 显示执行开始信息
            self.append_output(f"\n{'=' * 60}")
            self.append_output(f"开始执行文件: {file_path}")
            self.append_output(f"执行时间: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self.append_output(f"{'=' * 60}\n")

            # 创建并启动执行线程
            self.execution_thread = ExecutionThread(code, file_path)
            self.execution_thread.output_signal.connect(self.append_output)
            self.execution_thread.error_signal.connect(self.append_error)
            self.execution_thread.finished_signal.connect(self.on_thread_finished)
            self.execution_thread.start()

        except Exception as e:
            self.execution_error.emit(f"读取文件失败: {str(e)}")
            self.execution_finished.emit(False)

    def on_thread_finished(self, success, result_message):
        """线程执行完成处理"""
        self.last_execution_success = success
        self.last_execution_result = result_message

        # 发送结果到输出
        if success:
            self.append_output("\n✅ 代码执行完成！")
        else:
            self.append_error("\n❌ 代码执行失败！")

        self.execution_finished.emit(success)

        # 如果配置了助手反馈，自动发送结果
        if self.assistant_config.get('enabled') and self.assistant_config.get('assistant_id'):
            self.send_result_to_assistant(success, result_message, self.current_file)
            self.append_output("\n📤 结果已自动发送给助手和云聊")
            self.send_btn.setEnabled(False)
        else:
            # 允许手动发送
            self.send_btn.setEnabled(True)

    def stop_execution(self):
        """停止执行"""
        if self.execution_thread and self.execution_thread.isRunning():
            self.execution_thread.stop()
            self.execution_thread.terminate()
            self.execution_thread.wait()

        self.is_executing = False
        self.append_output("\n⚠️ 执行被用户中断")
        self.execute_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.file_info_label.setText(f"已中断: {os.path.basename(self.current_file) if self.current_file else '无'}")

    def clear_output(self):
        """清空输出区域"""
        self.output_text.clear()

    def append_output(self, text):
        """添加输出文本"""
        self.output_text.append(text)
        # 滚动到底部
        cursor = self.output_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.output_text.setTextCursor(cursor)

    def append_error(self, text):
        """添加错误文本（红色显示）"""
        self.output_text.append(f'<span style="color: #ff6b6b;">{text}</span>')
        cursor = self.output_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.output_text.setTextCursor(cursor)

    def on_execution_finished(self, success):
        """执行完成后的处理"""
        self.is_executing = False
        self.execute_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        if success:
            self.file_info_label.setText(
                f"执行成功: {os.path.basename(self.current_file) if self.current_file else '无'}")
        else:
            self.file_info_label.setText(
                f"执行失败: {os.path.basename(self.current_file) if self.current_file else '无'}")

        self.append_output(f"\n{'=' * 60}")
        self.append_output(f"执行结束时间: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.append_output(f"{'=' * 60}")

        # 记录到历史
        if self.current_file:
            history_item = {
                'file': self.current_file,
                'time': dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'success': success,
                'error': '' if success else '执行失败'
            }
            self.execution_history.insert(0, history_item)
            self.save_history()
            self.refresh_history_list()
            self.refresh_file_list()

    def clear_all_history(self):
        """清除所有历史记录"""
        reply = QMessageBox.question(
            self,
            "确认清除",
            "确定要清除所有历史记录吗？\n此操作不可恢复！",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.execution_history = []
            self.save_history()
            self.refresh_file_list()
            self.refresh_history_list()
            QMessageBox.information(self, "完成", "历史记录已清除")

    def closeEvent(self, event):
        """重写关闭事件"""
        # 停止执行线程
        if self.execution_thread and self.execution_thread.isRunning():
            self.execution_thread.stop()
            self.execution_thread.terminate()
            self.execution_thread.wait()

        self.save_history()
        event.accept()


def main():
    app = QApplication(sys.argv)

    # 检查是否通过文件关联启动
    file_to_execute = None
    if len(sys.argv) > 1:
        potential_file = sys.argv[1]
        if potential_file.endswith('.do') and os.path.exists(potential_file):
            file_to_execute = potential_file

    # 创建主窗口
    window = DoFileExecutor(file_to_execute)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()