"""
scorer.py — IAT D-score 算出モジュール
Greenwald, Nosek & Banaji (2003) の改良D法に準拠

D = (mean_RT_blockB - mean_RT_blockA) / SD_pooled

blockA = フェーズ4（自律+達成 / 制約+安定）
blockB = フェーズ7（制約+達成 / 自律+安定）

D > 0  → 自律・達成への潜在的ポジティブ態度が強い
D < 0  → 安定・制約環境への潜在的ポジティブ態度が強い
"""

import math
import statistics
from typing import List, Tuple

from models import TrialResult, AxisScore


# ── 定数 ─────────────────────────────────────────────────────
RT_MIN_MS     = 300    # 300ms未満は除外（速すぎ = 先行押し）
RT_MAX_MS     = 3000   # 3000ms超は除外（遅すぎ = 離席等）
ERROR_PENALTY = 400    # エラー試行へのペナルティ加算 (ms)

BLOCK_A_ID = 4   # 合体ブロック① 本番フェーズ
BLOCK_B_ID = 7   # 合体ブロック② 本番フェーズ


# ── ユーティリティ ────────────────────────────────────────────
def _apply_penalty(trial: TrialResult) -> float:
    """エラー試行にペナルティを加算して返す"""
    rt = trial.reaction_time_ms
    if not trial.correct:
        rt += ERROR_PENALTY
    return rt


def _filter_rts(rts: List[float]) -> List[float]:
    """外れ値を除外する (RT_MIN_MS〜RT_MAX_MS の範囲のみ残す)"""
    return [rt for rt in rts if RT_MIN_MS <= rt <= RT_MAX_MS]


def _mean(values: List[float]) -> float:
    return statistics.mean(values) if values else 0.0


def _pooled_sd(a: List[float], b: List[float]) -> float:
    """2グループをプールした標準偏差"""
    combined = a + b
    if len(combined) < 2:
        return 1.0  # ゼロ除算防止
    return statistics.stdev(combined)


def _interpret_d(d: float, pos_label: str, neg_label: str) -> str:
    """D-scoreを日本語の解釈文に変換する"""
    abs_d = abs(d)
    if abs_d < 0.15:
        strength = "ほぼ中立"
        direction = ""
    elif abs_d < 0.35:
        strength = "やや"
        direction = pos_label if d > 0 else neg_label
    elif abs_d < 0.65:
        strength = "強い"
        direction = pos_label if d > 0 else neg_label
    else:
        strength = "非常に強い"
        direction = pos_label if d > 0 else neg_label

    if abs_d < 0.15:
        return f"{pos_label}・{neg_label}への態度はほぼ均等です"
    return f"{strength}{direction}傾向があります"


# ── メイン計算関数 ────────────────────────────────────────────
def calc_d_score(trials: List[TrialResult]) -> Tuple[float, float, float, float, int]:
    """
    D-scoreを計算して返す。

    Returns:
        (d_score, mean_a, mean_b, sd_pooled, valid_count)
    """
    # ブロックごとに分類
    block_a_raw = [_apply_penalty(t) for t in trials if t.block_id == BLOCK_A_ID]
    block_b_raw = [_apply_penalty(t) for t in trials if t.block_id == BLOCK_B_ID]

    # 外れ値除去
    block_a = _filter_rts(block_a_raw)
    block_b = _filter_rts(block_b_raw)

    if not block_a or not block_b:
        return 0.0, 0.0, 0.0, 0.0, 0

    mean_a   = _mean(block_a)
    mean_b   = _mean(block_b)
    sd       = _pooled_sd(block_a, block_b)
    d        = (mean_b - mean_a) / sd
    count    = len(block_a) + len(block_b)

    # D-scoreは通常 -2.0〜+2.0 の範囲にクリップ
    d = max(-2.0, min(2.0, d))

    return round(d, 4), round(mean_a, 1), round(mean_b, 1), round(sd, 1), count


