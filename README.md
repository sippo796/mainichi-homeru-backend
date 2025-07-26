# Mainichi Homeru Backend

横浜 DeNA ベイスターズの日々の応援記事を自動生成するバックエンドシステム

## アーキテクチャ

- **Lambda 関数**: 記事取得・記事生成
- **S3**: 記事ストレージ
- **API Gateway**: REST API エンドポイント

## 開発

### 記事作成テスト

```bash
# 新しい記事を生成
./scripts/create-article.sh
```

### 本番 API

フロントエンドは本番 API Gateway 経由で直接アクセス：

- 記事一覧: `GET /articles`
- 記事詳細: `GET /articles/{date}`

## デプロイ

```bash
cd terraform
terraform plan
terraform apply
```
