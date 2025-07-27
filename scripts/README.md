# 📁 Scripts Directory

「毎日褒める」プロジェクトの各種スクリプト・ツール集

## 🏟️ ベイスターズニュース収集

### `baystars-news-scraper.py` ⭐ **メイン機能**
Yahoo!スポーツからベイスターズ関連ニュースを詳細に収集・保存するメインスクレイパー

**機能:**
- Yahoo!スポーツからベイスターズ専用リンクを抽出
- 各記事の詳細内容（タイトル、本文、画像、公開日）を自動取得
- ベイスターズ関連キーワードでフィルタリング
- 重複記事の自動検出・スキップ
- 記事データをJSON形式で個別保存
- 過去記事の統計・管理機能

**使用方法:**
```bash
# 仮想環境をアクティベート
source .venv/bin/activate

# スクレイピング実行
python baystars-news-scraper.py
```

**出力:**
- `scraped_data/` ディレクトリに記事がJSONファイルとして保存
- `seen_articles.json` で重複チェック用ハッシュを管理

**データ例:**
```json
{
  "url": "記事URL",
  "title": "記事タイトル",
  "content": "記事本文",
  "summary": "要約（200文字）",
  "publish_date": "公開日時",
  "images": ["画像URL配列"],
  "is_baystars_related": true,
  "baystars_keywords_found": ["DeNA", "横浜", "東"],
  "hash": "重複チェック用ハッシュ"
}
```

---

## 🚀 Lambda関連

### `run-local-lambda.py` ⭐ **時間モック対応**
AWS Lambdaをローカル環境でテスト実行するためのスクリプト

**機能:**
- MCP Orchestrator Lambda関数のローカル実行
- 時間帯別記事生成のテスト機能
- 仮想環境からのbuildディレクトリ利用
- S3への実際のアップロード

**使用方法:**
```bash
# 実時間で実行（現在の時刻に基づいて記事生成）
python run-local-lambda.py

# 午前10時で実行（朝の記事生成をテスト）
python run-local-lambda.py --mock-hour 10

# 午後21時で実行（夜の記事生成をテスト）
python run-local-lambda.py --mock-hour 21

# 任意の時間で実行（0-23時）
python run-local-lambda.py --mock-hour 14
```

**時間モック機能:**
- `--mock-hour`: 0-23の時間を指定して時間帯をモック
- 朝（6-12時）と夜（13-23時）で異なる選手選択
- 記事ファイル名も時間帯に応じて変更（`YYYY-MM-DD-morning.md` / `YYYY-MM-DD-evening.md`）
- 既存の日付のみファイル（`YYYY-MM-DD.md`）との後方互換性維持

**出力例:**
```
📦 buildディレクトリを使用: .../build
🕙 時間モック: 10時で実行
🔧 環境変数を設定しました（10時でテスト実行）
✅ AWS認証確認済み
🚀 MCP Orchestratorを実行中...
📝 S3に記事を保存中: .../articles/2025-07-27-morning.md
✅ 実行成功: 200
```

### `deploy-lambda.sh`
LambdaファンクションをAWSにデプロイするスクリプト

**使用方法:**
```bash
./deploy-lambda.sh
```

### `test-lambda.sh`
デプロイ済みLambdaファンクションの動作テスト

**使用方法:**
```bash
./test-lambda.sh
```

---

## 📰 News API関連

### `test-newsapi.sh`
News APIを使用したニュース取得のテストスクリプト

**使用方法:**
```bash
./test-newsapi.sh
```

### `test-newsapi-multiple.sh`
複数のNews APIエンドポイントをテストするスクリプト

**使用方法:**
```bash
./test-newsapi-multiple.sh
```

---

## 📝 記事作成

### `create-article.sh`
記事作成用のヘルパースクリプト

**使用方法:**
```bash
./create-article.sh
```

---

## 📂 ディレクトリ構成

