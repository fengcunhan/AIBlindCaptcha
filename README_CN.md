# AI 致盲验证码：时间编码视频验证码系统

一个基于 **时间盲视** 现象的先进验证码系统，该现象指AI模型难以感知人类能够轻易检测的时间信息。本系统创建基于视频的验证码，内容仅在播放时可见，使其能够抵抗静态图像分析，同时仍可被人类解决。

## 🌟 特性

### 🔐 **高级验证码模式**
- **文本模式**：3-5个字符的单词，字体大且易读
- **形状模式**：几何形状（圆形、矩形、三角形、心形、箭头）
- **深度图模式**：可配置阈值的自定义深度图像
- **随机模式**：自动从所有可用模式中选择

### 🎯 **时间编码安全性**
- **时间编码**：内容仅在视频播放期间可见
- **算法2实现**：移动前景像素配合静态噪声背景
- **OCR抵抗**：单帧呈现为结构化噪声
- **运动连贯性**：需要时间积分才能解决

### 🌐 **现代Web界面**
- **响应式设计**：清晰、直观的界面，支持视频循环播放
- **智能自动播放**：优雅处理浏览器自动播放策略
- **实时验证**：即时反馈和提示系统
- **多语言支持**：中文界面，易于国际化

### ⚙️ **技术特性**
- **FastAPI后端**：高性能异步API服务器
- **H.264视频编码**：最大浏览器兼容性
- **内存存储**：安全的基于TTL的会话管理
- **深度图处理**：可配置的阈值过滤
- **可扩展架构**：易于添加新的验证码模式

## 🚀 快速开始

### 环境要求

- Python 3.8+
- FFmpeg（用于视频编码）
- 推荐使用虚拟环境

### 安装步骤

```bash
# 克隆仓库
git clone https://github.com/your-username/AIBlindCaptcha.git
cd AIBlindCaptcha

# 创建并激活虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows系统: .venv\Scripts\activate

# 安装依赖
pip install fastapi uvicorn opencv-python pillow numpy
```

### 运行服务器

```bash
# 启动开发服务器
python -m uvicorn server:app --reload

# 访问演示页面 http://127.0.0.1:8000
```

## 🎮 使用方法

### 基础使用

1. **选择模式**：在文本、形状、深度图或随机模式中选择
2. **生成验证码**：点击"获取验证码"创建时间编码视频
3. **解决挑战**：观看循环播放的视频并识别内容
4. **提交答案**：输入你看到的内容并验证
5. **获取帮助**：如需要可使用提示系统（消耗尝试次数）

### 高级功能

#### 深度图模式配置
- 上传自定义深度图像
- 调整阈值范围（tl, tu）进行像素过滤
- 根据图像特征微调难度

#### API使用

```python
import requests

# 生成新验证码
response = requests.post("http://localhost:8000/captcha/new", json={
    "mode": "text",
    "difficulty": "medium"
})

data = response.json()
captcha_id = data["id"]
video_data = data["video_base64"]
hint = data["hint"]

# 验证答案
verify_response = requests.post("http://localhost:8000/captcha/verify", json={
    "id": captcha_id,
    "answer": "你的答案"
})

result = verify_response.json()
print(f"成功: {result['success']}")
```

## 🏗️ 架构设计

### 核心组件

- **`captcha_generator.py`**：时间编码视频生成引擎
  - 时间掩码创建和噪声合成
  - 多模态验证码生成（文本/形状/深度图）
  - H.264视频编码，确保浏览器兼容性

- **`server.py`**：FastAPI服务层
  - RESTful API端点
  - 基于TTL的内存会话管理
  - 安全特性（尝试限制、速率控制）

- **`static_demo.html`**：交互式前端
  - 视频循环播放和智能自动播放
  - 实时模式切换
  - 深度图像上传和处理

### 安全特性

- **基于TTL的会话**：默认3分钟过期
- **尝试限制**：每个验证码最多5次尝试
- **模糊匹配**：智能形状识别
- **输入验证**：服务端答案验证
- **错误处理**：优雅降级和日志记录

## 📊 API端点

### 生成验证码
```http
POST /captcha/new
Content-Type: application/json

{
  "mode": "text|shape|depth|random",
  "difficulty": "easy|medium|hard",
  "threshold_low": 0.2,      // 深度图模式
  "threshold_high": 0.8,     // 深度图模式
  "depth_image": "base64..." // 可选
}
```

