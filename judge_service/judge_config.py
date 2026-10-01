"""判题服务配置加载。

数据库等配置统一从配置文件读取：
- 默认加载与本模块同目录的 ``.env``（``docker compose`` 也会自动读取该文件），
  从而保证判题数据库容器与判题服务使用同一套配置；
- 配置文件路径可通过环境变量 ``JUDGE_CONFIG_FILE`` 指定；
- 优先级：真实环境变量 > ``.env`` 配置文件 > 代码内置默认值。

支持的 ``.env`` 语法（由 python-dotenv 解析）：``KEY=VALUE`` 每行一条，
以 ``#`` 开头的行为注释，值可用单引号/双引号包裹。
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger("judge_service.config")

# 配置文件路径：默认 judge_service/.env，可用 JUDGE_CONFIG_FILE 覆盖
CONFIG_FILE = Path(
    os.environ.get("JUDGE_CONFIG_FILE", str(Path(__file__).resolve().parent / ".env"))
)

# 加载配置文件；override=False 保证已存在的真实环境变量优先级更高
load_dotenv(dotenv_path=CONFIG_FILE, override=False)


def get_str(key: str, default: str) -> str:
    """读取字符串配置，缺失或为空时返回默认值。"""
    value = os.environ.get(key)
    return default if value is None or value == "" else value


def get_int(key: str, default: int) -> int:
    """读取整型配置，缺失或非法时返回默认值。"""
    value = os.environ.get(key)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning("配置项 %s 的值 %r 不是合法的整数，回退到默认值 %s", key, value, default)
        return default
