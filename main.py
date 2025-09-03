import json
import logging
import asyncio
from flask import Flask, request, Response, stream_with_context, jsonify
import httpx
import time
from dotenv import load_dotenv
import os
import ast

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 设置httpx的日志级别为WARNING，减少不必要的输出
logging.getLogger("httpx").setLevel(logging.WARNING)

# 加载环境变量
load_dotenv()

# 从环境变量读取有效的API密钥（逗号分隔）
VALID_API_KEYS = [key.strip() for key in os.getenv("VALID_API_KEYS", "").split(",") if key]

# 获取会话记忆功能模式配置
# 1: 构造history_message附加到消息中的模式(默认)
# 2: 零宽字符模式
# 3: 无历史上下文模式 - 每次对话都是独立的，不包含任何历史信息
CONVERSATION_MEMORY_MODE = int(os.getenv('CONVERSATION_MEMORY_MODE', '1'))

# HTTP客户端超时配置（秒）
HTTP_TIMEOUT = int(os.getenv('HTTP_TIMEOUT', '30'))  # 默认30秒超时
HTTP_CONNECT_TIMEOUT = int(os.getenv('HTTP_CONNECT_TIMEOUT', '10'))  # 默认10秒连接超时

class DifyModelManager:
    def __init__(self):
        self.api_keys = []
        self.name_to_api_key = {}  # 应用名称到API Key的映射
        self.api_key_to_name = {}  # API Key到应用名称的映射
        self.load_api_keys()

    def load_api_keys(self):
        """从环境变量加载API Keys"""
        api_keys_str = os.getenv('DIFY_API_KEYS', '')
        if api_keys_str:
            self.api_keys = [key.strip() for key in api_keys_str.split(',') if key.strip()]
            logger.info(f"Loaded {len(self.api_keys)} API keys")

    async def fetch_app_info(self, api_key):
        """获取Dify应用信息"""
        try:
            async with httpx.AsyncClient(timeout=(HTTP_TIMEOUT, HTTP_CONNECT_TIMEOUT)) as client:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                response = await client.get(
                    f"{DIFY_API_BASE}/info",
                    headers=headers,
                    params={"user": "default_user"}
                )
                
                if response.status_code == 200:
                    app_info = response.json()
                    return app_info.get("name", "Unknown App")
                else:
                    logger.error(f"Failed to fetch app info for API key: {api_key[:8]}...")
                    return None
        except Exception as e:
            logger.error(f"Error fetching app info: {str(e)}")
            return None

    async def refresh_model_info(self):
        """刷新所有应用信息"""
        self.name_to_api_key.clear()
        self.api_key_to_name.clear()
        
        for api_key in self.api_keys:
            app_name = await self.fetch_app_info(api_key)
            if app_name:
                self.name_to_api_key[app_name] = api_key
                self.api_key_to_name[api_key] = app_name
                logger.info(f"Mapped app '{app_name}' to API key: {api_key[:8]}...")

    def get_api_key(self, model_name):
        """根据模型名称获取API Key"""
        return self.name_to_api_key.get(model_name)

    def get_available_models(self):
        """获取可用模型列表"""
        return [
            {
                "id": name,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "dify"
            }
            for name in self.name_to_api_key.keys()
        ]

# 创建模型管理器实例
model_manager = DifyModelManager()

# 从环境变量获取API基础URL
DIFY_API_BASE = os.getenv("DIFY_API_BASE", "")

app = Flask(__name__)

def get_api_key(model_name):
    """根据模型名称获取对应的API密钥"""
    api_key = model_manager.get_api_key(model_name)
    if not api_key:
        logger.warning(f"No API key found for model: {model_name}")
    return api_key

