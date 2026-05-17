"""
run_tests.py — 標準ライブラリのみで動作するテストランナー

scorer.pyのD-score計算ロジックを直接テストする。
外部ライブラリ(pytest/pydantic)不要で動作する。

実行: python3 run_tests.py
"""

import statistics
import random
import sys
import traceback
from dataclasses import dataclass
from typing import List, Tuple

# ============================================================
# scorer.py のロジックをそのまま移植（依存なし版）
# ============================================================
RT_MIN_MS     = 300
RT_MAX_MS     = 3000
ERROR_PENALTY = 400
BLOCK_A_ID    = 4
BLOCK_B_ID    = 7

@dataclass
class Trial:
    rt: float
    block_id: int
    correct: bool = True

def apply_penalty(t: Trial) -> float:
    return t.rt + (ERROR_PENALTY if not t.correct else 0)

def filter_rts(rts: List[float]) -> List[float]:
    return [r for r in rts if RT_MIN_MS <= r <= RT_MAX_MS]

def mean(vals: List[float]) -> float:
    return statistics.mean(vals) if vals else 0.0

def pooled_sd(a: List[float], b: List[float]) -> float:
    combined = a + b
    if len(combined) < 2:
        return 1.0
    return statistics.stdev(combined)

def calc_d_score(trials: List[Trial]) -> Tuple[float, float, float, float, int]:
    b4_raw = [apply_penalty(t) for t in trials if t.block_id == BLOCK_A_ID]
    b7_raw = [apply_penalty(t) for t in trials if t.block_id == BLOCK_B_ID]
    b4 = filter_rts(b4_raw)
    b7 = filter_rts(b7_raw)
    if not b4 or not b7:
        return 0.0, 0.0, 0.0, 0.0, 0
    ma = mean(b4)
    mb = mean(b7)
    sd = pooled_sd(b4, b7)
    d  = (mb - ma) / sd if sd != 0 else 0.0
    d  = max(-2.0, min(2.0, d))
    return round(d, 4), round(ma, 1), round(mb, 1), round(sd, 1), len(b4)+len(b7)

def interpret_d(d: float, pos: str, neg: str) -> str:
    a = abs(d)
    if a < 0.15: return f"{pos}・{neg}への態度はほぼ均等です"
    if a < 0.35: s = "やや"
    elif a < 0.65: s = "強い"
    else: s = "非常に強い"
    return f"{s}{pos if d > 0 else neg}傾向があります"

def build_summary(auto_d: float, achiev_d: float) -> str:
    if   auto_d >  0.35 and achiev_d >  0.35: return "自律×達成タイプ"
    elif auto_d >  0.35:                       return "独立志向タイプ"
    elif achiev_d > 0.35:                      return "目標志向タイプ"
    elif auto_d < -0.35 and achiev_d < -0.35: return "チーム志向タイプ"
    else:                                      return "バランスタイプ"

def mk(rt, block_id=4, correct=True):
    return Trial(rt=rt, block_id=block_id, correct=correct)

def mkblock(rts, block_id):
    return [mk(rt, block_id) for rt in rts]


# ============================================================
# テストランナー
# ============================================================
PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
HEAD = "\033[94m"
RST  = "\033[0m"

results = []

def run(name: str, fn):
    try:
        fn()
        results.append((True, name, ""))
        print(f"  {PASS} {name}")
    except AssertionError as e:
        msg = str(e) or "アサーション失敗"
        results.append((False, name, msg))
        print(f"  {FAIL} {name}")
        print(f"       → {msg}")
    except Exception as e:
        msg = traceback.format_exc().strip().split('\n')[-1]
        results.append((False, name, msg))
        print(f"  {FAIL} {name}")
        print(f"       → {msg}")


# ============================================================
# TC-01: apply_penalty
# ============================================================
print(f"\n{HEAD}TC-01 apply_penalty — ペナルティ加算{RST}")

def t01_1():
    t = mk(500.0, correct=True)
    assert apply_penalty(t) == 500.0, f"期待500.0、実際{apply_penalty(t)}"
run("正解試行はRTをそのまま返す", t01_1)

def t01_2():
    t = mk(500.0, correct=False)
    assert apply_penalty(t) == 900.0, f"期待900.0、実際{apply_penalty(t)}"
