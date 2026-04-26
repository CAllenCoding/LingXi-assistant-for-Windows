import os
import sys
import time
import json
import re
import requests
import datetime as dt
import ast
import platform
import cv2
import numpy as np
import threading
import base64
import socket
from PIL import ImageGrab
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QPushButton, QVBoxLayout,
    QSizePolicy, QSpacerItem, QPlainTextEdit, QLabel, QScrollArea, QMenu, QAction, QInputDialog,
    QGroupBox, QCheckBox, QSpinBox, QComboBox, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtGui import QMouseEvent, QContextMenuEvent
from openai import OpenAI
import psutil


# 获取本机IP地址
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


# 屏幕捕获和发送线程 - 支持多端口发送
class ScreenShareThread(QThread):
    frame_sent = pyqtSignal(bool, str)  # (success, message)
    status_changed = pyqtSignal(str)

    def __init__(self, chat_ports, assistant_id, target_user_id, chat_server_ip='127.0.0.1'):
        """
        chat_ports: 列表，包含多个目标端口 [5001, 5002] 等
        chat_server_ip: 灵犀云聊服务IP地址
        """
        super().__init__()
        self.chat_ports = chat_ports if isinstance(chat_ports, list) else [chat_ports]
        self.assistant_id = assistant_id
        self.target_user_id = target_user_id
        self.chat_server_ip = chat_server_ip
        self.running = False
        self.fps = 10  # 10帧/秒
        self.quality = 70  # 图像质量
        self.scale_factor = 0.5  # 缩放因子

    def run(self):
        self.running = True
        self.status_changed.emit("屏幕共享已启动")

        last_frame_time = 0
        frame_interval = 1.0 / self.fps

        while self.running:
            try:
                current_time = time.time()

                # 控制帧率
                if current_time - last_frame_time < frame_interval:
                    time.sleep(0.01)
                    continue

                # 捕获屏幕
                screen = ImageGrab.grab()

                # 转换为numpy数组
                frame = np.array(screen)

                # ImageGrab返回的是RGB，不需要转换
                # frame已经是RGB格式

                # 缩放图像
                height, width = frame.shape[:2]
                new_width = int(width * self.scale_factor)
                new_height = int(height * self.scale_factor)
                frame = cv2.resize(frame, (new_width, new_height))

                # OpenCV的imencode需要BGR格式，所以要转换
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

                # 压缩为JPEG
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.quality]
                _, buffer = cv2.imencode('.jpg', frame_bgr, encode_param)

                frame_data = buffer.tobytes()
                encoded = base64.b64encode(frame_data).decode('utf-8')
                timestamp = dt.datetime.now().strftime('%H:%M:%S.%f')[:-3]

                # 发送到本地的chat_bot.py
                try:
                    url = "http://127.0.0.1:5004/api/screen_stream"
                    # 从chat_bot的助手数据库中获取实际的助手ID
                    import json
                    import os
                    # 尝试不同的路径
                    possible_paths = [
                        os.path.join('data', 'assistants.json'),
                        os.path.join(os.getcwd(), 'data', 'assistants.json'),
                        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'assistants.json')
                    ]
                    
                    assistant_id = None
                    for path in possible_paths:
                        if os.path.exists(path):
                            print(f"找到助手数据库: {path}")
                            with open(path, 'r', encoding='utf-8') as f:
                                assistants = json.load(f)
                                if assistants:
                                    # 使用第一个助手ID作为发送者ID
                                    assistant_id = list(assistants.keys())[0]
                                    print(f"使用助手ID: {assistant_id}")
                                    break
                                else:
                                    print("助手数据库为空")
                    
                    if not assistant_id:
                        print("没有找到有效的助手ID")
                        success_count = 0
                        continue
                    
                    data = {
                        'assistant_id': assistant_id,
                        'target_user_id': self.target_user_id,
                        'frame': encoded,
                        'timestamp': timestamp
                    }
                    print(f"发送屏幕帧到chat_bot.py: {data.keys()}")

                    # 发送请求
                    response = requests.post(url, json=data, timeout=0.5)

                    if response.status_code == 200:
                        print(f"画面帧已发送到chat_bot.py: {response.json()}")
                        success_count = 1
                    else:
                        print(f"发送到chat_bot.py失败: {response.status_code}, {response.text}")
                        success_count = 0

                except Exception as e:
                    print(f"发送到chat_bot.py失败: {e}")
                    success_count = 0

                # 如果失败，才报告错误
                if success_count == 0:
                    self.frame_sent.emit(False, "无法连接到chat_bot.py")

                last_frame_time = current_time

            except Exception as e:
                self.frame_sent.emit(False, str(e))
                time.sleep(1)

        self.status_changed.emit("屏幕共享已停止")

    def stop(self):
        self.running = False
        self.wait()


# 消息接收线程
class MessageReceiver(QThread):
    message_received = pyqtSignal(str, str)
    screen_request_received = pyqtSignal(str, bool)
    file_send_request = pyqtSignal(str, str, str)  # (from_user_id, file_path, file_name)

    def __init__(self, assistant_id, port=5003):
        super().__init__()
        self.assistant_id = assistant_id
        self.port = port
        self.running = True
        from flask import Flask, request, jsonify

        self.app = Flask(__name__)

        @self.app.route('/api/receive_from_chat', methods=['POST'])
        def receive_from_chat():
            data = request.json
            from_user_id = data.get('from_user_id')
            message = data.get('message')

            print(f"助手收到消息: from={from_user_id}, message={message}")

            if from_user_id and message:
                self.message_received.emit(from_user_id, message)
                return jsonify({'success': True})
            return jsonify({'success': False, 'message': '参数错误'}), 400

        @self.app.route('/api/screen_control', methods=['POST'])
        def screen_control():
            data = request.json
            from_user_id = data.get('from_user_id')
            action = data.get('action')

            print(f"收到屏幕控制请求: from={from_user_id}, action={action}")

            if from_user_id and action:
                self.screen_request_received.emit(from_user_id, action == 'start')
                return jsonify({'success': True})
            return jsonify({'success': False, 'message': '参数错误'}), 400

        @self.app.route('/api/send_file', methods=['POST'])
        def send_file_to_chat():
            """接收文件发送请求"""
            data = request.json
            from_user_id = data.get('from_user_id')
            file_path = data.get('file_path')
            file_name = data.get('file_name')

            print(f"收到文件发送请求: from={from_user_id}, file_path={file_path}, file_name={file_name}")

            if from_user_id and file_path:
                # 检查信号是否存在
                if hasattr(self, 'file_send_request'):
                    self.file_send_request.emit(from_user_id, file_path, file_name)
                    return jsonify({'success': True})
                else:
                    print("错误: file_send_request 信号不存在")
                    return jsonify({'success': False, 'message': '信号未初始化'}), 500
            return jsonify({'success': False, 'message': '参数错误'}), 400

        @self.app.route('/api/stop_screen', methods=['POST'])
        def stop_screen():
            """停止屏幕共享"""
            data = request.json
            from_user_id = data.get('from_user_id')

            if from_user_id:
                self.screen_request_received.emit(from_user_id, False)
                return jsonify({'success': True})
            return jsonify({'success': False, 'message': '参数错误'}), 400

    def run(self):
        print(f"=" * 50)
        print(f"助手消息接收服务启动")
        print(f"本地访问: http://127.0.0.1:{self.port}")
        print(f"局域网访问: http://{get_local_ip()}:{self.port}")
        print(f"助手ID: {self.assistant_id}")
        print(f"=" * 50)
        self.app.run(host='0.0.0.0', port=self.port, debug=False, use_reloader=False, threaded=True)

    def stop(self):
        self.running = False
        self.terminate()


class ClickableLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.setOpenExternalLinks(True)
        self.setWordWrap(True)

    def show_context_menu(self, pos):
        menu = QMenu(self)
        copy_action = QAction("复制", self)
        copy_action.triggered.connect(self.copy_text)
        menu.addAction(copy_action)
        menu.exec_(self.mapToGlobal(pos))

    def setText(self, text):
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
        text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)
        text = text.replace("\n", "<br>")
        super().setText(f"<html>{text}</html>")

    def copy_text(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.text().replace("灵犀助手: ", "").replace("你: ", "").strip()
                          .replace("<b>", "**").replace("</b>", "**")
                          .replace("<i>", "*").replace("</i>", "*")
                          .replace("<code>", "`").replace("</code>", "`")
                          .replace("<html>", "").replace("</html>", ""))


class RoundedWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config_file = '../assistant_config.json'
        self.load_config()

        self.timer = QTimer()
        self.timer.setInterval(10)
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.check)
        self.update_timer.start(100)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 初始化变量（必须在创建 message_receiver 之前）
        self.screen_share_thread = None
        self.current_screen_user = None
        self.screen_sharing_active = False
        self.target_ports = [5001, 5002]

        # 初始化AI对话相关变量
        self.current_ai_message = ""
        self.is_ai_responding = False
        self.last_ai_response = ""
        self.continuation_count = 0
        self.max_continuations = 5
        self.current_message_label = None
        self.last_user_message = ""
        self.last_response_mode = ""
        self.last_received_content = ""
        self.thinking_content_cache = ""
        self.answer_content_cache = ""
        self.full_response_cache = ""
        self.deep_thinking_mode = False
        self.last_question_file_content = ""
        self.is_processing_question_file = False
        self.current_chat_user_id = None

        # 初始化API和模型配置
        self.api_key = ''
        self.model_name = 'Qwen/Qwen3.5-397B-A17B'
        self.load_api_config()

        self.ai_client = OpenAI(
            base_url='https://api-inference.modelscope.cn/v1',
            api_key=self.api_key,
        )

        # 初始化消息接收器（在连接信号之前）
        self.message_receiver = None
        self.start_message_receiver()

        # 初始化UI（在消息接收器之后）
        self.init_ui()

        # 添加主题菜单
        self.create_theme_menu()

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.assistant_id = config.get('assistant_id', self.generate_assistant_id())
                    self.current_theme = config.get('theme', 'dark')
                    self.deep_thinking_mode = config.get('deep_thinking', False)
                    self.chat_port = config.get('chat_port', 5001)
                    self.assistant_port = config.get('assistant_port', 5003)
                    self.target_ports = config.get('target_ports', [5001, 5002])
                    self.screen_fps = config.get('screen_fps', 10)
                    self.screen_quality = config.get('screen_quality', 70)
                    self.chat_server_ip = config.get('chat_server_ip', '127.0.0.1')
            except Exception as e:
                print(f"加载配置出错: {e}")
                self.assistant_id = self.generate_assistant_id()
                self.current_theme = 'dark'
                self.deep_thinking_mode = False
                self.chat_port = 5001
                self.assistant_port = 5003
                self.target_ports = [5001, 5002]
                self.screen_fps = 10
                self.screen_quality = 70
                self.chat_server_ip = '127.0.0.1'
        else:
            self.assistant_id = self.generate_assistant_id()
            self.current_theme = 'dark'
            self.deep_thinking_mode = False
            self.chat_port = 5001
            self.assistant_port = 5003
            self.target_ports = [5001, 5002]
            self.screen_fps = 10
            self.screen_quality = 70
            self.chat_server_ip = '127.0.0.1'
            self.save_config()

    def save_config(self):
        config = {
            'assistant_id': self.assistant_id,
            'theme': self.current_theme,
            'deep_thinking': self.deep_thinking_mode,
            'chat_port': self.chat_port,
            'assistant_port': self.assistant_port,
            'target_ports': self.target_ports,
            'screen_fps': self.screen_fps,
            'screen_quality': self.screen_quality,
            'chat_server_ip': self.chat_server_ip
        }
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)

    def generate_assistant_id(self):
        import random
        import string
        chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$'
        return 'AST_' + ''.join(random.choices(chars, k=6))

    def start_message_receiver(self):
        """启动消息接收器并连接信号"""
        if self.message_receiver and self.message_receiver.isRunning():
            self.message_receiver.stop()
            self.message_receiver.wait()

        # 创建新的消息接收器
        self.message_receiver = MessageReceiver(self.assistant_id, self.assistant_port)
        
        # 连接信号
        self.message_receiver.message_received.connect(self.on_message_from_chat)
        self.message_receiver.screen_request_received.connect(self.on_screen_request)
        
        # 检查并连接文件发送信号
        if hasattr(self.message_receiver, 'file_send_request'):
            self.message_receiver.file_send_request.connect(self.on_file_send_request)
            print("文件发送信号已连接")
        else:
            print("警告: file_send_request 信号不存在")
        
        # 启动接收器
        self.message_receiver.start()

    def on_screen_request(self, from_user_id, start):
        if start:
            print(f"收到屏幕共享请求 from {from_user_id}")

            if self.screen_sharing_active:
                self.stop_screen_sharing()

            self.current_screen_user = from_user_id
            self.start_screen_sharing()
        else:
            print(f"收到停止屏幕共享请求 from {from_user_id}")
            self.stop_screen_sharing()

    def start_screen_sharing(self):
        if self.screen_sharing_active:
            return

        try:
            # 使用目标端口列表
            self.screen_share_thread = ScreenShareThread(
                self.target_ports,  # 传递端口列表
                self.assistant_id,
                self.current_screen_user,
                self.chat_server_ip  # 传递灵犀云聊服务IP
            )
            self.screen_share_thread.fps = self.screen_fps
            self.screen_share_thread.quality = self.screen_quality
            self.screen_share_thread.status_changed.connect(self.on_screen_status_changed)
            self.screen_share_thread.frame_sent.connect(self.on_frame_sent)
            self.screen_share_thread.start()

            self.screen_sharing_active = True
            self.update_screen_status()

            self.add_message("系统", f"🖥️ 屏幕共享已开始 (发送到端口: {', '.join(map(str, self.target_ports))})")
            print("屏幕共享已开始")

        except Exception as e:
            error_msg = f"启动屏幕共享失败: {str(e)}"
            print(error_msg)
            self.add_message("系统", f"❌ {error_msg}")
            self.stop_screen_sharing()

    def stop_screen_sharing(self):
        if self.screen_share_thread and self.screen_share_thread.isRunning():
            self.screen_share_thread.stop()
            self.screen_share_thread = None

        self.screen_sharing_active = False
        self.current_screen_user = None
        self.update_screen_status()

        self.add_message("系统", "⏹️ 屏幕共享已停止")
        print("屏幕共享已停止")

    def on_screen_status_changed(self, status):
        print(f"屏幕状态: {status}")
        if "连接断开" in status:
            self.stop_screen_sharing()

    def on_frame_sent(self, success, message):
        if not success and message == "所有目标连接失败":
            print("⚠️ 所有目标端口连接失败，请检查 chat 服务是否运行")
        elif success:
            print("✅ 画面帧发送成功")

    def send_file_to_user(self, file_path, target_user_id, file_name=None):
        """向用户发送文件"""
        import os
        import base64
        import requests
        import json
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            print(f"文件不存在: {file_path}")
            self.add_message("系统", f"❌ 文件不存在: {file_path}")
            return False
        
        if not file_name:
            file_name = os.path.basename(file_path)
        
        try:
            # 读取文件
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            file_size = len(file_data)
            if file_size > 10 * 1024 * 1024 * 1024:
                self.add_message("系统", f"❌ 文件太大 ({file_size/1024/1024/1024:.1f}MB)，最大10GB")
                return False
            
            # Base64编码
            file_b64 = base64.b64encode(file_data).decode('utf-8')
            
            # 从chat_bot的数据库中获取助手信息
            chat_bot_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
            assistants_db_path = os.path.join(chat_bot_data_dir, 'assistants.json')
            
            if os.path.exists(assistants_db_path):
                with open(assistants_db_path, 'r', encoding='utf-8') as f:
                    assistants = json.load(f)
                
                # 查找当前助手ID
                assistant_id = None
                for aid, info in assistants.items():
                    if info.get('local_id') == self.assistant_id:
                        assistant_id = aid
                        break
                
                if assistant_id:
                    # 发送文件到chat_bot
                    chat_bot_url = "http://127.0.0.1:5004/api/receive_file_from_lingxi"
                    data = {
                        'assistant_id': assistant_id,
                        'target_user_id': target_user_id,
                        'file_name': file_name,
                        'file_data': file_b64,
                        'file_size': file_size,
                        'timestamp': dt.datetime.now().strftime('%H:%M:%S')
                    }
                    print(f"正在发送文件到 chat_bot: {chat_bot_url}")
                    response = requests.post(chat_bot_url, json=data, timeout=30)
                    if response.status_code == 200:
                        print(f"文件已发送到 chat_bot: {file_name}")
                        self.add_message("系统", f"📁 文件已发送: {file_name} ({file_size/1024:.1f}KB)")
                        return True
                    else:
                        print(f"chat_bot 响应错误: {response.status_code}")
                        self.add_message("系统", f"❌ 文件发送失败: chat_bot 响应错误")
                        return False
                else:
                    print("未找到助手信息")
                    self.add_message("系统", f"❌ 文件发送失败: 未找到助手信息")
                    return False
            else:
                print("chat_bot 数据库不存在")
                self.add_message("系统", f"❌ 文件发送失败: chat_bot 数据库不存在")
                return False
        except Exception as e:
            print(f"发送文件失败: {e}")
            self.add_message("系统", f"❌ 文件发送失败: {str(e)}")
            return False

    def on_file_send_request(self, from_user_id, file_path, file_name):
        """处理文件发送请求"""
        print(f"处理文件发送请求: to={from_user_id}, file={file_path}")
        self.current_chat_user_id = from_user_id
        self.send_file_to_user(file_path, from_user_id, file_name)

    def send_file_by_command(self, file_path_or_name, target_user_id=None):
        """通过命令发送文件（供AI调用）"""
        if os.path.exists(file_path_or_name):
            file_path = file_path_or_name
        else:
            file_path = os.path.join(os.path.dirname(__file__), file_path_or_name)
            if not os.path.exists(file_path):
                desktop = os.path.join(os.path.expanduser("~"), "Desktop")
                file_path = os.path.join(desktop, file_path_or_name)
                if not os.path.exists(file_path):
                    return f"错误: 找不到文件 '{file_path_or_name}'"

        user_id = target_user_id or self.current_chat_user_id
        if not user_id:
            return "错误: 没有指定接收用户"

        if self.send_file_to_user(file_path, user_id):
            return f"成功: 文件 '{os.path.basename(file_path)}' 已发送给用户"
        else:
            return f"失败: 无法发送文件 '{os.path.basename(file_path)}'"

    def test_send_file(self, file_path):
        """测试发送文件功能"""
        if not self.current_chat_user_id:
            self.add_message("系统", "❌ 没有活跃的聊天用户")
            return False
        
        result = self.send_file_to_user(file_path, self.current_chat_user_id)
        if result:
            self.add_message("系统", f"✅ 测试文件发送成功")
        else:
            self.add_message("系统", f"❌ 测试文件发送失败")
        return result

    def on_message_from_chat(self, from_user_id, message):
        print(f"收到来自用户 {from_user_id} 的消息: {message}")

        self.current_chat_user_id = from_user_id

        n = dt.datetime.now()
        self.add_message(f"用户 {from_user_id[:8]}", message)

        with open('聊天记录.txt', 'a', encoding='utf-8') as hs:
            hs.write(str(n) + '\n' + f'用户 {from_user_id[:8]}: ' + message + '\n\n')

        self.current_message_label = ClickableLabel("灵犀助手: ")
        self.current_message_label.setWordWrap(True)
        self.current_message_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.current_message_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.chat_layout.addWidget(self.current_message_label)

        self.is_ai_responding = True
        self.current_ai_message = ""
        self.ai_response_loop(message, mode="pcc")

    def send_response_to_chat(self, response):
        if not self.current_chat_user_id:
            return

        try:
            # 发送响应到本地的chat_bot.py
            chat_bot_url = "http://127.0.0.1:5004/api/receive_from_lingxi"
            # 从chat_bot的助手数据库中获取实际的助手ID
            import json
            import os
            assistant_db_path = os.path.join('data', 'assistants.json')
            if os.path.exists(assistant_db_path):
                with open(assistant_db_path, 'r', encoding='utf-8') as f:
                    assistants = json.load(f)
                    if assistants:
                        # 使用第一个助手ID作为发送者ID
                        assistant_id = list(assistants.keys())[0]
                        print(f"使用助手ID: {assistant_id}")
                    else:
                        print("没有找到助手信息")
                        return
            else:
                print("助手数据库不存在")
                return
            
            data = {
                'assistant_id': assistant_id,
                'target_user_id': self.current_chat_user_id,
                'message': response
            }
            print(f"发送消息到chat_bot.py: {data}")
            response = requests.post(chat_bot_url, json=data, timeout=5)
            if response.status_code == 200:
                print(f"响应已发送到chat_bot.py: {response.json()}")
            else:
                print(f"发送到chat_bot.py失败: {response.status_code}, {response.text}")
        except Exception as e:
            print(f"发送响应给chat_bot.py失败: {e}")

    def init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(5)

        self.id_label = QLabel(f"助手ID: {self.assistant_id}")
        self.id_label.setFixedHeight(30)
        self.id_label.setStyleSheet("padding: 5px; border-radius: 5px;")
        button_layout.addWidget(self.id_label)

        self.screen_status = QLabel("⚫ 屏幕: 未共享")
        self.screen_status.setFixedHeight(30)
        self.screen_status.setStyleSheet("padding: 5px; border-radius: 5px; background-color: #2a3a4a;")
        button_layout.addWidget(self.screen_status)

        self.apply_theme()

        self.theme_button = QPushButton("深色模式 🌙" if self.current_theme == "dark" else "浅色模式 ☀️")
        self.theme_button.setFixedSize(120, 30)
        self.theme_button.clicked.connect(self.toggle_theme)
        button_layout.addWidget(self.theme_button)

        self.deep_thinking_button = QPushButton("深度思考: 关闭" if not self.deep_thinking_mode else "深度思考: 开启")
        self.deep_thinking_button.setFixedSize(120, 30)
        self.deep_thinking_button.clicked.connect(self.toggle_deep_thinking)
        button_layout.addWidget(self.deep_thinking_button)

        self.api_config_button = QPushButton("API配置")
        self.api_config_button.setFixedSize(100, 30)
        self.api_config_button.clicked.connect(self.show_api_config_dialog)
        button_layout.addWidget(self.api_config_button)

        self.model_config_button = QPushButton("模型配置")
        self.model_config_button.setFixedSize(100, 30)
        self.model_config_button.clicked.connect(self.show_model_config_dialog)
        button_layout.addWidget(self.model_config_button)

        self.screen_config_button = QPushButton("屏幕配置")
        self.screen_config_button.setFixedSize(100, 30)
        self.screen_config_button.clicked.connect(self.show_screen_config_dialog)
        button_layout.addWidget(self.screen_config_button)

        # 添加目标端口配置按钮
        self.ports_config_button = QPushButton("端口配置")
        self.ports_config_button.setFixedSize(100, 30)
        self.ports_config_button.clicked.connect(self.show_ports_config_dialog)
        button_layout.addWidget(self.ports_config_button)

        # 添加灵犀云聊服务IP配置按钮
        self.server_ip_config_button = QPushButton("灵犀云聊IP配置")
        self.server_ip_config_button.setFixedSize(100, 30)
        self.server_ip_config_button.clicked.connect(self.show_server_ip_config_dialog)
        button_layout.addWidget(self.server_ip_config_button)

        spacer = QSpacerItem(20, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        button_layout.addItem(spacer)

        minimize_button = QPushButton("─")
        minimize_button.setFixedSize(30, 30)
        minimize_button.clicked.connect(self.showMinimized)
        button_layout.addWidget(minimize_button)

        close_button = QPushButton("×")
        close_button.setFixedSize(30, 30)
        close_button.clicked.connect(self.close)
        button_layout.addWidget(close_button)

        main_layout.addLayout(button_layout)

        self.chat_scroll_area = QScrollArea(self)
        self.chat_scroll_area.setWidgetResizable(True)

        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setAlignment(Qt.AlignTop)
        self.chat_layout.setSpacing(5)
        self.chat_layout.setContentsMargins(10, 10, 10, 10)

        self.chat_scroll_area.setWidget(self.chat_container)
        main_layout.addWidget(self.chat_scroll_area)

        input_layout = QHBoxLayout()
        self.message_input = QPlainTextEdit(self)
        self.message_input.setPlaceholderText('输入消息...')
        self.message_input.setFixedHeight(60)
        input_layout.addWidget(self.message_input)

        send_button = QPushButton('发送')
        send_button.setFixedSize(80, 60)
        send_button.clicked.connect(self.send_ai_message)
        input_layout.addWidget(send_button)

        pcc_button = QPushButton('副驾驶')
        pcc_button.setFixedSize(80, 60)
        pcc_button.clicked.connect(self.send_pcc_message)
        input_layout.addWidget(pcc_button)

        history_button = QPushButton("历史记录")
        history_button.setFixedSize(80, 60)
        history_button.clicked.connect(self.show_history)
        input_layout.addWidget(history_button)

        config_button = QPushButton("配置")
        config_button.setFixedSize(80, 60)
        config_button.clicked.connect(self.show_assistant_config)
        input_layout.addWidget(config_button)

        main_layout.addLayout(input_layout)
        self.resize(800, 900)
        self.center()

        self.drag_pos = None
        self.drag_edge = None
        self.resize_margin = 10

        self.apply_theme()

    def show_ports_config_dialog(self):
        """显示目标端口配置对话框"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox

        dialog = QDialog(self)
        dialog.setWindowTitle("目标端口配置")
        layout = QVBoxLayout(dialog)

        # 说明文字
        info_label = QLabel("配置助手向哪些端口发送实时画面\n默认同时发送到电脑端(5001)和手机端(5002)")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #81A1C1; padding: 5px;")
        layout.addWidget(info_label)

        # 当前端口显示
        current_ports = ', '.join(map(str, self.target_ports))
        current_label = QLabel(f"当前目标端口: {current_ports}")
        current_label.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(current_label)

        # 端口输入
        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("新端口列表:"))
        port_edit = QLineEdit()
        port_edit.setPlaceholderText("例如: 5001,5002")
        port_edit.setText(','.join(map(str, self.target_ports)))
        port_layout.addWidget(port_edit)
        layout.addLayout(port_layout)

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
            try:
                # 解析端口列表
                port_text = port_edit.text().strip()
                ports = []
                for p in port_text.split(','):
                    p = p.strip()
                    if p:
                        ports.append(int(p))

                if ports:
                    self.target_ports = ports
                    self.save_config()
                    QMessageBox.information(self, "成功", f"目标端口已更新为: {', '.join(map(str, ports))}")
                else:
                    QMessageBox.warning(self, "错误", "端口列表不能为空")
            except ValueError:
                QMessageBox.warning(self, "错误", "端口格式错误，请用逗号分隔数字")

    def show_server_ip_config_dialog(self):
        """显示灵犀云聊服务IP配置对话框"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox

        dialog = QDialog(self)
        dialog.setWindowTitle("灵犀云聊服务IP配置")
        layout = QVBoxLayout(dialog)

        # 说明文字
        info_label = QLabel("配置灵犀云聊服务的IP地址\n默认为 127.0.0.1（本机）\n如需连接其他电脑的灵犀云聊服务，请填写对应IP地址")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #81A1C1; padding: 5px;")
        layout.addWidget(info_label)

        # 当前IP显示
        current_label = QLabel(f"当前灵犀云聊服务IP: {self.chat_server_ip}")
        current_label.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(current_label)

        # IP输入
        ip_layout = QHBoxLayout()
        ip_layout.addWidget(QLabel("灵犀云聊服务IP:"))
        ip_edit = QLineEdit()
        ip_edit.setPlaceholderText("例如: 192.168.1.100")
        ip_edit.setText(self.chat_server_ip)
        ip_layout.addWidget(ip_edit)
        layout.addLayout(ip_layout)

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
            try:
                # 验证IP地址
                ip_text = ip_edit.text().strip()
                if not ip_text:
                    QMessageBox.warning(self, "错误", "IP地址不能为空")
                    return

                # 简单的IP地址验证
                import re
                ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
                if not re.match(ip_pattern, ip_text):
                    QMessageBox.warning(self, "错误", "IP地址格式不正确，请输入有效的IP地址")
                    return

                # 验证每个数字段
                parts = ip_text.split('.')
                for part in parts:
                    num = int(part)
                    if num < 0 or num > 255:
                        QMessageBox.warning(self, "错误", "IP地址的每个数字段必须在0-255之间")
                        return

                self.chat_server_ip = ip_text
                self.save_config()
                QMessageBox.information(self, "成功", f"灵犀云聊服务IP已更新为: {ip_text}\n\n助手将向 {ip_text} 发送消息和文件")

            except Exception as e:
                QMessageBox.warning(self, "错误", f"更新失败: {str(e)}")

    def show_screen_config_dialog(self):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QSpinBox, QDialogButtonBox, QHBoxLayout

        dialog = QDialog(self)
        dialog.setWindowTitle("屏幕共享配置")
        layout = QVBoxLayout(dialog)

        form_layout = QFormLayout()

        fps_spin = QSpinBox()
        fps_spin.setRange(5, 30)
        fps_spin.setValue(self.screen_fps)
        fps_spin.setSuffix(" fps")
        form_layout.addRow("帧率:", fps_spin)

        quality_spin = QSpinBox()
        quality_spin.setRange(30, 90)
        quality_spin.setValue(self.screen_quality)
        quality_spin.setSuffix("%")
        form_layout.addRow("图像质量:", quality_spin)

        layout.addLayout(form_layout)

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
            self.screen_fps = fps_spin.value()
            self.screen_quality = quality_spin.value()
            self.save_config()

    def show_assistant_config(self):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLineEdit, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle("助手配置")
        layout = QVBoxLayout(dialog)

        form_layout = QFormLayout()

        id_edit = QLineEdit(self.assistant_id)
        id_edit.setReadOnly(True)
        form_layout.addRow("助手ID:", id_edit)

        chat_port_edit = QLineEdit(str(self.chat_port))
        form_layout.addRow("灵犀云聊端口:", chat_port_edit)

        assistant_port_edit = QLineEdit(str(self.assistant_port))
        form_layout.addRow("助手端口:", assistant_port_edit)

        layout.addLayout(form_layout)

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
            try:
                new_chat_port = int(chat_port_edit.text())
                new_assistant_port = int(assistant_port_edit.text())
                self.chat_port = new_chat_port
                self.assistant_port = new_assistant_port
                self.start_message_receiver()
                self.save_config()
                QMessageBox.information(self, "成功",
                                        f"配置已保存\n灵犀云聊端口: {self.chat_port}\n助手端口: {self.assistant_port}")
            except ValueError:
                QMessageBox.warning(self, "错误", "端口号必须是数字")

    def create_theme_menu(self):
        self.theme_menu = QMenu(self)
        dark_action = QAction("深色模式", self)
        dark_action.triggered.connect(lambda: self.set_theme("dark"))
        light_action = QAction("浅色模式", self)
        light_action.triggered.connect(lambda: self.set_theme("light"))
        self.theme_menu.addAction(dark_action)
        self.theme_menu.addAction(light_action)
        self.theme_button.setMenu(self.theme_menu)

    def toggle_theme(self):
        new_theme = "light" if self.current_theme == "dark" else "dark"
        self.set_theme(new_theme)

    def set_theme(self, theme):
        self.current_theme = theme
        self.theme_button.setText("深色模式 🌙" if theme == "dark" else "浅色模式 ☀️")
        self.save_config()
        self.apply_theme()

    def toggle_deep_thinking(self):
        self.deep_thinking_mode = not self.deep_thinking_mode
        self.deep_thinking_button.setText("深度思考: 开启" if self.deep_thinking_mode else "深度思考: 关闭")
        self.save_config()

    def load_api_config(self):
        config_file = 'api_key.txt'
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    for line in lines:
                        line = line.strip()
                        if line.startswith('api_key='):
                            self.api_key = line.split('=', 1)[1]
                        elif line.startswith('model='):
                            self.model_name = line.split('=', 1)[1]
            except Exception as e:
                print(f"加载API配置时出错: {str(e)}")
                self.api_key = ''
                self.model_name = 'Qwen/Qwen3.5-397B-A17B'
        else:
            self.api_key = ''
            self.model_name = 'Qwen/Qwen3.5-397B-A17B'

    def save_api_config(self):
        with open('api_key.txt', 'w', encoding='utf-8') as f:
            f.write(f'api_key={self.api_key}\n')
            f.write(f'model={self.model_name}\n')

    def show_api_config_dialog(self):
        dialog = QInputDialog(self)
        dialog.setWindowTitle("API配置")
        dialog.setLabelText("请输入API Key:")
        dialog.setTextValue(self.api_key)
        dialog.setInputMode(QInputDialog.TextInput)
        dialog.setFixedSize(500, 150)
        if dialog.exec_() == QInputDialog.Accepted:
            new_api_key = dialog.textValue().strip()
            if new_api_key:
                self.api_key = new_api_key
                self.ai_client.api_key = self.api_key
                self.save_api_config()
                QMessageBox.information(self, "成功", "API Key已保存")

    def show_model_config_dialog(self):
        dialog = QInputDialog(self)
        dialog.setWindowTitle("模型配置")
        dialog.setLabelText("请输入模型名称:")
        dialog.setTextValue(self.model_name)
        dialog.setInputMode(QInputDialog.TextInput)
        dialog.setFixedSize(500, 150)
        if dialog.exec_() == QInputDialog.Accepted:
            new_model_name = dialog.textValue().strip()
            if new_model_name:
                self.model_name = new_model_name
                self.save_api_config()
                QMessageBox.information(self, "成功", f"模型名称已更新: {new_model_name}")

    def apply_theme(self):
        if self.current_theme == "dark":
            self.setStyleSheet("""
                QMainWindow { background: transparent; }
                QWidget { 
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                        stop:0 #0f172a, 
                        stop:0.5 #1e293b, 
                        stop:1 #0f172a); 
                    border-radius: 16px; 
                    border: 1px solid #334155; 
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
                }
                QPushButton { 
                    background-color: #334155; 
                    color: #94a3b8; 
                    border-radius: 12px; 
                    font-size: 14px; 
                    border: 1px solid #475569; 
                    padding: 6px 12px; 
                    transition: all 0.3s ease;
                }
                QPushButton:hover { 
                    background-color: #475569; 
                    color: #e2e8f0; 
                    transform: translateY(-1px);
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
                }
                QPushButton:pressed { 
                    background-color: #64748b; 
                    transform: translateY(1px);
                }
                QScrollArea { 
                    background-color: rgba(15, 23, 42, 0.5); 
                    border-radius: 12px; 
                    border: 1px solid #334155; 
                    box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.2);
                }
                QPlainTextEdit { 
                    background-color: rgba(15, 23, 42, 0.7); 
                    color: #cbd5e1; 
                    border-radius: 12px; 
                    border: 1px solid #334155; 
                    padding: 10px; 
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    font-size: 14px;
                }
                QPlainTextEdit:focus { 
                    border: 1px solid #64748b; 
                    outline: none;
                }
                QLabel, ClickableLabel { 
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                        stop:0 #1e293b, 
                        stop:1 #334155); 
                    color: #e2e8f0; 
                    border-radius: 12px; 
                    padding: 10px 14px; 
                    margin: 4px; 
                    border: 1px solid #475569; 
                    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
                }
                #id_label { 
                    background-color: #334155; 
                    color: #94a3b8; 
                    border-radius: 8px; 
                    padding: 4px 8px;
                }
                #screen_status { 
                    background-color: #1e293b; 
                    color: #94a3b8; 
                    border-radius: 8px; 
                    padding: 4px 8px;
                }
            """)
        else:
            self.setStyleSheet("""
                QMainWindow { background: transparent; }
                QWidget { 
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                        stop:0 #f0f9ff, 
                        stop:0.5 #e0f2fe, 
                        stop:1 #f0f9ff); 
                    border-radius: 16px; 
                    border: 1px solid #bae6fd; 
                    box-shadow: 0 8px 32px rgba(59, 130, 246, 0.1);
                }
                QPushButton { 
                    background-color: #dbeafe; 
                    color: #1e40af; 
                    border-radius: 12px; 
                    font-size: 14px; 
                    border: 1px solid #bfdbfe; 
                    padding: 6px 12px; 
                    transition: all 0.3s ease;
                }
                QPushButton:hover { 
                    background-color: #bfdbfe; 
                    color: #1e40af; 
                    transform: translateY(-1px);
                    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.2);
                }
                QPushButton:pressed { 
                    background-color: #93c5fd; 
                    transform: translateY(1px);
                }
                QScrollArea { 
                    background-color: rgba(240, 249, 255, 0.7); 
                    border-radius: 12px; 
                    border: 1px solid #bae6fd; 
                    box-shadow: inset 0 2px 4px rgba(59, 130, 246, 0.05);
                }
                QPlainTextEdit { 
                    background-color: rgba(240, 249, 255, 0.9); 
                    color: #1e40af; 
                    border-radius: 12px; 
                    border: 1px solid #bae6fd; 
                    padding: 10px; 
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    font-size: 14px;
                }
                QPlainTextEdit:focus { 
                    border: 1px solid #60a5fa; 
                    outline: none;
                }
                QLabel, ClickableLabel { 
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                        stop:0 #dbeafe, 
                        stop:1 #bfdbfe); 
                    color: #1e40af; 
                    border-radius: 12px; 
                    padding: 10px 14px; 
                    margin: 4px; 
                    border: 1px solid #bfdbfe; 
                    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.1);
                }
                #id_label { 
                    background-color: #dbeafe; 
                    color: #1e40af; 
                    border-radius: 8px; 
                    padding: 4px 8px;
                }
                #screen_status { 
                    background-color: #f0f9ff; 
                    color: #3b82f6; 
                    border-radius: 8px; 
                    padding: 4px 8px;
                }
            """)
        self.id_label.setObjectName("id_label")
        self.screen_status.setObjectName("screen_status")

    def update_screen_status(self):
        if self.screen_sharing_active and self.current_screen_user:
            ports_str = ', '.join(map(str, self.target_ports))
            self.screen_status.setText(f"🟢 屏幕: 共享中 (给 {self.current_screen_user[:8]} 端口:{ports_str})")
            self.screen_status.setStyleSheet(
                "padding: 5px; border-radius: 5px; background-color: #1a5a3a; color: #aaffaa;")
        else:
            self.screen_status.setText("⚫ 屏幕: 未共享")
            self.screen_status.setStyleSheet(
                "padding: 5px; border-radius: 5px; background-color: #2a3a4a; color: #aaa;")

    def check(self):
        try:
            with open('question.txt', 'r', encoding='utf-8') as hs:
                message_ = hs.read().strip()
            if (not message_ or
                    message_ == self.last_question_file_content or
                    self.is_processing_question_file or
                    self.is_ai_responding):
                return
            self.is_processing_question_file = True
            self.last_question_file_content = message_
            self.message_input.setPlainText(message_)
            QApplication.processEvents()
            self.send_ai_message()
            with open('question.txt', 'w', encoding='utf-8') as hs:
                hs.write('')
        except Exception as e:
            print(f"检查question.txt时出错: {str(e)}")
        finally:
            self.is_processing_question_file = False

    def send_ai_message(self):
        message = self.message_input.toPlainText().strip()
        if not message:
            return
        if hasattr(self, 'last_sent_message') and self.last_sent_message == message and self.is_ai_responding:
            return
        self.last_sent_message = message
        self.last_user_message = message
        n = dt.datetime.now()
        self.add_message("你", message)
        self.message_input.clear()
        self.chat_scroll_area.verticalScrollBar().setValue(
            self.chat_scroll_area.verticalScrollBar().maximum()
        )
        with open('聊天记录.txt', 'a', encoding='utf-8') as hs:
            hs.write(str(n) + '\n' + message + '\n\n')
        self.current_message_label = ClickableLabel("灵犀助手: ")
        self.current_message_label.setWordWrap(True)
        self.current_message_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.current_message_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.chat_layout.addWidget(self.current_message_label)
        self.is_ai_responding = True
        self.current_ai_message = ""
        self.ai_response_loop(message, mode="normal")

    def send_pcc_message(self):
        message = self.message_input.toPlainText().strip()
        if not message:
            return
        self.last_user_message = message
        n = dt.datetime.now()
        self.add_message("你", message)
        self.message_input.clear()
        self.chat_scroll_area.verticalScrollBar().setValue(
            self.chat_scroll_area.verticalScrollBar().maximum()
        )
        with open('聊天记录.txt', 'a', encoding='utf-8') as hs:
            hs.write(str(n) + '\n' + message + '\n\n')
        self.current_message_label = ClickableLabel("副驾驶: ")
        self.current_message_label.setWordWrap(True)
        self.current_message_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.current_message_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.chat_layout.addWidget(self.current_message_label)
        self.is_ai_responding = True
        self.current_ai_message = ""
        self.ai_response_loop(message, mode="pcc")

    def ai_response_loop(self, user_message, mode="normal", is_continuation=False):
        try:
            if is_continuation:
                self.continuation_count += 1
            else:
                self.continuation_count = 0
                self.last_response_mode = mode
                self.last_received_content = ""
                self.thinking_content_cache = ""
                self.answer_content_cache = ""
                self.full_response_cache = ""

            with open('聊天记录.txt', 'r', encoding='utf-8') as hs:
                history_ = hs.read()

            if mode == "normal":
                system_content = f"""你是灵犀助手，为用户答疑解惑。你与用户的聊天记录为：{history_}，请根据聊天记录和当前问题提供帮助。"""
            else:
                system_content = f"""你是灵犀助手，为用户答疑解惑。你与用户的聊天记录为：{history_}，如果用户让你进行电脑实际操作等非文本性操作的话，
                生成相应的python代码，并且只生成一个Python程序，能满足用户的所有要求，生成Python代码的开头要有```python这一标志性字符串

                【重要】如果用户要求你发送文件给他，请使用以下格式：
                [SEND_FILE]
                文件路径（可以是绝对路径，也可以是相对于助手程序目录的路径）
                [/SEND_FILE]

                例如，如果用户说"把桌面的图片发给我"，你需要在回答中输出：
                [SEND_FILE]
                C:\\Users\\用户名\\Desktop\\图片.jpg
                [/SEND_FILE]

                如果用户说"把当前目录下的test.txt文件发给我"，输出：
                [SEND_FILE]
                test.txt
                [/SEND_FILE]

                注意：文件大小不能超过10GB。发送文件后，助手会自动将文件传送给用户。

                【图像识别功能】当用户需要识别图像内容或者你需要尝试读取屏幕时（如用户需要你去搜索或者查看什么并且需要你总结或者给出具体内容时），请使用 `recognize_image` 函数进行图像识别：
                
                # 调用示例
                result = recognize_image("识别图像内容", "image_path.png")  # 替换为实际图片路径
                print(result)
                
                注意：我的环境下已经有了recognize_image函数，不需导入
                
                【语音识别功能】当用户需要识别音频内容时，请使用 `recognize_audio` 函数进行语音识别：
                
                # 调用示例
                result = recognize_audio("audio_path.mp3")  # 替换为实际音频路径
                print(result)
                
                注意：我的环境下已经有了recognize_audio函数，不需导入
                
                【发送文件功能】当在执行任务过程中需要发送文件时，请使用 `send_file` 函数：
                
                # 调用示例
                result = send_file("file_path.txt", "{self.current_chat_user_id}")  # 替换为实际文件路径
                print(result)

                注意：若用户除了发送文件外还要有实际操作，请不要使用 [SEND_FILE] 格式发送文件，而是使用 `send_file` 函数，如果单纯发送文件就使用[SEND_FILE]。
                另外注意：用户id为{self.current_chat_user_id}，这个是作为文件传输的第二个参数

                若有操作类似的任务并且用户已让你保存过do，直接写入json变量文件后直接用os.popen('xxx.do')打开do，不要重新编写自动化代码，
                你需要通过Python代码，仅用到pyautogui的键盘操作以及快捷键等进行操作，不要用自定义函数，
                注意，只可使用快捷键，模仿人进行快捷键操作，
                如果需要输入文字，就用pyperclip，你的电脑操作代码要先用keyboard模块检测是否开启大写锁定，
                如果未开启便开启大写锁定，操作结束后再关闭大写锁定，
                如果用户在网站上需要搜索（默认为百度搜索）某个内容，可以直接通过网址来跳过搜索过程，不用模拟人为的搜索方式，
                若用户需要打开某个东西，可以通过Windows搜索框来搜索并打开对应项目进行下一步操作，提醒：用户用的是{platform.platform()}系统，
                若用户需要保存对应的自动化程序，注意是仅仅这个时候，便把这个自动化程序默认保存到当前目录下的xxx.do这个文件，xxx你自己尝试简短概括一下是什么内容，
                如果用户有说要保存到哪里，就保存到对应目录的xxx.do，特别注意必须用python的open()、write()函数方式写入文件，
                你不要在写代码的时候写多余的无用的思考、注释什么的，浪费时间，千万不要加那么多注释代表你在思考，
                如果用户需要保存do文件，有关发信息以及一些下一次会有不同的输入、搜索内容但是基本操作框架相同的话，就保存基本框架的代码为do文件，变量不写入do文件，用读取方式更方便，下次可以利用，
                然后不确定内容就用另一个json文件作为变量保存，供给do文件读取，下次默认用基本框架do文件，
                还有你和用户的聊天记录在当前目录的聊天记录.txt文件中，若要清楚时，直接用open、write的"w"写入""字符串以清空"""

            if is_continuation and self.full_response_cache:
                continuation_prompt = f"\n\n注意：你的回答刚才因为网络连接中断而未完成。这是你刚才的回答（已接收部分）：\n{self.full_response_cache}\n\n请从刚才中断的地方继续完成你的回答，确保回答的完整性和连贯性。如果你之前正在生成代码，请确保代码的完整性。"
                user_message_with_context = user_message + continuation_prompt
            else:
                user_message_with_context = user_message

            extra_body = {
                "enable_thinking": self.deep_thinking_mode
            }

            response = self.ai_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {'role': 'system', 'content': system_content},
                    {'role': 'user', 'content': user_message_with_context}
                ],
                stream=True,
                extra_body=extra_body
            )

            done_thinking = False
            thinking_content = self.thinking_content_cache
            answer_content = self.answer_content_cache
            full_response = self.full_response_cache

            for chunk in response:
                if chunk.choices:
                    thinking_chunk = chunk.choices[0].delta.reasoning_content or ""
                    answer_chunk = chunk.choices[0].delta.content or ""

                    if thinking_chunk != '':
                        thinking_content += thinking_chunk
                        self.thinking_content_cache = thinking_content
                        if is_continuation:
                            thinking_display = f"🔄 重新连接后继续思考...\n{thinking_content}"
                        else:
                            thinking_display = f"🤔 思考中...\n{thinking_content}"
                        self.current_ai_message = thinking_display
                        self.update_ai_display("")

                    elif answer_chunk != '':
                        if not done_thinking and self.deep_thinking_mode:
                            answer_header = "\n\n=== 回答 ===\n\n"
                            if is_continuation:
                                answer_header = "\n\n=== 续答 ===\n\n"
                            self.current_ai_message = thinking_display + answer_header
                            self.update_ai_display(answer_header)
                            done_thinking = True
                        answer_content += answer_chunk
                        self.answer_content_cache = answer_content
                        full_response += answer_chunk
                        self.full_response_cache = full_response
                        if self.deep_thinking_mode:
                            self.current_ai_message = thinking_display + "\n\n=== 回答 ===\n\n" + answer_content
                        else:
                            self.current_ai_message = answer_content
                        self.update_ai_display(answer_chunk)

                    time.sleep(0.01)
                    QApplication.processEvents()

            if mode == "pcc" and answer_content.strip():
                self.extract_and_execute_code(answer_content, user_message)
            elif mode == "normal" and not self.is_response_complete(
                    full_response) and self.continuation_count < self.max_continuations:
                self.continuation_count += 1
                QTimer.singleShot(100, lambda: self.ai_response_loop(user_message, mode))
                return

            self.finalize_ai_response(user_message, mode)
            self.is_ai_responding = False
            if hasattr(self, 'last_sent_message'):
                del self.last_sent_message

            if self.current_chat_user_id:
                self.send_response_to_chat(self.current_ai_message)

        except Exception as e:
            error_msg = str(e)
            if "peer closed connection without sending complete message body" in error_msg or \
                    "incomplete chunked read" in error_msg:
                if self.continuation_count < self.max_continuations:
                    continuation_msg = "\n\n⏳ 连接中断，正在尝试续答..."
                    self.current_ai_message += continuation_msg
                    self.update_ai_display(continuation_msg)
                    QTimer.singleShot(500, lambda: self.retry_ai_response(user_message, mode))
                    return
                else:
                    error_msg = "网络连接不稳定，已尝试多次续答仍失败。请稍后重试。"
                    self.current_ai_message += f"\n❌ {error_msg}"
                    self.update_ai_display(f"\n❌ {error_msg}")
            else:
                error_msg = f"灵犀助手响应错误: {str(e)}"
                self.current_ai_message += f"\n❌ {error_msg}"
                self.update_ai_display(f"\n❌ {error_msg}")
            self.finalize_ai_response(user_message, mode)
            self.is_ai_responding = False
            if hasattr(self, 'last_sent_message'):
                del self.last_sent_message

    def retry_ai_response(self, user_message, mode):
        try:
            retry_msg = f"\n🔄 正在续答... (尝试 {self.continuation_count + 1}/{self.max_continuations})"
            self.current_ai_message += retry_msg
            self.update_ai_display(retry_msg)
            self.ai_response_loop(user_message, mode, is_continuation=True)
        except Exception as e:
            error_msg = f"续答失败: {str(e)}"
            self.current_ai_message += f"\n❌ {error_msg}"
            self.update_ai_display(f"\n❌ {error_msg}")
            self.finalize_ai_response(user_message, mode)
            self.is_ai_responding = False

    def extract_and_execute_code(self, full_response, user_message):
        try:
            # 检查是否是发送文件的请求
            send_file_match = re.search(r'\[SEND_FILE\](.*?)\[/SEND_FILE\]', full_response, re.DOTALL)
            if send_file_match:
                file_spec = send_file_match.group(1).strip()
                lines = file_spec.split('\n')
                file_path = lines[0].strip()
                result = self.send_file_by_command(file_path)
                success_msg = f"\n\n📁 {result}"
                self.current_ai_message += success_msg
                self.update_ai_display(success_msg)
                return

            code_pattern = r'```python(.*?)```'
            matches = re.findall(code_pattern, full_response, re.DOTALL)
            if matches:
                extracted_code = matches[0].strip()
                with open('generated_code.do', 'w', encoding='utf-8') as f:
                    f.write(extracted_code)
                try:
                    self.import_required_modules(extracted_code)
                    os.popen('generated_code.do')
                    success_msg = "\n\n✅ 灵犀助手代码执行成功！"
                    self.current_ai_message += success_msg
                    self.update_ai_display(success_msg)
                except Exception as e:
                    error_msg = f"\n\n❌ 代码执行错误: {str(e)}"
                    self.current_ai_message += error_msg
                    self.update_ai_display(error_msg)
            else:
                no_code_msg = "\n\n⚠️ 未找到可执行的Python代码块。"
                self.current_ai_message += no_code_msg
                self.update_ai_display(no_code_msg)
        except Exception as e:
            error_msg = f"处理灵犀助手响应时出错: {str(e)}"
            self.current_ai_message += f"\n{error_msg}"
            self.update_ai_display(f"\n{error_msg}")

    def import_required_modules(self, code):
        try:
            imported_modules = []
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imported_modules.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imported_modules.append(node.module)
            import importlib
            for module_name in imported_modules:
                try:
                    importlib.import_module(module_name)
                except ModuleNotFoundError as e:
                    print(f"模块 {module_name} 未安装: {str(e)}")
        except Exception as e:
            print(f"解析导入模块时出错: {str(e)}")

    def update_ai_display(self, content):
        if self.current_message_label:
            formatted_message = self.current_ai_message
            if "```" in formatted_message:
                formatted_message = formatted_message.replace("    ", "&nbsp;&nbsp;&nbsp;&nbsp;")
            self.current_message_label.setText(formatted_message)
            self.current_message_label.adjustSize()
            self.chat_scroll_area.verticalScrollBar().setValue(
                self.chat_scroll_area.verticalScrollBar().maximum()
            )
            QApplication.processEvents()

    def finalize_ai_response(self, user_message, mode="normal"):
        if not self.current_ai_message.strip():
            return
        self.chat_scroll_area.verticalScrollBar().setValue(
            self.chat_scroll_area.verticalScrollBar().maximum()
        )
        QApplication.processEvents()
        n = dt.datetime.now()
        prefix = "副驾驶" if mode == "pcc" else "灵犀助手"
        with open('聊天记录.txt', 'a', encoding='utf-8') as hs:
            hs.write(str(n) + '\n' + prefix + ': ' + self.current_ai_message + '\n\n')
        with open('answer.txt', 'w', encoding='utf-8') as hs:
            hs.write(self.current_ai_message)
        with open('question.txt', 'w', encoding='utf-8') as hs:
            hs.write('')

    def show_history(self):
        os.popen('历史记录查看.exe')

    def is_response_complete(self, response):
        if not response.strip():
            return True
        if "```" in response:
            return response.count("```") % 2 == 0
        lines = response.split('\n')
        last_line = lines[-1].strip()
        if last_line.startswith(('- ', '* ', '1. ', '2. ', '3. ', '# ', '## ', '### ')):
            return False
        incomplete_indicators = ['，', ',', '、', '而且', '但是', '不过', '然而', '然后', '接着', '因此', '所以', '因为']
        if any(response.rstrip().endswith(indicator) for indicator in incomplete_indicators):
            return False
        if response.count('"') % 2 != 0 or response.count("'") % 2 != 0:
            return False
        if (response.count('(') != response.count(')') or
                response.count('[') != response.count(']') or
                response.count('{') != response.count('}')):
            return False
        last_line = lines[-1].strip()
        if len(last_line) > 0 and last_line[-1] not in {'.', '!', '?', '。', '！', '？', ';', '；', ':', '：'}:
            if len(lines) > 1:
                return False
        return True

    def add_message(self, sender, message):
        message_label = ClickableLabel(f"{sender}: {message}")
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        message_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.chat_layout.addWidget(message_label)
        self.chat_scroll_area.verticalScrollBar().setValue(
            self.chat_scroll_area.verticalScrollBar().maximum()
        )

    def center(self):
        screen = QApplication.primaryScreen().geometry()
        size = self.geometry()
        x = (screen.width() - size.width()) // 2
        y = (screen.height() - size.height()) // 2
        self.move(x, y)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPos()
            self.drag_edge = self.get_edge(event.pos())

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.LeftButton:
            if self.drag_edge:
                self.resize_window(event.globalPos())
            else:
                self.move(self.pos() + event.globalPos() - self.drag_pos)
                self.drag_pos = event.globalPos()
                event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.drag_pos = None
            self.drag_edge = None

    def get_edge(self, pos):
        rect = self.rect()
        if pos.x() <= self.resize_margin:
            if pos.y() <= self.resize_margin:
                return "top-left"
            elif pos.y() >= rect.height() - self.resize_margin:
                return "bottom-left"
            else:
                return "left"
        elif pos.x() >= rect.width() - self.resize_margin:
            if pos.y() <= self.resize_margin:
                return "top-right"
            elif pos.y() >= rect.height() - self.resize_margin:
                return "bottom-right"
            else:
                return "right"
        elif pos.y() <= self.resize_margin:
            return "top"
        elif pos.y() >= rect.height() - self.resize_margin:
            return "bottom"
        return None

    def resize_window(self, global_pos):
        rect = self.rect()
        delta = global_pos - self.drag_pos
        geometry = self.geometry()
        if self.drag_edge == "left":
            geometry.setLeft(geometry.left() + delta.x())
        elif self.drag_edge == "right":
            geometry.setRight(geometry.right() + delta.x())
        elif self.drag_edge == "top":
            geometry.setTop(geometry.top() + delta.y())
        elif self.drag_edge == "bottom":
            geometry.setBottom(geometry.bottom() + delta.y())
        elif self.drag_edge == "top-left":
            geometry.setTopLeft(geometry.topLeft() + delta)
        elif self.drag_edge == "top-right":
            geometry.setTopRight(geometry.topRight() + delta)
        elif self.drag_edge == "bottom-left":
            geometry.setBottomLeft(geometry.bottomLeft() + delta)
        elif self.drag_edge == "bottom-right":
            geometry.setBottomRight(geometry.bottomRight() + delta)
        self.setGeometry(geometry)
        self.drag_pos = global_pos

    def closeEvent(self, event):
        self.stop_screen_sharing()
        if self.message_receiver and self.message_receiver.isRunning():
            self.message_receiver.stop()
            self.message_receiver.wait()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = RoundedWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    hs = open('cl.txt', 'w', encoding='utf-8')
    hs.write('0')
    hs.close()
    hs = open('question.txt', 'w', encoding='utf-8')
    hs.write('')
    hs.close()
    pd = os.listdir('./')
    flag = 0
    if '账号记录.txt' not in pd:
        a = open('账号记录.txt', 'w', encoding='utf-8')
        a.write('')
        a.close()
    hs = open('账号记录.txt', 'r', encoding='utf-8')
    user = hs.read()
    hs.close()
    if user == '':
        os.popen('登录窗口.exe')
    while True:
        hs = open('账号记录.txt', 'r', encoding='utf-8')
        user = hs.read()
        hs.close()
        if user != '':
            break
    os.popen('execute_app.exe')
    main()