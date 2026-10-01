"""Read only the official Ark model catalog; never print credentials."""
import httpx

from app import config

if __name__ == '__main__':
    try:
        response = httpx.get(config.BASE_URL + '/models', headers={'Authorization':f'Bearer {config.API_KEY}'}, timeout=30)
        print('MODEL_CATALOG_HTTP', response.status_code)
        if response.is_success:
            data = response.json()
            models = data.get('data', [])
            print('\n'.join(m['id'] for m in models if 'id' in m))
        else:
            print('Model list is unavailable. Configure model IDs from the Ark console.')
    except httpx.HTTPError:
        print('Model list request failed.')
