# PDF2MD - PDF转Markdown MCP服务器

这是一个基于[Model Context Protocol (MCP)](https://modelcontextprotocol.io)的服务器，提供PDF转Markdown的功能。该服务器使用Mineru API进行PDF内容提取和转换。

## 功能特点

- 将PDF文件转换为Markdown格式
- 支持本地PDF文件和PDF URL链接的处理
- 自动根据文件类型和大小选择最佳处理方法
- 保存Markdown内容到文件
- 通过MCP协议与LLM客户端（如Claude Desktop）集成
- 提供简化的自然语言请求接口

## 安装要求

- Python 3.12或更高版本
- 依赖包：
  - httpx
  - mcp
  - python-dotenv

## 安装方法

1. 克隆仓库：

```bash
git clone https://github.com/yourusername/pdf2md.git
cd pdf2md
```

2. 创建虚拟环境并安装依赖：

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# 或
.venv\Scripts\activate     # Windows

pip install -e .
```

3. 配置环境变量：

在项目根目录创建`.env`文件，并设置以下环境变量：

```
MINERU_API_BASE=https://mineru.net/api/v4/extract/task
MINERU_FILE_URLS_API=https://mineru.net/api/v4/file-urls/batch
MINERU_BATCH_API=https://mineru.net/api/v4/extract/task/batch
MINERU_BATCH_RESULTS_API=https://mineru.net/api/v4/extract-results/batch
MINERU_API_KEY=Bearer your_api_key_here
```

## 使用方法

### 作为MCP服务器运行

使用MCP CLI工具安装并运行服务器：

```bash
mcp install server.py
```

这将在Claude Desktop或其他支持MCP的客户端中注册服务器。

### 开发模式

使用MCP Inspector进行开发和测试：

```bash
mcp dev server.py
```

在MCP Inspector界面中：

1. 在"Transport Type"下拉菜单中选择"STDIO"
2. 在"Command"字段中输入`uv`（如果已安装）或`python`
3. 在"Arguments"字段中输入相应的参数：
   - 对于`uv`：`run,--with,mcp,mcp,run,server.py`
   - 对于`python`：`server.py`
4. 点击"Connect"按钮连接到服务器
5. 连接成功后，您可以使用提供的工具

### 直接运行

```bash
python server.py
```

## MCP工具

服务器提供以下MCP工具：

- `convert_pdf_url`: 将PDF URL转换为Markdown格式
  - 参数：
    - `url` - PDF文件的URL或URL列表
    - `enable_ocr` - 是否启用OCR（默认：True）
  - 返回：转换结果信息，包含下载文件路径

- `convert_pdf_file`: 将本地PDF文件转换为Markdown
  - 参数：
    - `input_files` - PDF文件的本地路径或路径列表
    - `enable_ocr` - 是否启用OCR（默认：True）
  - 返回：转换结果信息，包含下载文件路径

- `convert_pdf_auto`: 自动选择最佳方式将PDF转换为Markdown
  - 参数：
    - `source` - PDF文件的URL或本地路径，或者URL/路径的列表
    - `enable_ocr` - 是否启用OCR（默认：True）
  - 返回：转换结果信息，包含下载文件路径

- `convert_pdf`: 简化的PDF转换工具（推荐用于自然语言请求）
  - 参数：
    - `path` - PDF文件的URL或本地路径
    - `enable_ocr` - 是否启用OCR（默认：True）
  - 返回：转换结果信息，包含下载文件路径

## 使用示例

### 在Claude Desktop中使用

1. 确保服务器已安装并运行
2. 在Claude Desktop中，您可以使用自然语言请求转换PDF：

```
请将 https://arxiv.org/pdf/1706.03762.pdf 转换为Markdown
```

或者

```
请将 C:\Documents\sample.pdf 转换为Markdown
```

Claude将自动调用`convert_pdf`工具来处理您的请求。

### 在MCP Inspector中

1. 连接到服务器后，选择`convert_pdf_url`工具
2. 输入PDF文件的URL，例如：`https://example.com/document.pdf`
   或者输入URL列表，例如：
   ```json
   ["https://example.com/doc1.pdf", "https://example.com/doc2.pdf"]
   ```
   或者JSON字符串形式的URL列表：
   ```
   "[\"https://example.com/doc1.pdf\", \"https://example.com/doc2.pdf\"]"
   ```
3. 执行工具并查看转换结果
4. 选择`convert_pdf_file`工具
5. 输入PDF文件的本地路径，例如：`C:/path/to/your/file.pdf`
   或者输入文件路径列表，例如：
   ```json
   ["C:/path/to/doc1.pdf", "C:/path/to/doc2.pdf"]
   ```
   或者JSON字符串形式的文件路径列表：
   ```
   "[\"C:/path/to/doc1.pdf\", \"C:/path/to/doc2.pdf\"]"
   ```
6. 执行工具并查看转换结果
7. 选择`convert_pdf_auto`工具
8. 输入混合的URL和文件路径列表，例如：
   ```json
   ["https://example.com/doc1.pdf", "C:/path/to/doc2.pdf"]
   ```
   或者JSON字符串形式：
   ```
   "[\"https://example.com/doc1.pdf\", \"C:/path/to/doc2.pdf\"]"
   ```
9. 执行工具并查看转换结果

## 资源

服务器提供以下MCP资源：

- `status://api`: 获取API状态信息
- `help://usage`: 获取使用帮助信息

## 处理逻辑说明

- 如果输入是URL链接，系统会使用URL API方式处理
- 如果输入是本地文件，系统会使用文件上传API方式处理
- 自动选择功能会根据输入类型选择最合适的处理方法
- 处理过程包括：
  - 创建批处理任务
  - 自动轮询任务状态直到完成
  - 自动下载转换结果ZIP文件
  - 在结果ZIP中包含所有转换的Markdown文件

## 错误处理

常见错误及解决方案：

- 401认证错误: 检查API密钥是否正确设置，是否包含"Bearer "前缀
- 格式错误: 确保URL格式正确，包含http://或https://
- 批处理错误: 查看详细错误信息，确保所有参数格式正确
- 文件不可访问: 确保本地文件路径正确且有读取权限
- URL不可访问: 确保URL链接可以公开访问，不需要认证

如果遇到认证问题，检查`.env`文件中的API密钥格式，确保格式为`Bearer your_api_key_here`。

## 许可证

MIT