import os
import json
import random
import string
import time
import datetime
import requests
import socket
from flask import Flask, request, jsonify, render_template_string, session
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'lingxi_chat_bot_secret_key_ultra_secure'
app.config['UPLOAD_FOLDER'] = 'uploads'

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
if not os.path.exists('data'):
    os.makedirs('data')

# 数据库文件
ASSISTANT_DB = os.path.join('data', 'assistants.json')
CONFIG_DB = os.path.join('data', 'config.json')

# 初始化数据库
def init_db():
    if not os.path.exists(ASSISTANT_DB):
        with open(ASSISTANT_DB, 'w') as f:
            json.dump({}, f)
    if not os.path.exists(CONFIG_DB):
        with open(CONFIG_DB, 'w') as f:
            json.dump({
                'port': 5004,
                'chat_pc_url': 'http://116.62.84.244:5002',  # 默认云端chat_pc地址
                'lingxi_port': 5003  # 默认LingXi端口
            }, f)

# 加载JSON文件
def load_json(filepath):
    if not os.path.exists(filepath):
        return {}
    with open(filepath, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except:
            return {}

# 保存JSON文件
def save_json(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# 生成唯一的助手ID
def generate_assistant_id():
    chars = string.ascii_letters + string.digits + "!@#$"
    while True:
        aid = 'AST_' + ''.join(random.choices(chars, k=6))
        assistants = load_json(ASSISTANT_DB)
        if aid not in assistants:
            return aid

# 生成随机密码
def generate_password(length=8):
    chars = string.ascii_letters + string.digits + "!@#$"
    return ''.join(random.choices(chars, k=length))

# 初始化数据库
init_db()

# HTML模板
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>灵犀助手Bot - 本地服务器</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0d17;
            --panel-color: #15192b;
            --text-color: #e0e6ed;
            --accent-color: #00f2ff;
            --accent-hover: #00c8d4;
            --border-color: #2a3040;
            --danger: #ff4757;
            --success: #2ed573;
            --warning: #ffa502;
            --transition: all 0.3s ease;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Segoe UI', sans-serif;
        }

        body {
            background-color: var(--bg-color);
            color: var(--text-color);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 800px;
            margin: 0 auto;
            background: var(--panel-color);
            border-radius: 15px;
            box-shadow: 0 0 30px rgba(0,0,0,0.5);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(135deg, var(--accent-color), #9b59b6);
            padding: 30px;
            text-align: center;
        }

        .header h1 {
            font-size: 28px;
            font-weight: bold;
            margin-bottom: 10px;
            color: white;
        }

        .header p {
            color: rgba(255,255,255,0.8);
            font-size: 14px;
        }

        .content {
            padding: 30px;
        }

        .section {
            margin-bottom: 30px;
        }

        .section h2 {
            font-size: 20px;
            margin-bottom: 20px;
            color: var(--accent-color);
            border-bottom: 2px solid var(--border-color);
            padding-bottom: 10px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
        }

        .form-group input {
            width: 100%;
            padding: 12px;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            background: var(--bg-color);
            color: var(--text-color);
            font-size: 16px;
            transition: var(--transition);
        }

        .form-group input:focus {
            border-color: var(--accent-color);
            outline: none;
            box-shadow: 0 0 10px rgba(0, 242, 255, 0.2);
        }

        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: var(--transition);
            margin-right: 10px;
        }

        .btn-primary {
            background: var(--accent-color);
            color: #000;
        }

        .btn-primary:hover {
            background: var(--accent-hover);
            transform: translateY(-2px);
        }

        .btn-danger {
            background: var(--danger);
            color: white;
        }

        .btn-danger:hover {
            background: #ff3747;
            transform: translateY(-2px);
        }

        .btn-success {
            background: var(--success);
            color: white;
        }

        .btn-success:hover {
            background: #28c76f;
            transform: translateY(-2px);
        }

        .assistant-list {
            margin-top: 20px;
        }

        .assistant-item {
            background: var(--bg-color);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 15px;
            transition: var(--transition);
        }

        .assistant-item:hover {
            border-color: var(--accent-color);
            box-shadow: 0 0 15px rgba(0, 242, 255, 0.1);
        }

        .assistant-item h3 {
            font-size: 18px;
            margin-bottom: 10px;
            color: var(--accent-color);
        }

        .assistant-info {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-bottom: 15px;
        }

        .info-item {
            font-size: 14px;
        }

        .info-item strong {
            color: var(--accent-color);
        }

        .config-section {
            background: var(--bg-color);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
        }

        .status {
            padding: 10px 15px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: bold;
            display: inline-block;
            margin-top: 10px;
        }

        .status-online {
            background: rgba(46, 213, 115, 0.2);
            color: var(--success);
        }

        .status-offline {
            background: rgba(255, 71, 87, 0.2);
            color: var(--danger);
        }

        .toast {
            position: fixed;
            top: 20px;
            right: 20px;
            background: var(--panel-color);
            border: 1px solid var(--accent-color);
            color: var(--text-color);
            padding: 15px 20px;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.3);
            z-index: 1000;
            animation: slideIn 0.3s ease;
            display: none;
        }

        @keyframes slideIn {
            from {
                transform: translateX(100%);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }

        @media (max-width: 768px) {
            .container {
                margin: 0;
                border-radius: 0;
            }

            .assistant-info {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="toast" id="toast"></div>

    <div class="container">
        <div class="header">
            <h1><i class="fa-solid fa-robot"></i> 灵犀助手Bot</h1>
            <p>本地服务器 - 连接云端灵犀云聊与本地助手</p>
        </div>

        <div class="content">
            <!-- 配置部分 -->
            <div class="section">
                <h2><i class="fa-solid fa-cog"></i> 服务器配置</h2>
                <div class="config-section">
                    <div class="form-group">
                        <label>本地服务器端口</label>
                        <input type="number" id="portInput" value="{{ config.port }}" min="1024" max="65535">
                    </div>
                    <div class="form-group">
                        <label>云端灵犀云聊地址</label>
                        <input type="text" id="chatPcUrlInput" value="{{ config.chat_pc_url }}">
                    </div>
                    <div class="form-group">
                        <label>LingXi助手端口</label>
                        <input type="number" id="lingxiPortInput" value="{{ config.lingxi_port }}" min="1024" max="65535">
                    </div>
                    <button class="btn btn-primary" onclick="saveConfig()">保存配置</button>
                </div>
            </div>

            <!-- 连接云端助手 -->
            <div class="section">
                <h2><i class="fa-solid fa-cloud"></i> 连接云端助手</h2>
                <div class="config-section">
                    <div class="form-group">
                        <label>助手ID</label>
                        <input type="text" id="cloudAssistantIdInput" placeholder="输入云端生成的助手ID">
                    </div>
                    <div class="form-group">
                        <label>助手密码</label>
                        <input type="password" id="cloudAssistantPasswordInput" placeholder="输入云端生成的助手密码">
                    </div>
                    <button class="btn btn-primary" onclick="connectCloudAssistant()">连接助手</button>
                </div>
            </div>

            <!-- 助手列表 -->
            <div class="section">
                <h2><i class="fa-solid fa-list"></i> 助手列表</h2>
                <div class="assistant-list" id="assistantList">
                    {% if assistants %}
                        {% for aid, assistant in assistants.items() %}
                            <div class="assistant-item">
                                <h3>{{ assistant.name }} <span class="status {{ 'status-online' if assistant.status == 'online' else 'status-offline' }}">{{ assistant.status }}</span></h3>
                                <div class="assistant-info">
                                    <div class="info-item"><strong>助手ID:</strong> {{ aid }}</div>
                                    <div class="info-item"><strong>密码:</strong> {{ assistant.password }}</div>
                                    <div class="info-item"><strong>创建时间:</strong> {{ assistant.created_at }}</div>
                                    <div class="info-item"><strong>状态:</strong> {{ assistant.status }}</div>
                                </div>
                                <button class="btn btn-success" onclick="testConnection('{{ aid }}')">测试连接</button>
                                <button class="btn btn-danger" onclick="deleteAssistant('{{ aid }}')">删除助手</button>
                            </div>
                        {% endfor %}
                    {% else %}
                        <div style="text-align: center; padding: 40px; opacity: 0.5;">
                            <i class="fa-solid fa-robot" style="font-size: 48px; margin-bottom: 20px;"></i>
                            <p>暂无助手，请添加助手</p>
                        </div>
                    {% endif %}
                </div>
            </div>
        </div>
    </div>

    <script>
        // 显示提示消息
        function showToast(message) {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.style.display = 'block';
            setTimeout(() => {
                toast.style.display = 'none';
            }, 3000);
        }

        // 保存配置
        async function saveConfig() {
            const port = document.getElementById('portInput').value;
            const chatPcUrl = document.getElementById('chatPcUrlInput').value;
            const lingxiPort = document.getElementById('lingxiPortInput').value;

            try {
                const response = await fetch('/api/save_config', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        port: parseInt(port),
                        chat_pc_url: chatPcUrl,
                        lingxi_port: parseInt(lingxiPort)
                    })
                });
                const data = await response.json();
                if (data.success) {
                    showToast('配置保存成功');
                } else {
                    showToast('配置保存失败: ' + data.message);
                }
            } catch (error) {
                showToast('保存失败: ' + error.message);
            }
        }

        // 添加助手
        async function addAssistant() {
            const name = document.getElementById('assistantNameInput').value.trim();
            if (!name) {
                showToast('请输入助手名称');
                return;
            }

            try {
                const response = await fetch('/api/add_assistant', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({name: name})
                });
                const data = await response.json();
                if (data.success) {
                    showToast('助手添加成功');
                    setTimeout(() => location.reload(), 1000);
                } else {
                    showToast('添加失败: ' + data.message);
                }
            } catch (error) {
                showToast('添加失败: ' + error.message);
            }
        }

        // 测试连接
        async function testConnection(assistantId) {
            try {
                const response = await fetch('/api/test_connection', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({assistant_id: assistantId})
                });
                const data = await response.json();
                showToast(data.message);
            } catch (error) {
                showToast('测试失败: ' + error.message);
            }
        }

        // 删除助手
        async function deleteAssistant(assistantId) {
            if (!confirm('确定要删除这个助手吗？')) return;

            try {
                const response = await fetch('/api/delete_assistant', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({assistant_id: assistantId})
                });
                const data = await response.json();
                if (data.success) {
                    showToast('助手删除成功');
                    setTimeout(() => location.reload(), 1000);
                } else {
                    showToast('删除失败: ' + data.message);
                }
            } catch (error) {
                showToast('删除失败: ' + error.message);
            }
        }

        // 连接云端助手
        async function connectCloudAssistant() {
            const assistantId = document.getElementById('cloudAssistantIdInput').value.trim();
            const password = document.getElementById('cloudAssistantPasswordInput').value.trim();

            if (!assistantId) {
                showToast('请输入助手ID');
                return;
            }
            if (!password) {
                showToast('请输入助手密码');
                return;
            }

            try {
                const response = await fetch('/api/connect_cloud_assistant', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({assistant_id: assistantId, password: password})
                });
                const data = await response.json();
                if (data.success) {
                    showToast('连接成功');
                    setTimeout(() => location.reload(), 1000);
                } else {
                    showToast('连接失败: ' + data.message);
                }
            } catch (error) {
                showToast('连接失败: ' + error.message);
            }
        }
    </script>
