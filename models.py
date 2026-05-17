"""
models.py — IATツール データモデル定義
リクエスト/レスポンスの型をPydanticで定義する
"""

from pydantic import BaseModel, Field
from typing import List, Optional


# ── IATスコア送信 ──────────────────────────────────────────────
class TrialResult(BaseModel):
    """1試行分の計測データ"""
    word:        str            # 提示単語
    category:    str            # 単語カテゴリ (autonomy_pos / achieve_neg など)
    correct_key: str            # 正解キー ("left" | "right")
    pressed_key: str            # 実際に押したキー
    correct:     bool           # 正解/不正解
    reaction_time_ms: float     # 反応時間 ms (performance.now() 計測値)
    block_id:    int            # フェーズID (1〜7)


class IATSubmitRequest(BaseModel):
    """フロントエンドから送信される全試行データ"""
    trials: List[TrialResult]
    session_id: Optional[str] = None  # 将来的なセッション管理用（現在は使わない）


# ── D-scoreレスポンス ──────────────────────────────────────────
class AxisScore(BaseModel):
    """1軸分のスコアと解釈"""
    d_score:      float
    mean_block_a: float   # 合体ブロック①の平均RT (ms)
    mean_block_b: float   # 合体ブロック②の平均RT (ms)
    sd_pooled:    float   # プール標準偏差
    trial_count:  int     # 有効試行数
    interpretation: str   # "非常に強い自律志向" など


class IATScoreResponse(BaseModel):
    """D-score計算結果"""
    autonomy_score:  AxisScore
    achievement_score: AxisScore
    profile_summary: str          # 両軸を合わせた総合コメント
    raw_block4_mean: float        # デバッグ用
    raw_block7_mean: float        # デバッグ用


# ── 企業マッチング ─────────────────────────────────────────────
class MatchingRequest(BaseModel):
    """マッチングAPIへのリクエスト"""
    autonomy_d_score:    float = Field(..., ge=-2.0, le=2.0)
    achievement_d_score: float = Field(..., ge=-2.0, le=2.0)
    top_n: int = Field(default=5, ge=1, le=10)  # 上位何社を返すか


class CompanyMatch(BaseModel):
    """マッチした企業1社分のデータ"""
    rank:          int
    company_name:  str
    match_score:   float          # 0.0〜1.0
    match_percent: int            # 0〜100 (表示用)
    reason:        str            # AIによるマッチ理由コメント
    culture_tags:  List[str]      # ["裁量大", "成果主義", ...] など


class MatchingResponse(BaseModel):
    """企業マッチング結果"""
    matches:         List[CompanyMatch]
    profile_label:   str    # "自律×達成タイプ" など
    search_summary:  str    # AIが検索した企業情報の要約
