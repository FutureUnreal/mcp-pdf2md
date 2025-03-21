import os
import json
import time
import asyncio
import httpx
import re
import logging
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional, List, Dict, Any
from mcp.server.fastmcp import FastMCP

# 设置日志
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("pdf2md.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("pdf2md")

# 加载环境变量
load_dotenv()

# API配置
MINERU_API_BASE = os.environ.get("MINERU_API_BASE", "https://mineru.net/api/v4/extract/task")
MINERU_API_KEY = os.environ.get("MINERU_API_KEY", "")
MINERU_BATCH_API = os.environ.get("MINERU_BATCH_API", "https://mineru.net/api/v4/extract/task/batch")
MINERU_BATCH_RESULTS_API = os.environ.get("MINERU_BATCH_RESULTS_API", "https://mineru.net/api/v4/extract-results/batch")
MINERU_FILE_URLS_API = os.environ.get("MINERU_FILE_URLS_API", "https://mineru.net/api/v4/file-urls/batch")

# 全局变量
OUTPUT_DIR = "./downloads"

# API认证请求头
HEADERS = {
    "Authorization": MINERU_API_KEY if MINERU_API_KEY.startswith("Bearer ") else f"Bearer {MINERU_API_KEY}", 
    "Content-Type": "application/json"
}

def set_output_dir(output_dir: str):
    """设置输出目录路径"""
    global OUTPUT_DIR
    OUTPUT_DIR = output_dir
    logger.info(f"已设置输出目录为: {output_dir}")

# 创建MCP服务器
mcp = FastMCP("PDF到Markdown转换服务")

# 辅助函数
async def download_zip_file(client, zip_url, file_name, prefix="md", max_retries=3):
    """
    下载并保存ZIP文件，然后自动解压
    
    Args:
        client: HTTP客户端
        zip_url: ZIP文件URL
        file_name: 文件名
        prefix: 保存文件前缀
        max_retries: 最大重试次数
        
    Returns:
        dict: 包含文件名、ZIP路径和解压目录的字典，失败则返回None
    """
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # 下载ZIP文件内容
            logger.info(f"正在下载ZIP文件 (尝试 {retry_count+1}/{max_retries})...")
            zip_response = await client.get(zip_url, follow_redirects=True, timeout=120.0)
            
            if zip_response.status_code == 200:
                # 保存ZIP文件
                current_date = time.strftime("%Y%m%d")
                
                # 简化文件名，去掉扩展名并处理特殊字符
                base_name = os.path.splitext(file_name)[0]
                # 替换文件名中的特殊字符
                safe_name = re.sub(r'[^\w\s-]', '', base_name).strip()
                # 将连续的空白字符替换为单个下划线
                safe_name = re.sub(r'\s+', '_', safe_name)
                
                # 如果文件名只是数字，添加前缀"paper_"
                if safe_name.isdigit() or re.match(r'^\d+\.\d+$', safe_name):
                    safe_name = f"paper_{safe_name}"
                    
                zip_filename = f"{prefix}_{safe_name}_{current_date}.zip"
                
                # 创建存放下载的目录
                download_dir = Path(OUTPUT_DIR)
                if not download_dir.exists():
                    download_dir.mkdir(parents=True)
                
                save_path = download_dir / zip_filename
                
                with open(save_path, "wb") as f:
                    f.write(zip_response.content)
                
                logger.info(f"文件已保存为: {save_path}")
                
                # 创建解压目录
                extract_dir = download_dir / safe_name
                if not extract_dir.exists():
                    extract_dir.mkdir(parents=True)
                
                # 解压ZIP文件
                import zipfile
                try:
                    with zipfile.ZipFile(save_path, 'r') as zip_ref:
                        zip_ref.extractall(extract_dir)
                    logger.info(f"文件已解压到: {extract_dir}")
                except Exception as e:
                    logger.error(f"解压文件时出错: {e}")
                
                # 返回下载文件信息
                return {
                    "file_name": file_name,
                    "zip_path": str(save_path),
                    "extract_dir": str(extract_dir)
                }
            else:
                logger.error(f"下载ZIP文件失败: {zip_response.status_code}")
                retry_count += 1
                if retry_count < max_retries:
                    await asyncio.sleep(2)
                continue
        except Exception as e:
            logger.error(f"获取ZIP内容时出错: {e}")
            retry_count += 1
            if retry_count < max_retries:
                await asyncio.sleep(2)
            continue
    
    logger.error(f"下载ZIP文件失败，已达到最大重试次数 ({max_retries})")
    return None

def print_task_status(extract_results):
    """
    打印任务状态并检查是否全部完成
    
    Args:
        extract_results: 任务结果列表
        
    Returns:
        tuple: (所有任务是否完成, 是否有任务完成)
    """
    all_done = True
    any_done = False
    
    logger.info("\n===== 任务状态报告 =====")
    for i, result in enumerate(extract_results):
        current_status = result.get("state", "")
        file_name = result.get("file_name", "")
        
        status_icon = "✅" if current_status == "done" else "⏳"
        logger.info(f"{status_icon} 任务 {i+1}/{len(extract_results)} - 文件: {file_name}, 状态: {current_status}")
        
        if current_status == "done":
            any_done = True
        else:
            all_done = False
    
    logger.info("=========================\n")
    
    return all_done, any_done

async def check_task_status(client, batch_id, max_retries=60, sleep_seconds=5):
    """
    检查批量任务状态
    
    Args:
        client: HTTP客户端
        batch_id: 批次ID
        max_retries: 最大重试次数
        sleep_seconds: 每次重试间隔秒数
        
    Returns:
        dict: 包含任务状态信息的字典，失败则返回错误信息
    """
    retry_count = 0
    
    while retry_count < max_retries:
        retry_count += 1
        logger.info(f"查询状态 ({retry_count}/{max_retries})...")
        
        # 构建查询URL
        status_url = f"{MINERU_BATCH_RESULTS_API}/{batch_id}"
        
        try:
            # 发送请求
            status_response = await client.get(
                status_url,
                headers=HEADERS,
                timeout=60.0  # 减少单次请求的超时时间
            )
            
            if status_response.status_code != 200:
                logger.error(f"查询状态失败: {status_response.status_code}")
                await asyncio.sleep(sleep_seconds)
                continue
            
            try:
                status_data = status_response.json()
            except Exception as e:
                logger.error(f"解析JSON失败: {e}")
                await asyncio.sleep(sleep_seconds)
                continue
            
            # 检查code字段
            if status_data.get("code") != 0 and status_data.get("code") != 200:
                logger.error(f"查询状态错误: {status_data.get('msg', '未知错误')}")
                await asyncio.sleep(sleep_seconds)
                continue
            
            # 获取任务状态
            task_data = status_data.get("data", {})
            extract_results = task_data.get("extract_result", [])
            
            # 检查是否有任务结果
            if not extract_results:
                logger.info("未找到任务结果，继续轮询...")
                await asyncio.sleep(sleep_seconds)
                continue
            
            # 检查所有任务的状态
            all_done, any_done = print_task_status(extract_results)
            
            # 如果所有任务都已完成，返回结果
            if all_done:
                logger.info("\n批量任务已完成")
                return {
                    "success": True,
                    "extract_results": extract_results,
                    "task_data": task_data,
                    "status_data": status_data
                }
            
            # 如果有任务还在处理中，继续轮询
            logger.info(f"有任务仍在处理中，{sleep_seconds}秒后继续轮询...")
            await asyncio.sleep(sleep_seconds)
            
        except Exception as e:
            logger.error(f"检查任务状态时出错: {e}")
            await asyncio.sleep(sleep_seconds)
    
    logger.error("轮询超时，未能获取最终结果")
    return {
        "success": False,
        "error": "轮询超时，未能获取最终结果"
    }

async def download_batch_results(client, extract_results):
    """
    下载批量任务结果
    
    Args:
        client: HTTP客户端
        extract_results: 任务结果列表
        
    Returns:
        list: 下载文件信息列表
    """
    downloaded_files = []
    
    logger.info("\n准备下载任务结果...")
    
    # 从extract_results中获取下载链接
    for i, result in enumerate(extract_results):
        if result.get("state") == "done":
            try:
                # 获取文件信息
                file_name = result.get("file_name", f"file_{i+1}")
                zip_url = result.get("full_zip_url", "")
                
                if not zip_url:
                    logger.warning(f"警告: 文件 {file_name} 没有ZIP下载URL")
                    continue
                
                logger.info(f"下载文件 {i+1}/{len(extract_results)}: {file_name}")
                
                # 下载ZIP文件
                downloaded_file = await download_zip_file(client, zip_url, file_name)
                if downloaded_file:
                    downloaded_files.append(downloaded_file)
            except Exception as e:
                logger.error(f"获取ZIP内容时出错: {e}")
    
    if downloaded_files:
        logger.info(f"成功下载了 {len(downloaded_files)} 个文件")
    else:
        logger.info("没有文件被下载")
        
    return downloaded_files

def parse_url_string(url_string):
    """
    解析以空格、逗号或换行符分隔的URL字符串
    
    Args:
        url_string: URL字符串
        
    Returns:
        list: URL列表
    """
    # 如果输入是带引号的字符串，先去除引号
    if isinstance(url_string, str):
        if (url_string.startswith('"') and url_string.endswith('"')) or \
           (url_string.startswith("'") and url_string.endswith("'")):
            url_string = url_string[1:-1]
    
    urls = []
    for part in url_string.split():
        if ',' in part:
            urls.extend(part.split(','))
        elif '\n' in part:
            urls.extend(part.split('\n'))
        else:
            urls.append(part)
    
    # 去除每个URL中可能的引号
    cleaned_urls = []
    for url in urls:
        if (url.startswith('"') and url.endswith('"')) or \
           (url.startswith("'") and url.endswith("'")):
            cleaned_urls.append(url[1:-1])
        else:
            cleaned_urls.append(url)
    
    return cleaned_urls

def parse_path_string(path_string):
    """
    解析以空格、逗号或换行符分隔的文件路径字符串
    
    Args:
        path_string: 文件路径字符串
        
    Returns:
        list: 文件路径列表
    """
    # 如果输入是带引号的字符串，先去除引号
    if isinstance(path_string, str):
        if (path_string.startswith('"') and path_string.endswith('"')) or \
           (path_string.startswith("'") and path_string.endswith("'")):
            path_string = path_string[1:-1]
    
    paths = []
    for part in path_string.split():
        if ',' in part:
            paths.extend(part.split(','))
        elif '\n' in part:
            paths.extend(part.split('\n'))
        else:
            paths.append(part)
    
    # 去除每个路径中可能的引号
    cleaned_paths = []
    for path in paths:
        if (path.startswith('"') and path.endswith('"')) or \
           (path.startswith("'") and path.endswith("'")):
            cleaned_paths.append(path[1:-1])
        else:
            cleaned_paths.append(path)
    
    return cleaned_paths

# 定义MCP工具
@mcp.tool()  
async def convert_pdf_url(url: str, enable_ocr: bool = True) -> Dict[str, Any]:
    """
    【专用工具】将PDF URL转换为Markdown，支持单个URL或URL列表
    
    Args:
        url: PDF文件的URL或URL列表，可以是以空格、逗号或换行符分隔的字符串
        enable_ocr: 是否启用OCR（默认：True）

    Returns:
        dict: 转换结果信息
    """
    if not MINERU_API_KEY:
        return {"success": False, "error": "缺少API密钥，请设置环境变量MINERU_API_KEY"}
    
    # 解析URL输入
    if isinstance(url, str):
        # 处理以空格、逗号或换行符分隔的URL列表
        urls = parse_url_string(url)
    else:
        urls = [url]  # 处理单个非字符串类型URL（理论上不应该发生）
    
    logger.info(f"处理URL输入: {urls}")
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            # 创建批量任务
            files = []
            for i, url_item in enumerate(urls):
                files.append({
                    "url": url_item, 
                    "is_ocr": enable_ocr, 
                    "data_id": f"url_convert_{i+1}_{int(time.time())}"
                })
            
            batch_data = {
                "enable_formula": True,
                "language": "auto",
                "layout_model": "doclayout_yolo",
                "enable_table": True,
                "files": files
            }
            
            response = await client.post(
                MINERU_BATCH_API,
                headers=HEADERS,
                json=batch_data,
                timeout=300.0
            )
            
            if response.status_code != 200:
                return {"success": False, "error": f"请求失败: {response.status_code}"}
            
            try:
                status_data = response.json()
                
                if status_data.get("code") != 0 and status_data.get("code") != 200:
                    error_msg = status_data.get("msg", "未知错误")
                    return {"success": False, "error": f"API返回错误: {error_msg}"}
                    
                # 获取批次ID
                batch_id = status_data.get("data", {}).get("batch_id", "")
                if not batch_id:
                    return {"success": False, "error": "未获取到批次ID"}
                    
                logger.info(f"批次ID: {batch_id}")
                
                # 轮询任务状态
                task_status = await check_task_status(client, batch_id)
                
                if not task_status.get("success"):
                    return task_status
                
                # 下载批量任务结果
                downloaded_files = await download_batch_results(client, task_status.get("extract_results", []))
                
                return {
                    "success": True, 
                    "downloaded_files": downloaded_files,
                    "batch_id": batch_id,
                    "total_urls": len(urls),
                    "processed_urls": len(downloaded_files)
                }
                
            except json.JSONDecodeError as e:
                return {"success": False, "error": f"解析JSON失败: {e}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}

@mcp.tool()  
async def convert_pdf_file(file_path: str, enable_ocr: bool = True) -> Dict[str, Any]:
    """
    【专用工具】将本地PDF文件转换为Markdown，支持单个文件或文件列表
    
    Args:
        file_path: PDF文件的本地路径或路径列表，可以是以空格、逗号或换行符分隔的字符串
        enable_ocr: 是否启用OCR（默认：True）

    Returns:
        dict: 转换结果信息
    """
    if not MINERU_API_KEY:
        return {"success": False, "error": "缺少API密钥，请设置环境变量MINERU_API_KEY"}
    
    # 解析文件路径输入
    if isinstance(file_path, str):
        # 处理以空格、逗号或换行符分隔的路径列表
        file_paths = parse_path_string(file_path)
    else:
        file_paths = [file_path]  # 处理单个非字符串类型路径（理论上不应该发生）
    
    logger.info(f"处理文件路径输入: {file_paths}")
    
    # 检查文件是否存在
    for path in file_paths:
        logger.info(f"检查文件: {path}")
        if not os.path.exists(path):
            logger.error(f"文件不存在: {path}")
            return {"success": False, "error": f"文件不存在: {path}"}
        else:
            logger.info(f"文件存在，大小: {os.path.getsize(path)} 字节")
        
        # 检查文件是否为PDF
        if not path.lower().endswith('.pdf'):
            logger.error(f"文件不是PDF格式: {path}")
            return {"success": False, "error": f"文件不是PDF格式: {path}"}
    
    logger.info(f"开始处理 {len(file_paths)} 个文件")
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            # 获取文件名
            file_names = [os.path.basename(path) for path in file_paths]
            
            # 获取上传链接
            files_data = []
            for i, name in enumerate(file_names):
                files_data.append({
                    "name": name,
                    "is_ocr": enable_ocr,
                    "data_id": f"file_convert_{i+1}_{int(time.time())}"
                })
            
            file_url_data = {
                "enable_formula": True,
                "language": "auto",
                "layout_model": "doclayout_yolo",
                "enable_table": True,
                "files": files_data
            }
            
            file_url_response = await client.post(
                MINERU_FILE_URLS_API,
                headers=HEADERS,
                json=file_url_data,
                timeout=60.0
            )
            
            if file_url_response.status_code != 200:
                return {"success": False, "error": f"获取上传链接失败: {file_url_response.status_code}"}
            
            # 解析结果
            file_url_result = file_url_response.json()
            
            if file_url_result.get("code") != 0 and file_url_result.get("code") != 200:
                error_msg = file_url_result.get("msg", "未知错误")
                return {"success": False, "error": f"获取上传链接失败: {error_msg}"}
            
            # 解析批次ID和文件上传URL
            batch_id = file_url_result.get("data", {}).get("batch_id", "")
            file_urls = file_url_result.get("data", {}).get("file_urls", [])
            
            if not batch_id or not file_urls or len(file_urls) != len(file_paths):
                return {"success": False, "error": "上传链接获取失败或缺少批次ID"}
            
            logger.info(f"批次ID: {batch_id}, 开始上传文件...")
            
            # 上传文件
            upload_results = []
            for i, (file_path, upload_url) in enumerate(zip(file_paths, file_urls)):
                try:
                    # 直接使用httpx.Client进行PUT请求，不设置任何请求头
                    with open(file_path, 'rb') as f:
                        file_content = f.read()
                        
                        # 直接使用PUT方法上传，不设置Content-Type
                        upload_response = await client.put(
                            upload_url,
                            content=file_content,
                            headers={},  # 不设置任何请求头
                            timeout=300.0
                        )
                    
                    # 检查上传状态
                    if upload_response.status_code != 200:
                        logger.error(f"上传文件失败: {file_names[i]} - 状态码: {upload_response.status_code}")
                        upload_results.append({"file": file_names[i], "success": False})
                    else:
                        logger.info(f"文件 {file_names[i]} 上传成功!")
                        upload_results.append({"file": file_names[i], "success": True})
                except Exception as e:
                    logger.error(f"上传文件时出错: {file_names[i]} - {e}")
                    upload_results.append({"file": file_names[i], "success": False, "error": str(e)})
            
            # 检查是否有文件上传成功
            if not any(result["success"] for result in upload_results):
                return {"success": False, "error": "所有文件上传失败", "upload_results": upload_results}
            
            logger.info("文件上传完成，开始轮询任务状态...")
            
            # 轮询任务状态
            task_status = await check_task_status(client, batch_id)
            
            if not task_status.get("success"):
                return task_status
            
            # 下载批量任务结果
            downloaded_files = await download_batch_results(client, task_status.get("extract_results", []))
            
            return {
                "success": True, 
                "downloaded_files": downloaded_files,
                "batch_id": batch_id,
                "upload_results": upload_results,
                "total_files": len(file_paths),
                "processed_files": len(downloaded_files)
            }
                
        except Exception as e:
            return {"success": False, "error": str(e)}

@mcp.prompt()
def default_prompt() -> str:
    """创建默认工具使用提示"""
    return """
PDF到Markdown转换服务提供两个工具，各有不同分工：

- convert_pdf_url：专门处理单个或多个URL链接
- convert_pdf_file：专门处理单个或多个本地文件路径

请根据输入类型选择合适的工具：
- 如果是单个或多个URL，使用convert_pdf_url
- 如果是单个或多个本地文件，使用convert_pdf_file
- 如果同时包含URL和本地文件路径，请分别调用以上两个工具处理对应的输入
"""

@mcp.prompt()
def pdf_prompt(path: str) -> str:
    """创建PDF处理提示"""
    return f"""
请将以下PDF转换为Markdown格式：

{path}

请根据输入类型选择合适的工具：
- 如果是单个或多个URL，使用convert_pdf_url
- 如果是单个或多个本地文件，使用convert_pdf_file
"""

# 定义MCP资源
@mcp.resource("status://api")
def get_api_status() -> str:
    """获取API状态信息"""
    if not MINERU_API_KEY:
        return "API状态: 未配置（缺少API密钥）"
    return f"API状态: 已配置\nAPI基础URL: {MINERU_API_BASE}\nAPI密钥: {MINERU_API_KEY[:10]}..."

@mcp.resource("help://tools")
def get_usage_help() -> str:
    """获取工具使用帮助信息"""
    return """
# PDF到Markdown转换服务

## 可用工具：

1. **convert_pdf_url** - 将PDF URL转换为Markdown，可以包含多个URL
   - 参数：
     - url: PDF文件的URL或URL列表
     - enable_ocr: 是否启用OCR（默认：True）

2. **convert_pdf_file** - 将本地PDF文件转换为Markdown，可以包含多个文件路径
   - 参数：
     - file_path: PDF文件的本地路径或路径列表
     - enable_ocr: 是否启用OCR（默认：True）

## 工具分工：

- **convert_pdf_url**: 专门处理URL链接，适用于单个或多个URL输入场景
- **convert_pdf_file**: 专门处理本地文件，适用于单个或多个文件路径输入场景

## 混合输入处理：

当同时需要处理URL和本地文件时，请分别调用convert_pdf_url和convert_pdf_file处理相应的输入部分。

## 使用示例：

```python
# 转换URL
result = await convert_pdf_url("https://example.com/document.pdf")

# 转换本地文件
result = await convert_pdf_file("C:/Documents/document.pdf")

# 混合输入处理
url_result = await convert_pdf_url("https://example.com/doc1.pdf")
file_result = await convert_pdf_file("C:/Documents/doc2.pdf")
```

## 转换结果：
成功时返回包含转换结果的字典，可能包含文件下载信息。
"""

# 运行服务器
if __name__ == "__main__":
    # 检查API密钥
    if not MINERU_API_KEY:
        logger.warning("警告: 未设置API密钥，请设置环境变量MINERU_API_KEY")
    
    # 运行MCP服务器
    mcp.run()
