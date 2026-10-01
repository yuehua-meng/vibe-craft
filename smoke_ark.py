"""Explicit live smoke test. --image also generates one billable image."""
import argparse
import asyncio

from app.main import app
from app.media import save_generated
from app.providers import ArkProvider, safe_error


async def main(with_image):
    provider = ArkProvider(app.state.repo)
    try:
        text = await provider.chat('This is a connection test.', 'Reply OK')
        print('ARK_TEXT_OK:', text[:30])
    except Exception as exc:
        print('ARK_TEXT_FAILED:', safe_error(exc))
        return
    if with_image:
        state = {'platform':'wechat', 'asset_ids':[next(iter(app.state.repo.assets))], 'mode':'ark',
            'summary':{'summary':'简约的浅绿色随行杯，深绿色杯盖。', 'image_prompt':'自然光下的简洁书桌，保持商品外观。', 'caption':'日常的小小从容'}}
        try:
            raw = await provider.image(state)
            asset = save_generated(app.state.repo, state, raw)
            print('ARK_IMAGE_OK:', asset['url'])
        except Exception as exc:
            print('ARK_IMAGE_FAILED:', safe_error(exc))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', action='store_true')
    asyncio.run(main(parser.parse_args().image))
