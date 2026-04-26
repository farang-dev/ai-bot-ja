import os
import re
import feedparser
import tweepy
from openai import OpenAI
from dotenv import load_dotenv
from supabase import create_client, Client
from html import unescape

load_dotenv()

# Configuration
X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_SECRET = os.getenv("X_ACCESS_SECRET")
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")

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
        # Tweepy Client (For POSTING only)
        self.client = tweepy.Client(
            bearer_token=X_BEARER_TOKEN,
            consumer_key=X_API_KEY,
            consumer_secret=X_API_SECRET,
            access_token=X_ACCESS_TOKEN,
            access_token_secret=X_ACCESS_SECRET,
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
        response = self.supabase.table("processed_tweets").select("tweet_id").eq("tweet_id", str(tweet_id)).execute()
        return len(response.data) > 0

    def mark_as_processed(self, tweet_id: str, username: str):
        self.supabase.table("processed_tweets").insert({
            "tweet_id": str(tweet_id),
            "username": username
        }).execute()

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
        print("Starting bot execution (Multi-RSS Mode - FREE)...")
        for username in TARGET_USERNAMES:
            username = username.strip()
            success = False
            
            # Try multiple Nitter instances in case some are blocked
            for instance in NITTER_INSTANCES:
                print(f"Checking updates for @{username} via {instance}...")
                rss_url = f"{instance}/{username}/rss"
                
                try:
                    feed = feedparser.parse(rss_url)
                    if not feed.entries:
                        print(f"No entries found at {instance}. Trying next instance...")
                        continue
                    
                    # Successfully fetched feed!
                    success = True
                    entries = sorted(feed.entries, key=lambda x: x.published_parsed if hasattr(x, 'published_parsed') else 0)
                    
                    # Process entries
                    for entry in entries[-5:]:
                        tweet_id = self.extract_tweet_id(entry.link)
                        if not tweet_id or self.is_already_processed(tweet_id):
                            continue
                        
                        clean_text = self.clean_html(entry.description)
                        if clean_text.startswith("RT by @"):
                            print(f"Skipping retweet: {tweet_id}")
                            self.mark_as_processed(tweet_id, username)
                            continue

                        print(f"Processing new tweet: {tweet_id}")
                        jp_text = self.process_tweet_content(clean_text)
                        if not jp_text:
                            continue
                        
                        try:
                            self.client.create_tweet(
                                text=jp_text,
                                quote_tweet_id=tweet_id
                            )
                            print(f"Successfully posted quote tweet for {tweet_id}")
                            self.mark_as_processed(tweet_id, username)
                        except Exception as e:
                            print(f"Error posting tweet: {e}")
                    
                    break # Stop trying instances if we successfully processed this user
                    
                except Exception as e:
                    print(f"Error with instance {instance}: {e}")
            
            if not success:
                print(f"FATAL: All instances failed for @{username}.")
        
        print("Bot execution finished.")

if __name__ == "__main__":
    bot = XBot()
    bot.run()
