import json
import boto3
import os
from datetime import datetime
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')

def lambda_handler(event, context):
    logger.info(f"Event: {json.dumps(event)}")
    
    # CORS preflight request handling
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
                'Access-Control-Max-Age': '86400'
            },
            'body': ''
        }

    try:
        bucket_name = os.environ.get('S3_BUCKET_NAME', 'test-bucket')
        logger.info(f"Using bucket: {bucket_name}")
        
        # ローカルテスト用：test-bucketの場合はモックデータを返す
        if bucket_name == 'test-bucket':
            logger.info("Local test mode - returning mock data")
            mock_articles = [
                {
                    'date': '2024-07-20',
                    'title': 'テスト記事：今日もベイスターズ最高！',
                    'preview': '牧選手の打撃が素晴らしいですね！今日も元気にベイスターズを応援...',
                    'lastModified': '2024-07-20T12:00:00Z'
                },
                {
                    'date': '2024-07-19',
                    'title': 'テスト記事：ベイスターズの魅力',
                    'preview': 'ハマスタの雰囲気は最高です！選手たちの頑張りが...',
                    'lastModified': '2024-07-19T12:00:00Z'
                }
            ]
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'articles': mock_articles}, ensure_ascii=False)
            }

        # 本番環境：実際のS3から記事一覧を取得
        try:
            response = s3_client.list_objects_v2(
                Bucket=bucket_name,
                Prefix='articles/',
                MaxKeys=10
            )
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchBucket':
                logger.warning(f"Bucket {bucket_name} does not exist - returning empty articles")
                return {
                    'statusCode': 200,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({'articles': []}, ensure_ascii=False)
                }
            else:
                raise e

        if 'Contents' not in response:
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'articles': []})
            }

        articles = []

        # 最新5件を取得してプレビュー作成
        sorted_objects = sorted(
            [obj for obj in response['Contents'] if obj['Key'].endswith('.md')],
            key=lambda x: x['LastModified'],
            reverse=True
        )[:5]

        for obj in sorted_objects:
            try:
                date = obj['Key'].replace('articles/', '').replace('.md', '')

                # プレビュー取得（最初の500文字程度、安全にデコード）
                try:
                    # まず全体を取得してから切り詰める方が安全
                    full_response = s3_client.get_object(
                        Bucket=bucket_name,
                        Key=obj['Key']
                    )
                    
                    content = full_response['Body'].read().decode('utf-8')
                except UnicodeDecodeError:
                    # デコードエラーの場合はフォールバック
                    logger.warning(f"Unicode decode error for {obj['Key']}, using fallback")
                    content = "記事を読み込み中..."
                lines = content.split('\n')
                title = lines[0].replace('#', '').strip() if lines and lines[0].startswith('#') else 'ベイスターズ記事'
                
                # プレビュー作成：タイトル行を除いた本文から作成
                content_lines = [line.strip() for line in lines[1:] if line.strip() and not line.startswith('#')]
                preview_text = ' '.join(content_lines)[:200] + '...' if content_lines else '記事を準備中...'

                articles.append({
                    'date': date,
                    'title': title,
                    'preview': preview_text,
                    'lastModified': obj['LastModified'].isoformat()
                })

            except Exception as e:
                logger.error(f"Error processing {obj['Key']}: {str(e)}")
                continue

        # 動的キャッシュ制御とETag生成
        from datetime import datetime, timezone, timedelta
        import hashlib
        
        jst = timezone(timedelta(hours=9))
        today = datetime.now(jst).strftime('%Y-%m-%d')
        
        # 今日の記事があるかチェック
        has_todays_article = any(article['date'] == today for article in articles)
        
        # キャッシュ時間：今日の記事がある場合は長時間、ない場合は短時間
        cache_seconds = 3600 if has_todays_article else 60  # 1時間 or 1分
        
        # ETag生成（記事の日付とタイトルから）
        etag_data = ''.join([f"{a['date']}{a['title']}" for a in articles])
        etag = hashlib.md5(etag_data.encode('utf-8')).hexdigest()
        
        # If-None-Match チェック
        request_etag = event.get('headers', {}).get('If-None-Match')
        if request_etag == f'"{etag}"':
            return {
                'statusCode': 304,
                'headers': {
                    'ETag': f'"{etag}"',
                    'Cache-Control': f'public, max-age={cache_seconds}',
                    'Access-Control-Allow-Origin': '*'
                }
            }
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Cache-Control': f'public, max-age={cache_seconds}',
                'ETag': f'"{etag}"',
                'Last-Modified': articles[0]['lastModified'] if articles else datetime.now(jst).isoformat()
            },
            'body': json.dumps({'articles': articles}, ensure_ascii=False)
        }

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': 'Failed to fetch articles',
                'message': str(e)
            })
        }
    