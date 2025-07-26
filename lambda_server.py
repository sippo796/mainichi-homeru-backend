#!/usr/bin/env python3
"""
Lambda関数をローカルで実行するためのFlaskサーバー
既存のLambda関数をそのまま使用し、HTTPリクエストをLambdaイベント形式に変換
"""

import os
import sys
import json
import boto3
from flask import Flask, request, jsonify
from flask_cors import CORS
from botocore.config import Config

# Lambda関数のパスを追加
sys.path.append('/app/lambdas/get_article')
sys.path.append('/app/lambdas/get_articles')

# Lambda関数をインポート
try:
    from lambdas.get_article.app import lambda_handler as get_article_handler
    from lambdas.get_articles.app import lambda_handler as get_articles_handler
    print("✅ Lambda関数のインポートに成功しました")
except ImportError as e:
    print(f"❌ Lambda関数のインポートに失敗しました: {e}")
    sys.exit(1)

app = Flask(__name__)
CORS(app)  # すべてのオリジンからのアクセスを許可

def setup_boto3_for_minio():
    """MinIO用にboto3を設定"""
    # 環境変数でboto3のエンドポイントを設定
    os.environ.setdefault('AWS_ENDPOINT_URL', 'http://minio:9000')
    os.environ.setdefault('AWS_ACCESS_KEY_ID', 'minioadmin')
    os.environ.setdefault('AWS_SECRET_ACCESS_KEY', 'minioadmin')
    os.environ.setdefault('AWS_DEFAULT_REGION', 'us-east-1')
    
    print(f"🔧 MinIOエンドポイント: {os.environ.get('AWS_ENDPOINT_URL')}")
    print(f"🪣 S3バケット名: {os.environ.get('S3_BUCKET_NAME')}")

def convert_flask_to_lambda_event(flask_request, path_params=None):
    """FlaskリクエストをLambdaイベント形式に変換"""
    headers = {}
    for key, value in flask_request.headers:
        headers[key] = value
    
    event = {
        'httpMethod': flask_request.method,
        'path': flask_request.path,
        'pathParameters': path_params or {},
        'queryStringParameters': dict(flask_request.args) or None,
        'headers': headers,
        'body': flask_request.get_data(as_text=True) if flask_request.data else None,
        'isBase64Encoded': False,
        'requestContext': {
            'requestId': 'local-test',
            'stage': 'local',
            'httpMethod': flask_request.method
        }
    }
    return event

def convert_lambda_response_to_flask(lambda_response):
    """Lambdaレスポンスをflaskレスポンスに変換"""
    status_code = lambda_response.get('statusCode', 200)
    headers = lambda_response.get('headers', {})
    body = lambda_response.get('body', '')
    
    # JSONレスポンスの場合はパース
    if headers.get('Content-Type') == 'application/json':
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            pass
    
    response = jsonify(body) if isinstance(body, (dict, list)) else body
    response.status_code = status_code
    
    # ヘッダーを設定
    for key, value in headers.items():
        if key.lower() not in ['content-type', 'content-length']:
            response.headers[key] = value
    
    return response

@app.route('/')
def root():
    return jsonify({
        'message': 'Mainichi Homeru Local API Server',
        'status': 'running',
        'endpoints': {
            'health': '/health',
            'articles': '/api/articles',
            'article': '/api/articles/<date>'
        }
    })

@app.route('/health')
def health():
    """ヘルスチェックエンドポイント"""
    try:
        # MinIOへの接続テスト
        s3_client = boto3.client('s3', 
            endpoint_url=os.environ.get('AWS_ENDPOINT_URL'),
            aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
            region_name=os.environ.get('AWS_DEFAULT_REGION'),
            config=Config(signature_version='s3v4')
        )
        
        bucket_name = os.environ.get('S3_BUCKET_NAME', 'mainichi-homeru-articles')
        s3_client.head_bucket(Bucket=bucket_name)
        
        return jsonify({
            'status': 'healthy',
            'minio': 'connected',
            'bucket': bucket_name,
            'endpoint': os.environ.get('AWS_ENDPOINT_URL')
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy', 
            'error': str(e),
            'bucket': os.environ.get('S3_BUCKET_NAME', 'mainichi-homeru-articles'),
            'endpoint': os.environ.get('AWS_ENDPOINT_URL')
        }), 500

@app.route('/api/articles', methods=['GET', 'OPTIONS'])
def get_articles():
    """記事一覧を取得（Lambda関数を使用）"""
    try:
        # FlaskリクエストをLambdaイベントに変換
        event = convert_flask_to_lambda_event(request)
        context = {}  # Lambda context（ローカルでは空）
        
        print(f"📥 記事一覧リクエスト: {event['httpMethod']} {event['path']}")
        
        # Lambda関数を呼び出し
        lambda_response = get_articles_handler(event, context)
        
        print(f"📤 Lambda応答: {lambda_response['statusCode']}")
        
        # Lambdaレスポンスをflaskレスポンスに変換
        return convert_lambda_response_to_flask(lambda_response)
        
    except Exception as e:
        print(f"❌ 記事一覧取得エラー: {str(e)}")
        return jsonify({'error': 'Internal server error', 'message': str(e)}), 500

@app.route('/api/articles/<date>', methods=['GET', 'OPTIONS'])
def get_article(date):
    """特定の日付の記事を取得（Lambda関数を使用）"""
    try:
        # FlaskリクエストをLambdaイベントに変換
        event = convert_flask_to_lambda_event(request, {'date': date})
        context = {}
        
        print(f"📥 記事詳細リクエスト: {event['httpMethod']} {event['path']} (date: {date})")
        
        # Lambda関数を呼び出し
        lambda_response = get_article_handler(event, context)
        
        print(f"📤 Lambda応答: {lambda_response['statusCode']}")
        
        # Lambdaレスポンスをflaskレスポンスに変換
        return convert_lambda_response_to_flask(lambda_response)
        
    except Exception as e:
        print(f"❌ 記事詳細取得エラー: {str(e)}")
        return jsonify({'error': 'Internal server error', 'message': str(e)}), 500

if __name__ == '__main__':
    print("🚀 Lambda Server を起動中...")
    
    # MinIO用のboto3設定
    setup_boto3_for_minio()
    
    print("✅ サーバー設定完了")
    print("🔗 http://localhost:8000 でサーバーが起動します")
    
    # 開発用サーバーを起動
    app.run(host='0.0.0.0', port=8000, debug=True)