### 验证答案
```http
POST /captcha/verify
Content-Type: application/json

{
  "id": "验证码ID",
  "answer": "用户答案"
}
```

### 获取提示
```http
GET /captcha/hint/{captcha_id}
```

## 🔬 工作原理

### 时间编码算法

1. **掩码创建**：为前景内容生成二进制掩码
2. **噪声合成**：为背景创建平铺噪声模式
3. **时间运动**：对前景像素应用垂直运动（y + v*t）
4. **帧合成**：将运动前景与静态背景结合
5. **视频编码**：导出为H.264 MP4用于网络传输

### 安全原理

- **静态分析抵抗**：单帧呈现为噪声
- **时间连贯性**：仅在播放时内容显现
- **人类优势**：人类擅长时间模式识别
- **AI限制**：当前模型难以处理时间积分

## 🛠️ 配置选项

### 环境变量

```bash
# 服务器设置
export HOST=0.0.0.0
export PORT=8000
export TTL_SECONDS=180

# 视频设置
export DEFAULT_WIDTH=640
export DEFAULT_HEIGHT=360
export DEFAULT_FPS=24
export DEFAULT_DURATION=4.0
```

### 自定义配置

修改 `captcha_generator.py` 中的常量：
- `DEFAULT_NOISE_DENSITY`：背景噪声强度
- `DEFAULT_SPEED_PX_PER_FRAME`：前景运动速度
- `FONT_PATHS_CANDIDATES`：文本渲染的系统字体路径

## 🧪 开发

### 运行测试

```bash
# 启动测试服务器
python -m uvicorn server:app --reload --host 0.0.0.0 --port 8000

# 测试API端点
curl -X POST "http://localhost:8000/captcha/new" \
  -H "Content-Type: application/json" \
  -d '{"mode": "text", "difficulty": "medium"}'
```

### 添加新验证码模式

1. 在 `captcha_generator.py` 中创建掩码生成函数
2. 将模式添加到 `generate_time_captcha()` 函数
3. 在 `static_demo.html` 中更新前端模式选择
4. 如需要，添加服务端验证逻辑

## 📈 性能指标

- **生成时间**：每个验证码约2-3秒
- **视频大小**：每个MP4约50-100 KB
- **内存使用**：内存存储约10 MB
- **并发处理**：支持100+并发请求

## 🔒 安全考虑

### 生产环境部署

- **必需HTTPS**：所有通信使用TLS
- **速率限制**：实现基于IP的速率限制
- **Redis存储**：用Redis替换内存存储
- **CDN分发**：使用CDN分发视频文件
- **监控**：实现日志记录和监控

### 最佳实践

- **短TTL**：保持验证码生命周期最小（3-5分钟）
- **尝试限制**：限制每次会话的最大尝试次数
- **输入验证**：清理所有用户输入
- **错误处理**：不要在错误中泄露敏感信息

## 🤝 贡献

我们欢迎贡献！请查看我们的[贡献指南](CONTRIBUTING.md)了解详情。

### 开发环境设置

```bash
# 克隆仓库
git clone https://github.com/your-username/AIBlindCaptcha.git
cd AIBlindCaptcha

# 设置开发环境
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 运行开发服务器
python -m uvicorn server:app --reload
```

## 📄 许可证

本项目采用MIT许可证 - 详情请参阅[LICENSE](LICENSE)文件。

## 🙏 致谢

- **时间盲视论文**：[Time Blindness: Why Video-Language Models Can't See What Humans Can?](https://arxiv.org/pdf/2505.24867)
- **FastAPI**：用于构建API的现代快速Web框架
- **OpenCV**：视频处理的计算机视觉库
- **Pillow**：Python图像处理库

## 📞 支持

- 🐛 [报告问题](https://github.com/your-username/AIBlindCaptcha/issues)
- 💬 [讨论区](https://github.com/your-username/AIBlindCaptcha/discussions)
- 📧 [邮件支持](mailto:support@example.com)

---

⭐ **如果这个项目对你有用，请给我们一个星标！**

使用 Python、FastAPI 和计算机技术构建 ❤️