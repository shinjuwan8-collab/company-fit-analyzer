# IAT就活マッチングツール

IATで無意識の価値観を測定し、AIが企業の求める人物像を調査してマッチング結果を提示するWebアプリ。

---

## ディレクトリ構成

```
iat-backend/
├── main.py             # FastAPIアプリ本体
├── models.py           # Pydanticデータモデル
├── scorer.py           # D-score算出（Greenwald 2003準拠）
├── routers/
│   ├── iat.py          # POST /api/iat/submit
│   └── matching.py     # POST /api/matching/search
├── frontend/
│   ├── iat.html        # IAT測定画面
│   └── matching.html   # 企業ランキング結果画面
├── run_tests.py        # ユニットテスト（標準ライブラリのみ）
├── test_scorer.py      # pytest版テスト（scorer.py）
├── test_api.py         # pytest版テスト（APIエンドポイント）
├── render.yaml         # Renderデプロイ設定
├── requirements.txt
└── .env.example
```

---

## ローカル開発

```bash
# 1. 仮想環境を作成・有効化
python3 -m venv venv
source venv/bin/activate   # Mac/Linux
# venv\Scripts\activate    # Windows

# 2. パッケージをインストール
pip install -r requirements.txt

# 3. 環境変数を設定
cp .env.example .env
# .envを開いてANTHROPIC_API_KEYを設定する

# 4. サーバー起動
uvicorn main:app --reload --port 8000
```

- http://localhost:8000/       → IAT画面
- http://localhost:8000/matching → 企業ランキング画面
- http://localhost:8000/docs   → Swagger UIドキュメント

### テスト実行

```bash
# 標準ライブラリのみ（外部パッケージ不要）
python3 run_tests.py

# pytestを使う場合
pip install pytest httpx
pytest test_scorer.py test_api.py -v
```

---

## Renderへのデプロイ手順

### Step 1: GitHubリポジトリを作成

```bash
cd iat-backend
git init
git add .
git commit -m "first commit"
```

GitHubで新しいリポジトリを作成し（例: `iat-matching-tool`）、pushする。

```bash
git remote add origin https://github.com/あなたのユーザー名/iat-matching-tool.git
git branch -M main
git push -u origin main
```

### Step 2: Renderでサービスを作成

1. https://render.com にアクセスしてGitHubアカウントでサインアップ
2. ダッシュボードの **「New +」→「Web Service」** をクリック
3. GitHubリポジトリ「iat-matching-tool」を選択して **「Connect」**
4. 以下の設定を確認（render.yamlから自動入力される）:
   - **Name**: `iat-matching-tool`
   - **Runtime**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. **「Advanced」** を展開して環境変数を設定:
   - Key: `ANTHROPIC_API_KEY`
   - Value: `sk-ant-xxxxxxxx...`（Anthropicコンソールで取得したAPIキー）
6. **「Create Web Service」** をクリック

### Step 3: デプロイ完了を確認

- ビルドログが `Application startup complete.` で終わればOK
- 発行されたURL（例: `https://iat-matching-tool.onrender.com`）にアクセス
- IAT画面が表示されればデプロイ成功

---

## APIエンドポイント

### POST /api/iat/submit
IATの全試行データを受け取り、D-scoreを計算する。

```json
// リクエスト
{
  "trials": [
    {
      "word": "裁量",
      "category": "autonomy_pos",
      "correct_key": "left",
      "pressed_key": "left",
      "correct": true,
      "reaction_time_ms": 523.4,
      "block_id": 4
    }
  ]
}

// レスポンス
{
  "autonomy_score": {
    "d_score": 0.72,
    "interpretation": "強い自律志向傾向があります",
    "trial_count": 72
  },
  "achievement_score": { ... },
  "profile_summary": "自律性・達成動機ともに高い「自律×達成タイプ」です..."
}
```

### POST /api/matching/search
D-scoreをClaude APIに送り、Web検索で企業マッチングを実行する。

```json
// リクエスト
{
  "autonomy_d_score": 0.72,
  "achievement_d_score": 0.58,
  "top_n": 5
}

// レスポンス
{
  "matches": [
    {
      "rank": 1,
      "company_name": "株式会社サイバーエージェント",
      "match_percent": 92,
      "reason": "「自走できる人材」を明示的に求めており...",
      "culture_tags": ["裁量大", "成果主義", "挑戦文化"]
    }
  ],
  "profile_label": "自律×達成タイプ",
  "search_summary": "Web検索で収集した企業情報の要約..."
}
```

---

## D-score計算の仕組み（Greenwald 2003）

```
D = (mean_RT_block7 - mean_RT_block4) / SD_pooled

block4 = フェーズ4本番（自律+達成 / 制約+安定）の反応時間
block7 = フェーズ7本番（制約+達成 / 自律+安定）の反応時間

・D > 0  → 自律・達成への潜在的ポジティブ態度
・D < 0  → 安定・管理環境への潜在的ポジティブ態度
・エラー試行には +400ms のペナルティを加算
・300ms未満・3000ms超の試行は外れ値として除外
```
