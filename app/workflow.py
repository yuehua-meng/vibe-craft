import asyncio
import copy
from typing import TypedDict

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from . import config
from .media import export_bundle, save_generated
from .providers import ArkProvider, GatewayProvider, MockProvider, safe_error


class ContentState(TypedDict, total=False):
    task_id: str
    platform: str
    name: str
    description: str
    instruction: str
    mode: str
    asset_ids: list[str]
    topics: list[dict]
    confirmed_topic: dict
    topic_version: int
    article_draft: str
    article_version: int
    approved_article: str
    feedback: str
    summary: dict
    image: dict
    output: dict

STAGES = {
    'generate_topics': '正在生成候选选题', 'review_topic': '等待选题确认',
    'generate_article': '正在创作文章', 'review_article': '等待文章审核',
    'generate_summary': '正在提炼摘要与配图方案', 'generate_images': '正在用摘要与原图生成新图片',
    'compose_layout': '正在编排图文并打包成品',
}

class WorkflowService:
    def __init__(self, repo):
        self.repo = repo
        # GATEWAY_MODE=1 时真实模式经模型网关调用（用量可在网关看板观测）；否则直连方舟。
        real = GatewayProvider if config.GATEWAY_MODE else ArkProvider
        self.providers = {'ark': real(repo), 'mock': MockProvider(repo)}
        self.checkpointer: AsyncSqliteSaver | None = None
        self.graph = None
        self.locks: dict[tuple, asyncio.Lock] = {}
        self.running: set[asyncio.Task] = set()
        self.semaphore = asyncio.Semaphore(3)

    async def startup(self):
        """Open the SQLite checkpointer; must run inside the running event loop."""
        conn = await aiosqlite.connect(self.repo.data_dir / 'checkpoints.db')
        self.checkpointer = AsyncSqliteSaver(conn)
        self.graph = self.build_graph()

    def config(self, task_id, platform):
        return {'configurable': {'thread_id': f'{task_id}:{platform}'}, 'recursion_limit': 100}

    def branch(self, state):
        return self.repo.tasks[state['task_id']]['branches'][state['platform']]

    def begin_node(self, state, name):
        branch = self.branch(state)
        branch['stage'] = name
        self.repo.event(state['task_id'], state['platform'], name, STAGES[name])

    def traced(self, name, function):
        async def node(state):
            self.begin_node(state, name)
            result = await function(state)
            self.branch(state)['data'].update(copy.deepcopy(result))
            return result
        return node

    def build_graph(self):
        graph = StateGraph(ContentState)

        async def topics(state):
            result = await self.providers[state['mode']].topics(state)
            return {'topics': result, 'topic_version': state.get('topic_version', 0) + 1,
                    'article_draft': '', 'approved_article': '', 'summary': {}, 'image': {}, 'output': {}}

        def review_topic(state):
            self.begin_node(state, 'review_topic')
            answer = interrupt({'stage': 'topic', 'topics': state['topics'], 'version': state['topic_version']})
            if answer['action'] == 'revise':
                return Command(update={'feedback': answer['feedback']}, goto='generate_topics')
            selected = next(t for t in state['topics'] if t['id'] == answer['topic_id'])
            return Command(update={'confirmed_topic': selected, 'feedback': ''}, goto='generate_article')

        async def article(state):
            result = await self.providers[state['mode']].article(state)
            return {'article_draft': result, 'article_version': state.get('article_version', 0) + 1,
                    'approved_article': '', 'summary': {}, 'image': {}, 'output': {}}

        def review_article(state):
            self.begin_node(state, 'review_article')
            answer = interrupt({'stage': 'article', 'article': state['article_draft'], 'version': state['article_version']})
            if answer['action'] == 'retopic':
                return Command(update={'feedback': answer['feedback']}, goto='generate_topics')
            if answer['action'] == 'revise':
                return Command(update={'feedback': answer['feedback'],
                    'article_draft': answer.get('article') or state['article_draft']}, goto='generate_article')
            approved = (answer.get('article') or state['article_draft']).strip()
            return Command(update={'approved_article': approved, 'feedback': ''}, goto='generate_summary')

        async def summary(state):
            return {'summary': await self.providers[state['mode']].summary(state)}

        async def images(state):
            raw = await self.providers[state['mode']].image(state)
            image = await asyncio.to_thread(save_generated, self.repo, state, raw)
            return {'image': image}

        async def layout(state):
            return {'output': await asyncio.to_thread(export_bundle, self.repo, state)}

        for name, fn in [('generate_topics', topics), ('generate_article', article),
                         ('generate_summary', summary), ('generate_images', images), ('compose_layout', layout)]:
            graph.add_node(name, self.traced(name, fn))
        graph.add_node('review_topic', review_topic)
        graph.add_node('review_article', review_article)
        graph.add_edge(START, 'generate_topics')
        graph.add_edge('generate_topics', 'review_topic')
        graph.add_edge('generate_article', 'review_article')
        graph.add_edge('generate_summary', 'generate_images')
        graph.add_edge('generate_images', 'compose_layout')
        graph.add_edge('compose_layout', END)
        return graph.compile(checkpointer=self.checkpointer)

    def schedule(self, task_id, platform, graph_input):
        branch = self.repo.tasks[task_id]['branches'][platform]
        # Set synchronously, before yielding: duplicate clicks cannot schedule twice.
        branch.update(status='running', error=None, interrupt=None)
        self.repo.save_task(task_id)
        task = asyncio.create_task(self.run(task_id, platform, graph_input))
        self.running.add(task)
        task.add_done_callback(self.running.discard)

    def start(self, task):
        for platform in task['platforms']:
            initial = {key: task[key] for key in ('name', 'description', 'instruction', 'mode', 'asset_ids')}
            initial.update(task_id=task['id'], platform=platform, topic_version=0, article_version=0, feedback='')
            self.schedule(task['id'], platform, initial)

    async def run(self, task_id, platform, graph_input):
        lock = self.locks.setdefault((task_id, platform), asyncio.Lock())
        branch = self.repo.tasks[task_id]['branches'][platform]
        cfg = self.config(task_id, platform)
        async with lock, self.semaphore:
            try:
                async for _ in self.graph.astream(graph_input, cfg, stream_mode='updates'):
                    snapshot = await self.graph.aget_state(cfg)
                    branch['data'] = copy.deepcopy(snapshot.values)
                    self.repo.save_task(task_id)
                snapshot = await self.graph.aget_state(cfg)
                branch['data'] = copy.deepcopy(snapshot.values)
                interrupts = [i for task in snapshot.tasks for i in task.interrupts]
                if interrupts:
                    pending = interrupts[0]
                    branch.update(status='waiting', interrupt={'id': pending.id, **pending.value},
                                  version=pending.value['version'])
                else:
                    branch.update(status='completed', stage='completed', interrupt=None)
                    self.repo.event(task_id, platform, 'completed', '图文编排完成，可以预览与下载')
                self.repo.save_task(task_id)
            except Exception as exc:
                branch.update(status='error', error=safe_error(exc))
                self.repo.event(task_id, platform, 'error', branch['error'])

    async def close(self):
        for task in list(self.running):
            task.cancel()
        await asyncio.gather(*self.running, return_exceptions=True)
        if self.checkpointer is not None:
            await self.checkpointer.conn.close()
        self.repo.close()
