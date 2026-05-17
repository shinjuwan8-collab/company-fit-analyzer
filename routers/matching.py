"""
routers/matching.py — 企業マッチングエンドポイント

POST /api/matching/search
    D-scoreプロファイルをClaude APIに送り、
    Web検索で企業情報を取得してマッチング結果を返す。
"""

import os
import json
import re
from fastapi import APIRouter, HTTPException
import anthropic

from models import MatchingRequest, MatchingResponse, CompanyMatch

router = APIRouter(prefix="/api/matching", tags=["Matching"])


def _build_profile_label(auto_d: float, achiev_d: float) -> str:
    """D-scoreからプロファイルラベルを生成"""
    a = "自律" if auto_d > 0.2 else ("安定" if auto_d < -0.2 else "中立")
    b = "達成" if achiev_d > 0.2 else ("安定" if achiev_d < -0.2 else "中立")
    return f"{a}×{b}タイプ"


def _build_prompt(auto_d: float, achiev_d: float, top_n: int) -> str:
    """Claude APIへ送るプロンプトを構築"""
    return f"""
あなたは就職活動のキャリアカウンセラーです。
以下のIAT（潜在連合テスト）の結果をもとに、候補者に最も合う日本の企業を{top_n}社選定してください。

## 候補者の潜在プロファイル（D-score）
- 自律性スコア: {auto_d:+.2f}（+が自律志向、−が安定・管理志向、範囲-2.0〜+2.0）
- 達成動機スコア: {achiev_d:+.2f}（+が達成・挑戦志向、−が安定・維持志向）

## 作業手順
1. まずWeb検索を使って「日本 IT企業 社風 裁量 成果主義 働き方」などのキーワードで
   候補者のプロファイルに合いそうな日本企業の情報を3〜4回検索してください
2. 収集した情報をもとに、候補者のD-scoreプロファイルと企業文化のマッチ度を分析してください
3. 上位{top_n}社を選んで、以下のJSON形式で出力してください

## 出力形式（必ずこのJSONのみを出力すること）
{{
  "matches": [
    {{
      "rank": 1,
      "company_name": "企業名",
      "match_score": 0.92,
      "match_percent": 92,
      "reason": "マッチ理由を2〜3文で具体的に説明（企業の文化・制度・求める人物像と候補者プロファイルの対応を明示）",
      "culture_tags": ["裁量大", "成果主義", "挑戦文化"]
    }}
  ],
  "profile_label": "自律×達成タイプ",
  "search_summary": "検索で得た企業情報の要約（3〜4文）"
}}

注意:
- match_scoreは0.0〜1.0の小数
- culture_tagsは2〜4個の短いラベル
- 実在する日本企業のみを選ぶ
- JSONのみ出力し、前後の説明文は不要
"""


@router.post("/search", response_model=MatchingResponse)
async def search_matching(body: MatchingRequest) -> MatchingResponse:
    """
    D-scoreをもとにClaude APIで企業マッチングを実行する。

    Claude APIのWeb検索ツールを使って企業情報をリアルタイム取得し、
    マッチ度を算出してランキング形式で返す。
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY が設定されていません。.envファイルを確認してください。"
        )

    client = anthropic.Anthropic(api_key=api_key)

    prompt = _build_prompt(
        auto_d   = body.autonomy_d_score,
        achiev_d = body.achievement_d_score,
        top_n    = body.top_n,
    )

    # ── Claude API呼び出し（Web検索ツール付き） ─────────────
    try:
        response = client.messages.create(
            model      = "claude-sonnet-4-20250514",
            max_tokens = 2000,
            tools      = [{"type": "web_search_20250305", "name": "web_search"}],
            messages   = [{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=401, detail="APIキーが無効です")
    except anthropic.RateLimitError:
        raise HTTPException(status_code=429, detail="APIレート制限に達しました。しばらく待ってから再試行してください")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude API呼び出しエラー: {str(e)}")

    # ── レスポンスからJSONを抽出 ──────────────────────────────
    raw_text = ""
    for block in response.content:
        if block.type == "text":
            raw_text += block.text

    if not raw_text:
        raise HTTPException(status_code=502, detail="Claude APIからテキストレスポンスが得られませんでした")

    # JSONを抽出（```json ... ``` のコードブロックにも対応）
    json_match = re.search(r'\{[\s\S]*\}', raw_text)
    if not json_match:
        raise HTTPException(status_code=502, detail=f"JSONの抽出に失敗しました。レスポンス: {raw_text[:200]}")

    try:
        data = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail=f"JSONパースエラー: {e}")

    # ── レスポンスオブジェクトを構築 ──────────────────────────
    try:
        matches = [CompanyMatch(**m) for m in data.get("matches", [])]
        return MatchingResponse(
            matches        = matches,
            profile_label  = data.get("profile_label", _build_profile_label(body.autonomy_d_score, body.achievement_d_score)),
            search_summary = data.get("search_summary", ""),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"レスポンス変換エラー: {e}")


@router.get("/health")
async def health():
    return {"status": "ok", "service": "matching"}
