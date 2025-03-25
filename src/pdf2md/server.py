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

# Set up logging - disable all log output
logging.basicConfig(
    level=logging.CRITICAL,  # Only record critical errors
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[]  # Remove all handlers, no log output
)
logger = logging.getLogger("pdf2md")
logger.disabled = True  # Completely disable logging

# Load environment variables
load_dotenv()

# API configuration
MINERU_API_BASE = os.environ.get("MINERU_API_BASE", "https://mineru.net/api/v4/extract/task")
MINERU_API_KEY = os.environ.get("MINERU_API_KEY", "")
MINERU_BATCH_API = os.environ.get("MINERU_BATCH_API", "https://mineru.net/api/v4/extract/task/batch")
MINERU_BATCH_RESULTS_API = os.environ.get("MINERU_BATCH_RESULTS_API", "https://mineru.net/api/v4/extract-results/batch")
MINERU_FILE_URLS_API = os.environ.get("MINERU_FILE_URLS_API", "https://mineru.net/api/v4/file-urls/batch")

# Global variables
OUTPUT_DIR = "./downloads"

# API authentication headers
HEADERS = {
    "Authorization": MINERU_API_KEY if MINERU_API_KEY.startswith("Bearer ") else f"Bearer {MINERU_API_KEY}", 
    "Content-Type": "application/json"
}

def set_output_dir(output_dir: str):
    """Set the output directory path"""
    global OUTPUT_DIR
    # Normalize path to handle Unicode characters properly
    OUTPUT_DIR = os.path.normpath(output_dir)

def print_task_status(extract_results):
    """
    Print task status and check if all tasks are completed
    
    Args:
        extract_results: List of task results
        
    Returns:
        tuple: (all tasks completed, any task completed)
    """
    all_done = True
    any_done = False
    
    for i, result in enumerate(extract_results):
        current_status = result.get("state", "")
        file_name = result.get("file_name", "")
        
        status_icon = "✅" if current_status == "done" else "⏳"
        
        if current_status == "done":
            any_done = True
        else:
            all_done = False
    
    return all_done, any_done

async def check_task_status(client, batch_id, max_retries=60, sleep_seconds=5):
    """
    Check batch task status
    
    Args:
        client: HTTP client
        batch_id: Batch ID
        max_retries: Maximum number of retries
        sleep_seconds: Seconds between retries
        
    Returns:
        dict: Dictionary containing task status information, or error message if failed
    """
    retry_count = 0
    
    while retry_count < max_retries:
        retry_count += 1
        
        try:
            status_response = await client.get(
                f"{MINERU_BATCH_RESULTS_API}/{batch_id}",
                headers=HEADERS,
                timeout=60.0  
            )
            
            if status_response.status_code != 200:
                retry_count += 1
                if retry_count < max_retries:
                    await asyncio.sleep(sleep_seconds)
                continue
            
            try:
                status_data = status_response.json()
            except Exception as e:
                retry_count += 1
                if retry_count < max_retries:
                    await asyncio.sleep(sleep_seconds)
                continue
            
            task_data = status_data.get("data", {})
            extract_results = task_data.get("extract_result", [])
            
            all_done, any_done = print_task_status(extract_results)
            
            if all_done:
                return {
                    "success": True,
                    "extract_results": extract_results,
                    "task_data": task_data,
                    "status_data": status_data
                }
            
            await asyncio.sleep(sleep_seconds)
            
        except Exception as e:
            retry_count += 1
            if retry_count < max_retries:
                await asyncio.sleep(sleep_seconds)
    
    return {
        "success": False,
        "error": "Polling timeout, unable to get final results"
    }

async def download_batch_results(client, extract_results):
    """
    Download batch task results
    
    Args:
        client: HTTP client
        extract_results: List of task results
        
    Returns:
        list: List of downloaded file information
    """
    downloaded_files = []
    
    for i, result in enumerate(extract_results):
        if result.get("state") == "done":
            try:
                file_name = result.get("file_name", f"file_{i+1}")
                zip_url = result.get("full_zip_url", "")
                
                if not zip_url:
                    continue
                
                downloaded_file = await download_zip_file(client, zip_url, file_name)
                if downloaded_file:
                    downloaded_files.append(downloaded_file)
            except Exception as e:
                pass
    
    return downloaded_files

