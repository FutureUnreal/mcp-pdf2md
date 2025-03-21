from .server import mcp

def main():
    """PDF to Markdown Conversion Service - Provides MCP service for converting PDF files to Markdown"""
    import os
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="PDF to Markdown Conversion Service")
    parser.add_argument("--output-dir", default="./downloads", help="Specify output directory path, default is ./downloads")
    args = parser.parse_args()
    
    # Set output directory
    from .server import set_output_dir
    set_output_dir(args.output_dir)
    
    # Check API key
    from .server import MINERU_API_KEY, logger
    if not MINERU_API_KEY:
        logger.warning("Warning: API key not set, please set the MINERU_API_KEY environment variable")
    
    # Run MCP server
    mcp.run()

__all__ = ['main']