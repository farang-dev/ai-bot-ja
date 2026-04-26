from fastapi import FastAPI, BackgroundTasks, HTTPException, Header
import os
from bot import XBot

app = FastAPI()

# Optional: Add a simple secret key to prevent unauthorized triggers
CRON_SECRET = os.getenv("CRON_SECRET")

@app.get("/")
def read_root():
    return {"status": "AI X Bot is running"}

@app.get("/run")
def trigger_bot(background_tasks: BackgroundTasks, x_cron_secret: str = Header(None)):
    """
    Endpoint to trigger the bot. 
    Can be called by cron-job.org
    """
    if CRON_SECRET and x_cron_secret != CRON_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    # Run the bot in the background so the request doesn't timeout
    background_tasks.add_task(run_bot_task)
    return {"message": "Bot execution started in background"}

def run_bot_task():
    try:
        bot = XBot()
        bot.run()
    except Exception as e:
        print(f"Background task error: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
