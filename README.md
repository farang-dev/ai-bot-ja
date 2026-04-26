# AI X Bot (Japanese Translator/Summarizer)

AI関連企業（OpenAI, Anthropic, Google AI, Perplexity）の最新ツイートを自動で検出し、OpenRouterを使用して日本語に翻訳・要約して引用ツイート（Quote Tweet）するボットです。

## 🚀 機能
- **GitHub Actions連携**: サーバー不要。無料で定期実行（10分おきなど）。
- **AI要約/翻訳**: OpenRouterの無料モデルを使用。
- **重複防止**: Supabaseを使用して、元ツイートIDベースで確実に重複を排除。
- **引用ツイート**: 元のツイートを引用する形で投稿。

## 📋 準備するもの
1. **X (Twitter) API キー**: [X Developer Portal](https://developer.twitter.com/en/portal/dashboard) で取得（Basicプラン推奨）。
2. **OpenRouter API キー**: [OpenRouter](https://openrouter.ai/) で取得。
3. **Supabase**: [Supabase](https://supabase.com/) でプロジェクトを作成し、`processed_tweets` テーブルを作成。

## 🛠 セットアップ

### 1. Supabase のテーブル作成
SQL Editorで以下を実行してください：
```sql
create table processed_tweets (
  tweet_id text primary key,
  username text not null,
  created_at timestamp with time zone default now() not null
);
```

### 2. GitHub Secrets の設定
GitHubリポジトリの `Settings > Secrets and variables > Actions` に移動し、以下の **New repository secret** を登録してください：

- `X_API_KEY`, `X_API_SECRET`
- `X_ACCESS_TOKEN`, `X_ACCESS_SECRET`
- `X_BEARER_TOKEN`
- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL` (例: `google/gemini-2.0-flash-exp:free`)
- `SUPABASE_URL`, `SUPABASE_KEY`
- `TARGET_USERNAMES` (例: `OpenAI,anthropicai,GoogleAI,perplexity_ai`)

### 3. デプロイ
GitHubにコードをプッシュするだけで、自動的に GitHub Actions が動き出します。

## ⏰ 実行間隔の変更
`.github/workflows/cron.yml` の `cron: '*/10 * * * *'` の部分を書き換えることで変更可能です。

## ⚠️ 注意点
- **状態の保存**: このコードは `state.json` を使って最後に取得したツイートIDを記録します。Render（Free）などの環境では、サーバーが再起動するとこのファイルが消えるため、過去のツイートを再投稿してしまう可能性があります。
- **恒久的な解決策**: Supabase や Redis などのデータベースに ID を保存するようにカスタマイズすることをお勧めします。