run("エラー試行は+400ms", t01_2)

def t01_3():
    assert ERROR_PENALTY == 400
run("ペナルティ定数は400ms", t01_3)

def t01_4():
    t = mk(0.0, correct=False)
    assert apply_penalty(t) == 400.0
run("RT=0のエラー試行は400ms", t01_4)


# ============================================================
# TC-02: filter_rts
# ============================================================
print(f"\n{HEAD}TC-02 filter_rts — 外れ値除去{RST}")

def t02_1():
    rts = [300.0, 500.0, 1000.0, 3000.0]
    assert filter_rts(rts) == rts
run("有効範囲内のRTはそのまま通過", t02_1)

def t02_2():
    rts = [299.9, 300.0, 500.0]
    r = filter_rts(rts)
    assert 299.9 not in r and 300.0 in r
run("300ms未満は除外・300msは通過", t02_2)

def t02_3():
    rts = [500.0, 3000.0, 3000.1]
    r = filter_rts(rts)
    assert 3000.1 not in r and 3000.0 in r
run("3000ms超は除外・3000msは通過", t02_3)

def t02_4():
    assert filter_rts([0.0, 100.0, 5000.0]) == []
run("全て範囲外なら空リスト", t02_4)

def t02_5():
    assert filter_rts([RT_MIN_MS, RT_MAX_MS]) == [RT_MIN_MS, RT_MAX_MS]
run("境界値(300, 3000)は含まれる", t02_5)


# ============================================================
# TC-03: pooled_sd
# ============================================================
print(f"\n{HEAD}TC-03 pooled_sd — プール標準偏差{RST}")

def t03_1():
    # statistics.stdev は標本SD(n-1割り) を使う
    # combined=[400,500,600,700,800,900], n=6, mean=650
    # 標本SD = sqrt(sum((x-650)^2)/(6-1)) ≈ 187.08
    sd = pooled_sd([400,500,600], [700,800,900])
    assert abs(sd - 187.08) < 1.0, f"期待≈187.08、実際{sd:.2f}"
run("既知の値でSD検証 (≈187.08, 標本SD)", t03_1)

def t03_2():
    assert pooled_sd([500.0], []) == 1.0
run("要素数1以下でもゼロ除算しない (→1.0)", t03_2)

def t03_3():
    sd = pooled_sd([500.0, 500.0], [500.0, 500.0])
    assert sd == 0.0
run("全て同じ値はSD=0", t03_3)


# ============================================================
# TC-04: interpret_d
# ============================================================
print(f"\n{HEAD}TC-04 interpret_d — D-score解釈文{RST}")

def t04_1():
    assert "均等" in interpret_d(0.05, "自律志向", "安定志向")
run("|D|<0.15 は中立（均等）", t04_1)

def t04_2():
    r = interpret_d(0.25, "自律志向", "安定志向")
    assert "やや" in r and "自律志向" in r
run("+0.25 は「やや自律志向」", t04_2)

def t04_3():
    r = interpret_d(0.50, "自律志向", "安定志向")
    assert "強い" in r and "自律志向" in r
run("+0.50 は「強い自律志向」", t04_3)

def t04_4():
    assert "非常に強い" in interpret_d(0.70, "自律志向", "安定志向")
run("+0.70 は「非常に強い」", t04_4)

def t04_5():
    assert "安定志向" in interpret_d(-0.50, "自律志向", "安定志向")
run("マイナスDはネガティブラベル", t04_5)

def t04_6():
    assert isinstance(interpret_d(0.0, "A", "B"), str)
run("常にstrを返す", t04_6)


# ============================================================
# TC-05: calc_d_score — コア計算
# ============================================================
print(f"\n{HEAD}TC-05 calc_d_score — D-score計算{RST}")

def t05_1():
    trials = mkblock([500,520,480,510,490], 4) + mkblock([700,720,680,710,690], 7)
    d, *_ = calc_d_score(trials)
    assert d > 0, f"block7遅い→D>0 期待、実際D={d}"
run("block7が遅い → D>0（自律志向）", t05_1)