```
scripts/
├── README.md                     # このファイル
├── baystars-news-scraper.py      # メインのニューススクレイパー
├── scraped_data/                 # スクレイピングしたデータ保存先
│   ├── YYYYMMDD_xxxxxxxx.json   # 個別記事データ
│   └── seen_articles.json       # 重複チェック用ハッシュ
├── .venv/                        # Python仮想環境
├── run-local-lambda.py           # ローカルLambda実行
├── deploy-lambda.sh              # Lambdaデプロイ
├── test-lambda.sh                # Lambdaテスト
├── test-newsapi.sh               # News APIテスト
├── test-newsapi-multiple.sh      # 複数News APIテスト
└── create-article.sh             # 記事作成ヘルパー
```

---

## 🔧 セットアップ

### 1. Python仮想環境の設定
```bash
# backendディレクトリで仮想環境作成（初回のみ）
cd ../backend
python3 -m venv venv

# 仮想環境アクティベート
source venv/bin/activate

# Lambda用の依存関係をインストール
pip install -r lambdas/mcp_orchestrator/requirements.txt
```

**注意:** 
- Lambda関数のローカル実行では `backend/venv` を使用
- buildディレクトリが存在する場合は自動的にそちらを優先
- AWS認証情報が設定されている必要があります

### 2. 権限設定
```bash
# スクリプトに実行権限を付与
chmod +x *.sh
```

---

## 📊 使用の流れ

### 日次ニュース収集の場合

1. **ニュース収集**
   ```bash
   source .venv/bin/activate
   python baystars-news-scraper.py
   ```

2. **収集結果確認**
   ```bash
   ls -la scraped_data/
   ```

3. **Lambda環境での処理**
   ```bash
   ./test-lambda.sh
   ```

---

## ⚠️ 注意事項

- **レート制限**: スクレイピング時は1秒間隔でアクセス
- **重複回避**: 同じ記事の重複取得を自動で防止
- **ベイスターズ専用**: 他球団の記事は自動フィルタリング
- **データ永続化**: `scraped_data/` ディレクトリは削除しないこと

---

## 🏷️ ベイスターズ関連キーワード

スクレイパーが検出する主要キーワード：

**チーム関連:**
- ベイスターズ, DeNA, 横浜, baystars, dena, yokohama

**主力選手:**
- 佐野, 牧, 宮崎, 森, 関根, 桑原, 大和, 三浦
- 今永, 大貫, 東, 上茶谷, 平良, 入江, 伊勢

**野球用語:**
- 打率, 本塁打, HR, RBI, 防御率, ERA, 勝利, 敗戦
- 投手, 捕手, 内野手, 外野手

---

## 🔄 更新履歴

- **2025/07/27**: メインスクレイパー `baystars-news-scraper.py` 実装
- **2025/07/27**: 不要なテスト用ファイルを整理・削除
- **2025/07/27**: README作成
- **2025/07/27**: `run-local-lambda.py` に時間モック機能追加（`--mock-hour`オプション）
- **2025/07/27**: 時間帯別記事生成（morning/evening）とファイル名対応
- **2025/07/27**: 後方互換性維持（既存の日付のみファイルも読み込み可能）

---

## 📞 トラブルシューティング

### よくある問題

1. **`ModuleNotFoundError: No module named 'requests'`**
   ```bash
   source .venv/bin/activate
   pip install requests beautifulsoup4
   ```

2. **Permission denied エラー**
   ```bash
   chmod +x *.sh
   ```

3. **スクレイピングが失敗する**
   - ネットワーク接続を確認
   - Yahoo!スポーツサイトの構造変更の可能性

4. **データが保存されない**
   - `scraped_data/` ディレクトリの書き込み権限を確認

---

## 📈 今後の拡張予定

- [ ] RSS フィード対応
- [ ] 他スポーツサイト対応
- [ ] 記事の感情分析
- [ ] 自動的な「褒めコメント」生成
- [ ] 定期実行スケジューラー

---

**🏟️ 頑張れベイスターズ！**