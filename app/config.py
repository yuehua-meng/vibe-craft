import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env', encoding='utf-8-sig')
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)
API_KEY = os.getenv('ARK_API_KEY', '')
BASE_URL = os.getenv('ARK_BASE_URL', 'https://ark.cn-beijing.volces.com/api/v3').rstrip('/')
TEXT_MODEL = os.getenv('ARK_TEXT_MODEL', 'doubao-seed-2-0-lite-260428')
IMAGE_MODEL = os.getenv('ARK_IMAGE_MODEL', 'doubao-seedream-4-0-20260415')

# 网关模式：模型调用经由 agent-gateway，凭据换成项目 Key，模型名换成网关的逻辑别名。
# 关闭（GATEWAY_MODE 未设置）时行为与直连方舟完全一致，可随时回退。
GATEWAY_MODE = os.getenv('GATEWAY_MODE', '').strip().lower() in {'1', 'true', 'yes', 'on'}
GATEWAY_BASE_URL = os.getenv('GATEWAY_BASE_URL', 'http://gateway:8020/v1').rstrip('/')
GATEWAY_PROJECT_KEY = os.getenv('GATEWAY_PROJECT_KEY', '')
GATEWAY_TEXT_MODEL = os.getenv('GATEWAY_TEXT_MODEL', 'text.default')
GATEWAY_VISION_MODEL = os.getenv('GATEWAY_VISION_MODEL', 'text.vision')
GATEWAY_IMAGE_MODEL = os.getenv('GATEWAY_IMAGE_MODEL', 'image.default')
# 必须大于网关路由的 deadline（生图 260 秒），否则应用先超时而网关仍在计费。
GATEWAY_CHAT_TIMEOUT = int(os.getenv('GATEWAY_CHAT_TIMEOUT', '210'))
GATEWAY_IMAGE_TIMEOUT = int(os.getenv('GATEWAY_IMAGE_TIMEOUT', '300'))


def provider_ready():
    """当前模式下是否具备调用真实模型的条件。"""
    return bool(GATEWAY_PROJECT_KEY) if GATEWAY_MODE else bool(API_KEY)

PLATFORMS = {
    'xiaohongshu': {'name': '小红书', 'color': '#e64b65', 'mark': '红', 'size': [1536, 2048],
        'style': '中文；生活场景切入，标题简洁；正文约400字，短段落，少量emoji；不伪装真实使用体验；结尾3个相关话题标签。'},
    'wechat': {'name': '微信公众号', 'color': '#21a779', 'mark': '微', 'size': [2048, 1152],
        'style': '中文；完整叙事，清晰导语、3个小标题和结尾；正文约800字；理性自然，有依据地解释卖点。'},
    'twitter': {'name': 'X / Twitter', 'color': '#252a34', 'mark': '𝕏', 'size': [2048, 1152],
        'style': '中文；生成3条简洁串帖，每条不超过100字，用空行分隔；每条聚焦一个信息；不捏造体验或数据。'},
}
