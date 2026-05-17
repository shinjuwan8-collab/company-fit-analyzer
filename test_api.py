"""
test_api.py — FastAPI エンドポイントのテスト

テスト対象:
  - POST /api/iat/submit  : バリデーション・スコア計算
  - GET  /api/iat/health  : ヘルスチェック
  - GET  /api             : ルートエンドポイント

実行方法:
  python -m pytest test_api.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


# ============================================================
# テストデータファクトリー
# ============================================================
def make_trial_dict(rt=500.0, block_id=4, correct=True):
    return {
        "word": "裁量",
        "category": "autonomy_pos",
        "correct_key": "left",
        "pressed_key": "left" if correct else "right",
        "correct": correct,
        "reaction_time_ms": rt,
        "block_id": block_id,
    }


def make_block_dicts(rts: list, block_id: int) -> list:
    return [make_trial_dict(rt=rt, block_id=block_id) for rt in rts]


def make_minimal_valid_payload():
    """最低限有効なリクエストボディを生成（block4+7各5試行）"""
    trials = (
        make_block_dicts([500, 520, 480, 510, 490], block_id=4) +
        make_block_dicts([700, 720, 680, 710, 690], block_id=7)
    )
    return {"trials": trials}


def make_full_payload():
    """全7フェーズ180試行の完全なリクエストボディを生成"""
    import random
    random.seed(42)

    def rand_block(n, base_rt):
        return make_block_dicts(
            [base_rt + random.uniform(-50, 50) for _ in range(n)],
            block_id=0  # あとで上書き
        )

    trials = []
    configs = [(1,20,600),(2,20,600),(3,20,580),(4,40,500),(5,20,620),(6,20,750),(7,40,800)]
    for block_id, n, base in configs:
        block = make_block_dicts(
            [base + random.uniform(-50, 50) for _ in range(n)],
            block_id=block_id
        )
        trials.extend(block)

    return {"trials": trials}


# ============================================================
# TC-A: ヘルスチェック・ルート
# ============================================================
class TestHealthAndRoot:

    def test_root_returns_200(self):
        """GET /api が200を返す"""
        res = client.get("/api")
        assert res.status_code == 200

    def test_root_has_endpoints_info(self):
        """ルートレスポンスにエンドポイント情報が含まれる"""
        res = client.get("/api")
        data = res.json()
        assert "endpoints" in data

    def test_iat_health(self):
        """GET /api/iat/health が ok を返す"""
        res = client.get("/api/iat/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

    def test_matching_health(self):
        """GET /api/matching/health が ok を返す"""
        res = client.get("/api/matching/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"


# ============================================================
# TC-B: POST /api/iat/submit — 正常系
# ============================================================
class TestIatSubmitSuccess:

    def test_minimal_valid_request_returns_200(self):
        """最低限有効なリクエストで200が返る"""
        res = client.post("/api/iat/submit", json=make_minimal_valid_payload())
        assert res.status_code == 200

    def test_response_has_required_fields(self):
        """レスポンスに必須フィールドが全て含まれる"""
        res = client.post("/api/iat/submit", json=make_minimal_valid_payload())
        data = res.json()
        assert "autonomy_score"    in data
        assert "achievement_score" in data
        assert "profile_summary"   in data
        assert "raw_block4_mean"   in data
        assert "raw_block7_mean"   in data

    def test_autonomy_score_has_d_score(self):
        """autonomy_scoreにd_scoreが含まれる"""
        res = client.post("/api/iat/submit", json=make_minimal_valid_payload())
        data = res.json()
        assert "d_score" in data["autonomy_score"]

    def test_d_score_is_float(self):
        """D-scoreがfloatであること"""
        res = client.post("/api/iat/submit", json=make_minimal_valid_payload())
        data = res.json()
        assert isinstance(data["autonomy_score"]["d_score"], float)

    def test_d_score_within_range(self):
        """D-scoreが-2.0〜+2.0の範囲内"""
        res = client.post("/api/iat/submit", json=make_minimal_valid_payload())
        data = res.json()
        d = data["autonomy_score"]["d_score"]
        assert -2.0 <= d <= 2.0

    def test_interpretation_is_nonempty_string(self):
        """interpretationが空でない文字列"""
        res = client.post("/api/iat/submit", json=make_minimal_valid_payload())
        data = res.json()
        interp = data["autonomy_score"]["interpretation"]
        assert isinstance(interp, str)
        assert len(interp) > 0

    def test_profile_summary_is_nonempty_string(self):
        """profile_summaryが空でない文字列"""
        res = client.post("/api/iat/submit", json=make_minimal_valid_payload())
        data = res.json()
        assert isinstance(data["profile_summary"], str)
        assert len(data["profile_summary"]) > 10

    def test_full_180_trials_returns_200(self):
        """180試行フルデータで200が返る"""
        res = client.post("/api/iat/submit", json=make_full_payload())
        assert res.status_code == 200

    def test_full_payload_trial_count_is_positive(self):
        """180試行版でtrial_countが正の整数"""
        res = client.post("/api/iat/submit", json=make_full_payload())
        data = res.json()
        assert data["autonomy_score"]["trial_count"] > 0

    def test_block4_mean_is_positive(self):
        """block4の平均RTが正の値"""
        res = client.post("/api/iat/submit", json=make_minimal_valid_payload())
        data = res.json()
        assert data["raw_block4_mean"] > 0

    def test_positive_d_when_block7_slower(self):
        """block7が遅い場合D>0になること（自律志向の検出）"""
        payload = {
            "trials": (
                make_block_dicts([400]*10, block_id=4) +  # 速い
                make_block_dicts([900]*10, block_id=7)    # 遅い
            )
        }
        res = client.post("/api/iat/submit", json=payload)
        data = res.json()
        assert data["autonomy_score"]["d_score"] > 0

    def test_negative_d_when_block4_slower(self):
        """block4が遅い場合D<0になること（安定志向の検出）"""
        payload = {
            "trials": (
                make_block_dicts([900]*10, block_id=4) +  # 遅い
                make_block_dicts([400]*10, block_id=7)    # 速い
            )
        }
        res = client.post("/api/iat/submit", json=payload)
        data = res.json()
        assert data["autonomy_score"]["d_score"] < 0

    def test_with_error_trials(self):
        """エラー試行が含まれていても正常に処理される"""
        payload = {
            "trials": (
                [make_trial_dict(rt=500, block_id=4, correct=False)] * 5 +
                make_block_dicts([500]*5, block_id=4) +
                make_block_dicts([700]*10, block_id=7)
            )
        }
        res = client.post("/api/iat/submit", json=payload)
        assert res.status_code == 200


# ============================================================
# TC-C: POST /api/iat/submit — バリデーション異常系
# ============================================================
class TestIatSubmitValidation:

    def test_empty_trials_returns_400(self):
        """試行データが空なら400"""
        res = client.post("/api/iat/submit", json={"trials": []})
        assert res.status_code == 400

    def test_too_few_trials_returns_400(self):
        """試行数が少なすぎる（<20）なら400"""
        res = client.post("/api/iat/submit", json={
            "trials": [make_trial_dict()] * 5
        })
        assert res.status_code == 400

    def test_missing_trials_key_returns_422(self):
        """trialsキーがない場合422（FastAPIのバリデーションエラー）"""
        res = client.post("/api/iat/submit", json={})
        assert res.status_code == 422

    def test_invalid_body_type_returns_422(self):
        """不正な型のボディは422"""
        res = client.post("/api/iat/submit", json={"trials": "not_a_list"})
        assert res.status_code == 422

    def test_no_block4_returns_400(self):
        """block4データがない場合400"""
        payload = {
            "trials": make_block_dicts([500]*20, block_id=7)  # block7のみ
        }
        res = client.post("/api/iat/submit", json=payload)
        assert res.status_code == 400

    def test_no_block7_returns_400(self):
        """block7データがない場合400"""
        payload = {
            "trials": make_block_dicts([500]*20, block_id=4)  # block4のみ
        }
        res = client.post("/api/iat/submit", json=payload)
        assert res.status_code == 400

    def test_error_message_in_response(self):
        """エラーレスポンスに detail フィールドが含まれる"""
        res = client.post("/api/iat/submit", json={"trials": []})
        assert "detail" in res.json()


# ============================================================
# TC-D: POST /api/matching/search — バリデーション
# ============================================================
class TestMatchingValidation:

    def test_d_score_out_of_range_returns_422(self):
        """D-scoreが範囲外(-2.0〜2.0)なら422"""
        res = client.post("/api/matching/search", json={
            "autonomy_d_score":    5.0,  # 範囲外
            "achievement_d_score": 0.5,
            "top_n": 5,
        })
        assert res.status_code == 422

    def test_top_n_zero_returns_422(self):
        """top_n=0は422"""
        res = client.post("/api/matching/search", json={
            "autonomy_d_score":    0.5,
            "achievement_d_score": 0.5,
            "top_n": 0,
        })
        assert res.status_code == 422

    def test_top_n_over_10_returns_422(self):
        """top_n>10は422"""
        res = client.post("/api/matching/search", json={
            "autonomy_d_score":    0.5,
            "achievement_d_score": 0.5,
            "top_n": 11,
        })
        assert res.status_code == 422

    def test_missing_api_key_returns_500(self):
        """APIキー未設定なら500（環境変数なし状態）"""
        import os
        original = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            res = client.post("/api/matching/search", json={
                "autonomy_d_score":    0.5,
                "achievement_d_score": 0.5,
                "top_n": 3,
            })
            assert res.status_code == 500
            assert "ANTHROPIC_API_KEY" in res.json()["detail"]
        finally:
            if original:
                os.environ["ANTHROPIC_API_KEY"] = original
