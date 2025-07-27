#!/usr/bin/env python3
"""
ベイスターズニュース詳細スクレイパー
Yahoo!スポーツから抽出したリンクを辿って記事の詳細情報を取得・保存する
"""

import requests
import json
import re
import time
import hashlib
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from pathlib import Path

class BaystarsNewsScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # データ保存用ディレクトリ
        self.data_dir = Path(__file__).parent / "scraped_data"
        self.data_dir.mkdir(exist_ok=True)
        
        # 重複チェック用のハッシュ保存ファイル
        self.seen_articles_file = self.data_dir / "seen_articles.json"
        self.seen_articles = self._load_seen_articles()
        
        # ベイスターズ関連キーワード
        self.baystars_keywords = [
            'ベイスターズ', 'DeNA', '横浜', 'baystars', 'dena', 'yokohama',
            '佐野', '牧', '宮崎', '森', '関根', '桑原', '大和', '三浦',
            '今永', '大貫', '東', '上茶谷', '平良', '入江', '伊勢'
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

    def extract_article_content(self, url):
        """リンク先の記事内容を詳細に抽出"""
        try:
            print(f"📰 記事取得中: {url}")
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 記事情報を抽出
            article_data = {
                'url': url,
                'scraped_at': datetime.now().isoformat(),
                'title': '',
                'content': '',
                'summary': '',
                'publish_date': '',
                'author': '',
                'tags': [],
                'images': [],
                'is_baystars_related': False,
                'baystars_keywords_found': []
            }
            
            # タイトル抽出
            title_selectors = [
                'h1',
                '.article-title',
                '.news-title', 
                '[class*="title"]',
                'title'
            ]
            
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem and title_elem.get_text().strip():
                    article_data['title'] = title_elem.get_text().strip()
                    break
            
            # 本文抽出
            content_selectors = [
                '.article-body',
                '.news-body',
                '.content',
                '[class*="body"]',
                '[class*="content"]',
                'article p',
                '.text'
            ]
            
            content_parts = []
            for selector in content_selectors:
                elements = soup.select(selector)
                for elem in elements:
                    text = elem.get_text().strip()
                    if len(text) > 50:  # 意味のあるテキストのみ
                        content_parts.append(text)
                
                if content_parts:  # 最初に見つかったセレクターを使用
                    break
            
            article_data['content'] = '\n\n'.join(content_parts)
            
            # 要約作成（最初の200文字）
            if article_data['content']:
                article_data['summary'] = article_data['content'][:200] + '...' if len(article_data['content']) > 200 else article_data['content']
            
            # 公開日時抽出
            date_selectors = [
                '[class*="date"]',
                '[class*="time"]',
                'time',
                '.publish-date'
            ]
            
            for selector in date_selectors:
                date_elem = soup.select_one(selector)
                if date_elem:
                    date_text = date_elem.get_text().strip()
                    if re.search(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', date_text):
                        article_data['publish_date'] = date_text
                        break
            
            # 画像抽出
            img_elements = soup.select('img[src]')
            for img in img_elements[:5]:  # 最大5枚
                src = img.get('src', '')
                if src and not src.startswith('data:'):
                    full_url = urljoin(url, src)
                    article_data['images'].append(full_url)
            
            # ベイスターズ関連判定
            full_text = f"{article_data['title']} {article_data['content']}"
            article_data['is_baystars_related'] = self._is_baystars_related(full_text)
            
            # 見つかったキーワード記録
            found_keywords = []
            for keyword in self.baystars_keywords:
                if keyword.lower() in full_text.lower():
                    found_keywords.append(keyword)
            article_data['baystars_keywords_found'] = found_keywords
            
            return article_data
            
        except Exception as e:
            print(f"❌ 記事抽出エラー ({url}): {e}")
            return None

    def process_links(self, links, max_articles=10):
        """リンクのリストを処理して記事データを取得"""
        print(f"🔄 {len(links)} 件のリンクを処理開始...")
        
        processed_articles = []
        new_articles_count = 0
        
        for i, link in enumerate(links, 1):
            if new_articles_count >= max_articles:
                print(f"📊 最大記事数 ({max_articles}) に達しました")
                break
                
            url = link.get('url', '')
            title = link.get('text', '')
            
            if not url:
                continue
            
            # 重複チェック
            article_hash = self._generate_article_hash(url, title)
            if article_hash in self.seen_articles:
                print(f"   [{i:2d}] ⏭️  スキップ (既処理): {title[:50]}...")
                continue
            
            print(f"   [{i:2d}] 🆕 処理中: {title[:50]}...")
            
            # 記事内容取得
            article_data = self.extract_article_content(url)
            
            if article_data and article_data['is_baystars_related']:
                # 新しい記事として記録
                self.seen_articles.add(article_hash)
                article_data['hash'] = article_hash
                article_data['source_link_text'] = title
                
                processed_articles.append(article_data)
                new_articles_count += 1
                
                print(f"        ✅ ベイスターズ関連記事として保存")
                print(f"        🏷️  キーワード: {', '.join(article_data['baystars_keywords_found'][:3])}")
                
                # 保存
                self._save_article(article_data)
                
            else:
                print(f"        ⏭️  ベイスターズ関連ではないためスキップ")
            
            # レート制限
            time.sleep(1)
        
        # 処理済みハッシュを保存
        self._save_seen_articles()
        
        print(f"\n📊 処理完了: {new_articles_count} 件の新しいベイスターズ記事を取得")
        return processed_articles

    def _save_article(self, article_data):
        """個別記事をJSONファイルとして保存"""
        try:
            # ファイル名生成（日付 + ハッシュ）
            date_str = datetime.now().strftime('%Y%m%d')
            filename = f"{date_str}_{article_data['hash'][:8]}.json"
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
                if json_file.name == "seen_articles.json":
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

def main():
    """メイン関数 - test-yahoo-scraping.pyからのリンクを使用"""
    scraper = BaystarsNewsScraper()
    
    print("🏟️  ベイスターズニュース詳細スクレイパー")
    print("=" * 60)
    
    # まず基本的なリンク抽出を実行
    print("📡 Yahoo!スポーツからリンク抽出中...")
    
    try:
        # test-yahoo-scraping.pyの機能を使用してリンク取得
        from pathlib import Path
        import sys
        sys.path.append(str(Path(__file__).parent))
        
        # 直接Yahoo!からリンク抽出
        url = "https://baseball.yahoo.co.jp/npb/teams/3/"
        response = scraper.session.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # リンク抽出（改善版ロジック使用）
        links = soup.find_all('a', href=True)
        relevant_links = []
        
        baystars_link_keywords = [
            'ベイスターズ', 'dena', '横浜', 'baystars',
            'ニュース', 'news', '試合', 'game', '選手', 'player',
            '勝利', '敗戦', '結果', '速報', '成績', 'スタメン'
        ]
        
        for link in links:
            href = link.get('href', '')
            text = link.get_text().strip()
            text_lower = text.lower()
            
            if (any(keyword in text_lower for keyword in baystars_link_keywords) or 
                '/npb/teams/3/' in href):
                if text and len(text) < 80:
                    full_url = urljoin(url, href)
                    relevant_links.append({'text': text, 'url': full_url})
        
        print(f"✅ {len(relevant_links)} 件のベイスターズ関連リンクを発見")
        
        # リンクを処理
        articles = scraper.process_links(relevant_links, max_articles=5)
        
        # 結果表示
        if articles:
            print(f"\n🎉 {len(articles)} 件のベイスターズ記事を詳細取得！")
            
            for i, article in enumerate(articles, 1):
                print(f"\n📰 記事 {i}:")
                print(f"   タイトル: {article['title'][:60]}...")
                print(f"   URL: {article['url']}")
                print(f"   要約: {article['summary'][:100]}...")
                print(f"   キーワード: {', '.join(article['baystars_keywords_found'][:3])}")
                
        else:
            print("\n📭 新しい記事は見つかりませんでした")
        
        # 最近の記事統計
        recent = scraper.get_recent_articles(days=7)
        print(f"\n📊 過去7日間の記事: {len(recent)} 件")
        
        return 0
        
    except Exception as e:
        print(f"❌ エラー: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())