async def upload_image_to_dify(api_key, base64_data, user_id="default_user"):
    """上传图片到Dify并返回文件ID
    支持处理base64编码的图片数据，自动检测并提取有效的base64数据
    """
    try:
        # 解码base64数据
        if base64_data.startswith('data:image'):
            # 提取实际的base64数据 (去除data:image/*;base64,前缀)
            base64_data = base64_data.split(',')[1]
        
        import base64
        image_data = base64.b64decode(base64_data)
        
        # 创建临时文件
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
            tmp_file.write(image_data)
            tmp_file_path = tmp_file.name
        
        try:
            # 使用httpx上传文件到Dify
            async with httpx.AsyncClient(timeout=(HTTP_TIMEOUT, HTTP_CONNECT_TIMEOUT)) as client:
                headers = {
                    "Authorization": f"Bearer {api_key}"
                }
                
                # 准备multipart数据用于文件上传
                # Dify当前仅支持图片类型附件的上传 (PNG, JPG, JPEG, WEBP, GIF)
                with open(tmp_file_path, 'rb') as file_handle:
                    files = {
                        'file': ('image.png', file_handle, 'image/png')
                    }
                    data = {
                        'user': user_id
                    }
                    
                    response = await client.post(
                        f"{DIFY_API_BASE}/files/upload",
                        headers=headers,
                        files=files,
                        data=data
                    )
                
                # 检查上传响应状态码
                # HTTP 200: OK, HTTP 201: Created
                if response.status_code in [200, 201]:
                    file_info = response.json()
                    logger.info(f"Successfully uploaded image, file_id: {file_info.get('id')}")
                    return file_info.get('id')
                else:
                    logger.error(f"Failed to upload image, status_code: {response.status_code}, response: {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error uploading image: {str(e)}")
            return None
            
        finally:
            # 确保临时文件被清理，避免磁盘空间泄露
            if tmp_file_path and os.path.exists(tmp_file_path):
                try:
                    # 等待一小段时间确保文件句柄完全释放
                    import asyncio
                    await asyncio.sleep(0.1)
                    os.unlink(tmp_file_path)
                    logger.debug(f"Temporary file cleaned up: {tmp_file_path}")
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup temporary file {tmp_file_path}: {cleanup_error}")
                    # 如果立即删除失败，尝试延迟删除
                    try:
                        await asyncio.sleep(1)
                        if os.path.exists(tmp_file_path):
                            os.unlink(tmp_file_path)
                            logger.debug(f"Temporary file cleaned up after delay: {tmp_file_path}")
                    except Exception as delayed_cleanup_error:
                        logger.error(f"Failed to cleanup temporary file after delay {tmp_file_path}: {delayed_cleanup_error}")
            
    except Exception as e:
        logger.error(f"Error processing image data: {str(e)}")
        return None

