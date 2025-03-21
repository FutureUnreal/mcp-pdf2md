from .server import mcp

def main():
    """PDF到Markdown转换服务 - 提供PDF文件转换为Markdown的MCP服务"""
    import os
    import argparse
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="PDF到Markdown转换服务")
    parser.add_argument("--output-dir", default="./downloads", help="指定输出目录路径，默认为./downloads")
    args = parser.parse_args()
    
    # 设置输出目录
    from .server import set_output_dir
    set_output_dir(args.output_dir)
    
    # 检查API密钥
    from .server import MINERU_API_KEY, logger
    if not MINERU_API_KEY:
        logger.warning("警告: 未设置API密钥，请设置环境变量MINERU_API_KEY")
    
    # 运行MCP服务器
    mcp.run()

__all__ = ['main']