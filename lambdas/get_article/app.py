import json
import boto3
import os
import re
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
        # パスパラメータから日付と時間を取得
        path_parameters = event.get('pathParameters', {})
        if not path_parameters or 'date' not in path_parameters:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Date parameter is required'})
            }

        date_param = path_parameters['date']
        time_param = path_parameters.get('time', None)

        # 新しい形式: /articles/{date}/{time} または 日付--時間形式の互換性対応
        if time_param:
            # 新しい形式: /articles/2025-07-27/0900
            date = date_param
            time = time_param
        elif '--' in date_param:
            # 一時的な形式: /articles/2025-07-27--0900
            parts = date_param.split('--')
            date = parts[0]
            time = parts[1] if len(parts) > 1 else None
            
            # 日付バリデーション (YYYY-MM-DD format)
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', date):
                return {
                    'statusCode': 400,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({'error': 'Invalid date format. Use YYYY-MM-DD'})
                }
            
            # 時間バリデーション (HHMM format)
            if not re.match(r'^\d{4}$', time):
                return {
                    'statusCode': 400,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({'error': 'Invalid time format. Use HHMM'})
                }
        else:
            # 旧形式の互換性維持: YYYY-MM-DD-period format
            if '-' in date_param and len(date_param.split('-')) >= 4:
                parts = date_param.split('-')
                date = '-'.join(parts[:3])  # YYYY-MM-DD
                period = parts[3]  # evening, morning, etc.
                time = None
            else:
                # YYYY-MM-DD format (既存の互換性維持)
                date = date_param
                period = None
                time = None

            # 日付バリデーション (YYYY-MM-DD format)
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', date):
                return {
                    'statusCode': 400,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({'error': 'Invalid date format. Use YYYY-MM-DD'})
                }

        bucket_name = os.environ.get('S3_BUCKET_NAME', 'test-bucket')
        logger.info(f"Using bucket: {bucket_name}")
        
        # ローカルテスト用：test-bucketの場合はモックデータを返す
        if bucket_name == 'test-bucket':
            logger.info(f"Local test mode - returning mock article for date: {date}, period: {period}")
            if date == '2024-07-20':
                mock_content = f"""# テスト記事：今日もベイスターズ最高！{' (' + period + ')' if period else ''}

牧選手の打撃が本当に素晴らしいですね！今日も元気にベイスターズを応援していきましょう！

今日も一日頑張ろう！ 💪"""
                return {
                    'statusCode': 200,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'date': date_param,  # Return original date_param to include period
                        'content': mock_content,
                        'lastModified': '2024-07-20T12:00:00Z'
                    }, ensure_ascii=False)
                }
            else:
                return {
                    'statusCode': 404,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({'error': 'Article not found'})
                }

        # S3から記事を取得（新しいフォルダ構造対応）
        if time:
            # 新しい形式: articles/YYYY-MM-DD/HHMM.md
            response = s3_client.get_object(
                Bucket=bucket_name,
                Key=f'articles/{date}/{time}.md'
            )
        elif period:
            # 旧形式の互換性維持: date-period.mdを試し、なければdate.mdを試す
            try:
                response = s3_client.get_object(
                    Bucket=bucket_name,
                    Key=f'articles/{date}-{period}.md'
                )
            except ClientError as e:
                if e.response['Error']['Code'] == 'NoSuchKey':
                    # Fallback to date.md
                    response = s3_client.get_object(
                        Bucket=bucket_name,
                        Key=f'articles/{date}.md'
                    )
                else:
                    raise e
        else:
            # 旧形式: date.md
            response = s3_client.get_object(
                Bucket=bucket_name,
                Key=f'articles/{date}.md'
            )

        content = response['Body'].read().decode('utf-8')
        
        # ETagを生成（S3のETagとlastModifiedを使用）
        s3_etag = response.get('ETag', '').strip('"')
        last_modified = response['LastModified'].isoformat()
        
        import hashlib
        content_hash = hashlib.md5(f"{s3_etag}:{last_modified}:{len(content)}".encode()).hexdigest()[:8]

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Cache-Control': 'public, max-age=3600',
                'ETag': f'"{content_hash}"'
            },
            'body': json.dumps({
                'date': date,
                'time': time if time else None,
                'datetime': f"{date} {time[:2]}:{time[2:]}" if time else date,
                'content': content,
                'lastModified': last_modified
            }, ensure_ascii=False)
        }

    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return {
                'statusCode': 404,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Article not found'})
            }
        else:
            logger.error(f"S3 Error: {str(e)}")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': 'Failed to fetch article',
                    'message': str(e)
                })
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
                'error': 'Failed to fetch article',
                'message': str(e)
            })
        }