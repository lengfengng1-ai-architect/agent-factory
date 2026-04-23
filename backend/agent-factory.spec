# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['app/cli.py'],
    pathex=['.', '.venv/lib/python3.11/site-packages'],
    binaries=[],
    datas=[('../frontend/dist', 'dist')],
    hiddenimports=[
        # SQLAlchemy
        'sqlalchemy',
        'sqlalchemy.ext.declarative',
        'sqlalchemy.orm',
        'sqlalchemy.sql.default_comparator',
        # FastAPI & Uvicorn
        'fastapi',
        'fastapi.middleware.cors',
        'uvicorn',
        'uvicorn.loops.auto',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan.on',
        # Pydantic
        'pydantic',
        'pydantic.v1',
        'pydantic_core._pydantic_core',
        # LangChain
        'langchain',
        'langchain_core',
        'langchain_openai',
        'langchain_deepseek',
        'langgraph',
        # Redis
        'redis',
        # Lark/Feishu
        'lark_oapi',
        'lark_oapi.api',
        # Search
        'duckduckgo_search',
        'ddgs',
        # PDF & multipart
        'pypdf',
        'python_multipart',
        # App routers
        'app.routers.agents',
        'app.routers.groups',
        'app.routers.tasks',
        'app.routers.chat',
        'app.routers.models',
        'app.routers.providers',
        'app.routers.group_chat',
        'app.routers.files',
        'app.routers.summaries',
        'app.routers.feishu',
        # App modules
        'app.models',
        'app.database',
        'app.schemas',
        'app.llm_factory',
        'app.task_engine',
        'app.workflow_engine',
        'app.tools',
        'app.summarizer',
        'app.context_manager',
        'app.file_utils',
        'app.redis_client',
        'app.feishu_client',
        'app.feishu_ws',
        'starlette.staticfiles', 'aiofiles',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='agent-factory-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    onefile=True,
)
