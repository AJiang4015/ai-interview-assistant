import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# 日志落盘目录：<项目根>/logs（已在 .gitignore 忽略）
LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_FILE = LOG_DIR / "app.log"
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # 控制台输出（APP 前台可见）
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        logger.addHandler(console)

        # 滚动文件日志：单文件 10MB 后轮转，保留 5 个备份，避免日志无限增长
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                str(LOG_FILE), maxBytes=LOG_MAX_BYTES,
                backupCount=LOG_BACKUP_COUNT, encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception:
            # 文件写入不可用时仅保留控制台，不阻塞服务启动
            pass

        logger.setLevel(logging.INFO)
    return logger