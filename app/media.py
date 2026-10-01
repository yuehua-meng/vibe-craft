import base64
import hashlib
import html
import io
import json
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .config import PLATFORMS

Image.MAX_IMAGE_PIXELS = 20_000_000

def ingest_image(repo, raw: bytes, filename: str):
    if not raw or len(raw) > 8 * 1024 * 1024:
        raise ValueError('每张图片需小于 8 MB')
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in ('JPEG', 'PNG', 'WEBP'):
                raise ValueError('仅支持 PNG、JPEG、WebP 图片')
            if source.width * source.height > 20_000_000 or min(source.size) < 32:
                raise ValueError('图片尺寸需至少 32px，且不超过 2000 万像素')
            normalized = ImageOps.exif_transpose(source).convert('RGB')
            normalized.thumbnail((2048, 2048))
            out = io.BytesIO()
            normalized.save(out, format='JPEG', quality=94)
    except (OSError, Image.DecompressionBombError) as exc:
        raise ValueError('无法读取图片，请上传有效图片') from exc
    content = out.getvalue()
    asset_id = hashlib.sha256(content).hexdigest()[:24]
    path = repo.data_dir / 'assets' / f'{asset_id}.jpg'
    path.write_bytes(content)
    asset = {'id': asset_id, 'name': Path(filename).name[:100], 'url': f'/media/assets/{path.name}',
             'width': normalized.width, 'height': normalized.height, 'bytes': len(content)}
    repo.add_asset(asset)
    return asset

def image_data_url(repo, asset_id):
    path = repo.data_dir / 'assets' / f'{asset_id}.jpg'
    return 'data:image/jpeg;base64,' + base64.b64encode(path.read_bytes()).decode()

def font(size):
    for path in ('C:/Windows/Fonts/msyh.ttc', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)

def make_sample(repo):
    """A clearly fictional, locally drawn product fixture for demo/testing."""
    img = Image.new('RGB', (900, 1000), '#e9ece4')
    draw = ImageDraw.Draw(img)
    draw.ellipse((170, 845, 735, 925), fill='#d5dacd')
    draw.rounded_rectangle((300, 180, 595, 880), radius=65, fill='#a5b39c')
    draw.rounded_rectangle((315, 145, 580, 245), radius=25, fill='#52664e')
    draw.rounded_rectangle((355, 420, 540, 620), radius=4, fill='#f4f3eb')
    draw.text((386, 453), 'MORI', font=font(37), fill='#314532')
    draw.text((375, 524), 'DAILY / 01', font=font(20), fill='#697260')
    draw.text((54, 60), 'MORI STUDIO', font=font(25), fill='#52664e')
    out = io.BytesIO()
    img.save(out, 'PNG')
    return ingest_image(repo, out.getvalue(), 'MORI-示例随行杯.png')

def demo_image(repo, state):
    width, height = PLATFORMS[state['platform']]['size']
    width, height = width // 2, height // 2
    canvas = Image.new('RGB', (width, height), '#e7ebdf')
    source = Image.open(repo.data_dir / 'assets' / f"{state['asset_ids'][0]}.jpg")
    source.thumbnail((int(width * .76), int(height * .65)))
    canvas.paste(source, ((width-source.width)//2, (height-source.height)//2 + 28))
    d = ImageDraw.Draw(canvas)
    d.text((35, 25), 'MORI / CREATIVE STUDIO', font=font(18), fill='#4f6659')
    d.text((35, 66), state['summary']['caption'][:21], font=font(25), fill='#243c30')
    d.text((35, height-42), '演示模式 · 模板合成 / 非 AI 生图', font=font(16), fill='#4f6659')
    out = io.BytesIO()
    canvas.save(out, 'PNG')
    return out.getvalue()

def save_generated(repo, state, raw):
    # Validate provider output and normalize it before serving to the browser.
    with Image.open(io.BytesIO(raw)) as image:
        image.load()
        if image.width * image.height > 20_000_000:
            raise ValueError('生成图片尺寸过大')
        output = io.BytesIO()
        image.convert('RGB').save(output, 'JPEG', quality=95)
    digest = hashlib.sha256(output.getvalue()).hexdigest()[:20]
    filename = f"{state['platform']}-{digest}.jpg"
    (repo.data_dir / 'generated' / filename).write_bytes(output.getvalue())
    return {'url': f'/media/generated/{filename}', 'filename': filename,
            'caption': state['summary']['caption'], 'mode': state['mode']}

def render_document(title, article, summary, image_src, platform):
    color = PLATFORMS[platform]['color']
    paragraphs = []
    for part in article.split('\n'):
        text = part.strip()
        if not text:
            continue
        tag = 'h2' if text.startswith('## ') else 'p'
        text = text.removeprefix('## ')
        paragraphs.append(f'<{tag} style="line-height:1.9;margin:18px 0">{html.escape(text)}</{tag}>')
    body = '\n'.join(paragraphs)
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<body style="margin:0;background:#f5f5f1;color:#26342d;font-family:Arial,Microsoft YaHei,sans-serif">
<article style="max-width:720px;margin:28px auto;background:white;padding:32px;border-radius:12px">
<div style="font-size:12px;color:{color}">{html.escape(PLATFORMS[platform]['name'])} · 图文成品</div>
<h1 style="font-size:28px;line-height:1.5">{html.escape(title)}</h1>
<p style="color:#78847c;font-size:14px;line-height:1.8">{html.escape(summary)}</p>
<img alt="营销配图" src="{image_src}" style="width:100%;border-radius:8px">{body}
</article></body></html>'''

def export_bundle(repo, state):
    image = state['image']
    raw = (repo.data_dir / 'generated' / image['filename']).read_bytes()
    image_url = 'data:image/jpeg;base64,' + base64.b64encode(raw).decode()
    title = state['confirmed_topic']['title']
    document = render_document(title, state['approved_article'], state['summary']['summary'], image_url, state['platform'])
    filename = f"{state['task_id']}-{state['platform']}-v{state['article_version']}"
    path = repo.data_dir / 'exports'
    (path / f'{filename}.html').write_text(document, encoding='utf-8')
    with zipfile.ZipFile(path / f'{filename}.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('article.html', document)
        archive.writestr('article.txt', state['approved_article'])
        archive.writestr('cover.jpg', raw)
        archive.writestr('metadata.json', json.dumps({'platform': state['platform'], 'mode': state['mode'],
            'article_version': state['article_version'], 'topic': state['confirmed_topic'],
            'summary': state['summary']}, ensure_ascii=False, indent=2))
    return {'html_url': f'/media/exports/{filename}.html', 'zip_url': f'/media/exports/{filename}.zip'}