async def transform_openai_to_dify(openai_request, endpoint, api_key=None):
    """将OpenAI格式的请求转换为Dify格式"""
    
    if endpoint == "/chat/completions":
        messages = openai_request.get("messages", [])
        stream = openai_request.get("stream", False)
        user_id = openai_request.get("user", "default_user")
        
        # 尝试从历史消息中提取conversation_id
        conversation_id = None
        
        # 提取system消息内容
        system_content = ""
        system_messages = [msg for msg in messages if msg.get("role") == "system"]
        if system_messages:
            system_content = system_messages[0].get("content", "")
            # 记录找到的system消息
            logger.info(f"Found system message: {system_content[:100]}{'...' if len(system_content) > 100 else ''}")
        
        # 处理用户消息，支持图片
        user_message = messages[-1] if messages and messages[-1].get("role") != "system" else {}
        user_content = user_message.get("content", "")
        
        # 存储上传的文件ID
        uploaded_files = []
        
        # 检查用户消息是否包含图片
        if isinstance(user_content, list):
            # 处理多模态内容（文本+图片）
            text_parts = []
            image_parts = []
            
            for item in user_content:
                if item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
                elif item.get("type") == "image_url":
                    image_url = item.get("image_url", {}).get("url", "")
                    if image_url:
                        image_parts.append(image_url)
            
            # 组合文本内容
            user_query = "\n".join(text_parts) if text_parts else ""
            
            # 上传图片文件
            if api_key and image_parts:
                logger.info(f"Found {len(image_parts)} images to upload")
                successful_uploads = 0
                failed_uploads = 0
                
                for i, image_data in enumerate(image_parts):
                    try:
                        logger.info(f"Uploading image {i+1}/{len(image_parts)}")
                        file_id = await upload_image_to_dify(api_key, image_data, user_id)
                        if file_id:
                            uploaded_files.append({
                                "type": "image",
                                "transfer_method": "local_file",
                                "upload_file_id": file_id
                            })
                            successful_uploads += 1
                            logger.info(f"Successfully uploaded image {i+1}/{len(image_parts)}, file_id: {file_id}")
                        else:
                            failed_uploads += 1
                            logger.warning(f"Failed to upload image {i+1}/{len(image_parts)}")
                    except Exception as e:
                        failed_uploads += 1
                        logger.error(f"Exception occurred while uploading image {i+1}/{len(image_parts)}: {str(e)}")
                
                # 记录上传结果统计
                if successful_uploads > 0:
                    logger.info(f"Uploaded {successful_uploads}/{len(image_parts)} files successfully")
                if failed_uploads > 0:
                    logger.warning(f"Failed to upload {failed_uploads}/{len(image_parts)} files")
                
                # 如果所有图片都上传失败，记录警告
                if successful_uploads == 0 and failed_uploads > 0:
                    logger.warning("All image uploads failed, proceeding with text-only request")
        else:
            # 处理纯文本内容
            user_query = user_content
        
        logger.info(f"Processing request with {len(uploaded_files)} uploaded files")
        
        if CONVERSATION_MEMORY_MODE == 2:  # 零宽字符模式
            if len(messages) > 1:
                # 遍历历史消息，找到最近的assistant消息
                for msg in reversed(messages[:-1]):  # 除了最后一条消息
                    if msg.get("role") == "assistant":
                        content = msg.get("content", "")
                        # 尝试解码conversation_id
                        conversation_id = decode_conversation_id(content)
                        if conversation_id:
                            break
            
            # 如果有system消息且是首次对话(没有conversation_id)，则将system内容添加到用户查询前
            if system_content and not conversation_id:
                user_query = f"系统指令: {system_content}\n\n用户问题: {user_query}"
                logger.info(f"[零宽字符模式] 首次对话，添加system内容到查询前")
            
            dify_request = {
                "inputs": {},
                "query": user_query,
                "response_mode": "streaming" if stream else "blocking",
                "conversation_id": conversation_id,
                "user": user_id
            }
            
            # 如果有上传的文件，添加到请求中
            if uploaded_files:
                dify_request["files"] = uploaded_files
                
        elif CONVERSATION_MEMORY_MODE == 3:  # 无历史上下文模式
            # 完全忽略历史消息，只处理当前用户问题和system指令
            # 这种模式适用于：
            # 1. 需要避免模型幻觉的场景
            # 2. 每次对话都应该是独立的问答
            # 3. 客服场景，避免历史对话干扰当前问题
            # 4. 对响应速度要求高，成本敏感的场景
            if system_content:
                user_query = f"系统指令: {system_content}\n\n用户问题: {user_query}"
                logger.info(f"[无历史上下文模式] 添加system内容到查询前")
            
            dify_request = {
                "inputs": {},
                "query": user_query,
                "response_mode": "streaming" if stream else "blocking",
                "user": user_id
            }
            
            # 如果有上传的文件，添加到请求中
            if uploaded_files:
                dify_request["files"] = uploaded_files
                
        else:  # history_message模式(默认)
            # 构造历史消息
            if len(messages) > 1:
                history_messages = []
                has_system_in_history = False
                
                # 检查历史消息中是否已经包含system消息
                for msg in messages[:-1]:  # 除了最后一条消息
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if role and content:
                        if role == "system":
                            has_system_in_history = True
                        history_messages.append(f"{role}: {content}")
                
                # 如果历史中没有system消息但现在有system消息，则添加到历史的最前面
                if system_content and not has_system_in_history:
                    history_messages.insert(0, f"system: {system_content}")
                    logger.info(f"[history_message模式] 添加system内容到历史消息前")
                
                # 将历史消息添加到查询中
                if history_messages:
                    history_context = "\n\n".join(history_messages)
                    user_query = f"<history>\n{history_context}\n</history>\n\n用户当前问题: {user_query}"
            elif system_content:  # 没有历史消息但有system消息
                user_query = f"系统指令: {system_content}\n\n用户问题: {user_query}"
                logger.info(f"[history_message模式] 首次对话，添加system内容到查询前")
            
            dify_request = {
                "inputs": {},
                "query": user_query,
                "response_mode": "streaming" if stream else "blocking",
                "user": user_id
            }
            
            # 如果有上传的文件，添加到请求中
            if uploaded_files:
                dify_request["files"] = uploaded_files

        return dify_request
    
    return None