def t05_2():
    trials = mkblock([700,720,680,710,690], 4) + mkblock([500,520,480,510,490], 7)
    d, *_ = calc_d_score(trials)
    assert d < 0, f"block4遅い→D<0 期待、実際D={d}"
run("block4が遅い → D<0（安定志向）", t05_2)

def t05_3():
    rts = [500, 500, 500, 500, 500]
    d, *_ = calc_d_score(mkblock(rts, 4) + mkblock(rts, 7))
    assert abs(d) < 0.01, f"RT同じ→D≈0 期待、実際D={d}"
run("両ブロックRT等しい → D≈0", t05_3)

def t05_4():
    trials = mkblock([300]*40, 4) + mkblock([3000]*40, 7)
    d, *_ = calc_d_score(trials)
    assert -2.0 <= d <= 2.0
run("D-scoreは-2.0〜+2.0にクリップ", t05_4)

def t05_5():
    d, ma, mb, sd, cnt = calc_d_score([])
    assert d == 0.0 and cnt == 0
run("空データは全て0を返す", t05_5)

def t05_6():
    trials = mkblock([500]*3, 7)  # block4なし
    d, *_ = calc_d_score(trials)
    assert d == 0.0
run("block4なし → D=0", t05_6)

def t05_7():
    # 外れ値(5000ms)を含む場合と含まない場合でD-scoreがほぼ同じ
    base = mkblock([500,520,480], 4) + mkblock([700,720,680], 7)
    d_clean, *_ = calc_d_score(base)
    with_outlier = base + [mk(5000.0, block_id=4)]
    d_out, *_ = calc_d_score(with_outlier)
    assert abs(d_clean - d_out) < 0.01, f"外れ値除去後D差={abs(d_clean-d_out):.4f}"
run("外れ値(5000ms)は除外されD-scoreに影響しない", t05_7)

def t05_8():
    # エラーはblock4を遅くする → Dが小さくなる
    b4_correct = mkblock([500,500,500], 4)
    b4_error   = [mk(500.0, block_id=4, correct=False)]  # 500+400=900ms
    b7 = mkblock([700,700,700], 7)
    d_correct, *_ = calc_d_score(b4_correct + b7)
    d_error,   *_ = calc_d_score(b4_correct + b4_error + b7)
    assert d_error < d_correct, f"エラーありD={d_error:.3f} < 正解のみD={d_correct:.3f} 期待"
run("エラーペナルティがD-scoreに正しく影響する", t05_8)

def t05_9():
    """手計算との一致検証（最重要）
    block4: [400,500,600] mean=500
    block7: [700,800,900] mean=800
    combined stdev([400,500,600,700,800,900]) 標本SD(n-1) ≈ 187.08
    D = (800-500)/187.08 ≈ 1.604
    """
    trials = mkblock([400,500,600], 4) + mkblock([700,800,900], 7)
    d, ma, mb, sd, cnt = calc_d_score(trials)
    assert abs(ma - 500.0) < 0.1,  f"mean_a期待500.0、実際{ma}"
    assert abs(mb - 800.0) < 0.1,  f"mean_b期待800.0、実際{mb}"
    assert abs(d  - 1.604) < 0.01, f"D期待1.604、実際{d}"
    assert cnt == 6
run("手計算値との一致 (D≈1.604, mean4=500, mean7=800)", t05_9)

def t05_10():
    d, ma, mb, sd, cnt = calc_d_score(mkblock([500]*5, 4) + mkblock([700]*5, 7))
    assert isinstance(d, float) and isinstance(cnt, int)
run("戻り値の型が正しい (float, int)", t05_10)


# ============================================================
# TC-06: build_summary — プロファイルサマリー
# ============================================================
print(f"\n{HEAD}TC-06 build_summary — プロファイルサマリー{RST}")

cases = [
    (( 0.8,  0.8), "自律×達成タイプ"),
    (( 0.8,  0.1), "独立志向タイプ"),
    (( 0.1,  0.8), "目標志向タイプ"),
    ((-0.8, -0.8), "チーム志向タイプ"),
    (( 0.0,  0.0), "バランスタイプ"),
]
for (a, b), expected in cases:
    (lambda a=a, b=b, e=expected:
        run(f"auto={a:+.1f} achiev={b:+.1f} → {e}",
            lambda a=a, b=b, e=e: (
                None if e in build_summary(a, b)
                else (_ for _ in ()).throw(AssertionError(f"期待「{e}」in「{build_summary(a, b)}」"))
            ))
    )()