def compute_scores(trials: List[TrialResult]) -> dict:
    """
    全試行データから AxisScore x2 を計算して返す。

    今回の設計では1回のIATで「自律性」と「達成動機」を
    同時に測定しているため、同じブロックデータから
    2軸のスコアを導出する（実験的アプローチ）。

    本来は軸ごとに独立したIATを実施するのが望ましいが、
    ユーザー負担を減らすためにこの近似を採用している。
    """
    d, mean_a, mean_b, sd, count = calc_d_score(trials)

    # ── 自律性スコア ──────────────────────────────────────────
    # ブロック4: 自律+達成 vs 制約+安定
    # ブロック7: 制約+達成 vs 自律+安定
    # → 自律語とポジティブが同じ側に来るブロック4が速い人 = 自律志向
    autonomy_d = round(d + 0.0, 4)   # 主軸のD-score

    # ── 達成動機スコア ────────────────────────────────────────
    # 達成語は両ブロックに含まれるため、ブロック内でのRT差で推定
    # 練習ブロック(3,6)との比較で達成動機の寄与を分離する
    practice_a = [_apply_penalty(t) for t in trials if t.block_id == 3]
    practice_b = [_apply_penalty(t) for t in trials if t.block_id == 6]
    p_a = _filter_rts(practice_a)
    p_b = _filter_rts(practice_b)

    if p_a and p_b:
        prac_d = (_mean(p_b) - _mean(p_a)) / max(_pooled_sd(p_a, p_b), 1.0)
        # 本番ブロックと練習ブロックの差分から達成動機スコアを推定
        achievement_d = round((d + prac_d) / 2, 4)
    else:
        achievement_d = round(d * 0.85, 4)  # フォールバック

    # ── スコアオブジェクト作成 ────────────────────────────────
    autonomy = AxisScore(
        d_score      = autonomy_d,
        mean_block_a = mean_a,
        mean_block_b = mean_b,
        sd_pooled    = sd,
        trial_count  = count,
        interpretation = _interpret_d(autonomy_d, "自律志向", "安定・管理志向"),
    )

    achievement = AxisScore(
        d_score      = achievement_d,
        mean_block_a = mean_a,
        mean_block_b = mean_b,
        sd_pooled    = sd,
        trial_count  = count,
        interpretation = _interpret_d(achievement_d, "達成・挑戦志向", "安定・維持志向"),
    )

    # ── プロファイルサマリー ──────────────────────────────────
    summary = _build_summary(autonomy_d, achievement_d)

    return {
        "autonomy_score":     autonomy,
        "achievement_score":  achievement,
        "profile_summary":    summary,
        "raw_block4_mean":    mean_a,
        "raw_block7_mean":    mean_b,
    }


def _build_summary(auto_d: float, achiev_d: float) -> str:
    """両軸スコアから総合プロファイルコメントを生成"""
    high_auto   = auto_d   > 0.35
    high_achiev = achiev_d > 0.35
    low_auto    = auto_d   < -0.35
    low_achiev  = achiev_d < -0.35

    if high_auto and high_achiev:
        return (
            "自律性・達成動機ともに高い「自律×達成タイプ」です。"
            "裁量が大きく、成果でフェアに評価される環境で最も力を発揮できます。"
            "スタートアップや成長企業、実力主義の外資系が高マッチになりやすいです。"
        )
    elif high_auto and not high_achiev:
        return (
            "自律性が高い「独立志向タイプ」です。"
            "指示より自己判断を好み、担当領域に裁量が与えられる環境が合います。"
            "専門職採用や少数精鋭チームのある企業が向いています。"
        )
    elif not high_auto and high_achiev:
        return (
            "達成動機が高い「目標志向タイプ」です。"
            "明確な目標と成長機会がある環境でモチベーションが上がります。"
            "営業・コンサル・事業開発などの職種・企業が向いています。"
        )
    elif low_auto and low_achiev:
        return (
            "安定・協調を重視する「チーム志向タイプ」です。"
            "役割が明確で、チームワークを大切にする組織文化と相性が良いです。"
            "大手メーカー・公共系・安定基盤のあるBtoB企業などが向いています。"
        )
    else:
        return (
            "自律性・達成動機ともに中程度の「バランスタイプ」です。"
            "特定の環境への強い偏りがなく、多様な職場環境に適応しやすい傾向があります。"
            "業界・職種の幅広い選択肢を検討してみてください。"
        )
