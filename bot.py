import os
import re
import httpx
import tweepy
from openai import OpenAI
from dotenv import load_dotenv
from supabase import create_client, Client
import json

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

    def fetch_tweets_free(self, username):
        """
        Fetches tweets using X's official syndication API (no login/API key required for read).
        This is much more stable than Nitter.
        """
        url = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{username}"
        try:
            # Need to look like a real browser
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            response = httpx.get(url, headers=headers)
            if response.status_code != 200:
                print(f"Failed to fetch {username}: HTTP {response.status_code}")
                return []
            
            # Extract JSON from the HTML response (it's embedded in a script tag)
            html = response.text
            match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
            if not match:
                print(f"Could not find data in response for {username}")
                return []
            
            data = json.loads(match.group(1))
            timeline = data.get("props", {}).get("pageProps", {}).get("timeline", {}).get("entries", [])
            
            tweets = []
            for entry in timeline:
                if entry.get("type") == "tweet":
                    t_data = entry.get("content", {}).get("tweet", {})
                    if t_data:
                        tweets.append({
                            "id": t_data.get("id_str"),
                            "text": t_data.get("full_text"),
                            "is_retweet": "retweeted_status" in t_data
                        })
            return tweets
        except Exception as e:
            print(f"Error fetching {username}: {e}")
            return []

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
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error with OpenRouter: {e}")
            return None

    def run(self):
        print("Starting bot execution (Syndication Mode - FREE)...")
        for username in TARGET_USERNAMES:
            username = username.strip()
            print(f"Checking updates for @{username}...")
            
            tweets = self.fetch_tweets_free(username)
            if not tweets:
                print(f"No tweets found for @{username}.")
                continue
            
            # Process from oldest to newest
            for tweet in reversed(tweets[:5]):
                tweet_id = tweet["id"]
                if not tweet_id or self.is_already_processed(tweet_id):
                    continue
                
                if tweet["is_retweet"]:
                    print(f"Skipping retweet: {tweet_id}")
                    self.mark_as_processed(tweet_id, username)
                    continue

                print(f"Processing new tweet: {tweet_id}")
                jp_text = self.process_tweet_content(tweet["text"])
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
        
        print("Bot execution finished.")

if __name__ == "__main__":
    bot = XBot()
    bot.run()
