"""Development server entry point: ``python -m zhihui_qilu.main``."""

import uvicorn

from zhihui_qilu.api.app import create_app
from zhihui_qilu.config import get_settings

app = create_app(get_settings())


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
