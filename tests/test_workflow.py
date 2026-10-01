import io
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.providers import ProviderError


@pytest.fixture
def client(tmp_path):
    application = create_app(tmp_path)
    with TestClient(application) as session:
        yield session

def create(client, platforms=None):
    asset = client.get('/api/config').json()['sample_asset']['id']
    response = client.post('/api/tasks', json={'name': '随行杯', 'description': '浅绿色杯身，深绿色杯盖。',
        'instruction': '不要编造参数', 'asset_ids': [asset], 'platforms': platforms or ['xiaohongshu'], 'mode': 'mock'})
    assert response.status_code == 201, response.text
    return response.json()['id']

def wait(client, task_id, platform='xiaohongshu', status='waiting'):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        task = client.get(f'/api/tasks/{task_id}').json()
        branch = task['branches'][platform]
        if branch['status'] == status:
            return branch
        if branch['status'] == 'error' and status != 'error':
            pytest.fail(str(branch['error']))
        time.sleep(.025)
    pytest.fail(f'Timed out: {branch}')

def answer(client, task_id, branch, action='approve', **extra):
    payload = {'interrupt_id': branch['interrupt']['id'], 'version': branch['interrupt']['version'],
               'action': action, **extra}
    return client.post(f"/api/tasks/{task_id}/{branch['platform']}/review", json=payload)

def test_full_three_platform_flow_and_human_edits(client):
    task_id = create(client, ['xiaohongshu', 'wechat', 'twitter'])
    for platform in ['xiaohongshu', 'wechat', 'twitter']:
        branch = wait(client, task_id, platform)
        assert branch['interrupt']['stage'] == 'topic'
        assert not branch['data'].get('image')
        assert answer(client, task_id, branch, topic_id='2').status_code == 202
        branch = wait(client, task_id, platform)
        assert branch['interrupt']['stage'] == 'article'
        assert not branch['data'].get('summary')
        text = f'人工最终审核内容：{platform}\n\n## 产品信息\n只描述原图中可确认的外观。'
        assert answer(client, task_id, branch, article=text).status_code == 202
        branch = wait(client, task_id, platform, 'completed')
        assert branch['data']['approved_article'] == text
        assert '人工最终审核内容' in branch['data']['summary']['summary']
        assert client.get(branch['data']['image']['url']).status_code == 200
        bundle = client.get(branch['data']['output']['zip_url'])
        assert bundle.status_code == 200
        with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
            assert archive.read('article.txt').decode() == text
            assert 'data:image/jpeg;base64,' in archive.read('article.html').decode()
            assert len(archive.read('cover.jpg')) > 1000
    assert client.get(f'/api/tasks/{task_id}').json()['status'] == 'completed'

def test_revise_topics_article_and_retopic(client):
    task_id = create(client)
    branch = wait(client, task_id)
    assert answer(client, task_id, branch, 'revise', feedback='聚焦通勤').status_code == 202
    branch = wait(client, task_id)
    assert branch['interrupt']['version'] == 2
    assert '聚焦通勤' in branch['interrupt']['topics'][0]['outline']
    answer(client, task_id, branch, topic_id='1')
    branch = wait(client, task_id)
    assert answer(client, task_id, branch, 'revise', feedback='语气更简洁', article='保留人工草稿').status_code == 202
    branch = wait(client, task_id)
    assert branch['interrupt']['version'] == 2
    assert '语气更简洁' in branch['interrupt']['article']
    assert not branch['data'].get('image')
    assert answer(client, task_id, branch, 'retopic', feedback='改成办公室场景').status_code == 202
    branch = wait(client, task_id)
    assert branch['interrupt']['stage'] == 'topic'
    assert not branch['data']['approved_article']
    assert not branch['data']['output']

def test_stale_duplicate_and_invalid_review(client):
    task_id = create(client)
    branch = wait(client, task_id)
    assert answer(client, task_id, branch, topic_id='missing').status_code == 400
    stale = {'interrupt_id': branch['interrupt']['id'], 'version': 999, 'action':'approve','topic_id':'1'}
    assert client.post(f'/api/tasks/{task_id}/xiaohongshu/review', json=stale).status_code == 409
    assert answer(client, task_id, branch, topic_id='1').status_code == 202
    assert answer(client, task_id, branch, topic_id='1').status_code == 409
    article = wait(client, task_id)
    assert answer(client, task_id, article, article='  ').status_code == 400
    assert answer(client, task_id, article, 'revise', feedback='').status_code == 400

