from .server import serve


def main():
    """PDF到Markdown转换服务 - 提供PDF文件转换为Markdown的MCP服务"""
    import argparse
    import asyncio
    import os
    from dotenv import load_dotenv
    
    # 加载环境变量
    load_dotenv()
    
    parser = argparse.ArgumentParser(
        description="提供PDF文件转换为Markdown的MCP服务"
    )
    parser.add_argument("--api-key", type=str, help="Mineru API密钥")
    
    args = parser.parse_args()
    
    # 如果命令行提供了API密钥，则使用它
    if args.api_key:
        os.environ["MINERU_API_KEY"] = args.api_key
    
    asyncio.run(serve())


if __name__ == "__main__":
    main()
