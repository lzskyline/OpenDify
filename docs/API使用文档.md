# OpenDify API 使用文档

## 概述

OpenDify 是一个 OpenAI 兼容的 API 代理服务，支持与 Dify 平台的无缝集成。本文档提供了完整的 API 使用示例和说明。

## 服务配置

### 环境变量

确保您已经设置了以下环境变量：

- `VALID_API_KEYS`: 有效的API密钥列表（逗号分隔）
- `DIFY_API_KEYS`: Dify应用的API密钥列表（逗号分隔）
- `DIFY_API_BASE`: Dify API的基础URL
- `CONVERSATION_MEMORY_MODE`: 会话记忆模式（1或2）
- `SERVER_HOST`: 服务器主机地址（默认：127.0.0.1）
- `SERVER_PORT`: 服务器端口（默认：5000）

### 会话记忆模式

- **模式1（默认）**: history_message模式 - 构造history_message附加到消息中
- **模式2**: 零宽字符模式 - 使用零宽字符隐藏conversation_id

## API 接口

### 1. 聊天完成接口

#### 1.1 基本聊天请求

```bash
curl -X POST http://127.0.0.1:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "model": "your_model_name",
    "messages": [
      {
        "role": "user",
        "content": "你好，请介绍一下你自己"
      }
    ],
    "stream": false
  }'
```

#### 1.2 流式聊天请求

```bash
curl -X POST http://127.0.0.1:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "model": "your_model_name",
    "messages": [
      {
        "role": "user",
        "content": "请写一首关于春天的诗"
      }
    ],
    "stream": true
  }'
```

#### 1.3 带系统指令的聊天请求

```bash
curl -X POST http://127.0.0.1:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "model": "your_model_name",
    "messages": [
      {
        "role": "system",
        "content": "你是一个专业的编程助手，请用简洁明了的方式回答问题。"
      },
      {
        "role": "user",
        "content": "如何实现一个快速排序算法？"
      }
    ],
    "stream": false
  }'
```

#### 1.4 多轮对话请求

```bash
curl -X POST http://127.0.0.1:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "model": "your_model_name",
    "messages": [
      {
        "role": "user",
        "content": "什么是Python？"
      },
      {
        "role": "assistant",
        "content": "Python是一种高级编程语言..."
      },
      {
        "role": "user",
        "content": "它有什么优势？"
      }
    ],
    "stream": false
  }'
```

#### 1.5 带图片上传的聊天请求

```bash
curl -X POST http://127.0.0.1:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "model": "your_model_name",
    "messages": [
      {
        "role": "user",
        "content": [
          {
            "type": "text",
            "text": "请描述这张图片中的内容"
          },
          {
            "type": "image_url",
            "image_url": {
              "url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
            }
          }
        ]
      }
    ],
    "stream": false
  }'
```

### 2. 模型列表接口

```bash
curl -X GET http://127.0.0.1:5000/v1/models \
  -H "Authorization: Bearer YOUR_API_KEY"
```

## 请求参数说明

### 聊天完成接口参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| model | string | 是 | 模型名称，对应Dify应用名称 |
| messages | array | 是 | 消息列表 |
| stream | boolean | 否 | 是否使用流式响应，默认false |
| user | string | 否 | 用户ID，默认"default_user" |

### 消息格式

```json
{
  "role": "user|assistant|system",
  "content": "消息内容" // 或包含文本和图片的数组
}
```

### 多模态内容格式

```json
{
  "role": "user",
  "content": [
    {
      "type": "text",
      "text": "文本内容"
    },
    {
      "type": "image_url",
      "image_url": {
        "url": "data:image/png;base64,..."
      }
    }
  ]
}
```

## 响应格式

### 普通响应格式

```json
{
  "id": "message_id",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "your_model_name",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "AI回复内容"
      },
      "finish_reason": "stop"
    }
  ]
}
```

### 流式响应格式

流式响应使用 Server-Sent Events (SSE) 格式：

```
data: {"id":"message_id","object":"chat.completion.chunk","created":1234567890,"model":"your_model_name","choices":[{"index":0,"delta":{"content":"部分内容"},"finish_reason":null}]}

data: {"id":"message_id","object":"chat.completion.chunk","created":1234567890,"model":"your_model_name","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

### 模型列表响应格式

```json
{
  "object": "list",
  "data": [
    {
      "id": "model_name",
      "object": "model",
      "created": 1234567890,
      "owned_by": "dify"
    }
  ]
}
```

## 错误处理

### 常见错误码

| 状态码 | 错误类型 | 说明 |
|--------|----------|------|
| 401 | invalid_api_key | API密钥无效或缺失 |
| 404 | model_not_found | 模型不存在 |
| 400 | invalid_request_error | 请求格式错误 |
| 503 | api_error | Dify API连接错误 |
| 500 | internal_error | 服务器内部错误 |

### 错误响应格式

```json
{
  "error": {
    "message": "错误描述",
    "type": "错误类型",
    "code": "错误代码"
  }
}
```

## 使用示例

### Python 示例

```python
import requests
import json

# 基本聊天请求
def chat_completion(api_key, model, messages, stream=False):
    url = "http://127.0.0.1:5000/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": model,
        "messages": messages,
        "stream": stream
    }
    
    response = requests.post(url, headers=headers, json=data)
    return response.json()

# 使用示例
api_key = "YOUR_API_KEY"
model = "your_model_name"
messages = [
    {"role": "user", "content": "你好"}
]

result = chat_completion(api_key, model, messages)
print(result)
```

### JavaScript 示例

```javascript
// 基本聊天请求
async function chatCompletion(apiKey, model, messages, stream = false) {
    const url = "http://127.0.0.1:5000/v1/chat/completions";
    const headers = {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${apiKey}`
    };
    const data = {
        model: model,
        messages: messages,
        stream: stream
    };
    
    const response = await fetch(url, {
        method: "POST",
        headers: headers,
        body: JSON.stringify(data)
    });
    
    return await response.json();
}

// 使用示例
const apiKey = "YOUR_API_KEY";
const model = "your_model_name";
const messages = [
    {role: "user", content: "你好"}
];

chatCompletion(apiKey, model, messages)
    .then(result => console.log(result))
    .catch(error => console.error(error));
```

## 注意事项

1. **API密钥安全**: 请妥善保管您的API密钥，不要在客户端代码中硬编码
2. **图片上传**: 支持PNG、JPG、JPEG、WEBP、GIF格式的图片
3. **流式响应**: 流式响应适合需要实时显示AI回复的场景
4. **会话记忆**: 系统会自动处理多轮对话的上下文记忆
5. **超时设置**: 默认HTTP超时时间为30秒，连接超时为10秒

## 技术支持

如有问题，请检查：
1. 环境变量配置是否正确
2. Dify API服务是否正常运行
3. 网络连接是否正常
4. API密钥是否有效

---

*本文档最后更新时间：2025年9月5日*
