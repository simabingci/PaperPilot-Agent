"""Interactive local configuration: never print keys or invoke the model."""

import getpass
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import set_key

root = Path(__file__).resolve().parent.parent
target = root / ".env"
base_url = input("OpenAI 兼容 Base URL（北京百炼回车使用存量域名）: ").strip()
base_url = base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
parsed = urlsplit(base_url)
if parsed.scheme not in {"http", "https"} or not parsed.netloc:
    raise SystemExit("Base URL 格式无效")
model = input("模型 ID（填写控制台有可用额度的模型 Code）: ").strip()
key = getpass.getpass("API Key（隐藏输入，不会显示或写入日志）: ").strip()
if not model or not key:
    raise SystemExit("模型和密钥不能为空，未写入配置")
target.touch(mode=0o600, exist_ok=True)
if os.name != "nt":
    target.chmod(0o600)
for name, value in {"PAPERPILOT_MODE": "live", "OPENAI_BASE_URL": base_url,
                    "OPENAI_MODEL": model, "OPENAI_API_KEY": key}.items():
    set_key(str(target), name, value)
print("已保存私有 .env，尚未调用模型。重启 API 后，每次任务仍需确认。")
