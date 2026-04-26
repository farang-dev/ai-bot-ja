import os
import tweepy
from openai import OpenAI
from dotenv import load_dotenv
from supabase import create_client, Client

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
        # Tweepy Client for v2 API
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
        """Checks if the tweet ID has already been processed in Supabase."""
        response = self.supabase.table("processed_tweets").select("tweet_id").eq("tweet_id", str(tweet_id)).execute()
        return len(response.data) > 0

    def mark_as_processed(self, tweet_id: str, username: str):
        """Records the tweet ID in Supabase to avoid future duplicates."""
        self.supabase.table("processed_tweets").insert({
            "tweet_id": str(tweet_id),
            "username": username
        }).execute()

    def get_last_processed_id(self, username: str):
        """Fetches the latest tweet ID we processed for this user to optimize API calls."""
        response = self.supabase.table("processed_tweets") \
            .select("tweet_id") \
            .eq("username", username) \
            .order("tweet_id", desc=True) \
            .limit(1) \
            .execute()
        
        if response.data:
            return response.data[0]["tweet_id"]
        return None

    def get_user_id(self, username):
        try:
            user = self.client.get_user(username=username)
            if user.data:
                return user.data.id
        except Exception as e:
            print(f"Error fetching user ID for {username}: {e}")
        return None

    def process_tweet_content(self, original_text):
        """
        Uses OpenRouter to translate/summarize the tweet into Japanese.
        Ensures it fits within the 140-character limit for Japanese tweets.
        """
        system_prompt = (
            "あなたはAI技術の最新ニュースを日本語で伝えるニュースボットです。\n"
            "与えられた英語のツイート内容を、日本語で要約または翻訳してください。\n\n"
            "【制約事項】\n"
            "1. 日本語の文字数は130文字以内に収めてください（Twitterの無料枠280文字制限のため）。\n"
            "2. 内容は正確に、かつ日本のユーザーにとって有益な情報を優先してください。\n"
            "3. 元のツイートが短い場合は直訳し、長い場合は重要なポイントを要約してください。\n"
            "4. ハッシュタグは最小限（1-2個）にしてください。\n"
            "5. 絵文字を適度に使って読みやすくしてください。"
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
        print("Starting bot execution...")
        for username in TARGET_USERNAMES:
            username = username.strip()
            print(f"Checking updates for @{username}...")
            
            user_id = self.get_user_id(username)
            if not user_id:
                continue
            
            last_id = self.get_last_processed_id(username)
            
            try:
                # Fetch recent tweets
                kwargs = {"max_results": 10, "tweet_fields": ["id", "text", "created_at"]}
                if last_id:
                    kwargs["since_id"] = last_id
                
                tweets = self.client.get_users_tweets(user_id, **kwargs)
                
                if not tweets.data:
                    print(f"No new tweets for @{username}.")
                    continue
                
                # Process tweets from oldest to newest
                new_tweets = sorted(tweets.data, key=lambda x: x.id)
                
                for tweet in new_tweets:
                    # 1. Double check against DB (Safety First)
                    if self.is_already_processed(tweet.id):
                        print(f"Tweet {tweet.id} already processed. Skipping.")
                        continue
                    
                    print(f"Processing new tweet: {tweet.id}")
                    
                    # 2. AI Translation/Summary
                    jp_text = self.process_tweet_content(tweet.text)
                    if not jp_text:
                        continue
                    
                    # 3. Post Quote Tweet
                    try:
                        self.client.create_tweet(
                            text=jp_text,
                            quote_tweet_id=tweet.id
                        )
                        print(f"Successfully posted quote tweet for {tweet.id}")
                        
                        # 4. Mark as processed in DB
                        self.mark_as_processed(tweet.id, username)
                    except Exception as e:
                        print(f"Error posting tweet: {e}")
                        # Even if posting fails, we might want to skip it next time or retry?
                        # Usually it's better NOT to mark as processed if it failed.
                
            except Exception as e:
                print(f"Error fetching tweets for @{username}: {e}")
        
        print("Bot execution finished.")

if __name__ == "__main__":
    bot = XBot()
    bot.run()