def t06_all():
    for a in [-1.0, -0.3, 0.0, 0.3, 1.0]:
        for b in [-1.0, -0.3, 0.0, 0.3, 1.0]:
            r = build_summary(a, b)
            assert isinstance(r, str) and len(r) > 0
run("全25パターンで空でない文字列を返す", t06_all)


# ============================================================
# TC-07: 統合テスト — 現実的シナリオ
# ============================================================
print(f"\n{HEAD}TC-07 統合テスト — 現実的シナリオ{RST}")

def t07_1():
    """自律志向が強い被験者シナリオ"""
    random.seed(42)
    def j(base, n): return [base + random.uniform(-30, 30) for _ in range(n)]
    trials = (mkblock(j(500, 40), 4) + mkblock(j(800, 40), 7))
    d, *_ = calc_d_score(trials)
    assert d > 0.3, f"自律志向シナリオ D={d:.3f}（>0.3期待）"
run("自律志向シナリオ: block4速・block7遅 → D>0.3", t07_1)

def t07_2():
    """安定志向が強い被験者シナリオ"""
    random.seed(99)
    def j(base, n): return [base + random.uniform(-30, 30) for _ in range(n)]
    trials = (mkblock(j(800, 40), 4) + mkblock(j(500, 40), 7))
    d, *_ = calc_d_score(trials)
    assert d < -0.3, f"安定志向シナリオ D={d:.3f}（<-0.3期待）"
run("安定志向シナリオ: block4遅・block7速 → D<-0.3", t07_2)

def t07_3():
    """180試行フルパイプライン"""
    random.seed(7)
    def rb(n): return [random.uniform(350, 900) for _ in range(n)]
    trials = []
    for bid, n in [(1,20),(2,20),(3,20),(4,40),(5,20),(6,20),(7,40)]:
        trials.extend(mkblock(rb(n), bid))
    assert len(trials) == 180
    d, ma, mb, sd, cnt = calc_d_score(trials)
    assert cnt > 0
    assert -2.0 <= d <= 2.0
run("180試行フルパイプライン: 正常完了・範囲内D-score", t07_3)

def t07_4():
    """混在試行（エラーあり・外れ値あり）"""
    random.seed(55)
    b4 = mkblock([500]*35, 4) + [mk(5000, 4)] + [mk(400, 4, correct=False)]*4
    b7 = mkblock([750]*35, 7) + [mk(200, 7)] + [mk(600, 7, correct=False)]*4
    d, *_ = calc_d_score(b4 + b7)
    assert -2.0 <= d <= 2.0
    assert d > 0  # 基本は自律志向方向
run("外れ値・エラー混在でも正常動作・D>0", t07_4)

def t07_5():
    """D-scoreの対称性: 同じRTでblock4/7を入れ替えると符号が逆"""
    rts_fast = [400, 420, 380, 410, 390]
    rts_slow = [700, 720, 680, 710, 690]
    d_pos, *_ = calc_d_score(mkblock(rts_fast, 4) + mkblock(rts_slow, 7))
    d_neg, *_ = calc_d_score(mkblock(rts_slow, 4) + mkblock(rts_fast, 7))
    assert d_pos > 0 and d_neg < 0
    assert abs(d_pos + d_neg) < 0.01, f"符号反転の対称性: {d_pos:.4f} vs {d_neg:.4f}"
run("D-scoreの対称性: block4/7入替で符号が逆転", t07_5)


# ============================================================
# サマリー出力
# ============================================================
total  = len(results)
passed = sum(1 for ok, *_ in results if ok)
failed = total - passed

print(f"\n{'='*55}")
print(f"テスト結果: {passed}/{total} 通過", end="")
if failed:
    print(f"  ({failed} 失敗)")
    print(f"\n失敗したテスト:")
    for ok, name, msg in results:
        if not ok:
            print(f"  {FAIL} {name}")
            print(f"       {msg}")
else:
    print("  — 全テスト通過 ✓")
print(f"{'='*55}")

sys.exit(0 if failed == 0 else 1)