def test_error_retry_does_not_repeat_approved_nodes(client):
    provider = client.app.state.workflow.providers['mock']
    original = provider.image
    calls = {'image': 0, 'summary': 0}
    original_summary = provider.summary
    async def summary(state):
        calls['summary'] += 1
        return await original_summary(state)
    async def flaky(state):
        calls['image'] += 1
        if calls['image'] == 1:
            raise ProviderError('模拟供应商临时不可用')
        return await original(state)
    provider.image = flaky
    provider.summary = summary
    task_id = create(client)
    answer(client, task_id, wait(client, task_id), topic_id='1')
    answer(client, task_id, wait(client, task_id), article='人工审核后的正式文章。')
    branch = wait(client, task_id, status='error')
    assert branch['stage'] == 'generate_images'
    assert branch['data']['approved_article'] == '人工审核后的正式文章。'
    assert client.post(f'/api/tasks/{task_id}/xiaohongshu/retry').status_code == 202
    wait(client, task_id, status='completed')
    assert calls == {'image': 2, 'summary': 1}

def test_upload_validation_and_private_files(client):
    assert client.post('/api/assets', files={'file': ('x.png', b'not an image','image/png')}).status_code == 400
    assert client.post('/api/assets', files={'file': ('x.svg', b'<svg></svg>','image/svg+xml')}).status_code == 400
    sample = client.get('/api/config').json()['sample_asset']
    raw = client.get(sample['url']).content
    result = client.post('/api/assets', files={'file': ('real.jpg',raw,'image/jpeg')})
    assert result.status_code == 201
    assert result.json()['width'] > 0
    assert client.get('/.env').status_code == 404
    assert client.get('/static/../.env').status_code == 404
    assert 'api_key' not in client.get('/api/config').text.lower()

def test_exports_escape_user_text_and_origin_guard(client):
    task_id = create(client)
    answer(client, task_id, wait(client, task_id), topic_id='1')
    answer(client, task_id, wait(client, task_id), article='<script>alert(1)</script>\n合法的商品描述。')
    branch = wait(client, task_id, status='completed')
    document = client.get(branch['data']['output']['html_url']).text
    assert '<script>' not in document
    assert '&lt;script&gt;' in document
    assert client.post('/api/tasks', headers={'Origin':'https://untrusted.example'}, json={}).status_code == 403

def test_unknown_task_invalid_platform_and_assets(client):
    assert client.get('/api/tasks/unknown').status_code == 404
    assert client.post('/api/tasks', json={'name':'x','description':'合法描述内容','asset_ids':['bad'],
        'platforms':['unsupported'],'mode':'mock'}).status_code == 422
    assert client.post('/api/tasks', json={'name':'x','description':'合法描述内容','asset_ids':['bad'],
        'platforms':['wechat'],'mode':'mock'}).status_code == 400

def test_tasks_and_interrupts_survive_restart(tmp_path):
    with TestClient(create_app(tmp_path)) as first:
        task_id = create(first)
        branch = wait(first, task_id)
        assert branch['interrupt']['stage'] == 'topic'
    with TestClient(create_app(tmp_path)) as second:
        tasks = second.get('/api/tasks').json()
        assert [task['id'] for task in tasks] == [task_id]
        branch = tasks[0]['branches']['xiaohongshu']
        assert branch['status'] == 'waiting'
        assert branch['interrupt']['stage'] == 'topic'
        assert answer(second, task_id, branch, topic_id='1').status_code == 202
        branch = wait(second, task_id)
        assert branch['interrupt']['stage'] == 'article'
        assert answer(second, task_id, branch, article='重启后继续审核的正文。').status_code == 202
        branch = wait(second, task_id, status='completed')
        assert branch['data']['approved_article'] == '重启后继续审核的正文。'
        assert second.get(branch['data']['output']['zip_url']).status_code == 200
