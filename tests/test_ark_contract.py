import asyncio
import base64
import io

from PIL import Image

from app.media import make_sample
from app.providers import ArkProvider
from app.repository import SqliteRepository


def test_ark_image_receives_summary_and_original_images(tmp_path):
    repo = SqliteRepository(tmp_path)
    asset = make_sample(repo)
    provider = ArkProvider(repo)
    calls = []
    image = io.BytesIO()
    Image.new('RGB', (64,64)).save(image, 'PNG')
    async def fake_request(endpoint, body, timeout=150, headers=None):
        calls.append((endpoint, body))
        return {'data':[{'b64_json':base64.b64encode(image.getvalue()).decode()}]}
    provider.request = fake_request
    result = asyncio.run(provider.image({'platform':'wechat','asset_ids':[asset['id']],
        'summary':{'summary':'已审核文章摘要','image_prompt':'自然光背景'}}))
    assert result == image.getvalue()
    endpoint, body = calls[0]
    assert endpoint == '/images/generations'
    assert '已审核文章摘要' in body['prompt']
    assert '自然光背景' in body['prompt']
    assert body['image'][0].startswith('data:image/jpeg;base64,')
    assert body['response_format'] == 'b64_json'

def test_ark_topic_input_includes_original_images(tmp_path):
    repo = SqliteRepository(tmp_path)
    asset = make_sample(repo)
    provider = ArkProvider(repo)
    async def fake_request(endpoint, body, timeout=150, headers=None):
        assert endpoint == '/chat/completions'
        content = body['messages'][1]['content']
        assert content[1]['type'] == 'image_url'
        assert body['response_format'] == {'type':'json_object'}
        return {'choices':[{'message':{'content':'{"topics":[{"id":"a","title":"标题一","angle":"角度","outline":"概要"},{"id":"b","title":"标题二","angle":"角度","outline":"概要"},{"id":"c","title":"标题三","angle":"角度","outline":"概要"}]}'}}]}
    provider.request = fake_request
    result = asyncio.run(provider.topics({'platform':'xiaohongshu','asset_ids':[asset['id']],
        'description':'商品描述','instruction':'创作要求'}))
    assert [item['id'] for item in result] == ['1','2','3']
