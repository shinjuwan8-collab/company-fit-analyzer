"""
routers/matching.py — 企業マッチングエンドポイント
"""

import os
import json
import re
from fastapi import APIRouter, HTTPException
import anthropic

from models import MatchingRequest, MatchingResponse, CompanyMatch

router = APIRouter(prefix="/api/matching", tags=["Matching"])


def _build_profile_label(auto_d: float, achiev_d: float) -> str:
    a = "自律" if auto_d > 0.2 else ("安定" if auto_d < -0.2 else "中立")
    b = "達成" if achiev_d > 0.2 else ("安定" if achiev_d < -0.2 else "中立")
    return f"{a}×{b}タイプ"


def _extract_json(text: str) -> dict:
    """
    Claude APIのレスポンステキストからJSONを確実に抽出する。
    複数の方法を順番に試みる。
    """
    # 方法1: ```json ... ``` ブロックを探す
    code_block = re.search(r'```json\s*([\s\S]*?)\s*```', text)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except json.JSONDecodeError:
            pass

    # 方法2: ``` ... ``` ブロックを探す（jsonなし）
    code_block2 = re.search(r'```\s*([\s\S]*?)\s*```', text)
    if code_block2:
        try:
            return json.loads(code_block2.group(1))
        except json.JSONDecodeError:
            pass

    # 方法3: { で始まり } で終わる最大のブロックを探す
    # 括弧の深さを追跡して正確に抽出する
    start = text.find('{')
    if start != -1:
        depth = 0
        in_string = False
        escape_next = False
        for i, ch in enumerate(text[start:], start):
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    candidate = text[start:i+1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        # 制御文字などを除去して再試行
                        cleaned = re.sub(r'[\x00-\x1f\x7f]', ' ', candidate)
                        cleaned = re.sub(r',\s*}', '}', cleaned)
                        cleaned = re.sub(r',\s*]', ']', cleaned)
                        try:
                            return json.loads(cleaned)
                        except json.JSONDecodeError:
                            break

    raise ValueError(f"JSONを抽出できませんでした。レスポンス冒頭: {text[:300]}")


def _build_prompt(auto_d: float, achiev_d: float, top_n: int) -> str:
    return f"""あなたは就職活動のキャリアカウンセラーです。
以下のIATの結果をもとに、候補者に最も合う日本の企業を{top_n}社選定してください。

候補者プロファイル:
- 自律性スコア: {auto_d:+.2f}（+が自律志向、−が安定・管理志向）
- 達成動機スコア: {achiev_d:+.2f}（+が達成・挑戦志向、−が安定・維持志向）

Web検索で企業情報を調査し、以下のJSON形式のみで回答してください。
説明文・前置き・コードブロックは不要です。JSONだけ出力してください。

{{"matches":[{{"rank":1,"company_name":"企業名","match_score":0.92,"match_percent":92,"reason":"マッチ理由を2文で","culture_tags":["裁量大","成果主義"]}}],"profile_label":"自律×達成タイプ","search_summary":"検索結果の要約を3文で"}}

上記の形式で{top_n}社分のmatchesを含むJSONを出力してください。"""


@router.post("/search", response_model=MatchingResponse)
async def search_matching(body: MatchingRequest) -> MatchingResponse:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY が設定されていません。"
        )

    client = anthropic.Anthropic(api_key=api_key)

    prompt = _build_prompt(
        auto_d   = body.autonomy_d_score,
        achiev_d = body.achievement_d_score,
        top_n    = body.top_n,
    )

    try:
        response = client.messages.create(
            model      = "claude-sonnet-4-6",
            max_tokens = 2000,
            tools      = [{"type": "web_search_20250305", "name": "web_search"}],
            messages   = [{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=401, detail="APIキーが無効です")
    except anthropic.RateLimitError:
        raise HTTPException(status_code=429, detail="APIレート制限に達しました")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude API呼び出しエラー: {str(e)}")

    # テキストブロックを結合
    raw_text = ""
    for block in response.content:
        if block.type == "text":
            raw_text += block.text

    if not raw_text:
        raise HTTPException(status_code=502, detail="Claude APIからテキストレスポンスが得られませんでした")

    # JSON抽出
    try:
        data = _extract_json(raw_text)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))

    # レスポンス構築
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
