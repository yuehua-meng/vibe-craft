const $ = (s) => document.querySelector(s);
const e = (s = '') => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const paths = {
  leaf: '<path d="M19 4C9 3 3 7 5 14s12 8 14-10Z"/><path d="m7 17 7-8"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 5-5 4 4 4-6 5 7"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  edit: '<path d="m15 4 5 5-11 11-6 1 1-6L15 4Z"/><path d="m12 7 5 5"/>',
  download: '<path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>',
  spark: '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  refresh: '<path d="M20 7v5h-5M4 17v-5h5"/><path d="M5 8a8 8 0 0 1 13-3l2 3M4 16l2 3a8 8 0 0 0 13-3"/>',
  book: '<path d="M3 4h6a4 4 0 0 1 3 2 4 4 0 0 1 3-2h6v15h-6a4 4 0 0 0-3 2 4 4 0 0 0-3-2H3V4ZM12 6v15"/>',
};
const icon = (name, cls = '') => `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.spark}</svg>`;
let config, tasks = [], activeTask = null, activePlatform = null, view = 'create', busy = false;
let form = {name: '', description: '', instruction: '', platforms: ['xiaohongshu'], mode: 'ark', assets: []};
const selections = {}, drafts = {}, feedbacks = {};
let lastSignature = '';
const statuses = {queued: '排队中', running: '生成中', waiting: '待你确认', completed: '已完成', error: '需要处理'};
const stepLabels = ['上传素材', '选题确认', '文章审核', '提炼摘要', '生成图片', '图文编排'];
const stageIndex = {queued: 1, generate_topics: 1, review_topic: 1, generate_article: 2, review_article: 2, generate_summary: 3, generate_images: 4, compose_layout: 5, completed: 6};

