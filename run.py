import os

import uvicorn

from app.config import ROOT  # noqa: F401 导入 app.config 时会执行 load_dotenv，加载 .env

if __name__ == '__main__':
    uvicorn.run('app.main:app', host='127.0.0.1', port=int(os.getenv('APP_PORT', '8010')),
                reload=False, workers=1)