def transform_dify_to_openai(dify_response, model="claude-3-5-sonnet-v2", stream=False):
    """将Dify格式的响应转换为OpenAI格式"""
    
    if not stream:
        # 首先获取回答内容，支持不同的响应模式
        answer = ""
        mode = dify_response.get("mode", "")
        
        # 普通聊天模式
        if "answer" in dify_response:
            answer = dify_response.get("answer", "")
        
        # 如果是Agent模式，需要从agent_thoughts中提取回答
        elif "agent_thoughts" in dify_response:
            # Agent模式下通常最后一个thought包含最终答案
            agent_thoughts = dify_response.get("agent_thoughts", [])
            if agent_thoughts:
                for thought in agent_thoughts:
                    if thought.get("thought"):
                        answer = thought.get("thought", "")
        
        # 只在零宽字符会话记忆模式时处理conversation_id
        # 模式3（无历史上下文）不处理conversation_id，保持对话独立
        if CONVERSATION_MEMORY_MODE == 2:
            conversation_id = dify_response.get("conversation_id", "")
            history = dify_response.get("conversation_history", [])
            
            # 检查历史消息中是否已经有会话ID
            has_conversation_id = False
            if history:
                for msg in history:
                    if msg.get("role") == "assistant":
                        content = msg.get("content", "")
                        if decode_conversation_id(content) is not None:
                            has_conversation_id = True
                            break
            
            # 只在新会话且历史消息中没有会话ID时插入
            if conversation_id and not has_conversation_id:
                logger.info(f"[Debug] Inserting conversation_id: {conversation_id}, history_length: {len(history)}")
                encoded = encode_conversation_id(conversation_id)
                answer = answer + encoded
                logger.info(f"[Debug] Response content after insertion: {repr(answer)}")
        
        return {
            "id": dify_response.get("message_id", ""),
            "object": "chat.completion",
            "created": dify_response.get("created", int(time.time())),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": answer
                },
                "finish_reason": "stop"
            }]
        }
    else:
        # 流式响应的转换在stream_response函数中处理
        return dify_response

def create_openai_stream_response(content, message_id, model="claude-3-5-sonnet-v2"):
    """创建OpenAI格式的流式响应"""
    return {
        "id": message_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {
                "content": content
            },
            "finish_reason": None
        }]
    }

def encode_conversation_id(conversation_id):
    """将conversation_id编码为不可见的字符序列"""
    if not conversation_id:
        return ""
    
    # 使用Base64编码减少长度
    import base64
    encoded = base64.b64encode(conversation_id.encode()).decode()
    
    # 使用8种不同的零宽字符表示3位数字
    # 这样可以将编码长度进一步减少
    char_map = {
        '0': '\u200b',  # 零宽空格
        '1': '\u200c',  # 零宽非连接符
        '2': '\u200d',  # 零宽连接符
        '3': '\ufeff',  # 零宽非断空格
        '4': '\u2060',  # 词组连接符
        '5': '\u180e',  # 蒙古语元音分隔符
        '6': '\u2061',  # 函数应用
        '7': '\u2062',  # 不可见乘号
    }
    
    # 将Base64字符串转换为八进制数字
    result = []
    for c in encoded:
        # 将每个字符转换为8进制数字（0-7）
        if c.isalpha():
            if c.isupper():
                val = ord(c) - ord('A')
            else:
                val = ord(c) - ord('a') + 26
        elif c.isdigit():
            val = int(c) + 52
        elif c == '+':
            val = 62
        elif c == '/':
            val = 63
        else:  # '='
            val = 0
            
        # 每个Base64字符可以产生2个3位数字
        first = (val >> 3) & 0x7
        second = val & 0x7
        result.append(char_map[str(first)])
        if c != '=':  # 不编码填充字符的后半部分
            result.append(char_map[str(second)])
    
    return ''.join(result)

