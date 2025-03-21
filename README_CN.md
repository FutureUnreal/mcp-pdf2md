# PDF2MD 服务

基于MCP协议的高性能PDF转Markdown服务，由MinerU API提供支持，支持批量处理本地文件和URL链接，提供结构化输出。

## 主要特性

- 格式转换：将PDF文件转换为结构化Markdown格式。
- 多源支持：处理本地PDF文件和URL链接。
- 智能处理：自动选择最佳处理方法。
- 批量处理：支持多文件批量转换，高效处理大量PDF文件。
- OCR支持：可选启用OCR提高识别率。
- MCP集成：与Claude Desktop等LLM客户端无缝集成。

## 系统要求

- 软件：Python 3.10+
- 依赖：
  - httpx
  - mcp[cli]
  - python-dotenv
  - typer

## 快速开始

1. 克隆仓库并进入目录：
   ```bash
   git clone https://github.com/FutureUnreal/mcp-pdf2md.git
   cd mcp-pdf2md
   ```

2. 创建虚拟环境并安装依赖：
   
   **Linux/macOS**:
   ```bash
   uv venv
   source .venv/bin/activate
   uv pip install -e .
   ```
   
   **Windows**:
   ```bash
   uv venv
   .venv\Scripts\activate
   uv pip install -e .
   ```

3. 配置环境变量：

   在项目根目录创建`.env`文件，并设置以下环境变量：
   ```
   MINERU_API_BASE=https://mineru.net/api/v4/extract/task
   MINERU_BATCH_API=https://mineru.net/api/v4/extract/task/batch
   MINERU_BATCH_RESULTS_API=https://mineru.net/api/v4/extract-results/batch
   MINERU_API_KEY=Bearer your_api_key_here
   ```

4. 启动服务：
   ```bash
   uv run pdf2md
   ```

## Claude Desktop 配置

在Claude Desktop中添加以下配置：

**Windows**:
```json
{
    "mcpServers": {
        "pdf2md": {
            "command": "uv",
            "args": [
                "--directory",
                "C:\\path\\to\\mcp-pdf2md",  # 替换为实际路径
                "run",
                "pdf2md",
                "--output-dir",
                "C:\\path\\to\\output"  # 可选，指定输出目录
            ],
            "env": {
                "MINERU_API_KEY": "Bearer your_api_key_here"  # 替换为您的API密钥
            }
        }
    }
}
```

**Linux/macOS**:
```json
{
    "mcpServers": {
        "pdf2md": {
            "command": "uv",
            "args": [
                "--directory",
                "/path/to/mcp-pdf2md",  # 替换为实际路径
                "run",
                "pdf2md",
                "--output-dir",
                "/path/to/output"  # 可选，指定输出目录
            ],
            "env": {
                "MINERU_API_KEY": "Bearer your_api_key_here"  # 替换为您的API密钥
            }
        }
    }
}
```

**关于API密钥配置的说明：**
您可以通过两种方式设置API密钥：
1. 在项目目录中的`.env`文件中（推荐用于开发环境）
2. 在Claude Desktop配置中，如上所示（推荐用于日常使用）

如果您在两个地方都设置了API密钥，Claude Desktop配置中的密钥将优先生效。

## MCP工具

服务器提供以下MCP工具：

- **convert_pdf_url**：将PDF URL转换为Markdown
- **convert_pdf_file**：将本地PDF文件转换为Markdown

## 获取MinerU API密钥

本项目依赖MinerU API进行PDF内容提取。获取API密钥的步骤如下：

1. 访问[MinerU官网](https://mineru.net/)并注册账户
2. 登录后，需要在[此链接](https://mineru.net/apiManage/docs?openApplyModal=true)向MinerU团队申请API测试资格
3. 申请获批后，您才能访问[API管理](https://mineru.net/apiManage/token)页面
4. 按照提供的说明生成您的API密钥
5. 复制生成的API密钥
6. 将这个完整的字符串作为`MINERU_API_KEY`的值

请注意，目前MinerU API的访问权限还处于测试阶段，需要获得MinerU团队的批准。审批过程可能需要一些时间，请提前规划。

## 许可证

MIT许可证 - 详见LICENSE文件。

## 致谢

本项目基于[MinerU](https://github.com/opendatalab/MinerU/tree/master)的API。
