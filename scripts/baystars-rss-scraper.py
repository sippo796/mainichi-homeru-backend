#!/usr/bin/env python3
"""
Google News RSS経由でベイスターズニュースを取得する高速スクレイパー
Yahoo!スポーツのJavaScript問題を回避し、より安定したニュース取得を実現
"""

import feedparser
import requests
import json
import re
import time
import hashlib
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse, quote
from bs4 import BeautifulSoup
from pathlib import Path

class BaystarsRSSNewsCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # データ保存用ディレクトリ
        self.data_dir = Path(__file__).parent / "rss_scraped_data"
        self.data_dir.mkdir(exist_ok=True)
        
        # 重複チェック用のハッシュ保存ファイル
        self.seen_articles_file = self.data_dir / "seen_rss_articles.json"
        self.seen_articles = self._load_seen_articles()
        
        # ベイスターズ関連検索クエリ（重複を減らした特化型）
        self.search_queries = [
            "横浜DeNAベイスターズ",
            "横浜DeNAベイスターズ 試合"
        ]
        
        # ベイスターズ関連キーワード（強化版）
        self.baystars_keywords = [
            'ベイスターズ', 'DeNA', '横浜', 'baystars', 'dena', 'yokohama',
            '佐野', '牧', '宮崎', '森', '関根', '桑原', '大和', '三浦',
            '今永', '大貫', '東', '上茶谷', '平良', '入江', '伊勢', '山崎',
            '戸柱', '益子', '蝦名', '京田', '松尾', '石川',
            '藤浪', 'ビシエド', '橋本達弥'
        ]

    def _load_seen_articles(self):
        """既に処理済みの記事ハッシュを読み込み"""
        try:
            if self.seen_articles_file.exists():
                with open(self.seen_articles_file, 'r', encoding='utf-8') as f:
                    return set(json.load(f))
        except Exception as e:
            print(f"⚠️  既存データ読み込みエラー: {e}")
        return set()

    def _save_seen_articles(self):
        """処理済み記事ハッシュを保存"""
        try:
            with open(self.seen_articles_file, 'w', encoding='utf-8') as f:
                json.dump(list(self.seen_articles), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️  データ保存エラー: {e}")

    def _generate_article_hash(self, url, title):
        """記事の一意ハッシュを生成"""
        content = f"{url}#{title}".encode('utf-8')
        return hashlib.md5(content).hexdigest()

    def _is_baystars_related(self, text):
        """テキストがベイスターズ関連かチェック"""
        if not text:
            return False
        text_lower = text.lower()
        return any(keyword.lower() in text_lower for keyword in self.baystars_keywords)

    def fetch_rss_feed(self, query):
        """Google News RSSフィードを取得"""
        try:
            # Google News RSS URL構築
            encoded_query = quote(query)
            rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ja&gl=JP&ceid=JP:ja"
            
            print(f"📡 RSS取得中: {query}")
            
            # feedparserでRSSを解析
            feed = feedparser.parse(rss_url)
            
            if feed.bozo:
                print(f"⚠️  RSS解析警告: {feed.bozo_exception}")
            
            return feed
            
        except Exception as e:
            print(f"❌ RSS取得エラー ({query}): {e}")
            return None

    def extract_article_from_rss_item(self, item):
        """RSS itemから記事情報を抽出"""
        try:
            # 基本情報をRSSから取得
            article_data = {
                'title': item.get('title', ''),
                'url': item.get('link', ''),
                'summary': item.get('summary', ''),
                'publish_date': item.get('published', ''),
                'source': item.get('source', {}).get('title', ''),
                'scraped_at': datetime.now().isoformat(),
                'content': '',
                'images': [],
                'is_baystars_related': False,
                'baystars_keywords_found': [],
                'collection_method': 'google_news_rss'
            }
            
            # HTMLタグを除去して純粋なテキストを取得
            if article_data['summary']:
                soup = BeautifulSoup(article_data['summary'], 'html.parser')
                article_data['summary'] = soup.get_text().strip()
            
            # ベイスターズ関連判定
            full_text = f"{article_data['title']} {article_data['summary']}"
            article_data['is_baystars_related'] = self._is_baystars_related(full_text)
            
            # 見つかったキーワード記録
            found_keywords = []
            for keyword in self.baystars_keywords:
                if keyword.lower() in full_text.lower():
                    found_keywords.append(keyword)
            article_data['baystars_keywords_found'] = found_keywords
            
            # Google NewsのリダイレクトURLから実際のURLを抽出
            if '/rss/articles/' in article_data['url']:
                print(f"   📰 Google Newsリダイレクト記事: {article_data['title'][:50]}...")
                # 実際の記事取得は重いので、RSS情報のみ使用
            
            return article_data
            
        except Exception as e:
            print(f"❌ RSS記事抽出エラー: {e}")
            return None

    def collect_news_from_multiple_queries(self, max_articles_per_query=10):
        """複数のクエリでニュースを収集"""
        print(f"🔄 {len(self.search_queries)} 種類のクエリでRSSニュース収集開始...")
        
        all_articles = []
        new_articles_count = 0
        
        for i, query in enumerate(self.search_queries, 1):
            print(f"\n📋 クエリ {i}/{len(self.search_queries)}: {query}")
            
            # RSSフィード取得
            feed = self.fetch_rss_feed(query)
            if not feed or not hasattr(feed, 'entries'):
                print(f"   ❌ フィード取得失敗")
                continue
            
            print(f"   📊 RSS記事数: {len(feed.entries)} 件")
            
            query_articles = []
            
            for j, item in enumerate(feed.entries[:max_articles_per_query], 1):
                title = item.get('title', '')
                url = item.get('link', '')
                
                # 重複チェック
                article_hash = self._generate_article_hash(url, title)
                if article_hash in self.seen_articles:
                    print(f"   [{j:2d}] ⏭️  スキップ (既処理): {title[:40]}...")
                    continue
                
                print(f"   [{j:2d}] 🆕 処理中: {title[:40]}...")
                
                # RSS記事データ抽出
                article_data = self.extract_article_from_rss_item(item)
                
                if article_data and article_data['is_baystars_related']:
                    # 新しい記事として記録
                    self.seen_articles.add(article_hash)
                    article_data['hash'] = article_hash
                    article_data['query_used'] = query
                    
                    query_articles.append(article_data)
                    all_articles.append(article_data)
                    new_articles_count += 1
                    
                    print(f"        ✅ ベイスターズ関連記事として収集")
                    print(f"        🏷️  キーワード: {', '.join(article_data['baystars_keywords_found'][:3])}")
                    print(f"        📰 ソース: {article_data['source']}")
                    
                    # 保存
                    self._save_article(article_data)
                    
                else:
                    print(f"        ⏭️  ベイスターズ関連ではないためスキップ")
            
            print(f"   📊 クエリ結果: {len(query_articles)} 件の新記事")
            
            # レート制限（Google News APIに優しく）
            time.sleep(2)
        
        # 処理済みハッシュを保存
        self._save_seen_articles()
        
        print(f"\n📊 RSS収集完了: {new_articles_count} 件の新しいベイスターズ記事を取得")
        return all_articles

    def _save_article(self, article_data):
        """個別記事をJSONファイルとして保存"""
        try:
            # ファイル名生成（日付 + ハッシュ）
            date_str = datetime.now().strftime('%Y%m%d')
            filename = f"rss_{date_str}_{article_data['hash'][:8]}.json"
            filepath = self.data_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(article_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"⚠️  記事保存エラー: {e}")

    def get_recent_articles(self, days=7):
        """最近保存された記事を取得"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            recent_articles = []
            
            for json_file in self.data_dir.glob("*.json"):
                if json_file.name == "seen_rss_articles.json":
                    continue
                    
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        article = json.load(f)
                        
                    scraped_at = datetime.fromisoformat(article.get('scraped_at', ''))
                    if scraped_at >= cutoff_date:
                        recent_articles.append(article)
                        
                except Exception as e:
                    print(f"⚠️  記事読み込みエラー ({json_file}): {e}")
            
            # 新しい順にソート
            recent_articles.sort(key=lambda x: x.get('scraped_at', ''), reverse=True)
            return recent_articles
            
        except Exception as e:
            print(f"❌ 最近の記事取得エラー: {e}")
            return []

    def generate_summary_report(self, articles):
        """収集結果のサマリーレポートを生成"""
        if not articles:
            return "📭 新しい記事は見つかりませんでした"
        
        # 統計情報
        total_articles = len(articles)
        sources = {}
        keywords_count = {}
        
        for article in articles:
            # ソース別統計
            source = article.get('source', 'Unknown')
            sources[source] = sources.get(source, 0) + 1
            
            # キーワード別統計
            for keyword in article.get('baystars_keywords_found', []):
                keywords_count[keyword] = keywords_count.get(keyword, 0) + 1
        
        # レポート生成
        report = [
            f"📊 ベイスターズRSSニュース収集レポート",
            f"=" * 50,
            f"🎯 新規記事数: {total_articles} 件",
            f"📰 情報ソース数: {len(sources)} サイト",
            "",
            "📈 主要ソース:",
        ]
        
        # ソース別表示（上位5つ）
        sorted_sources = sorted(sources.items(), key=lambda x: x[1], reverse=True)
        for source, count in sorted_sources[:5]:
            report.append(f"   {source}: {count} 件")
        
        report.extend([
            "",
            "🏷️  頻出キーワード:"
        ])
        
        # キーワード別表示（上位10個）
        sorted_keywords = sorted(keywords_count.items(), key=lambda x: x[1], reverse=True)
        for keyword, count in sorted_keywords[:10]:
            report.append(f"   {keyword}: {count} 回")
        
        return "\n".join(report)

def main():
    """メイン関数"""
    collector = BaystarsRSSNewsCollector()
    
    print("🏟️  ベイスターズRSSニュースコレクター")
    print("=" * 60)
    print("📡 Google News RSS経由でベイスターズニュースを高速収集")
    print("")
    
    try:
        # RSS ニュース収集実行
        articles = collector.collect_news_from_multiple_queries(max_articles_per_query=15)
        
        # サマリーレポート表示
        print(f"\n{collector.generate_summary_report(articles)}")
        
        if articles:
            print(f"\n📰 最新記事サンプル:")
            print("-" * 60)
            
            for i, article in enumerate(articles[:3], 1):
                print(f"記事 {i}:")
                print(f"   タイトル: {article['title'][:60]}...")
                print(f"   ソース: {article['source']}")
                print(f"   公開日: {article['publish_date']}")
                print(f"   キーワード: {', '.join(article['baystars_keywords_found'][:5])}")
                print(f"   要約: {article['summary'][:100]}...")
                print("")
        
        # 最近の記事統計
        recent = collector.get_recent_articles(days=7)
        print(f"📊 過去7日間の記事: {len(recent)} 件")
        
        return 0
        
    except KeyboardInterrupt:
        print(f"\n⏹️  ユーザーによって中断されました")
        return 1
    except Exception as e:
        print(f"❌ エラー: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())