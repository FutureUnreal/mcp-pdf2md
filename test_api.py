#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PDF到Markdown API测试脚本

使用方法:
    1. 测试批量URL API:
       python test_api.py url

    2. 测试批量文件上传API:
       python test_api.py file [文件路径1] [文件路径2] ...
       
       如果不提供文件路径，将使用脚本中预设的文件路径。
       
    3. 打印请求体:
       python test_api.py print_bodies
"""

import os
import json
import time
import asyncio
import httpx
import pprint
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional, List, Dict, Any

# 加载环境变量
load_dotenv()

# API配置
MINERU_API_BASE = os.environ.get("MINERU_API_BASE", "https://mineru.net/api/v4/extract/task")
MINERU_API_KEY = os.environ.get("MINERU_API_KEY", "")
MINERU_BATCH_API = os.environ.get("MINERU_BATCH_API", "https://mineru.net/api/v4/extract/task/batch")
MINERU_BATCH_RESULTS_API = os.environ.get("MINERU_BATCH_RESULTS_API", "https://mineru.net/api/v4/extract-results/batch")
MINERU_FILE_URLS_API = os.environ.get("MINERU_FILE_URLS_API", "https://mineru.net/api/v4/file-urls/batch")

# API认证请求头
HEADERS = {
    "Authorization": MINERU_API_KEY if MINERU_API_KEY.startswith("Bearer ") else f"Bearer {MINERU_API_KEY}", 
    "Content-Type": "application/json"
}

print(f"API密钥: {MINERU_API_KEY[:20]}...") if MINERU_API_KEY else print("警告: 未设置API密钥")

async def download_zip_file(client, zip_url, file_name, prefix="result"):
    """
    下载ZIP文件并保存到本地
    
    Args:
        client: HTTP客户端
        zip_url: ZIP文件URL
        file_name: 文件名
        prefix: 保存文件前缀
        
    Returns:
        dict: 包含文件名和保存路径的字典，失败则返回None
    """
    try:
        # 下载ZIP文件内容
        zip_response = await client.get(zip_url, follow_redirects=True, timeout=300.0)
        if zip_response.status_code == 200:
            # 保存ZIP文件
            current_time = time.strftime("%Y%m%d")
            
            # 简化文件名，去掉扩展名
            base_name = os.path.splitext(file_name)[0]
            zip_filename = f"{prefix}_{base_name}_{current_time}.zip"
            
            # 创建存放下载的目录
            download_dir = Path("./downloads")
            if not download_dir.exists():
                download_dir.mkdir(parents=True)
            
            save_path = download_dir / zip_filename
            
            with open(save_path, "wb") as f:
                f.write(zip_response.content)
            
            # 返回下载文件信息
            return {
                "file_name": file_name,
                "saved_path": str(save_path)
            }
        else:
            print(f"下载ZIP文件失败: {zip_response.status_code}")
            return None
    except Exception as e:
        print(f"获取ZIP内容时出错: {e}")
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
    
    print("\n===== 任务状态报告 =====")
    for i, result in enumerate(extract_results):
        current_status = result.get("state", "")
        file_name = result.get("file_name", "")
        
        print(f"任务 {i+1}/{len(extract_results)} - 文件: {file_name}, 状态: {current_status}")
        
        if current_status == "done":
            any_done = True
        else:
            all_done = False
    
    print("=========================\n")
    
    if all_done:
        print("所有任务已完成")
    elif any_done:
        print("部分任务已完成")
    else:
        print("没有任务完成")
    
    return all_done, any_done

async def check_task_status(client, batch_id, max_retries=60, sleep_seconds=6):
    """
    检查批量任务状态
    
    Args:
        client: HTTP客户端
        batch_id: 批次ID
        max_retries: 最大重试次数
        sleep_seconds: 每次重试间隔秒数
        
    Returns:
        dict: 包含任务状态信息的字典，失败则返回None
    """
    retry_count = 0
    
    while retry_count < max_retries:
        retry_count += 1
        print(f"查询状态 ({retry_count}/{max_retries})...")
        
        # 构建查询URL
        status_url = f"{MINERU_BATCH_RESULTS_API}/{batch_id}"
        
        try:
            # 发送请求
            status_response = await client.get(
                status_url,
                headers=HEADERS,
                timeout=300.0
            )
            
            if status_response.status_code != 200:
                print(f"查询状态失败: {status_response.status_code}")
                await asyncio.sleep(sleep_seconds)
                continue
            
            try:
                status_data = status_response.json()
            except Exception as e:
                print(f"解析JSON失败: {e}")
                await asyncio.sleep(sleep_seconds)
                continue
            
            # 检查code字段
            if status_data.get("code") != 0 and status_data.get("code") != 200:
                print(f"查询状态错误: {status_data.get('msg', '未知错误')}")
                await asyncio.sleep(sleep_seconds)
                continue
            
            # 获取任务状态
            task_data = status_data.get("data", {})
            extract_results = task_data.get("extract_result", [])
            
            # 检查是否有任务结果
            if not extract_results:
                print("未找到任务结果，继续轮询...")
                await asyncio.sleep(sleep_seconds)
                continue
            
            # 检查所有任务的状态
            all_done, any_done = print_task_status(extract_results)
            
            # 如果所有任务都已完成，返回结果
            if all_done:
                print("\n批量任务已完成")
                return {
                    "success": True,
                    "extract_results": extract_results,
                    "task_data": task_data,
                    "status_data": status_data
                }
            
            # 如果有任务还在处理中，继续轮询
            print(f"有任务仍在处理中，{sleep_seconds}秒后继续轮询...")
            await asyncio.sleep(sleep_seconds)
            
        except Exception as e:
            print(f"检查任务状态时出错: {e}")
            await asyncio.sleep(sleep_seconds)
    
    print("轮询超时，未能获取最终结果")
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
    
    print("\n准备下载任务结果...")
    
    # 从extract_results中获取下载链接
    for i, result in enumerate(extract_results):
        if result.get("state") == "done":
            try:
                # 获取文件信息
                file_name = result.get("file_name", f"file_{i+1}")
                zip_url = result.get("full_zip_url", "")
                
                if not zip_url:
                    print(f"警告: 文件 {file_name} 没有ZIP下载URL")
                    continue
                
                print(f"下载文件 {i+1}/{len(extract_results)}: {file_name}")
                
                # 下载ZIP文件
                downloaded_file = await download_zip_file(client, zip_url, file_name)
                if downloaded_file:
                    downloaded_files.append(downloaded_file)
            except Exception as e:
                print(f"获取ZIP内容时出错: {e}")
    
    return downloaded_files

async def test_batch_url_api():
    """
    测试批量URL API
    """
    print("开始测试批量URL API...")
    
    # 测试URLs
    test_urls = [
        "https://arxiv.org/pdf/1706.03762.pdf",  # Attention is All You Need
        "https://arxiv.org/pdf/1810.04805.pdf"   # BERT
    ]
    
    print(f"测试URLs: {test_urls}")
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            # 1. 创建批量任务
            print("创建批量任务...")
            
            # 准备文件列表
            files = []
            for i, url in enumerate(test_urls):
                files.append({
                    "url": url, 
                    "is_ocr": True, 
                    "data_id": f"test_batch_url_{i+1}_{int(time.time())}"
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
                print(f"请求失败: {response.status_code}")
                return {"success": False, "error": f"请求失败: {response.status_code}"}
            
            try:
                status_data = response.json()
                
                if status_data.get("code") != 0 and status_data.get("code") != 200:
                    error_msg = status_data.get("msg", "未知错误")
                    print(f"API返回错误: {error_msg}")
                    return {"success": False, "error": f"API返回错误: {error_msg}"}
                    
                # 获取批次ID
                batch_id = status_data.get("data", {}).get("batch_id", "")
                if not batch_id:
                    print("未获取到批次ID")
                    return {"success": False, "error": "未获取到批次ID"}
                    
                print(f"批次ID: {batch_id}")
                
                # 2. 轮询任务状态
                print("开始轮询任务状态...")
                task_status = await check_task_status(client, batch_id)
                
                if not task_status.get("success"):
                    return task_status
                
                # 下载批量任务结果
                downloaded_files = await download_batch_results(client, task_status.get("extract_results", []))
                
                print("测试完成!")
                return {
                    "success": True, 
                    "downloaded_files": downloaded_files,
                    "batch_id": batch_id
                }
                
            except json.JSONDecodeError as e:
                print(f"解析JSON失败: {e}")
                return {"success": False, "error": f"解析JSON失败: {e}"}
                
        except Exception as e:
            print(f"发生错误: {str(e)}")
            import traceback
            error_trace = traceback.format_exc()
            print(error_trace)
            return {"success": False, "error": str(e)}

async def test_batch_file_api():
    """
    测试批量文件上传API
    """
    print("开始测试批量文件上传API...")
    
    # 测试文件路径 - 使用原始字符串(r)前缀避免转义问题
    test_files = [
        # 真实文件路径，使用r前缀或双反斜杠避免转义问题
        r"C:\baidunetdiskdownload\机器学习\课件\04_梯度下降.pdf",
        r"C:\baidunetdiskdownload\机器学习\课件\03_线性回归.pdf"
    ]
    
    # 检查命令行参数中是否提供了文件路径
    import sys
    if len(sys.argv) > 2:
        # 使用命令行提供的文件路径
        test_files = []
        for i in range(2, len(sys.argv)):
            test_files.append(sys.argv[i])
    
    # 打印文件路径以检查是否正确
    for i, file_path in enumerate(test_files):
        print(f"文件 {i+1}: {file_path}")
        if os.path.exists(file_path):
            print(f" - 文件存在，大小: {os.path.getsize(file_path)} 字节")
        else:
            print(f" - 文件不存在!")
    
    # 检查所有文件是否存在
    missing_files = []
    for file_path in test_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    if missing_files:
        print(f"以下文件不存在: {missing_files}")
        return {"success": False, "error": f"部分文件不存在: {missing_files}"}
    
    print(f"测试文件: {test_files}")
    
    # 1. 获取上传URL
    print("获取上传URL...")
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            file_names = [os.path.basename(path) for path in test_files]
            
            # 获取上传链接 - 按照API文档格式构建请求
            files_data = []
            for i, file_name in enumerate(file_names):
                files_data.append({
                    "name": file_name,
                    "is_ocr": True,
                    "data_id": f"test_batch_file_{i+1}_{int(time.time())}"
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
                print(f"获取上传链接失败: {file_url_response.status_code}")
                return {"success": False, "error": f"获取上传链接失败: {file_url_response.status_code}"}
            
            # 解析结果
            file_url_result = file_url_response.json()
            
            if file_url_result.get("code") != 0 and file_url_result.get("code") != 200:
                print(f"获取上传链接失败: {file_url_result.get('msg', '未知错误')}")
                return {"success": False, "error": f"获取上传链接失败: {file_url_result.get('msg', '未知错误')}"}
            
            # 解析批次ID和文件上传URL
            batch_id = file_url_result.get("data", {}).get("batch_id", "")
            file_urls = file_url_result.get("data", {}).get("file_urls", [])
            
            if not batch_id or not file_urls or len(file_urls) != len(test_files):
                print(f"上传链接数量不匹配或缺少批次ID: 文件数={len(test_files)}, 链接数={len(file_urls)}")
                return {"success": False, "error": "上传链接数量不匹配或缺少批次ID"}
            
            print(f"批次ID: {batch_id}, 开始上传 {len(test_files)} 个文件...")
            
            # 开始上传文件
            for i, (file_path, file_url) in enumerate(zip(test_files, file_urls)):
                try:
                    print(f"上传文件 {i+1}/{len(test_files)}: {os.path.basename(file_path)}")
                    
                    # 直接使用httpx.Client进行PUT请求，不设置任何请求头
                    with open(file_path, 'rb') as f:
                        file_content = f.read()
                        
                        # 直接使用PUT方法上传，不设置Content-Type
                        upload_response = await client.put(
                            file_url,
                            content=file_content,
                            headers={},  # 不设置任何请求头
                            timeout=300.0
                        )
                    
                    # 检查上传状态
                    if upload_response.status_code != 200:
                        print(f"上传文件失败: {upload_response.status_code}")
                        return {"success": False, "error": f"上传文件失败: {upload_response.status_code}"}
                    
                    print(f"文件 {os.path.basename(file_path)} 上传成功!")
                except Exception as e:
                    print(f"上传文件 {file_path} 时出错: {e}")
                    return {"success": False, "error": f"上传文件 {file_path} 时出错: {e}"}
            
            print("\n所有文件上传完成，开始轮询任务状态...")
            
            # 打印状态信息
            print(f"批次ID: {batch_id}")
            
            # 4. 轮询任务状态
            task_status = await check_task_status(client, batch_id)
            
            if not task_status.get("success"):
                return task_status
            
            # 下载批量任务结果
            downloaded_files = await download_batch_results(client, task_status.get("extract_results", []))
            
            print("测试完成!")
            return {
                "success": True, 
                "downloaded_files": downloaded_files,
                "batch_id": batch_id
            }
                
        except Exception as e:
            print(f"发生错误: {str(e)}")
            import traceback
            error_trace = traceback.format_exc()
            print(error_trace)
            return {"success": False, "error": str(e)}

def print_request_bodies():
    """
    打印批量URL和文件请求的请求体
    """
    # 测试URLs
    test_urls = [
        "https://arxiv.org/pdf/1706.03762.pdf",  # Attention is All You Need
        "https://arxiv.org/pdf/1810.04805.pdf"   # BERT
    ]
    
    # 准备URL批量请求体
    url_files = []
    for i, url in enumerate(test_urls):
        url_files.append({
            "url": url, 
            "is_ocr": True, 
            "data_id": f"test_batch_url_{i+1}_{int(time.time())}"
        })
    
    url_batch_data = {
        "enable_formula": True,
        "language": "auto",
        "layout_model": "doclayout_yolo",
        "enable_table": True,
        "files": url_files
    }
    
    # 打印URL批量请求体
    print("\n===== 批量URL请求体 =====")
    print(json.dumps(url_batch_data, indent=2, ensure_ascii=False))
    print("========================\n")
    
    # 测试文件
    test_files = [
        "sample1.pdf",
        "sample2.pdf"
    ]
    
    # 准备文件批量请求体
    file_data = []
    for i, file_name in enumerate(test_files):
        file_data.append({
            "name": file_name,
            "is_ocr": True,
            "data_id": f"test_batch_file_{i+1}_{int(time.time())}"
        })
    
    file_batch_data = {
        "enable_formula": True,
        "language": "auto",
        "layout_model": "doclayout_yolo",
        "enable_table": True,
        "files": file_data
    }
    
    # 打印文件批量请求体
    print("\n===== 批量文件请求体 =====")
    print(json.dumps(file_batch_data, indent=2, ensure_ascii=False))
    print("=========================\n")

async def main():
    """
    主函数
    """
    if not MINERU_API_KEY:
        print("错误: 缺少API密钥，请设置环境变量MINERU_API_KEY")
        return
    
    print("=== 开始API测试 ===")
    
    # 根据命令行参数选择要运行的测试
    import sys
    if len(sys.argv) > 1:
        test_type = sys.argv[1].lower()
        
        if test_type == "url" or test_type == "batch_url":
            print("\n=== 测试批量URL API ===")
            batch_url_result = await test_batch_url_api()
            print(f"批量URL测试结果: {batch_url_result['success']}")
        
        elif test_type == "file" or test_type == "batch_file":
            print("\n=== 测试批量文件上传API ===")
            batch_file_result = await test_batch_file_api()
            print(f"批量文件测试结果: {batch_file_result['success']}")
            
        elif test_type == "print_bodies":
            print_request_bodies()
            
        else:
            print(f"未知的测试类型: {test_type}")
            print("可用的测试类型: url, file, print_bodies")
    else:
        # 默认运行所有测试
        print("\n=== 测试批量URL API ===")
        batch_url_result = await test_batch_url_api()
        print(f"批量URL测试结果: {batch_url_result['success']}")
        
        # 取消测试批量文件API的调用，因为需要实际的文件路径
        # print("\n=== 测试批量文件上传API ===")
        # batch_file_result = await test_batch_file_api()
        # print(f"批量文件测试结果: {batch_file_result['success']}")
    
    print("\n=== API测试完成 ===")

if __name__ == "__main__":
    # 如果直接运行此脚本，打印请求体
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--print-requests":
        print_request_bodies()
    else:
        # 检查API密钥
        if not MINERU_API_KEY:
            print("错误: 缺少API密钥，请设置环境变量MINERU_API_KEY")
            sys.exit(1)
        
        # 运行主函数
        asyncio.run(main())
