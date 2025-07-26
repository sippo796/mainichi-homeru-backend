#!/bin/bash

# 実際のS3バケットから記事をダウンロードしてMinIOに投入するスクリプト

set -e

# 設定
PROD_BUCKET="mainichi-homeru-prod-articles-902275209296"
LOCAL_BUCKET="mainichi-homeru-articles"
TEMP_DIR="/tmp/articles-sync"
MINIO_ENDPOINT="http://localhost:9000"
MINIO_USER="minioadmin"
MINIO_PASSWORD="minioadmin"

echo "🚀 記事同期スクリプトを開始します..."

# 一時ディレクトリを作成
rm -rf $TEMP_DIR
mkdir -p $TEMP_DIR

# 1. 実際のS3から記事をダウンロード
echo "📥 実際のS3バケットから記事をダウンロード中..."
aws s3 sync s3://$PROD_BUCKET/articles/ $TEMP_DIR/articles/ --delete

if [ $? -eq 0 ]; then
    echo "✅ S3からのダウンロードが完了しました"
    echo "📄 ダウンロードされた記事:"
    ls -la $TEMP_DIR/articles/
else
    echo "❌ S3からのダウンロードに失敗しました"
    exit 1
fi

# 2. MinIOが起動しているかチェック
echo "🔍 MinIOの接続をチェック中..."
curl -f $MINIO_ENDPOINT/minio/health/live > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ MinIOに接続できました"
else
    echo "❌ MinIOに接続できません。docker-compose upでMinIOを起動してください"
    exit 1
fi

# 3. MinIO CLIでバケットを作成（存在しない場合）
echo "🪣 MinIOバケットを準備中..."
docker run --rm --network host \
    -v $TEMP_DIR:/data \
    minio/mc:latest \
    sh -c "
    mc alias set local $MINIO_ENDPOINT $MINIO_USER $MINIO_PASSWORD;
    mc mb local/$LOCAL_BUCKET --ignore-existing;
    mc policy set public local/$LOCAL_BUCKET;
    echo 'バケット準備完了';
    "

# 4. 記事をMinIOにアップロード
echo "📤 記事をMinIOにアップロード中..."
docker run --rm --network host \
    -v $TEMP_DIR:/data \
    minio/mc:latest \
    sh -c "
    mc alias set local $MINIO_ENDPOINT $MINIO_USER $MINIO_PASSWORD;
    mc cp --recursive /data/articles/ local/$LOCAL_BUCKET/articles/;
    echo 'アップロード完了';
    "

# 5. アップロード結果を確認
echo "🔍 アップロード結果を確認中..."
docker run --rm --network host \
    minio/mc:latest \
    sh -c "
    mc alias set local $MINIO_ENDPOINT $MINIO_USER $MINIO_PASSWORD;
    echo '📄 MinIOにアップロードされた記事:';
    mc ls local/$LOCAL_BUCKET/articles/;
    "

# 一時ディレクトリを削除
rm -rf $TEMP_DIR

echo "🎉 記事同期が完了しました！"
echo "💡 MinIO管理画面: http://localhost:9001 (minioadmin/minioadmin)"
echo "🔗 API URL: http://localhost:8000"