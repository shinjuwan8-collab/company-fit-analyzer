"""
test_scorer.py — scorer.py のユニットテスト

テスト対象:
  - _apply_penalty    : エラーペナルティ加算
  - _filter_rts       : 外れ値除去
  - _pooled_sd        : プール標準偏差
  - _interpret_d      : D-score解釈文
  - calc_d_score      : D-score本計算（Greenwald 2003準拠）
  - compute_scores    : 2軸スコア生成
  - _build_summary    : プロファイルサマリー

実行方法:
  python -m pytest test_scorer.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import math
import pytest
from models import TrialResult, AxisScore
from scorer import (
    _apply_penalty, _filter_rts, _pooled_sd,
    _interpret_d, calc_d_score, compute_scores, _build_summary,
    RT_MIN_MS, RT_MAX_MS, ERROR_PENALTY,
)


# ============================================================
# テストデータファクトリー
# ============================================================
def make_trial(
    rt: float,
    block_id: int = 4,
    correct: bool = True,
    word: str = "裁量",
    category: str = "autonomy_pos",
) -> TrialResult:
    """テスト用の試行データを生成するヘルパー"""
    return TrialResult(
        word=word,
        category=category,
        correct_key="left",
        pressed_key="left" if correct else "right",
        correct=correct,
        reaction_time_ms=rt,
        block_id=block_id,
    )


def make_block(rts: list, block_id: int, correct: bool = True) -> list:
    """指定RTリストで1ブロック分の試行を生成"""
    return [make_trial(rt, block_id=block_id, correct=correct) for rt in rts]


# ============================================================
# TC-01: _apply_penalty — ペナルティ加算
# ============================================================
class TestApplyPenalty:

    def test_correct_trial_no_penalty(self):
        """正解試行はRTをそのまま返す"""
        trial = make_trial(500.0, correct=True)
        assert _apply_penalty(trial) == 500.0

    def test_incorrect_trial_adds_penalty(self):
        """エラー試行は +400ms される"""
        trial = make_trial(500.0, correct=False)
        assert _apply_penalty(trial) == 500.0 + ERROR_PENALTY

    def test_penalty_value_is_400(self):
        """ペナルティ値が仕様通り400msであること"""
        assert ERROR_PENALTY == 400

    def test_zero_rt_with_penalty(self):
        """RT=0のエラー試行は 400ms になる"""
        trial = make_trial(0.0, correct=False)
        assert _apply_penalty(trial) == 400.0


# ============================================================
# TC-02: _filter_rts — 外れ値除去
# ============================================================
class TestFilterRts:

    def test_valid_rts_pass_through(self):
        """有効範囲内のRTはそのまま通る"""
        rts = [300.0, 500.0, 1000.0, 3000.0]
        assert _filter_rts(rts) == rts

    def test_too_fast_excluded(self):
        """300ms未満は除外される"""
        rts = [299.9, 300.0, 500.0]
        result = _filter_rts(rts)
        assert 299.9 not in result
        assert 300.0 in result

    def test_too_slow_excluded(self):
        """3000ms超は除外される"""
        rts = [500.0, 3000.0, 3000.1]
        result = _filter_rts(rts)
        assert 3000.1 not in result
        assert 3000.0 in result

    def test_all_invalid_returns_empty(self):
        """全て範囲外なら空リストを返す"""
        rts = [0.0, 100.0, 5000.0]
        assert _filter_rts(rts) == []

    def test_boundary_values_included(self):
        """境界値(300, 3000)は含まれる"""
        rts = [RT_MIN_MS, RT_MAX_MS]
        assert _filter_rts(rts) == [RT_MIN_MS, RT_MAX_MS]


# ============================================================
# TC-03: _pooled_sd — プール標準偏差
# ============================================================
class TestPooledSd:

    def test_known_sd(self):
        """既知の値でSDを検証"""
        a = [400.0, 500.0, 600.0]
        b = [700.0, 800.0, 900.0]
        sd = _pooled_sd(a, b)
        # combined = [400,500,600,700,800,900], mean=650, stdev≈182.57
        assert abs(sd - 182.57) < 1.0

    def test_single_element_returns_safe_value(self):
        """要素数が1以下でもゼロ除算にならない"""
        sd = _pooled_sd([500.0], [])
        assert sd == 1.0  # ゼロ除算防止値

    def test_identical_values_sd_is_zero(self):
        """全て同じ値はSD=0になる（実際はstdev=0）"""
        # statistics.stdev([500,500,500]) = 0.0
        sd = _pooled_sd([500.0, 500.0], [500.0, 500.0])
        assert sd == 0.0


# ============================================================
# TC-04: _interpret_d — D-score解釈文
# ============================================================
class TestInterpretD:

    def test_near_zero_is_neutral(self):
        """|D| < 0.15 は中立判定"""
        result = _interpret_d(0.05, "自律志向", "安定志向")
        assert "均等" in result

    def test_positive_small(self):
        """+0.25 は「やや」ポジティブ"""
        result = _interpret_d(0.25, "自律志向", "安定志向")
        assert "やや" in result
        assert "自律志向" in result

    def test_positive_medium(self):
        """+0.50 は「強い」ポジティブ"""
        result = _interpret_d(0.50, "自律志向", "安定志向")
        assert "強い" in result
        assert "自律志向" in result

    def test_positive_strong(self):
        """+0.70 は「非常に強い」ポジティブ"""
        result = _interpret_d(0.70, "自律志向", "安定志向")
        assert "非常に強い" in result

    def test_negative_direction(self):
        """マイナスDはネガティブラベルが付く"""
        result = _interpret_d(-0.50, "自律志向", "安定志向")
        assert "安定志向" in result

    def test_returns_string(self):
        """常に文字列を返す"""
        assert isinstance(_interpret_d(0.0, "A", "B"), str)


# ============================================================
# TC-05: calc_d_score — D-score計算のコア
# ============================================================
class TestCalcDScore:

    def _make_trials(self, b4_rts, b7_rts):
        """block4とblock7の試行を生成するショートカット"""
        return make_block(b4_rts, 4) + make_block(b7_rts, 7)

    def test_positive_d_when_block7_slower(self):
        """block7の平均RTがblock4より遅い → D > 0（自律志向）"""
        trials = self._make_trials(
            b4_rts=[500, 520, 480, 510, 490],  # 速い（自律語と達成語が同じキー）
            b7_rts=[700, 720, 680, 710, 690],  # 遅い
        )
        d, *_ = calc_d_score(trials)
        assert d > 0

    def test_negative_d_when_block4_slower(self):
        """block4の平均RTがblock7より遅い → D < 0（安定志向）"""
        trials = self._make_trials(
            b4_rts=[700, 720, 680, 710, 690],
            b7_rts=[500, 520, 480, 510, 490],
        )
        d, *_ = calc_d_score(trials)
        assert d < 0

    def test_zero_when_equal_rts(self):
        """両ブロックのRT平均が等しい → D ≈ 0"""
        rts = [500, 500, 500, 500, 500]
        trials = self._make_trials(rts, rts)
        d, *_ = calc_d_score(trials)
        assert abs(d) < 0.01

    def test_d_score_clipped_to_range(self):
        """D-scoreは -2.0〜+2.0 にクリップされる"""
        # 極端なRT差を作る
        trials = self._make_trials(
            b4_rts=[300] * 40,
            b7_rts=[3000] * 40,
        )
        d, *_ = calc_d_score(trials)
        assert -2.0 <= d <= 2.0

    def test_empty_trials_returns_zero(self):
        """試行データが空なら全て0を返す"""
        d, ma, mb, sd, cnt = calc_d_score([])
        assert d == 0.0
        assert cnt == 0

    def test_no_block4_returns_zero(self):
        """block4データがない場合は0を返す"""
        trials = make_block([500, 600, 550], block_id=7)
        d, *_ = calc_d_score(trials)
        assert d == 0.0

    def test_outliers_excluded_from_calculation(self):
        """外れ値(>3000ms)は除外されてD-scoreに影響しない"""
        # 外れ値なし
        trials_clean = self._make_trials(
            b4_rts=[500, 520, 480],
            b7_rts=[700, 720, 680],
        )
        d_clean, *_ = calc_d_score(trials_clean)

        # 外れ値を追加（block4に5000ms=除外される）
        trials_with_outlier = trials_clean + [make_trial(5000.0, block_id=4)]
        d_outlier, *_ = calc_d_score(trials_with_outlier)

        # 外れ値は除外されるので結果はほぼ同じ
        assert abs(d_clean - d_outlier) < 0.01

    def test_error_penalty_makes_rts_longer(self):
        """エラー試行があるとRTが長くなりD-scoreに影響する"""
        # 全問正解
        trials_correct = self._make_trials(
            b4_rts=[500, 500, 500],
            b7_rts=[700, 700, 700],
        )
        d_correct, *_ = calc_d_score(trials_correct)

        # block4にエラーを追加（RT+400でblock4が遅くなる → Dが小さくなる）
        trials_with_error = (
            make_block([500, 500, 500], block_id=4) +
            [make_trial(500.0, block_id=4, correct=False)] +  # 500+400=900ms
            make_block([700, 700, 700], block_id=7)
        )
        d_with_error, *_ = calc_d_score(trials_with_error)

        # エラーあり版はblock4が遅くなるのでDが小さくなる
        assert d_with_error < d_correct

    def test_returns_correct_types(self):
        """戻り値の型が正しいこと"""
        trials = self._make_trials([500]*5, [700]*5)
        result = calc_d_score(trials)
        d, mean_a, mean_b, sd, count = result
        assert isinstance(d, float)
        assert isinstance(count, int)

    def test_manual_d_score_calculation(self):
        """手計算した値と一致するか検証（最重要テスト）"""
        # block4: [400, 500, 600] → mean=500
        # block7: [700, 800, 900] → mean=800
        # combined: [400,500,600,700,800,900] → stdev≈182.57
        # D = (800 - 500) / 182.57 ≈ 1.643
        b4_rts = [400.0, 500.0, 600.0]
        b7_rts = [700.0, 800.0, 900.0]
        trials = self._make_trials(b4_rts, b7_rts)

        d, mean_a, mean_b, sd, count = calc_d_score(trials)

        assert abs(mean_a - 500.0) < 0.1
        assert abs(mean_b - 800.0) < 0.1
        assert abs(d - 1.643) < 0.01
        assert count == 6


# ============================================================
# TC-06: compute_scores — 2軸スコア統合
# ============================================================
class TestComputeScores:

    def _make_full_trials(self, b3_rts, b4_rts, b6_rts, b7_rts):
        return (
            make_block(b3_rts, 3) +
            make_block(b4_rts, 4) +
            make_block(b6_rts, 6) +
            make_block(b7_rts, 7)
        )

    def test_returns_required_keys(self):
        """必要なキーが全て含まれること"""
        trials = self._make_full_trials([500]*5, [500]*5, [700]*5, [700]*5)
        result = compute_scores(trials)
        assert "autonomy_score"    in result
        assert "achievement_score" in result
        assert "profile_summary"   in result
        assert "raw_block4_mean"   in result
        assert "raw_block7_mean"   in result

    def test_autonomy_score_is_axis_score(self):
        """autonomy_scoreがAxisScoreインスタンスであること"""
        trials = self._make_full_trials([500]*5, [500]*5, [700]*5, [700]*5)
        result = compute_scores(trials)
        assert isinstance(result["autonomy_score"], AxisScore)

    def test_d_score_within_valid_range(self):
        """D-scoreが-2.0〜+2.0の範囲内であること"""
        trials = self._make_full_trials([300]*10, [300]*10, [3000]*10, [3000]*10)
        result = compute_scores(trials)
        assert -2.0 <= result["autonomy_score"].d_score <= 2.0
        assert -2.0 <= result["achievement_score"].d_score <= 2.0

    def test_interpretation_is_string(self):
        """interpretationが文字列であること"""
        trials = self._make_full_trials([500]*5, [600]*5, [700]*5, [800]*5)
        result = compute_scores(trials)
        assert isinstance(result["autonomy_score"].interpretation, str)
        assert len(result["autonomy_score"].interpretation) > 0

    def test_profile_summary_matches_scores(self):
        """高D-scoreなら自律×達成タイプのサマリーになること"""
        # block7をblock4より大幅に遅くしてD>0を作る
        trials = self._make_full_trials(
            [600]*10, [400]*10, [800]*10, [1000]*10
        )
        result = compute_scores(trials)
        if result["autonomy_score"].d_score > 0.35:
            assert "自律" in result["profile_summary"]


# ============================================================
# TC-07: _build_summary — プロファイルサマリー
# ============================================================
class TestBuildSummary:

    def test_high_auto_high_achiev(self):
        assert "自律×達成タイプ" in _build_summary(0.8, 0.8)

    def test_high_auto_low_achiev(self):
        assert "独立志向タイプ" in _build_summary(0.8, 0.1)

    def test_low_auto_high_achiev(self):
        assert "目標志向タイプ" in _build_summary(0.1, 0.8)

    def test_both_negative(self):
        assert "チーム志向タイプ" in _build_summary(-0.8, -0.8)

    def test_both_neutral(self):
        assert "バランスタイプ" in _build_summary(0.0, 0.0)

    def test_returns_nonempty_string(self):
        """常に空でない文字列を返す"""
        for auto in [-1.0, -0.3, 0.0, 0.3, 1.0]:
            for achiev in [-1.0, -0.3, 0.0, 0.3, 1.0]:
                result = _build_summary(auto, achiev)
                assert isinstance(result, str)
                assert len(result) > 0


# ============================================================
# TC-08: 統合テスト — 典型的なIATシナリオ
# ============================================================
class TestIntegration:

    def test_strong_autonomy_profile(self):
        """
        自律志向が強い被験者のシナリオ:
        - block4（自律+達成 / 制約+安定）: 速い（500ms前後）
        - block7（制約+達成 / 自律+安定）: 遅い（800ms前後）
        → D > 0.5 になるはず
        """
        import random
        random.seed(42)

        def jitter(base, n=20):
            return [base + random.uniform(-30, 30) for _ in range(n)]

        trials = (
            make_block(jitter(550, 20), block_id=3) +
            make_block(jitter(500, 40), block_id=4) +  # 速い
            make_block(jitter(750, 20), block_id=6) +
            make_block(jitter(800, 40), block_id=7)   # 遅い
        )

        result = compute_scores(trials)
        auto_d = result["autonomy_score"].d_score

        assert auto_d > 0.3, f"自律志向シナリオでD={auto_d:.3f}（0.3超を期待）"
        assert "自律" in result["profile_summary"]

    def test_stability_profile(self):
        """
        安定志向が強い被験者のシナリオ:
        - block4: 遅い（制約語と達成語の組み合わせに戸惑う）
        - block7: 速い（安定語側に親和性が高い）
        → D < -0.3 になるはず
        """
        import random
        random.seed(99)

        def jitter(base, n=20):
            return [base + random.uniform(-30, 30) for _ in range(n)]

        trials = (
            make_block(jitter(750, 20), block_id=3) +
            make_block(jitter(800, 40), block_id=4) +  # 遅い
            make_block(jitter(550, 20), block_id=6) +
            make_block(jitter(500, 40), block_id=7)   # 速い
        )

        result = compute_scores(trials)
        auto_d = result["autonomy_score"].d_score

        assert auto_d < -0.3, f"安定志向シナリオでD={auto_d:.3f}（-0.3未満を期待）"

    def test_full_pipeline_180_trials(self):
        """
        180試行フル版のパイプライン検証
        全フェーズ分のデータを生成して compute_scores が正常完了するか
        """
        import random
        random.seed(7)

        def rand_rt(n):
            return [random.uniform(350, 900) for _ in range(n)]

        trials = (
            make_block(rand_rt(20), block_id=1) +
            make_block(rand_rt(20), block_id=2) +
            make_block(rand_rt(20), block_id=3) +
            make_block(rand_rt(40), block_id=4) +
            make_block(rand_rt(20), block_id=5) +
            make_block(rand_rt(20), block_id=6) +
            make_block(rand_rt(40), block_id=7)
        )

        assert len(trials) == 180

        result = compute_scores(trials)

        # 全フィールドが揃っていること
        assert result["autonomy_score"].trial_count > 0
        assert result["achievement_score"].trial_count > 0
        assert len(result["profile_summary"]) > 10
        assert -2.0 <= result["autonomy_score"].d_score <= 2.0
