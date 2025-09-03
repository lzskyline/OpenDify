# OpenDify

OpenDify 是一个将 Dify API 转换为 OpenAI API 格式的代理服务器。它允许使用 OpenAI API 客户端直接与 Dify 服务进行交互。

> 🌟 本项目完全由AI自动生成，未手动编写任何代码（包括此Readme），向 AI 辅助编程的未来致敬！

[English Version](README_EN.md)

## 功能特点

- 完整支持 OpenAI API 格式转换为 Dify API
- 支持流式输出（Streaming）
- 智能动态延迟控制，提供流畅的输出体验
- 支持多种会话记忆模式，包括零宽字符模式和history_message模式
- 支持 OpenAI Function Call 和 MCP Server 功能
- **支持图片附件上传**：自动处理包含图片的多模态请求，支持视觉模型
- 支持多个模型配置
- 支持Dify Agent应用，处理高级工具调用（如生成图片等）
- 兼容标准的 OpenAI API 客户端
- 自动获取 Dify 应用信息

## 效果展示

### Function Call 和 MCP Server 支持

新增对 OpenAI Function Call 和 MCP Server 的支持，即使 Dify 不支持直接设置系统提示词：

- 自动检测请求中的 `system` 角色消息
- 智能将系统提示词插入到用户查询中
- 防止重复插入系统提示词
- 完美兼容 OpenAI 的 Function Call 格式

![Function Call 支持示例](images/3.png)

*上图展示了 OpenDify 对 Function Call 的支持。即使 Dify 应用不支持直接设置系统提示词，通过 OpenDify 的转换，也能正确处理 MCP Server 及 Function Call 的需求。*

### Dify Agent应用支持

![Dify Agent应用截图](images/1.png)

*截图展示了OpenDify代理服务支持的Dify Agent应用界面，可以看到Agent成功地处理了用户的Python多线程用法请求，并返回了相关代码示例。*

### 会话记忆功能

![Dify会话记忆功能截图](images/2.png)

*上图展示了OpenDify的会话记忆功能。当用户提问"今天是什么天气？"时，AI能够记住之前对话中提到"今天是晴天"的上下文信息，并给出相应回复。*

### 图片附件支持

OpenDify 现在支持处理包含图片的多模态请求，自动将图片上传到 Dify 平台并正确传递给支持视觉的模型。

![图片附件支持示例](images/4.png)

*上图展示了 OpenDify 对图片附件的支持。系统会自动检测请求中的图片内容，将其上传到 Dify 平台，并在请求中正确引用上传的文件。*

> ⚠️ **重要提醒**：
> 
> 1. **Dify 平台限制**：当前 Dify 平台仅支持图片类型的附件上传，请确保上传的文件为 PNG、JPG、JPEG、WEBP 或 GIF 格式。
> 
> 2. **Cherry Studio 客户端设置**：如果您使用的是 Cherry Studio 客户端，请确保在模型设置中启用了视觉支持（参考下图），否则客户端不会发送任何附件内容到 API。
> 
> ![Cherry Studio 视觉支持设置](images/5.png)
> 
> 3. **Dify 平台视觉设置**：同时请确保在 Dify 平台上对应的模型也已勾选开启视觉功能，否则平台侧不会响应任何图片内容。
> 
> ![Dify 平台视觉功能设置](images/6.png)

## 特性

### 会话记忆功能

该代理支持自动记忆会话上下文，无需客户端进行额外处理。提供了两种会话记忆模式：

1. **history_message模式**：将历史消息直接附加到当前消息中，支持客户端编辑历史消息（默认）
2. **零宽字符模式**：在每个新会话的第一条回复中，会自动嵌入不可见的会话ID，后续消息自动继承上下文

可以通过环境变量控制此功能：

```shell
# 在 .env 文件中设置会话记忆模式
# 1: 构造history_message附加到消息中的模式（默认）
# 2: 零宽字符模式
CONVERSATION_MEMORY_MODE=1
```