def decode_conversation_id(content):
    """从消息内容中解码conversation_id"""
    try:
        # 零宽字符到3位数字的映射
        char_to_val = {
            '\u200b': '0',  # 零宽空格
            '\u200c': '1',  # 零宽非连接符
            '\u200d': '2',  # 零宽连接符
            '\ufeff': '3',  # 零宽非断空格
            '\u2060': '4',  # 词组连接符
            '\u180e': '5',  # 蒙古语元音分隔符
            '\u2061': '6',  # 函数应用
            '\u2062': '7',  # 不可见乘号
        }
        
        # 提取最后一段零宽字符序列
        space_chars = []
        for c in reversed(content):
            if c not in char_to_val:
                break
            space_chars.append(c)
        
        if not space_chars:
            return None
            
        # 将零宽字符转换回Base64字符串
        space_chars.reverse()
        base64_chars = []
        for i in range(0, len(space_chars), 2):
            first = int(char_to_val[space_chars[i]], 8)
            if i + 1 < len(space_chars):
                second = int(char_to_val[space_chars[i + 1]], 8)
                val = (first << 3) | second
            else:
                val = first << 3
                
            # 转换回Base64字符
            if val < 26:
                base64_chars.append(chr(val + ord('A')))
            elif val < 52:
                base64_chars.append(chr(val - 26 + ord('a')))
            elif val < 62:
                base64_chars.append(str(val - 52))
            elif val == 62:
                base64_chars.append('+')
            else:
                base64_chars.append('/')
                
        # 添加Base64填充
        padding = len(base64_chars) % 4
        if padding:
            base64_chars.extend(['='] * (4 - padding))
            
        # 解码Base64字符串
        import base64
        base64_str = ''.join(base64_chars)
        return base64.b64decode(base64_str).decode()
        
    except Exception as e:
        logger.debug(f"Failed to decode conversation_id: {e}")
        return None

