"""
routers/iat.py — IAT スコアエンドポイント

POST /api/iat/submit
    フロントエンドから全試行データを受け取り、
    D-scoreを計算して返す。
"""

from fastapi import APIRouter, HTTPException
from models import IATSubmitRequest, IATScoreResponse
from scorer import compute_scores

router = APIRouter(prefix="/api/iat", tags=["IAT"])


@router.post("/submit", response_model=IATScoreResponse)
async def submit_iat(body: IATSubmitRequest) -> IATScoreResponse:
    """
    IATの全試行データを受け取りD-scoreを計算する。

    フロントエンドはテスト完了後にこのエンドポイントを呼び出す。
    レスポンスの autonomy_score.d_score と
    achievement_score.d_score を次の /api/matching/search に渡す。
    """
    trials = body.trials

    # ── バリデーション ─────────────────────────────────────
    if len(trials) == 0:
        raise HTTPException(status_code=400, detail="試行データが空です")

    if len(trials) < 20:
        raise HTTPException(
            status_code=400,
            detail=f"試行数が少なすぎます (受信: {len(trials)}, 最低: 20)"
        )

    # ブロック4と7のデータが存在するか確認
    block4 = [t for t in trials if t.block_id == 4]
    block7 = [t for t in trials if t.block_id == 7]

    if not block4:
        raise HTTPException(status_code=400, detail="ブロック4（本番①）のデータがありません")
    if not block7:
        raise HTTPException(status_code=400, detail="ブロック7（本番②）のデータがありません")

    # ── スコア計算 ─────────────────────────────────────────
    result = compute_scores(trials)

    return IATScoreResponse(**result)


@router.get("/health")
async def health():
    """ヘルスチェック用エンドポイント"""
    return {"status": "ok", "service": "iat-scorer"}
