from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from langgraph.types import Command

from . import config
from .media import ingest_image, make_sample
from .repository import SqliteRepository, now
from .schemas import Review, TaskCreate
from .workflow import WorkflowService


def create_app(data_dir=None):
    repo = SqliteRepository(data_dir or config.DATA)
    service = WorkflowService(repo)
    sample = make_sample(repo)

    @asynccontextmanager
    async def lifespan(app):
        await service.startup()
        yield
        await service.close()

    app = FastAPI(title='图文工坊 · LangGraph API', lifespan=lifespan)
    app.state.repo = repo
    app.state.workflow = service

    @app.middleware('http')
    async def local_origin(request: Request, call_next):
        # Local prototype: do not accept cross-site writes from arbitrary websites.
        origin = request.headers.get('origin')
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin:
            from urllib.parse import urlsplit
            if urlsplit(origin).netloc != request.headers.get('host'):
                return JSONResponse({'detail': '不允许跨站请求'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        return response

    def get_task(task_id):
        task = repo.tasks.get(task_id)
        if task is None:
            raise HTTPException(404, '任务不存在。Mock 数据在服务重启后会清空。')
        return task

    def get_branch(task_id, platform):
        task = get_task(task_id)
        if platform not in task['branches']:
            raise HTTPException(404, '任务中没有这个平台')
        return task, task['branches'][platform]

    @app.get('/api/config')
    def app_config():
        return {'platforms': config.PLATFORMS, 'key_configured': config.provider_ready(),
                'text_model': config.TEXT_MODEL, 'image_model': config.IMAGE_MODEL,
                'storage': 'sqlite', 'max_upload_mb': 8, 'sample_asset': sample,
                'workflow_engine': 'LangGraph StateGraph + AsyncSqliteSaver'}

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'engine': 'langgraph', 'storage': 'sqlite'}

    @app.post('/api/assets', status_code=201)
    async def upload(file: UploadFile = File(...)):
        raw = await file.read(8 * 1024 * 1024 + 1)
        await file.close()
        try:
            return ingest_image(repo, raw, file.filename or 'upload.jpg')
        except (ValueError, OSError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get('/api/tasks')
    def list_tasks():
        return [repo.public(t) for t in reversed(list(repo.tasks.values()))]

    @app.post('/api/tasks', status_code=201)
    async def create_task(payload: TaskCreate):
        if any(x not in repo.assets for x in payload.asset_ids):
            raise HTTPException(400, '素材不存在，请重新上传')
        if len(set(payload.asset_ids)) != len(payload.asset_ids):
            raise HTTPException(400, '请勿重复选择同一张图片')
        if payload.mode == 'ark' and not config.provider_ready():
            raise HTTPException(400, '请先配置真实模型凭据（ARK_API_KEY 或网关项目凭据），或切换到演示模式')
        if len(repo.tasks) >= 100:
            raise HTTPException(429, '本地原型最多保存100个任务，请清理 data 目录中的历史数据')
        task = repo.create(payload.model_dump())
        service.start(task)
        return repo.public(task)

    @app.get('/api/tasks/{task_id}')
    def task_detail(task_id: str):
        return repo.public(get_task(task_id))

    @app.post('/api/tasks/{task_id}/{platform}/review', status_code=202)
    async def review(task_id: str, platform: str, payload: Review):
        task, branch = get_branch(task_id, platform)
        pending = branch['interrupt']
        if branch['status'] != 'waiting' or not pending:
            raise HTTPException(409, '当前任务不在等待审核，请刷新任务状态')
        if payload.interrupt_id != pending['id'] or payload.version != pending['version']:
            raise HTTPException(409, '审核版本已变化，请刷新后重新确认')
        if pending['stage'] == 'topic':
            if payload.action == 'retopic':
                raise HTTPException(400, '当前阶段请选择确认或重新生成')
            if payload.action == 'approve' and payload.topic_id not in [t['id'] for t in pending['topics']]:
                raise HTTPException(400, '请选择有效选题')
        if payload.action in ('revise', 'retopic') and not payload.feedback.strip():
            raise HTTPException(400, '请填写修改意见')
        if pending['stage'] == 'article' and payload.article is not None and not payload.article.strip():
            raise HTTPException(400, '文章不能为空')
        if len(branch['history']) >= 40:
            raise HTTPException(400, '该分支已达到40次审核上限，请新建任务')
        # Keep the precise input that was reviewed, including edited approved text.
        branch['history'].append({'at': now(), 'stage': pending['stage'], 'version': pending['version'],
                                  'reviewed_content': pending, 'decision': payload.model_dump()})
        repo.event(task_id, platform, 'review_submitted', {'approve': '已确认，继续下一步',
            'revise': '已提交修改意见', 'retopic': '已退回选题阶段'}[payload.action])
        service.schedule(task_id, platform, Command(resume={pending['id']: payload.model_dump()}))
        return repo.public(task)

    @app.post('/api/tasks/{task_id}/{platform}/retry', status_code=202)
    async def retry(task_id: str, platform: str):
        task, branch = get_branch(task_id, platform)
        if branch['status'] != 'error':
            raise HTTPException(409, '只有失败的分支可以重试')
        retry_count = branch.get('retry_count', 0)
        if retry_count >= 3:
            raise HTTPException(400, '已达到3次重试上限，请检查配置后新建任务')
        branch['retry_count'] = retry_count + 1
        service.schedule(task_id, platform, None)
        return repo.public(task)

    for directory in ('assets', 'generated', 'exports'):
        app.mount(f'/media/{directory}', StaticFiles(directory=repo.data_dir / directory), name=directory)
    app.mount('/static', StaticFiles(directory=config.ROOT / 'web'), name='static')

    @app.get('/')
    def index():
        return FileResponse(config.ROOT / 'web' / 'index.html')

    return app

app = create_app()