</body>
</html>
'''

# 主页
@app.route('/')
def home():
    assistants = load_json(ASSISTANT_DB)
    config = load_json(CONFIG_DB)
    return render_template_string(HTML_TEMPLATE, assistants=assistants, config=config)

# 保存配置
@app.route('/api/save_config', methods=['POST'])
def save_config():
    data = request.json
    config = load_json(CONFIG_DB)
    
    config['port'] = data.get('port', 5004)
    config['chat_pc_url'] = data.get('chat_pc_url', 'http://116.62.84.244:5002')
    config['lingxi_port'] = data.get('lingxi_port', 5003)
    
    save_json(CONFIG_DB, config)
    return jsonify({'success': True, 'message': '配置保存成功'})

# 添加助手
@app.route('/api/add_assistant', methods=['POST'])
def add_assistant():
    data = request.json
    name = data.get('name')
    
    if not name:
        return jsonify({'success': False, 'message': '请输入助手名称'})
    
    assistants = load_json(ASSISTANT_DB)
    assistant_id = generate_assistant_id()
    password = generate_password()
    
    assistants[assistant_id] = {
        'id': assistant_id,
        'name': name,
        'password': password,
        'status': 'offline',
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'last_active': None
    }
    
    save_json(ASSISTANT_DB, assistants)
    return jsonify({'success': True, 'message': '助手添加成功', 'assistant_id': assistant_id, 'password': password})

# 删除助手
@app.route('/api/delete_assistant', methods=['POST'])
def delete_assistant():
    data = request.json
    assistant_id = data.get('assistant_id')
    
    if not assistant_id:
        return jsonify({'success': False, 'message': '参数错误'})
    
    assistants = load_json(ASSISTANT_DB)
    if assistant_id in assistants:
        del assistants[assistant_id]
        save_json(ASSISTANT_DB, assistants)
        return jsonify({'success': True, 'message': '助手删除成功'})
    else:
        return jsonify({'success': False, 'message': '助手不存在'})

# 测试连接
@app.route('/api/test_connection', methods=['POST'])
def test_connection():
    data = request.json
    assistant_id = data.get('assistant_id')
    
    if not assistant_id:
        return jsonify({'success': False, 'message': '参数错误'})
    
    assistants = load_json(ASSISTANT_DB)
    if assistant_id not in assistants:
        return jsonify({'success': False, 'message': '助手不存在'})
    
    # 测试与LingXi的连接
    config = load_json(CONFIG_DB)
    lingxi_url = f'http://127.0.0.1:{config.get("lingxi_port", 5003)}'
    
    try:
        response = requests.get(f'{lingxi_url}/api/receive_from_chat', timeout=2)
        if response.status_code == 200:
            assistants[assistant_id]['status'] = 'online'
            assistants[assistant_id]['last_active'] = time.strftime('%Y-%m-%d %H:%M:%S')
            save_json(ASSISTANT_DB, assistants)
            return jsonify({'success': True, 'message': '连接成功，助手在线'})
        else:
            return jsonify({'success': False, 'message': 'LingXi助手未运行'})
    except:
        return jsonify({'success': False, 'message': '无法连接到LingXi助手'})

# 助手登录验证
@app.route('/api/assistant_login', methods=['POST'])
def assistant_login():
    data = request.json
    assistant_id = data.get('assistant_id')
    password = data.get('password')
    
    if not assistant_id or not password:
        return jsonify({'success': False, 'message': '参数不完整'})
    
    assistants = load_json(ASSISTANT_DB)
    if assistant_id in assistants:
        if assistants[assistant_id]['password'] == password:
            # 更新状态为在线
            assistants[assistant_id]['status'] = 'online'
            assistants[assistant_id]['last_active'] = time.strftime('%Y-%m-%d %H:%M:%S')
            save_json(ASSISTANT_DB, assistants)
            return jsonify({'success': True, 'message': '登录成功'})
        else:
            return jsonify({'success': False, 'message': '密码错误'})
    else:
        return jsonify({'success': False, 'message': '助手不存在'})

# 接收来自chat_pc的消息
@app.route('/api/receive_from_chat', methods=['POST'])
def receive_from_chat():
    data = request.json
    from_user_id = data.get('from_user_id')
    message = data.get('message')
    assistant_id = data.get('assistant_id')
    
    if not from_user_id or not message or not assistant_id:
        return jsonify({'success': False, 'message': '参数不完整'})
    
    # 验证助手是否存在
    assistants = load_json(ASSISTANT_DB)
    if assistant_id not in assistants:
        return jsonify({'success': False, 'message': '助手不存在'})
    
    # 转发消息到LingXi
    config = load_json(CONFIG_DB)
    lingxi_url = f'http://127.0.0.1:{config.get("lingxi_port", 5003)}'
    
    try:
        response = requests.post(f'{lingxi_url}/api/receive_from_chat', json={
            'from_user_id': from_user_id,
            'message': message
        }, timeout=5)
        
        if response.status_code == 200:
            return jsonify({'success': True, 'message': '消息转发成功'})
        else:
            return jsonify({'success': False, 'message': 'LingXi助手未响应'})
    except Exception as e:
        print(f"转发消息失败: {e}")
        return jsonify({'success': False, 'message': '无法连接到LingXi助手'})

# 接收来自LingXi的消息
@app.route('/api/receive_from_lingxi', methods=['POST'])
def receive_from_lingxi():
    data = request.json
    assistant_id = data.get('assistant_id')
    target_user_id = data.get('target_user_id')
    message = data.get('message')
    
    if not assistant_id or not target_user_id or not message:
        return jsonify({'success': False, 'message': '参数不完整'})
    
    # 验证助手是否存在
    assistants = load_json(ASSISTANT_DB)
    if assistant_id not in assistants:
        return jsonify({'success': False, 'message': '助手不存在'})
    
    # 转发消息到两个端口
    config = load_json(CONFIG_DB)
    chat_pc_urls = [
        config.get('chat_pc_url', 'http://116.62.84.244:5002'),
        'http://116.62.84.244:5001'  # 额外添加5001端口
    ]
    
    success = False
    for chat_pc_url in chat_pc_urls:
        try:
            response = requests.post(f'{chat_pc_url}/api/receive_from_assistant', json={
                'assistant_id': assistant_id,
                'target_user_id': target_user_id,
                'message': message
            }, timeout=2)
            
            if response.status_code == 200:
                success = True
                print(f"消息已转发到 {chat_pc_url}")
        except Exception as e:
            print(f"转发消息到 {chat_pc_url} 失败: {e}")
    
    if success:
        return jsonify({'success': True, 'message': '消息转发成功'})
    else:
        return jsonify({'success': False, 'message': '无法连接到任何chat_pc'})

# 接收来自LingXi的屏幕流
@app.route('/api/screen_stream', methods=['POST'])
def screen_stream():
    data = request.json
    assistant_id = data.get('assistant_id')
    target_user_id = data.get('target_user_id')
    frame = data.get('frame')
    timestamp = data.get('timestamp')
    
    if not assistant_id or not target_user_id or not frame:
        return jsonify({'success': False, 'message': '参数不完整'})
    
    # 验证助手是否存在
    assistants = load_json(ASSISTANT_DB)
    if assistant_id not in assistants:
        return jsonify({'success': False, 'message': '助手不存在'})
    
    # 转发屏幕流到两个端口
    config = load_json(CONFIG_DB)
    chat_pc_urls = [
        config.get('chat_pc_url', 'http://116.62.84.244:5002'),
        'http://116.62.84.244:5001'  # 额外添加5001端口
    ]
    
    success = False
    for chat_pc_url in chat_pc_urls:
        try:
            response = requests.post(f'{chat_pc_url}/api/screen_stream', json={
                'assistant_id': assistant_id,
                'target_user_id': target_user_id,
                'frame': frame,
                'timestamp': timestamp
            }, timeout=0.3)
            
            if response.status_code == 200:
                success = True
                # 屏幕流不需要打印每条日志，减少输出
        except Exception as e:
            # 屏幕流连接失败不打印错误，避免日志过多
            pass
    
    if success:
        return jsonify({'success': True, 'message': '屏幕流转发成功'})
    else:
        return jsonify({'success': False, 'message': '无法连接到任何chat_pc'})

# 接收执行结果
@app.route('/api/receive_execution_result', methods=['POST'])
def receive_execution_result():
    data = request.json
    result = data.get('result')
    success = data.get('success')
    file = data.get('file')
    timestamp = data.get('timestamp')
    
    if not result:
        return jsonify({'success': False, 'message': '参数不完整'})
    
    # 获取助手信息
    assistants = load_json(ASSISTANT_DB)
    if not assistants:
        return jsonify({'success': False, 'message': '没有连接的助手'})
    
    # 使用第一个助手ID
    assistant_id = list(assistants.keys())[0]
    
    # 转发执行结果到两个端口
    config = load_json(CONFIG_DB)
    chat_pc_urls = [
        config.get('chat_pc_url', 'http://116.62.84.244:5002'),
        'http://116.62.84.244:5001'  # 额外添加5001端口
    ]
    
    success = False
    for chat_pc_url in chat_pc_urls:
        try:
            response = requests.post(f'{chat_pc_url}/api/receive_from_assistant', json={
                'assistant_id': assistant_id,
                'target_user_id': 'self',  # 发送给自己
                'message': result
            }, timeout=2)
            
            if response.status_code == 200:
                success = True
                print(f"执行结果已转发到 {chat_pc_url}")
        except Exception as e:
            print(f"转发执行结果到 {chat_pc_url} 失败: {e}")
    
    if success:
        return jsonify({'success': True, 'message': '执行结果转发成功'})
    else:
        return jsonify({'success': False, 'message': '无法连接到任何chat_pc'})


# 接收来自LingXi的文件
@app.route('/api/receive_file_from_lingxi', methods=['POST'])
def receive_file_from_lingxi():
    data = request.json
    assistant_id = data.get('assistant_id')
    target_user_id = data.get('target_user_id')
    file_name = data.get('file_name')
    file_data = data.get('file_data')
    file_size = data.get('file_size')
    timestamp = data.get('timestamp')
    
    if not assistant_id or not target_user_id or not file_name or not file_data:
        return jsonify({'success': False, 'message': '参数不完整'})
    
    # 转发文件到两个端口
    config = load_json(CONFIG_DB)
    chat_pc_urls = [
        config.get('chat_pc_url', 'http://116.62.84.244:5002'),
        'http://116.62.84.244:5001'  # 额外添加5001端口
    ]
    
    success = False
    for chat_pc_url in chat_pc_urls:
        try:
            response = requests.post(f'{chat_pc_url}/api/receive_file_from_assistant', json={
                'assistant_id': assistant_id,
                'target_user_id': target_user_id,
                'file_name': file_name,
                'file_data': file_data,
                'file_size': file_size,
                'timestamp': timestamp
            }, timeout=30)
            
            if response.status_code == 200:
                success = True
                print(f"文件已转发到 {chat_pc_url}: {file_name}")
        except Exception as e:
            print(f"转发文件到 {chat_pc_url} 失败: {e}")
    
    if success:
        return jsonify({'success': True, 'message': '文件已转发'})
    else:
        return jsonify({'success': False, 'message': '无法连接到任何chat_pc'})


# 接收来自execute_app的文件
@app.route('/api/receive_file_from_execute', methods=['POST'])
def receive_file_from_execute():
    data = request.json
    target_user_id = data.get('target_user_id')
    file_name = data.get('file_name')
    file_data = data.get('file_data')
    file_size = data.get('file_size')
    
    if not target_user_id or not file_name or not file_data:
        return jsonify({'success': False, 'message': '参数不完整'})
    
    # 获取助手信息
    assistants = load_json(ASSISTANT_DB)
    if not assistants:
        return jsonify({'success': False, 'message': '没有连接的助手'})
    
    # 使用第一个助手ID
    assistant_id = list(assistants.keys())[0]
    
    # 转发文件到两个端口
    config = load_json(CONFIG_DB)
    chat_pc_urls = [
        config.get('chat_pc_url', 'http://116.62.84.244:5002'),
        'http://116.62.84.244:5001'  # 额外添加5001端口
    ]
    
    success = False
    timestamp = datetime.datetime.now().strftime('%H:%M:%S')
    for chat_pc_url in chat_pc_urls:
        try:
            response = requests.post(f'{chat_pc_url}/api/receive_file_from_assistant', json={
                'assistant_id': assistant_id,
                'target_user_id': target_user_id,
                'file_name': file_name,
                'file_data': file_data,
                'file_size': file_size,
                'timestamp': timestamp
            }, timeout=30)
            
            if response.status_code == 200:
                success = True
                print(f"文件已转发到 {chat_pc_url}: {file_name}")
        except Exception as e:
            print(f"转发文件到 {chat_pc_url} 失败: {e}")
    
    if success:
        return jsonify({'success': True, 'message': '文件已转发'})
    else:
        return jsonify({'success': False, 'message': '无法连接到任何chat_pc'})

# 屏幕控制请求
@app.route('/api/screen_control', methods=['POST'])
def screen_control():
    data = request.json
    from_user_id = data.get('from_user_id')
    action = data.get('action')
    assistant_id = data.get('assistant_id')
    
    if not from_user_id or not action or not assistant_id:
        return jsonify({'success': False, 'message': '参数不完整'})
    
    # 验证助手是否存在
    assistants = load_json(ASSISTANT_DB)
    if assistant_id not in assistants:
        return jsonify({'success': False, 'message': '助手不存在'})
    
    # 转发屏幕控制请求到LingXi
    config = load_json(CONFIG_DB)
    lingxi_url = f'http://127.0.0.1:{config.get("lingxi_port", 5003)}'
    
    try:
        response = requests.post(f'{lingxi_url}/api/screen_control', json={
            'from_user_id': from_user_id,
            'action': action
        }, timeout=3)
        
        if response.status_code == 200:
            return jsonify({'success': True, 'message': '屏幕控制请求已发送'})
        else:
            return jsonify({'success': False, 'message': 'LingXi助手未响应'})
    except Exception as e:
        print(f"转发屏幕控制请求失败: {e}")
        return jsonify({'success': False, 'message': '无法连接到LingXi助手'})

# 连接云端助手
@app.route('/api/connect_cloud_assistant', methods=['POST'])
def connect_cloud_assistant():
    data = request.json
    assistant_id = data.get('assistant_id')
    password = data.get('password')
    
    if not assistant_id or not password:
        return jsonify({'success': False, 'message': '参数不完整'})
    
    # 验证连接到云端chat_pc
    config = load_json(CONFIG_DB)
    chat_pc_url = config.get('chat_pc_url', 'http://116.62.84.244:5002')
    
    try:
        # 验证助手ID和密码
        response = requests.post(f'{chat_pc_url}/api/verify_assistant', json={
            'assistant_id': assistant_id,
            'password': password
        }, timeout=5)
        
        if response.status_code != 200 or not response.json().get('success'):
            return jsonify({'success': False, 'message': '助手验证失败，请检查ID和密码'})
        
        # 保存助手信息
        assistants = load_json(ASSISTANT_DB)
        
        if assistant_id in assistants:
            return jsonify({'success': False, 'message': '助手ID已存在'})
        
        assistants[assistant_id] = {
            'id': assistant_id,
            'name': f'云端助手_{assistant_id[:6]}',
            'password': password,
            'status': 'online',
            'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'last_active': time.strftime('%Y-%m-%d %H:%M:%S'),
            'cloud_url': chat_pc_url
        }
        
        save_json(ASSISTANT_DB, assistants)
        
        # 启动消息监听线程
        import threading
        threading.Thread(target=listen_for_cloud_messages, args=(assistant_id,), daemon=True).start()
        
        return jsonify({'success': True, 'message': '连接成功'})
    except Exception as e:
        print(f"连接云端助手失败: {e}")
        return jsonify({'success': False, 'message': '无法连接到云端'})

# 监听云端消息
def listen_for_cloud_messages(assistant_id):
    """定期检查云端的消息"""
    print(f"开始监听云端消息: {assistant_id}")
    
    while True:
        try:
            # 获取助手信息
            assistants = load_json(ASSISTANT_DB)
            if assistant_id not in assistants:
                print(f"助手 {assistant_id} 不存在，停止监听")
                break
            
            assistant = assistants[assistant_id]
            password = assistant.get('password')
            cloud_url = assistant.get('cloud_url', 'http://116.62.84.244:5002')
            # 从助手信息中获取上次处理的消息ID
            last_message_id = assistant.get('last_message_id', 0)
            
            # 从云端获取消息
            response = requests.post(f'{cloud_url}/api/get_assistant_messages', json={
                'assistant_id': assistant_id,
                'password': password,
                'last_message_id': last_message_id
            }, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    messages = data.get('messages', [])
                    for msg in messages:
                        msg_id = msg.get('id')
                        content = msg.get('content', '')
                        msg_type = msg.get('type', 'message')
                        
                        # 转发消息到LingXi
                        config = load_json(CONFIG_DB)
                        lingxi_url = f'http://127.0.0.1:{config.get("lingxi_port", 5003)}'
                        
                        try:
                            if msg_type == 'screen_control':
                                # 处理屏幕控制请求
                                lingxi_response = requests.post(f'{lingxi_url}/api/screen_control', json={
                                    'from_user_id': msg.get('sender_id'),
                                    'assistant_id': assistant_id,
                                    'action': content
                                }, timeout=5)
                                
                                if lingxi_response.status_code == 200:
                                    print(f"屏幕控制请求已转发给LingXi: {content}")
                                else:
                                    print(f"转发屏幕控制请求给LingXi失败: {lingxi_response.status_code}")
                            else:
                                # 处理普通消息
                                lingxi_response = requests.post(f'{lingxi_url}/api/receive_from_chat', json={
                                    'from_user_id': msg.get('sender_id'),
                                    'message': content
                                }, timeout=5)
                                
                                if lingxi_response.status_code == 200:
                                    print(f"消息已转发给LingXi: {content}")
                                else:
                                    print(f"转发消息给LingXi失败: {lingxi_response.status_code}")
                            
                            # 更新最后消息ID
                            if msg_id > last_message_id:
                                last_message_id = msg_id
                                # 保存到助手数据库
                                assistant['last_message_id'] = last_message_id
                                save_json(ASSISTANT_DB, assistants)
                        except Exception as e:
                            print(f"转发给LingXi失败: {e}")
            
            time.sleep(2)  # 每2秒检查一次
        except Exception as e:
            print(f"监听云端消息失败: {e}")
            time.sleep(10)

# 获取本地IP地址
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return '127.0.0.1'

def start_message_listeners():
    """启动所有已连接助手的消息监听线程"""
    assistants = load_json(ASSISTANT_DB)
    for assistant_id in assistants:
        import threading
        threading.Thread(target=listen_for_cloud_messages, args=(assistant_id,), daemon=True).start()
        print(f"已启动助手 {assistant_id} 的消息监听")

# 主函数
if __name__ == '__main__':
    # 初始化数据库
    init_db()
    # 启动已保存助手的消息监听
    start_message_listeners()
    config = load_json(CONFIG_DB)
    port = config.get('port', 5004)
    print(f"灵犀助手Bot服务器启动")
    print(f"本地访问: http://127.0.0.1:{port}")
    print(f"局域网访问: http://{get_local_ip()}:{port}")
    print(f"配置文件: {CONFIG_DB}")
    print(f"助手数据库: {ASSISTANT_DB}")
    print("=" * 50)
    app.run(host='0.0.0.0', port=port, debug=False)