@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    try:
        # 新增：验证API密钥
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({
                "error": {
                    "message": "Missing Authorization header",
                    "type": "invalid_request_error",
                    "param": None,
                    "code": "invalid_api_key"
                }
            }), 401

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return jsonify({
                "error": {
                    "message": "Invalid Authorization header format. Expected: Bearer <API_KEY>",
                    "type": "invalid_request_error",
                    "param": None,
                    "code": "invalid_api_key"
                }
            }), 401

        provided_api_key = parts[1]
        if provided_api_key not in VALID_API_KEYS:
            return jsonify({
                "error": {
                    "message": "Invalid API key",
                    "type": "invalid_request_error",
                    "param": None,
                    "code": "invalid_api_key"
                }
            }), 401

        # 继续处理原始逻辑
        openai_request = request.get_json()
        
        logger.info(f"Received request: {json.dumps(openai_request, ensure_ascii=False)}")
        
        model = openai_request.get("model", "claude-3-5-sonnet")
        
        # 验证模型是否支持
        api_key = get_api_key(model)
        if not api_key:
            error_msg = f"Model {model} is not supported. Available models: {', '.join(model_manager.name_to_api_key.keys())}"
            logger.error(error_msg)
            return {
                "error": {
                    "message": error_msg,
                    "type": "invalid_request_error",
                    "code": "model_not_found"
                }
            }, 404
            
        # 转换请求并处理图片上传
        dify_request = asyncio.run(transform_openai_to_dify(openai_request, "/chat/completions", api_key))
        
        # Debug模式下打印转换后的请求
        if '--debug' in sys.argv:
            print("=" * 50)
            print("TRANSFORMED REQUEST DEBUG INFO")
            print("=" * 50)
            print(f"Transformed Body: {json.dumps(dify_request, ensure_ascii=False, indent=2)}")
            print("=" * 50)
        
        if not dify_request:
            logger.error("Failed to transform request")
            return {
                "error": {
                    "message": "Invalid request format",
                    "type": "invalid_request_error",
                }
            }, 400

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        stream = openai_request.get("stream", False)
        dify_endpoint = f"{DIFY_API_BASE}/chat-messages"
        logger.info(f"Sending request to Dify endpoint: {dify_endpoint}, stream={stream}")

        if stream:
            def generate():
                client = httpx.Client(timeout=None)
                
                def flush_chunk(chunk_data):
                    """Helper function to flush chunks immediately"""
                    return chunk_data.encode('utf-8')
                
                def calculate_delay(buffer_size):
                    """
                    根据缓冲区大小动态计算延迟
                    buffer_size: 缓冲区中剩余的字符数量
                    """
                    if buffer_size > 30:  # 缓冲区内容较多，快速输出
                        return 0.001  # 5ms延迟
                    elif buffer_size > 20:  # 中等数量，适中速度
                        return 0.002  # 10ms延迟
                    elif buffer_size > 10:  # 较少内容，稍慢速度
                        return 0.01  # 20ms延迟
                    else:  # 内容很少，使用较慢的速度
                        return 0.02  # 30ms延迟
                
                def send_char(char, message_id):
                    """Helper function to send single character"""
                    openai_chunk = {
                        "id": message_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {
                                "content": char
                            },
                            "finish_reason": None
                        }]
                    }
                    chunk_data = f"data: {json.dumps(openai_chunk)}\n\n"
                    return flush_chunk(chunk_data)
                
                # 初始化缓冲区
                output_buffer = []
                
                try:
                    with client.stream(
                        'POST',
                        dify_endpoint,
                        json=dify_request,
                        headers={
                            **headers,
                            'Accept': 'text/event-stream',
                            'Cache-Control': 'no-cache',
                            'Connection': 'keep-alive'
                        }
                    ) as response:
                        generate.message_id = None
                        buffer = ""
                        
                        for raw_bytes in response.iter_raw():
                            if not raw_bytes:
                                continue
                                
                            try:
                                buffer += raw_bytes.decode('utf-8')
                                
                                while '\n' in buffer:
                                    line, buffer = buffer.split('\n', 1)
                                    line = line.strip()
                                    
                                    if not line or not line.startswith('data: '):
                                        continue
                                        
                                    try:
                                        json_str = line[6:]
                                        dify_chunk = json.loads(json_str)
                                        
                                        if dify_chunk.get("event") == "message" and "answer" in dify_chunk:
                                            current_answer = dify_chunk["answer"]
                                            if not current_answer:
                                                continue
                                                
                                            message_id = dify_chunk.get("message_id", "")
                                            if not generate.message_id:
                                                generate.message_id = message_id
                                            
                                            # 将当前批次的字符添加到输出缓冲区
                                            for char in current_answer:
                                                output_buffer.append((char, generate.message_id))
                                            
                                            # 根据缓冲区大小动态调整输出速度
                                            while output_buffer:
                                                char, msg_id = output_buffer.pop(0)
                                                yield send_char(char, msg_id)
                                                # 根据剩余缓冲区大小计算延迟
                                                delay = calculate_delay(len(output_buffer))
                                                time.sleep(delay)
                                            
                                            # 立即继续处理下一个请求
                                            continue
                                        
                                        # 处理Agent模式的消息事件
                                        elif dify_chunk.get("event") == "agent_message" and "answer" in dify_chunk:
                                            current_answer = dify_chunk["answer"]
                                            if not current_answer:
                                                continue
                                                
                                            message_id = dify_chunk.get("message_id", "")
                                            if not generate.message_id:
                                                generate.message_id = message_id
                                            
                                            # 将当前批次的字符添加到输出缓冲区
                                            for char in current_answer:
                                                output_buffer.append((char, generate.message_id))
                                            
                                            # 根据缓冲区大小动态调整输出速度
                                            while output_buffer:
                                                char, msg_id = output_buffer.pop(0)
                                                yield send_char(char, msg_id)
                                                # 根据剩余缓冲区大小计算延迟
                                                delay = calculate_delay(len(output_buffer))
                                                time.sleep(delay)
                                            
                                            # 立即继续处理下一个请求
                                            continue
                                        
                                        # 处理Agent的思考过程，记录日志但不输出给用户
                                        elif dify_chunk.get("event") == "agent_thought":
                                            thought_id = dify_chunk.get("id", "")
                                            thought = dify_chunk.get("thought", "")
                                            tool = dify_chunk.get("tool", "")
                                            tool_input = dify_chunk.get("tool_input", "")
                                            observation = dify_chunk.get("observation", "")
                                            
                                            logger.info(f"[Agent Thought] ID: {thought_id}, Tool: {tool}")
                                            if thought:
                                                logger.info(f"[Agent Thought] Thought: {thought}")
                                            if tool_input:
                                                logger.info(f"[Agent Thought] Tool Input: {tool_input}")
                                            if observation:
                                                logger.info(f"[Agent Thought] Observation: {observation}")
                                            
                                            # 获取message_id以关联思考和最终输出
                                            message_id = dify_chunk.get("message_id", "")
                                            if not generate.message_id and message_id:
                                                generate.message_id = message_id
                                            
                                            continue
                                        
                                        # 处理消息中的文件(如图片)，记录日志但不直接输出给用户
                                        elif dify_chunk.get("event") == "message_file":
                                            file_id = dify_chunk.get("id", "")
                                            file_type = dify_chunk.get("type", "")
                                            file_url = dify_chunk.get("url", "")
                                            
                                            logger.info(f"[Message File] ID: {file_id}, Type: {file_type}, URL: {file_url}")
                                            continue
                                        
                                        elif dify_chunk.get("event") == "message_end":
                                            # 快速输出剩余内容
                                            while output_buffer:
                                                char, msg_id = output_buffer.pop(0)
                                                yield send_char(char, msg_id)
                                                time.sleep(0.001)  # 固定使用最小延迟快速输出剩余内容
                                            
                                            # 只在零宽字符会话记忆模式时处理conversation_id
                                            # 模式3（无历史上下文）不处理conversation_id，保持对话独立
                                            if CONVERSATION_MEMORY_MODE == 2:
                                                conversation_id = dify_chunk.get("conversation_id")
                                                history = dify_chunk.get("conversation_history", [])
                                                
                                                has_conversation_id = False
                                                if history:
                                                    for msg in history:
                                                        if msg.get("role") == "assistant":
                                                            content = msg.get("content", "")
                                                            if decode_conversation_id(content) is not None:
                                                                has_conversation_id = True
                                                                break
                                                
                                                # 只在新会话且历史消息中没有会话ID时插入
                                                if conversation_id and not has_conversation_id:
                                                    logger.info(f"[Debug] Inserting conversation_id in stream: {conversation_id}")
                                                    encoded = encode_conversation_id(conversation_id)
                                                    logger.info(f"[Debug] Stream encoded content: {repr(encoded)}")
                                                    for char in encoded:
                                                        yield send_char(char, generate.message_id)
                                            
                                            final_chunk = {
                                                "id": generate.message_id,
                                                "object": "chat.completion.chunk",
                                                "created": int(time.time()),
                                                "model": model,
                                                "choices": [{
                                                    "index": 0,
                                                    "delta": {},
                                                    "finish_reason": "stop"
                                                }]
                                            }
                                            yield flush_chunk(f"data: {json.dumps(final_chunk)}\n\n")
                                            yield flush_chunk("data: [DONE]\n\n")
                                        
                                    except json.JSONDecodeError as e:
                                        logger.error(f"JSON decode error: {str(e)}")
                                        continue
                                        
                            except Exception as e:
                                logger.error(f"Error processing chunk: {str(e)}")
                                continue

                finally:
                    client.close()

            return Response(
                stream_with_context(generate()),
                content_type='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache, no-transform',
                    'Connection': 'keep-alive',
                    'Transfer-Encoding': 'chunked',
                    'X-Accel-Buffering': 'no',
                    'Content-Encoding': 'none'
                },
                direct_passthrough=True
            )
        else:
            async def sync_response():
                try:
                    async with httpx.AsyncClient(timeout=(HTTP_TIMEOUT, HTTP_CONNECT_TIMEOUT)) as client:
                        response = await client.post(
                            dify_endpoint,
                            json=dify_request,
                            headers=headers
                        )
                        
                        if response.status_code != 200:
                            error_msg = f"Dify API error: {response.text}"
                            logger.error(f"Request failed: {error_msg}")
                            return {
                                "error": {
                                    "message": error_msg,
                                    "type": "api_error",
                                    "code": response.status_code
                                }
                            }, response.status_code

                        dify_response = response.json()
                        logger.info(f"Received response from Dify: {json.dumps(dify_response, ensure_ascii=False)}")
                        logger.info(f"[Debug] Response content: {repr(dify_response.get('answer', ''))}")
                        openai_response = transform_dify_to_openai(dify_response, model=model)
                        conversation_id = dify_response.get("conversation_id")
                        if conversation_id:
                            # 在响应头中传递conversation_id
                            return Response(
                                json.dumps(openai_response),
                                content_type='application/json',
                                headers={
                                    'Conversation-Id': conversation_id
                                }
                            )
                        else:
                            return openai_response
                except httpx.RequestError as e:
                    error_msg = f"Failed to connect to Dify: {str(e)}"
                    logger.error(error_msg)
                    return {
                        "error": {
                            "message": error_msg,
                            "type": "api_error",
                            "code": "connection_error"
                        }
                    }, 503

            return asyncio.run(sync_response())

    except Exception as e:
        logger.exception("Unexpected error occurred")
        return {
            "error": {
                "message": str(e),
                "type": "internal_error",
            }
        }, 500