async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, options);
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(typeof detail === 'string' ? detail : (Array.isArray(detail) ? detail.map(x => x.msg).join('；') : '请求失败'));
  }
  return data;
}
const post = (path, data) => api(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
let toastTimer;
function toast(message, error = false) {
  $('#toast').textContent = message;
  $('#toast').className = `show ${error ? 'error' : ''}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $('#toast').className = ''; }, 4500);
}
function brandMark(p) {
  const platform = config.platforms[p];
  return `<span class="platform-mark" style="--platform:${platform.color}">${e(platform.mark)}</span>`;
}
function badge(status) { return `<span class="badge ${status}"><i></i>${statuses[status] || e(status)}</span>`; }
function time(value) { return new Date(value).toLocaleString('zh-CN', {month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'}); }
function steps(index) {
  return `<div class="steps">${stepLabels.map((name, i) => `<div class="step ${i < index ? 'done' : i === index ? 'active' : ''}"><span>${i < index ? icon('check') : `0${i + 1}`}</span><b>${name}</b>${i === 1 || i === 2 ? '<small>人工确认</small>' : ''}</div>`).join('')}</div>`;
}
function shell(content) {
  const awaiting = tasks.reduce((n, t) => n + Object.values(t.branches).filter(b => b.status === 'waiting').length, 0);
  return `<aside class="sidebar">
    <a class="brand" href="#" data-action="home"><span class="brand-icon">${icon('leaf')}</span><span>图文工坊<small>CONTENT STUDIO</small></span></a>
    <div class="workspace-label">你的创作空间</div>
    <nav><button data-action="home" class="nav-item ${view === 'create' ? 'selected' : ''}">${icon('grid')}创作工作台</button>
    <button data-action="history" class="nav-item ${view === 'history' ? 'selected' : ''}">${icon('clock')}创作记录<span class="nav-count">${tasks.length}</span></button></nav>
    <div class="sidebar-rule"></div><div class="workspace-label">工作流</div>
    <div class="flow-links"><div><span>01</span>素材与平台</div><div><span>02</span>选题与文章审核</div><div><span>03</span>图片与图文编排</div></div>
    <div class="sidebar-note">${icon('leaf')}<strong>让灵感，多一种表达。</strong><p>从一份商品素材，走向每一个适合它的平台。</p><span>由 LangGraph 驱动</span></div>
    <div class="local-user"><div class="avatar">创</div><div>本地创作工作区<small>SQLite 存储 · 重启保留任务</small></div><i></i></div>
  </aside>
  <div class="workspace"><header class="topbar"><div class="breadcrumb">工作区 <span>/</span> ${view === 'task' ? '创作详情' : view === 'history' ? '创作记录' : '创作工作台'}</div><div class="topbar-right"><span class="connection"><i></i>本地服务已连接</span><span class="review-count">${icon('clock')}${awaiting} 项待确认</span></div></header>
    <main>${content}</main><footer>图文工坊 <span>·</span> 从商品素材到平台内容 <span class="footer-right">LOCAL WORKSPACE / 2026</span></footer>
  </div>`;
}
function createPage() {
  return `<section class="page-heading"><div><div class="eyebrow">CREATE SOMETHING GOOD</div><h1>一份灵感，多种表达<span>。</span></h1><p>上传商品素材，选择目标平台，让好内容一步步发生。</p></div><button class="btn secondary" data-action="demo">${icon('spark')}试用示例素材</button></section>
    ${steps(0)}
    <form id="create-form" class="creation-grid">
    <section class="panel material-panel"><div class="section-heading"><div class="section-title"><span class="section-no">01</span><h2>上传你的商品素材</h2></div><span class="subtle">好的内容，从真实素材开始</span></div>
      <div id="dropzone" class="dropzone ${form.assets.length ? 'compact' : ''}" tabindex="0" role="button" aria-label="上传商品图片"><div class="upload-icon">${icon('upload')}</div><strong>${form.assets.length ? '继续添加商品图片' : '拖拽商品图片到这里'}</strong><p>或 <span>点击上传</span></p><small>JPG、PNG、WebP · 最多 4 张 · 每张不超过 8 MB</small></div>
      <input id="file-input" type="file" accept="image/jpeg,image/png,image/webp" multiple hidden>
      ${form.assets.length ? `<div class="asset-grid">${form.assets.map((a, i) => `<div class="asset-tile"><img src="${e(a.url)}" alt="${e(a.name)}"><button type="button" class="remove-asset" data-action="remove-asset" data-index="${i}" aria-label="移除${e(a.name)}">${icon('close')}</button><span>${e(a.name)}</span></div>`).join('')}</div>` : ''}
      <label class="field-label" for="product-name">商品 / 项目名称 <em>*</em></label><input id="product-name" name="name" class="input" placeholder="例如：MORI 日常随行杯" maxlength="80" required value="${e(form.name)}">
      <label class="field-label" for="description">商品描述 <em>*</em><span>只填写已确认的商品信息</span></label><textarea id="description" name="description" class="input" rows="4" minlength="5" maxlength="6000" required placeholder="介绍商品特点、使用场景、核心卖点…">${e(form.description)}</textarea>
      <label class="field-label" for="instruction">创作要求 <span>选填</span></label><textarea id="instruction" name="instruction" class="input" rows="2" maxlength="3000" placeholder="例如：面向年轻通勤人群，自然克制，避免夸张用语">${e(form.instruction)}</textarea>
    </section>
    <div class="right-column"><section class="panel platform-panel"><div class="section-heading"><div class="section-title"><span class="section-no">02</span><h2>选择发布平台</h2></div><span class="small-tag">可多选</span></div><p class="section-description">每个平台独立生成选题与文章，由你确认后继续。</p>
      <div class="platform-options">${Object.entries(config.platforms).map(([id, p]) => `<label class="platform-option ${form.platforms.includes(id) ? 'checked' : ''}"><input type="checkbox" name="platform" value="${id}" ${form.platforms.includes(id) ? 'checked' : ''}>${brandMark(id)}<div><strong>${p.name}</strong><small>${{xiaohongshu:'生活化表达 · 封面与种草图文',wechat:'完整叙事 · 文章与正文排版',twitter:'简洁有力 · 短帖与串帖配图'}[id]}</small></div><span class="custom-check">${form.platforms.includes(id) ? icon('check') : ''}</span></label>`).join('')}</div>
      <div class="mode-row"><div><strong>生成方式</strong><small>${form.mode === 'ark' ? '使用火山方舟真实模型，按账户用量计费' : '本地示例文案与模板合成，不调用模型'}</small></div><select aria-label="生成方式" id="mode"><option value="ark" ${form.mode==='ark'?'selected':''}>火山方舟</option><option value="mock" ${form.mode==='mock'?'selected':''}>本地演示</option></select></div>
      <button type="submit" class="btn primary wide" ${busy ? 'disabled' : ''}>${busy ? '<span class="spinner"></span>正在创建' : `${icon('spark')}开始生成选题${icon('arrow')}`}</button><p class="button-note">先确认选题，再审核文章，每一步都由你掌握。</p>
    </section>
    <section class="inspiration-card"><div class="inspiration-text"><span class="eyebrow">FROM PRODUCT TO STORY</span><h3>让商品，<br>拥有自己的故事。</h3><p>内容与视觉，从同一份灵感出发。</p><div class="inspiration-chips"><span>品牌表达</span><span>多平台创作</span></div></div><img src="${e(config.sample_asset.url)}" alt="示例商品随行杯"><span class="sample-label">示例视觉</span></section></div></form>`;
}
function historyPage() {
  return `<section class="page-heading"><div><div class="eyebrow">YOUR CREATIVE LIBRARY</div><h1>每一份创作，都在这里。</h1><p>继续审核进行中的内容，或回看已经完成的作品。</p></div><button class="btn primary" data-action="home">${icon('plus')}新建创作</button></section>
  <section class="panel history-panel"><div class="section-heading"><h2>全部创作 <span class="subtle">${tasks.length}</span></h2><span class="small-tag">Mock 内存数据</span></div>
  ${tasks.length ? `<div class="task-list">${tasks.map(t => `<button class="task-row" data-action="open-task" data-id="${t.id}"><img src="${e(t.assets[0].url)}" alt="${e(t.name)}"><div class="task-row-title"><strong>${e(t.name)}</strong><span>${time(t.created_at)} · ${t.mode==='ark'?'火山方舟':'本地演示'}</span></div><div class="task-platforms">${t.platforms.map(brandMark).join('')}</div>${badge(t.status)}${icon('arrow')}</button>`).join('')}</div>` : `<div class="empty-state">${icon('book')}<h3>你的第一份作品，从这里开始</h3><p>上传商品图片和描述，开始一次新的创作。</p><button class="btn secondary" data-action="home">创建第一份图文</button></div>`}</section>`;
}
function currentKey(branch) { return `${activeTask.id}:${activePlatform}:${branch.interrupt?.id || branch.version}`; }
function topicReview(branch) {
  const k = currentKey(branch), pending = branch.interrupt;
  const selected = selections[k] || pending.topics[0]?.id;
  selections[k] = selected;
  return `<div class="review-title"><span class="stage-symbol">${icon('spark')}</span><div><h2>先选一个，让故事开始。</h2><p>我们准备了 3 个创作方向。确认后，将围绕选题生成文章。</p></div><span class="small-tag">第 ${pending.version} 版</span></div>
    <div class="topic-grid">${pending.topics.map((t, i) => `<label class="topic-card ${selected===t.id?'selected':''}"><input type="radio" name="topic" value="${e(t.id)}" ${selected===t.id?'checked':''}><span class="topic-top"><span>DIRECTION 0${i+1}</span><span class="radio-check"></span></span><h3>${e(t.title)}</h3><p class="angle">${e(t.angle)}</p><p>${e(t.outline)}</p></label>`).join('')}</div>
    <label class="field-label" for="feedback">想换个方向？<span>填写修改意见后重新生成</span></label><textarea class="input" id="feedback" rows="2" maxlength="3000" placeholder="例如：更聚焦办公室场景，减少抒情表达">${e(feedbacks[k] || '')}</textarea>
    <div class="action-bar"><button class="btn secondary" data-action="revise" ${busy?'disabled':''}>${icon('refresh')}重新生成选题</button><button class="btn primary" data-action="approve-topic" ${busy?'disabled':''}>确认选题，生成文章${icon('arrow')}</button></div>`;
}
function articleReview(branch) {
  const k = currentKey(branch), pending = branch.interrupt;
  if (!(k in drafts)) drafts[k] = pending.article;
  return `<div class="review-title"><span class="stage-symbol">${icon('edit')}</span><div><h2>让每一句，都符合你的心意。</h2><p>可直接编辑正文，或提交修改意见。审核通过后才会生成图片。</p></div><span class="small-tag">第 ${pending.version} 版</span></div>
    <div class="article-toolbar"><strong>文章正文</strong><span id="word-count">${drafts[k].length} 字</span></div><textarea id="article-editor" class="article-editor" maxlength="16000" aria-label="审核并编辑文章">${e(drafts[k])}</textarea>
    <label class="field-label" for="feedback">修改意见<span>退回修改时必填</span></label><textarea class="input" id="feedback" rows="2" maxlength="3000" placeholder="指出希望调整的语气、结构或具体内容">${e(feedbacks[k] || '')}</textarea>
    <div class="action-bar"><div class="button-group"><button class="btn text" data-action="retopic" ${busy?'disabled':''}>更换选题</button><button class="btn secondary" data-action="revise" ${busy?'disabled':''}>${icon('refresh')}按意见修改</button></div><button class="btn primary" data-action="approve-article" ${busy?'disabled':''}>${icon('check')}审核通过，继续生成</button></div>`;
}
function outputPanel(branch) {
  const data = branch.data;
  return `<div class="review-title"><span class="stage-symbol">${icon('check')}</span><div><h2>图文已就绪，看看最终效果。</h2><p>文章、摘要与图片已编排完成。下载素材包即可继续使用。</p></div></div>
    <div class="output-actions"><button class="btn secondary" data-action="copy">${icon('book')}复制文案</button><a class="btn secondary" href="${e(data.output.html_url)}" target="_blank" rel="noopener">${icon('image')}打开完整预览</a><a class="btn primary" href="${e(data.output.zip_url)}" download>${icon('download')}下载图文素材包</a></div>
    <div class="result-grid"><div><img class="result-image" src="${e(data.image.url)}" alt="${e(data.image.caption)}"><span class="image-note">${activeTask.mode==='mock'?'演示图片 · 本地模板合成':'AI 生成图片 · 请核对商品外观与细节'}</span></div><div class="result-copy"><div class="eyebrow">${e(config.platforms[activePlatform].name)}</div><h3>${e(data.confirmed_topic.title)}</h3><div class="summary-box"><strong>内容摘要</strong><p>${e(data.summary.summary)}</p></div><div class="article-text">${e(data.approved_article)}</div></div></div>`;
}
function progressPanel(branch) {
  const stageNames = {generate_topics:'正在寻找适合商品的表达方向',generate_article:'正在将选题写成文章',generate_summary:'正在从审核后的文章提炼摘要',generate_images:'正在把摘要与原图融合成新图片',compose_layout:'正在完成最后的图文编排',queued:'任务已进入创作队列'};
  if (branch.status === 'error') return `<div class="error-panel">${icon('refresh')}<h2>这一步需要处理一下</h2><p>${e(branch.error)}</p><small>已完成的步骤和审核记录会保留，重试从失败节点继续。</small><button class="btn primary" data-action="retry" ${busy?'disabled':''}>重试当前步骤</button></div>`;
  return `<div class="progress-panel"><div class="orb"><span class="spinner"></span>${icon('spark')}</div><span class="eyebrow">CREATING YOUR STORY</span><h2>${stageNames[branch.stage] || '正在继续创作'}</h2><p>你可以切换其他平台查看进度，当前任务会继续执行。</p><div class="progress-dots"><i></i><i></i><i></i></div></div>
    ${branch.data.summary?.summary ? `<div class="summary-box"><strong>已生成摘要</strong><p>${e(branch.data.summary.summary)}</p><small>配图方向：${e(branch.data.summary.image_prompt)}</small></div>` : ''}`;
}
function taskPage() {
  const task = activeTask;
  if (!activePlatform || !task.branches[activePlatform]) activePlatform = task.platforms[0];
  const branch = task.branches[activePlatform];
  let body = branch.status === 'waiting' ? (branch.interrupt.stage === 'topic' ? topicReview(branch) : articleReview(branch)) : branch.status === 'completed' ? outputPanel(branch) : progressPanel(branch);
  return `<section class="page-heading compact-heading"><div><div class="eyebrow">YOUR STORY IN PROGRESS</div><h1>${e(task.name)}</h1><p>${time(task.created_at)} 创建 <span class="dot">·</span> ${task.mode === 'ark' ? '火山方舟真实生成' : '本地演示 · 非 AI 生成'}</p></div><button class="btn secondary" data-action="home">${icon('plus')}新建创作</button></section>
    ${steps(stageIndex[branch.stage] ?? 0)}
    <div class="platform-tabs">${task.platforms.map(p => `<button data-action="platform" data-platform="${p}" class="platform-tab ${p===activePlatform?'active':''}">${brandMark(p)}<strong>${e(config.platforms[p].name)}</strong>${badge(task.branches[p].status)}</button>`).join('')}</div>
    <div class="task-grid"><section class="panel review-panel">${body}</section><aside class="task-context"><section class="panel"><div class="section-heading"><h2>创作简报</h2>${icon('book')}</div><div class="context-images">${task.assets.map(a=>`<img src="${e(a.url)}" alt="${e(a.name)}">`).join('')}</div><h4>商品资料</h4><p>${e(task.description)}</p>${task.instruction?`<h4>创作要求</h4><p>${e(task.instruction)}</p>`:''}${branch.data.confirmed_topic?`<h4>已确认选题</h4><p class="confirmed-topic">${e(branch.data.confirmed_topic.title)}</p>`:''}</section>
    <section class="panel activity"><h2>创作动态</h2><div class="timeline">${task.events.filter(ev=>ev.platform===activePlatform).slice(-7).reverse().map(ev=>`<div><span class="timeline-dot"></span><p>${e(ev.message)}</p><small>${time(ev.at)}</small></div>`).join('')}</div></section></aside></div>`;
}
function render() {
  $('#app').innerHTML = shell(view === 'create' ? createPage() : view === 'history' ? historyPage() : taskPage());
  const zone = $('#dropzone');
  if (zone) {
    zone.onclick = () => $('#file-input').click();
    zone.onkeydown = ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); $('#file-input').click(); } };
    zone.ondragover = ev => { ev.preventDefault(); zone.classList.add('dragging'); };
    zone.ondragleave = () => zone.classList.remove('dragging');
    zone.ondrop = ev => { ev.preventDefault(); uploadFiles(ev.dataTransfer.files); };
  }
}
async function uploadFiles(files) {
  if (busy) return;
  const available = 4 - form.assets.length;
  if (files.length > available) { toast('最多上传 4 张图片，请减少选择数量', true); return; }
  busy = true; render();
  try {
    for (const file of files) {
      if (file.size > 8*1024*1024) throw new Error('单张图片不能超过 8 MB');
      const data = new FormData(); data.append('file', file);
      const asset = await api('/assets', {method:'POST', body:data});
      if (!form.assets.some(a=>a.id===asset.id)) form.assets.push(asset);
    }
    toast('商品图片已上传');
  } catch (error) { toast(error.message, true); }
  finally { busy=false; render(); }
}
async function createTask(ev) {
  ev.preventDefault();
  if (busy) return;
  if (!form.assets.length) return toast('请先上传商品图片，或试用示例素材', true);
  if (!form.platforms.length) return toast('请至少选择一个平台', true);
  busy = true; render();
  try {
    activeTask = await post('/tasks', {...form, asset_ids: form.assets.map(a=>a.id), assets: undefined});
    tasks.unshift(activeTask); activePlatform=activeTask.platforms[0]; view='task';
    sessionStorage.setItem('activeTask', activeTask.id); lastSignature='';
    toast('创作任务已创建，正在生成选题');
  } catch (error) { toast(error.message, true); }
  finally { busy=false; render(); }
}
async function review(action) {
  if (busy) return;
  const branch = activeTask.branches[activePlatform], pending=branch.interrupt, k=currentKey(branch);
  const feedback = feedbacks[k] || '';
  if (action !== 'approve' && !feedback.trim()) return toast('请先填写修改意见', true);
  const payload = {action, interrupt_id:pending.id, version:pending.version, feedback};
  if (pending.stage === 'topic') payload.topic_id=selections[k];
  else payload.article=drafts[k];
  busy=true; render();
  try { activeTask=await post(`/tasks/${activeTask.id}/${activePlatform}/review`, payload); toast('已提交，工作流继续执行'); }
  catch (error) { toast(error.message, true); }
  finally { busy=false; render(); }
}
document.addEventListener('submit', ev => { if (ev.target.id==='create-form') createTask(ev); });
document.addEventListener('input', ev => {
  const {name, id, value}=ev.target;
  if (['name','description','instruction'].includes(name)) form[name]=value;
  if (id==='feedback' && activeTask) feedbacks[currentKey(activeTask.branches[activePlatform])]=value;
  if (id==='article-editor') { drafts[currentKey(activeTask.branches[activePlatform])]=value; $('#word-count').textContent=`${value.length} 字`; }
});
document.addEventListener('change', ev => {
  const target=ev.target;
  if (target.id==='file-input') uploadFiles(target.files);
  if (target.name==='platform') { form.platforms=[...document.querySelectorAll('[name=platform]:checked')].map(x=>x.value); render(); }
  if (target.id==='mode') { form.mode=target.value; render(); }
  if (target.name==='topic') { selections[currentKey(activeTask.branches[activePlatform])]=target.value; render(); }
});
document.addEventListener('click', async ev => {
  const target=ev.target.closest('[data-action]'); if(!target) return;
  ev.preventDefault(); const action=target.dataset.action;
  if (busy) return;
  if(action==='home') { view='create'; render(); }
  if(action==='history') { tasks=await api('/tasks').catch(()=>tasks); view='history'; render(); }
  if(action==='demo') { form={name:'MORI 日常随行杯', description:'浅绿色随行杯，深绿色杯盖，简约外观。面向关注生活美感的通勤人群。此为虚构演示商品，不提供容量、材质或保温性能承诺。',instruction:'语气自然克制，以日常生活场景切入。不要编造商品参数、价格或使用体验。', platforms:['xiaohongshu','wechat'], mode:'mock', assets:[config.sample_asset]}; render(); toast('已填入示例素材，当前为本地演示模式'); }
  if(action==='remove-asset') { form.assets.splice(Number(target.dataset.index),1); render(); }
  if(action==='open-task') { try { activeTask=await api(`/tasks/${target.dataset.id}`); activePlatform=activeTask.platforms[0]; view='task'; sessionStorage.setItem('activeTask',activeTask.id); render(); } catch(error){toast(error.message,true);} }
  if(action==='platform') { activePlatform=target.dataset.platform; render(); }
  if(action==='approve-topic'||action==='approve-article') await review('approve');
  if(action==='revise'||action==='retopic') await review(action);
  if(action==='retry') { busy=true; render(); try { activeTask=await post(`/tasks/${activeTask.id}/${activePlatform}/retry`, {}); } catch(error){toast(error.message,true);} finally{busy=false;render();} }
  if(action==='copy') { try { await navigator.clipboard.writeText(activeTask.branches[activePlatform].data.approved_article); toast('文章已复制到剪贴板'); } catch { toast('复制失败，请在完整预览中选择文字复制',true); } }
});
async function poll() {
  try {
    if(view==='task' && activeTask && !busy) {
      const task=await api(`/tasks/${activeTask.id}`);
      const signature=JSON.stringify(task);
      if(signature!==lastSignature) {
        activeTask=task;
        const i=tasks.findIndex(t=>t.id===task.id); if(i>=0)tasks[i]=task;
        // Keep caret/focus stable while another platform changes status.
        const editing=['TEXTAREA','INPUT'].includes(document.activeElement?.tagName);
        if(!busy && !editing) { lastSignature=signature; render(); }
      }
    }
  } catch(error) { if(error.message.includes('重启')) { sessionStorage.removeItem('activeTask'); activeTask=null; view='create'; tasks=[]; render(); toast(error.message,true); } }
  finally { setTimeout(poll, 1600); }
}
async function init() {
  try {
    config=await api('/config'); tasks=await api('/tasks');
    form.mode=config.key_configured?'ark':'mock';
    const saved=sessionStorage.getItem('activeTask');
    if(saved && tasks.some(t=>t.id===saved)) { activeTask=tasks.find(t=>t.id===saved); view='task'; }
    render(); poll();
  } catch(error) { $('#app').innerHTML=`<div class="boot"><h2>暂时无法连接服务</h2><p>${e(error.message)}</p><p>请启动项目后刷新页面。</p></div>`; }
}
init();
