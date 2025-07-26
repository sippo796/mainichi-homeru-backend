# ローカル開発環境セットアップ

このガイドでは、ローカル環境でMainichi HomeruのバックエンドAPIを実行する方法を説明します。

## 🚀 クイックスタート

### 1. 開発環境の起動

```bash
cd /Users/satomi/Work/AtelierHinata/mainichi-homeru/backend
./scripts/dev-setup.sh
```

このスクリプトが以下を自動で行います：
- Docker ComposeでMinIOとAPIサーバーを起動
- 実際のS3から最新の記事をダウンロード
- MinIOに記事をアップロード

### 2. 利用可能なエンドポイント

起動後、以下のエンドポイントが利用可能になります：

- **MinIO管理画面**: http://localhost:9001
  - ユーザー名: `minioadmin`
  - パスワード: `minioadmin`

- **API サーバー**: http://localhost:8000
  - ヘルスチェック: http://localhost:8000/health
  - 記事一覧: http://localhost:8000/api/articles
  - 記事詳細: http://localhost:8000/api/articles/2025-07-26

## 🔧 個別操作

### 記事の再同期

実際のS3から最新の記事を再ダウンロードしたい場合：

```bash
./scripts/sync-articles.sh
```

### サービスの管理

```bash
# サービス起動
docker-compose up -d

# サービス停止
docker-compose down

# ログ確認
docker-compose logs -f api
docker-compose logs -f minio
```

### MinIOの直接操作

MinIO CLIを使用してバケットを直接操作：

```bash
# バケット一覧
docker run --rm --network host minio/mc:latest sh -c "
  mc alias set local http://localhost:9000 minioadmin minioadmin;
  mc ls local/
"

# 記事一覧
docker run --rm --network host minio/mc:latest sh -c "
  mc alias set local http://localhost:9000 minioadmin minioadmin;
  mc ls local/mainichi-homeru-articles/articles/
"
```

## 🏗️ 仕組み

### アーキテクチャ

1. **MinIO**: S3互換のオブジェクトストレージ（実際のS3の代替）
2. **Lambda Server**: 既存のLambda関数をそのまま実行するFlaskサーバー
3. **同期スクリプト**: 実際のS3からMinIOへデータを同期

### Lambda関数の実行

- `lambdas/get_article/app.py` と `lambdas/get_articles/app.py` をそのまま使用
- FlaskサーバーがHTTPリクエストをLambdaイベント形式に変換
- 環境変数でMinIOエンドポイントを指定してS3クライアントを設定

### 環境変数

Lambda関数に渡される環境変数：

```bash
S3_BUCKET_NAME=mainichi-homeru-articles  # MinIOのバケット名
AWS_ENDPOINT_URL=http://minio:9000       # MinIOエンドポイント
AWS_ACCESS_KEY_ID=minioadmin             # MinIOアクセスキー
AWS_SECRET_ACCESS_KEY=minioadmin         # MinIOシークレット
AWS_DEFAULT_REGION=us-east-1             # リージョン
```

## 🛠️ トラブルシューティング

### よくある問題

1. **MinIOに接続できない**
   ```bash
   # MinIOの状態確認
   curl http://localhost:9000/minio/health/live
   
   # MinIOログ確認
   docker-compose logs minio
   ```

2. **記事が表示されない**
   ```bash
   # 記事の同期を実行
   ./scripts/sync-articles.sh
   
   # MinIOの記事一覧確認
   curl http://localhost:8000/health
   ```

3. **APIサーバーが起動しない**
   ```bash
   # APIサーバーログ確認
   docker-compose logs api
   
   # Lambda関数の実行確認
   curl http://localhost:8000/api/articles
   ```

### デバッグ

APIサーバーのデバッグログを有効にするには：

```bash
# Docker Composeでログを表示
docker-compose logs -f api
```

## 📝 開発時の注意点

- Lambda関数のコードを変更した場合は `docker-compose restart api` でAPIサーバーを再起動
- 実際のS3の記事が更新された場合は `./scripts/sync-articles.sh` で同期
- MinIOのデータを初期化したい場合は `docker-compose down -v` でボリュームも削除