默认情况下使用history_message模式，这种模式更灵活，支持客户端编辑历史消息，并能更好地处理系统提示词。

> 注意：history_message模式会将所有历史消息追加到当前消息中，可能会消耗更多的token。

### 流式输出优化

- 智能缓冲区管理
- 动态延迟计算
- 平滑的输出体验

### 配置灵活性

- 自动获取应用信息
- 简化的配置方式
- 动态模型名称映射

## 支持的模型

支持任意 Dify 应用，系统会自动从 Dify API 获取应用名称和信息。只需在配置文件中添加应用的 API Key 即可。

## API 使用

### List Models

获取所有可用模型列表：

```python
import openai

openai.api_base = "http://127.0.0.1:5068/v1"
openai.api_key = "sk-abc123"  # 使用配置的有效API Key

# 获取可用模型列表
models = openai.Model.list()
print(models)

# 输出示例：
{
    "object": "list",
    "data": [
        {
            "id": "My Translation App",  # Dify 应用名称
            "object": "model",
            "created": 1704603847,
            "owned_by": "dify"
        },
        {
            "id": "Code Assistant",  # 另一个 Dify 应用名称
            "object": "model",
            "created": 1704603847,
            "owned_by": "dify"
        }
    ]
}
```

系统会自动从 Dify API 获取应用名称，并用作模型 ID。

### Chat Completions

```python
import openai

openai.api_base = "http://127.0.0.1:5068/v1"
openai.api_key = "sk-abc123"  # 使用配置的有效API Key

response = openai.ChatCompletion.create(
    model="My Translation App",  # 使用 Dify 应用的名称
    messages=[
        {"role": "user", "content": "你好"}
    ],
    stream=True
)

for chunk in response:
    print(chunk.choices[0].delta.content or "", end="")
```

## 快速开始

### 环境要求

- Python 3.9+
- pip

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置

1. 复制 `.env.example` 文件并重命名为 `.env`：
```bash
cp .env.example .env
```

2. 在 Dify 平台配置应用：
   - 登录 Dify 平台，进入工作室
   - 点击"创建应用"，配置好需要的模型（如 Claude、Gemini 等）
   - 配置应用的提示语和其他参数
   - 发布应用
   - 进入"访问 API"页面，生成 API 密钥

   > **重要说明**：Dify 不支持在请求时动态传入提示词、切换模型及其他参数。所有这些配置都需要在创建应用时设置好。Dify 会根据 API 密钥来确定使用哪个应用及其对应的配置。系统会自动从 Dify API 获取应用的名称和描述信息。

3. 在 `.env` 文件中配置你的 Dify API Keys：
```env
# Dify API Keys Configuration
# Format: Comma-separated list of API keys
DIFY_API_KEYS=app-xxxxxxxx,app-yyyyyyyy,app-zzzzzzzz

# Dify API Base URL
DIFY_API_BASE="https://your-dify-api-base-url/v1"

# OpenAI Compatible API Keys (for client authentication)
VALID_API_KEYS="sk-abc123,sk-def456"

# Server Configuration
SERVER_HOST="127.0.0.1"
SERVER_PORT=5068

# HTTP Timeout Configuration (seconds)
HTTP_TIMEOUT=30          # 请求超时时间
HTTP_CONNECT_TIMEOUT=10  # 连接超时时间
```

配置说明：
- `DIFY_API_KEYS`：以逗号分隔的 API Keys 列表，每个 Key 对应一个 Dify 应用
- `VALID_API_KEYS`：客户端连接时使用的有效 API Keys，以逗号分隔
- 系统会自动从 Dify API 获取每个应用的名称和信息

### 运行服务

```bash
python main.py
```

服务将在 `http://127.0.0.1:5068` 启动

## 贡献指南

欢迎提交 Issue 和 Pull Request 来帮助改进项目。

## 许可证

[MIT License](LICENSE)