async def download_zip_file(client, zip_url, file_name, prefix="md", max_retries=3):
    """
    Download and save ZIP file, then automatically unzip
    
    Args:
        client: HTTP client
        zip_url: ZIP file URL
        file_name: File name
        prefix: File prefix
        max_retries: Maximum number of retries
        
    Returns:
        dict: Dictionary containing file name and unzip directory, or None if failed
    """
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            zip_response = await client.get(zip_url, follow_redirects=True, timeout=120.0)
            
            if zip_response.status_code == 200:
                current_date = time.strftime("%Y%m%d")
                
                base_name = os.path.splitext(file_name)[0]
                # Only remove control characters and chars that are invalid in filenames
                safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', base_name).strip()
                # Replace spaces with underscores
                safe_name = re.sub(r'\s+', '_', safe_name)
                
                if safe_name.isdigit() or re.match(r'^\d+\.\d+$', safe_name):
                    safe_name = f"paper_{safe_name}"
                    
                zip_filename = f"{prefix}_{safe_name}_{current_date}.zip"
                
                download_dir = Path(OUTPUT_DIR)
                if not download_dir.exists():
                    try:
                        download_dir.mkdir(parents=True, exist_ok=True)
                    except Exception as e:
                        print(f"Error creating directory: {e}")
                        return None
                
                save_path = download_dir / zip_filename
                
                with open(save_path, "wb") as f:
                    f.write(zip_response.content)
                
                extract_dir = download_dir / safe_name
                if not extract_dir.exists():
                    extract_dir.mkdir(parents=True)
                
                import zipfile
                try:
                    with zipfile.ZipFile(save_path, 'r') as zip_ref:
                        zip_ref.extractall(extract_dir)
                    os.remove(save_path)
                    
                    return {
                        "file_name": file_name,
                        "extract_dir": str(extract_dir)
                    }
                except Exception as e:
                    pass
            else:
                retry_count += 1
                if retry_count < max_retries:
                    await asyncio.sleep(2)
                continue
        except Exception as e:
            retry_count += 1
            if retry_count < max_retries:
                await asyncio.sleep(2)
            continue
    
    return None

def parse_url_string(url_string):
    """
    Parse URL string separated by spaces, commas, or newlines
    
    Args:
        url_string: URL string
        
    Returns:
        list: List of URLs
    """
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
    Parse file path string separated by spaces, commas, or newlines
    
    Args:
        path_string: File path string
        
    Returns:
        list: List of file paths
    """
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
    
    cleaned_paths = []
    for path in paths:
        if (path.startswith('"') and path.endswith('"')) or \
           (path.startswith("'") and path.endswith("'")):
            cleaned_paths.append(path[1:-1])
        else:
            cleaned_paths.append(path)
    
    return cleaned_paths

# Create MCP server
mcp = FastMCP("PDF to Markdown Conversion Service")

@mcp.tool()  
async def convert_pdf_url(url: str, enable_ocr: bool = True) -> Dict[str, Any]:
    """
    Convert PDF URL to Markdown, supports single URL or URL list
    
    Args:
        url: PDF file URL or URL list, can be separated by spaces, commas, or newlines
        enable_ocr: Whether to enable OCR (default: True)

    Returns:
        dict: Conversion result information
    """
    if not MINERU_API_KEY:
        return {"success": False, "error": "Missing API key, please set environment variable MINERU_API_KEY"}
    
    if isinstance(url, str):
        urls = parse_url_string(url)
    else:
        urls = [url]  
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
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
                return {"success": False, "error": f"Request failed: {response.status_code}"}
            
            try:
                status_data = response.json()
                
                if status_data.get("code") != 0 and status_data.get("code") != 200:
                    error_msg = status_data.get("msg", "Unknown error")
                    return {"success": False, "error": f"API returned error: {error_msg}"}
                    
                batch_id = status_data.get("data", {}).get("batch_id", "")
                if not batch_id:
                    return {"success": False, "error": "Failed to get batch ID"}
                
                task_status = await check_task_status(client, batch_id)
                
                if not task_status.get("success"):
                    return task_status
                
                downloaded_files = await download_batch_results(client, task_status.get("extract_results", []))
                
                return {
                    "success": True, 
                    "downloaded_files": downloaded_files,
                    "batch_id": batch_id,
                    "total_urls": len(urls),
                    "processed_urls": len(downloaded_files)
                }
                
            except json.JSONDecodeError as e:
                return {"success": False, "error": f"Failed to parse JSON: {e}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}

@mcp.tool()  
async def convert_pdf_file(file_path: str, enable_ocr: bool = True) -> Dict[str, Any]:
    """
    Convert local PDF file to Markdown, supports single file or file list
    
    Args:
        file_path: PDF file local path or path list, can be separated by spaces, commas, or newlines
        enable_ocr: Whether to enable OCR (default: True)

    Returns:
        dict: Conversion result information
    """
    if not MINERU_API_KEY:
        return {"success": False, "error": "Missing API key, please set environment variable MINERU_API_KEY"}
    
    if isinstance(file_path, str):
        file_paths = parse_path_string(file_path)
    else:
        file_paths = [file_path]  
    
    for path in file_paths:
        if not os.path.exists(path):
            return {"success": False, "error": f"File does not exist: {path}"}
        else:
            if not path.lower().endswith('.pdf'):
                return {"success": False, "error": f"File is not in PDF format: {path}"}
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            file_names = [os.path.basename(path) for path in file_paths]
            
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
                return {"success": False, "error": f"Failed to get upload link: {file_url_response.status_code}"}
            
            file_url_result = file_url_response.json()
            
            if file_url_result.get("code") != 0 and file_url_result.get("code") != 200:
                error_msg = file_url_result.get("msg", "Unknown error")
                return {"success": False, "error": f"Failed to get upload link: {error_msg}"}
            
            batch_id = file_url_result.get("data", {}).get("batch_id", "")
            file_urls = file_url_result.get("data", {}).get("file_urls", [])
            
            if not batch_id or not file_urls or len(file_urls) != len(file_paths):
                return {"success": False, "error": "Failed to get upload link or batch ID"}
            
            upload_results = []
            for i, (file_path, upload_url) in enumerate(zip(file_paths, file_urls)):
                try:
                    with open(file_path, 'rb') as f:
                        file_content = f.read()
                        
                        upload_response = await client.put(
                            upload_url,
                            content=file_content,
                            headers={},  
                            timeout=300.0
                        )
                    
                    if upload_response.status_code != 200:
                        upload_results.append({"file": file_names[i], "success": False})
                    else:
                        upload_results.append({"file": file_names[i], "success": True})
                except Exception as e:
                    upload_results.append({"file": file_names[i], "success": False, "error": str(e)})
            
            if not any(result["success"] for result in upload_results):
                return {"success": False, "error": "All files failed to upload", "upload_results": upload_results}
            
            task_status = await check_task_status(client, batch_id)
            
            if not task_status.get("success"):
                return task_status
            
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
    """Create default tool usage prompt"""
    return """
