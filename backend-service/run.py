"""
后端服务启动脚本
基于 main.py 中的 FastAPI 应用，提供更完善的启动配置
不修改 main.py 内容
"""

import uvicorn
import argparse
import sys
import os


def parse_args():
    parser = argparse.ArgumentParser(description="工业AI算法平台后端服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="监听端口 (默认: 8080)")
    parser.add_argument("--reload", action="store_true", help="启用热重载 (开发模式)")
    parser.add_argument("--workers", type=int, default=1, help="工作进程数 (默认: 1)")
    parser.add_argument("--log-level", default="info",
                        choices=["critical", "error", "warning", "info", "debug", "trace"],
                        help="日志级别 (默认: info)")
    return parser.parse_args()


def main():
    args = parse_args()

    print(f"启动工业AI算法平台后端服务")
    print(f"  地址: http://{args.host}:{args.port}")
    print(f"  文档: http://{args.host}:{args.port}/docs")
    print(f"  热重载: {'启用' if args.reload else '禁用'}")
    print(f"  日志级别: {args.log_level}")
    print()

    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers if not args.reload else 1,  # 热重载模式下只能单进程
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
