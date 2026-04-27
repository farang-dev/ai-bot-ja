import os
import re
import feedparser
import tweepy
import time
from openai import OpenAI
from dotenv import load_dotenv
from supabase import create_client, Client
from html import unescape

load_dotenv()

# Configuration (OAuth 1.0a)
X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_SECRET = os.getenv("X_ACCESS_SECRET")

# Configuration (OAuth 2.0)
X_OAUTH2_ACCESS_TOKEN = os.getenv("X_OAUTH2_ACCESS_TOKEN")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-exp:free")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

TARGET_USERNAMES = os.getenv("TARGET_USERNAMES", "OpenAI,anthropicai,GoogleAI,perplexity_ai").split(",")

# Working Nitter Instances (Fallbacks)
NITTER_INSTANCES = [
    "https://nitter.privacyredirect.com",
    "https://nitter.net",
    "https://nitter.mint.lgbt",
    "https://nitter.perennialte.ch"
]

class XBot:
    def __init__(self):
        # OAuth 1.0a Client (Post v2)
        self.client_v1a = tweepy.Client(
            consumer_key=X_API_KEY,
            consumer_secret=X_API_SECRET,
            access_token=X_ACCESS_TOKEN,
            access_token_secret=X_ACCESS_SECRET,
            wait_on_rate_limit=True
        )
        
        # OAuth 2.0 Client (Post v2) - if token is provided
        self.client_v2 = None
        if X_OAUTH2_ACCESS_TOKEN:
            self.client_v2 = tweepy.Client(
                access_token=X_OAUTH2_ACCESS_TOKEN,
                wait_on_rate_limit=True
            )
        
        # OpenRouter Client
        self.ai_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
        )
        
        # Supabase Client
        self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    def is_already_processed(self, tweet_id: str):
        try:
            response = self.supabase.table("processed_tweets").select("tweet_id").eq("tweet_id", str(tweet_id)).execute()
            return len(response.data) > 0
        except Exception as e:
            print(f"Supabase error: {e}")
            return False

    def mark_as_processed(self, tweet_id: str, username: str):
        try:
            self.supabase.table("processed_tweets").insert({
                "tweet_id": str(tweet_id),
                "username": username
            }).execute()
        except Exception as e:
            print(f"Supabase record error: {e}")

    def clean_html(self, raw_html):
        cleanr = re.compile('<.*?>')
        cleantext = re.sub(cleanr, '', raw_html)
        return unescape(cleantext)

    def extract_tweet_id(self, link):
        match = re.search(r'/status/(\d+)', link)
        return match.group(1) if match else None

    def process_tweet_content(self, original_text):
        system_prompt = (
            "あなたはAI技術の最新ニュースを日本語で伝えるニュースボットです。\n"
            "与えられた英語のツイート内容を、日本語で要約または翻訳してください。\n\n"
            "【制約事項】\n"
            "1. 日本語の文字数は130文字以内に収めてください。\n"
            "2. 内容は正確に、かつ有益な情報を優先してください。\n"
            "3. 短い場合は直訳、長い場合は要約してください。\n"
            "4. ハッシュタグは最小限にしてください。\n"
            "5. 絵文字を適度に使ってください。"
        )
        
        try:
            response = self.ai_client.chat.completions.create(
                model=OPENROUTER_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Translate/Summarize this tweet:\n\n{original_text}"}
                ],
                max_tokens=250
            )
            content = response.choices[0].message.content
            return content.strip() if content else None
        except Exception as e:
            print(f"Error with OpenRouter: {e}")
            return None

    def run(self):
        print("Starting bot execution (OAuth 1.0a + 2.0 Hybrid Mode)...")
        for username in TARGET_USERNAMES:
            username = username.strip()
            print(f"Checking @{username}...")
            
            success = False
            for instance in NITTER_INSTANCES:
                rss_url = f"{instance}/{username}/rss"
                try:
                    feed = feedparser.parse(rss_url)
                    if not feed.entries:
                        continue
                    
                    success = True
                    entries = sorted(feed.entries, key=lambda x: x.published_parsed if hasattr(x, 'published_parsed') else 0)
                    for entry in entries[-3:]:
                        tweet_id = self.extract_tweet_id(entry.link)
                        if not tweet_id or self.is_already_processed(tweet_id):
                            continue
                        
                        clean_text = self.clean_html(entry.description)
                        if clean_text.startswith("RT by @"):
                            self.mark_as_processed(tweet_id, username)
                            continue

                        print(f"Processing tweet: {tweet_id}")
                        jp_text = self.process_tweet_content(clean_text)
                        if not jp_text:
                            continue
                        
                        tweet_url = f"https://twitter.com/{username}/status/{tweet_id}"
                        full_text = f"{jp_text}\n\n{tweet_url}"
                        
                        # Try OAuth 2.0 first if available
                        posted = False
                        if self.client_v2:
                            try:
                                self.client_v2.create_tweet(text=full_text)
                                print(f"Successfully posted (OAuth 2.0) for {tweet_id}")
                                self.mark_as_processed(tweet_id, username)
                                posted = True
                                time.sleep(10)
                            except Exception as e2:
                                print(f"OAuth 2.0 failed: {e2}")

                        # Fallback to OAuth 1.0a
                        if not posted:
                            try:
                                self.client_v1a.create_tweet(text=full_text)
                                print(f"Successfully posted (OAuth 1.0a) for {tweet_id}")
                                self.mark_as_processed(tweet_id, username)
                                posted = True
                                time.sleep(10)
                            except Exception as e1a:
                                print(f"OAuth 1.0a failed: {e1a}")

                    break
                except Exception as e:
                    print(f"Error with {instance}: {e}")
            
            if not success:
                print(f"Failed to fetch @{username}.")
        
        print("Bot execution finished.")

if __name__ == "__main__":
    bot = XBot()
    bot.run()