PDF to Markdown Conversion Service provides two tools, each with different functions:

- convert_pdf_url: Specifically designed for handling single or multiple URL links
- convert_pdf_file: Specifically designed for handling single or multiple local file paths

Please choose the appropriate tool based on the input type:
- If it's a single or multiple URL, use convert_pdf_url
- If it's a single or multiple local file, use convert_pdf_file
- If it's a mix of URL and local file, please call the above two tools separately to handle the corresponding input

The converted Markdown files will be saved in the specified output directory, and the temporary downloaded ZIP files will be automatically deleted after unzipping to save space.
"""

@mcp.prompt()
def pdf_prompt(path: str) -> str:
    """Create PDF processing prompt"""
    return f"""
Please convert the following PDF to Markdown format:

{path}

Please choose the appropriate tool based on the input type:
- If it's a single or multiple URL, use convert_pdf_url
- If it's a single or multiple local file, use convert_pdf_file

The converted Markdown files will be saved in the specified output directory, and the temporary downloaded ZIP files will be automatically deleted after unzipping to save space.
"""

@mcp.resource("status://api")
def get_api_status() -> str:
    """Get API status information"""
    if not MINERU_API_KEY:
        return "API status: Not configured (missing API key)"
    return f"API status: Configured\nAPI base URL: {MINERU_API_BASE}\nAPI key: {MINERU_API_KEY[:10]}..."

@mcp.resource("help://usage")
def get_usage_help() -> str:
    """Get tool usage help information"""
    return """
# PDF to Markdown Conversion Service

## Available tools:

1. **convert_pdf_url** - Convert PDF URL to Markdown, supports single or multiple URLs
   - Parameters:
     - url: PDF file URL or URL list, can be separated by spaces, commas, or newlines
     - enable_ocr: Whether to enable OCR (default: True)

2. **convert_pdf_file** - Convert local PDF file to Markdown, supports single or multiple file paths
   - Parameters:
     - file_path: PDF file local path or path list, can be separated by spaces, commas, or newlines
     - enable_ocr: Whether to enable OCR (default: True)

## Tool functions:

- **convert_pdf_url**: Specifically designed for handling URL links, suitable for single or multiple URL inputs
- **convert_pdf_file**: Specifically designed for handling local files, suitable for single or multiple file path inputs

## Mixed input handling:

When handling both URL and local file inputs, please call the above two tools separately to handle the corresponding input parts.

## Usage examples:

```python
# Convert single URL
result = await convert_pdf_url("https://example.com/document.pdf")

# Convert multiple URLs (batch processing)
result = await convert_pdf_url('''
https://example.com/document1.pdf
https://example.com/document2.pdf
https://example.com/document3.pdf
''')

# Convert multiple URLs with comma separation
result = await convert_pdf_url("https://example.com/doc1.pdf, https://example.com/doc2.pdf")

# Convert single local file
result = await convert_pdf_file("C:/Documents/document.pdf")

# Convert multiple local files (batch processing)
result = await convert_pdf_file('''
C:/Documents/document1.pdf
C:/Documents/document2.pdf
C:/Documents/document3.pdf
''')

# Mixed input handling (URLs and local files)
url_result = await convert_pdf_url('''
https://example.com/doc1.pdf
https://example.com/doc2.pdf
''')
file_result = await convert_pdf_file('''
C:/Documents/doc1.pdf
C:/Documents/doc2.pdf
''')
```

## Conversion results:
Successful conversion returns a dictionary containing conversion result information, and the converted Markdown files will be saved in the specified output directory, with temporary downloaded ZIP files automatically deleted after unzipping to save space.
"""

if __name__ == "__main__":
    if not MINERU_API_KEY:
        print("Warning: API key not set, please set environment variable MINERU_API_KEY")
    
    mcp.run()
