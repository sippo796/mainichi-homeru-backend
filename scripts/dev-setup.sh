#!/bin/bash

# 開発環境セットアップスクリプト

set -e

echo "🛠️  開発環境をセットアップします..."

# 1. Docker Composeでサービスを起動
echo "🐳 Docker Composeでサービスを起動中..."
docker-compose up -d

# 2. MinIOが完全に起動するまで待機
echo "⏳ MinIOの起動を待機中..."
sleep 10

# MinIOのヘルスチェック
for i in {1..30}; do
    if curl -f http://localhost:9000/minio/health/live > /dev/null 2>&1; then
        echo "✅ MinIOが起動しました"
        break
    fi
    echo "⏳ MinIOの起動を待機中 ($i/30)..."
    sleep 2
done

# 3. 記事を同期
echo "🔄 記事を同期中..."
./scripts/sync-articles.sh

echo "🎉 開発環境のセットアップが完了しました！"
echo ""
echo "📍 利用可能なエンドポイント:"
echo "   - MinIO管理画面: http://localhost:9001 (minioadmin/minioadmin)"
echo "   - API サーバー: http://localhost:8000"
echo "   - 記事一覧: http://localhost:8000/api/articles"
echo "   - 記事詳細: http://localhost:8000/api/articles/2025-07-26"
echo ""
echo "🛑 停止するには: docker-compose down"
echo "🔄 記事を再同期するには: ./scripts/sync-articles.sh"