@app.route('/v1/models', methods=['GET'])
def list_models():
    """返回可用的模型列表"""
    logger.info("Listing available models")
    
    # 刷新模型信息
    asyncio.run(model_manager.refresh_model_info())
    
    # 获取可用模型列表
    available_models = model_manager.get_available_models()
    
    response = {
        "object": "list",
        "data": available_models
    }
    logger.info(f"Available models: {json.dumps(response, ensure_ascii=False)}")
    return response

import sys

# 在main.py的最后初始化时添加环境变量检查：
if __name__ == '__main__':
    # 检查命令行参数
    debug_mode = '--debug' in sys.argv
    
    if not VALID_API_KEYS:
        print("Warning: No API keys configured. Set the VALID_API_KEYS environment variable with comma-separated keys.")
    
    # 启动时初始化模型信息
    asyncio.run(model_manager.refresh_model_info())
    
    # 显示当前会话记忆模式信息
    mode_descriptions = {
        1: "history_message模式 - 构造history_message附加到消息中",
        2: "零宽字符模式 - 使用零宽字符隐藏conversation_id",
        3: "无历史上下文模式 - 每次对话都是独立的，不包含任何历史信息"
    }
    current_mode = CONVERSATION_MEMORY_MODE
    mode_desc = mode_descriptions.get(current_mode, "未知模式")
    logger.info(f"会话记忆模式: {current_mode} - {mode_desc}")
    print(f"会话记忆模式: {current_mode} - {mode_desc}")
    
    host = os.getenv("SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("SERVER_PORT", 5000))
    logger.info(f"Starting server on http://{host}:{port}")
    
    # 根据debug参数决定是否启用debug模式
    app.run(debug=debug_mode, host=host, port=port)
