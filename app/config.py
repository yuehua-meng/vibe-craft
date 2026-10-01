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

PLATFORMS = {
    'xiaohongshu': {'name': '小红书', 'color': '#e64b65', 'mark': '红', 'size': [1536, 2048],
        'style': '中文；生活场景切入，标题简洁；正文约400字，短段落，少量emoji；不伪装真实使用体验；结尾3个相关话题标签。'},
    'wechat': {'name': '微信公众号', 'color': '#21a779', 'mark': '微', 'size': [2048, 1152],
        'style': '中文；完整叙事，清晰导语、3个小标题和结尾；正文约800字；理性自然，有依据地解释卖点。'},
    'twitter': {'name': 'X / Twitter', 'color': '#252a34', 'mark': '𝕏', 'size': [2048, 1152],
        'style': '中文；生成3条简洁串帖，每条不超过100字，用空行分隔；每条聚焦一个信息；不捏造体验或数据。'},
}
