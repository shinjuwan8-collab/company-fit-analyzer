"""
main.py — IATマッチングツール FastAPIサーバー

ローカル起動:
    uvicorn main:app --reload --port 8000

本番(Render)起動コマンド:
    uvicorn main:app --host 0.0.0.0 --port $PORT
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
import os

# .envファイルの読み込み（ローカル開発時のみ。本番はRender環境変数を使う）
load_dotenv()

# ── ルーターのインポート ──────────────────────────────────────
from routers.iat      import router as iat_router
from routers.matching import router as matching_router

# ── FastAPIアプリ初期化 ───────────────────────────────────────
app = FastAPI(
    title       = "IAT就活マッチングツール API",
    description = "IATスコア計算・AI企業マッチング",
    version     = "1.0.0",
)

# ── CORS設定 ──────────────────────────────────────────────────
# 本番URLはRenderのサービスURLに合わせる（環境変数で上書き可能）
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ALLOWED_ORIGINS,
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ── ルーター登録 ──────────────────────────────────────────────
app.include_router(iat_router)
app.include_router(matching_router)

# ── 静的ファイル配信（フロントエンドHTML） ────────────────────
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        return FileResponse(os.path.join(FRONTEND_DIR, "iat.html"))

    @app.get("/matching", include_in_schema=False)
    async def serve_matching():
        return FileResponse(os.path.join(FRONTEND_DIR, "matching.html"))

# ── ルートAPIエンドポイント ───────────────────────────────────
@app.get("/api", tags=["Root"])
async def root():
    return {
        "message": "IAT就活マッチングツール API",
        "version": "1.0.0",
        "endpoints": {
            "POST /api/iat/submit":      "IATスコア送信・D-score計算",
            "POST /api/matching/search": "企業マッチング（Claude API）",
            "GET  /docs":                "APIドキュメント（Swagger）",
        }
    }

# ── 直接実行用（開発時） ──────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
