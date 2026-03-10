import asyncio
import time
import os
import io
import json
from datetime import datetime
from dotenv import load_dotenv
import aiohttp
import motor.motor_asyncio 

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, InputMediaPhoto

# --- 🧠 MACHINE LEARNING & GRAPHING LIBRARIES ---
import numpy as np
from sklearn.ensemble import RandomForestClassifier
import matplotlib
matplotlib.use('Agg') # Background တွင် ပုံဆွဲရန်
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings("ignore")
# ------------------------------------------

load_dotenv()

# ==========================================
# ⚙️ 1. CONFIGURATION
# ==========================================
USERNAME = os.getenv("BIGWIN_USERNAME")
PASSWORD = os.getenv("BIGWIN_PASSWORD")
TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.getenv("CHANNEL_ID")
MONGO_URI = os.getenv("MONGO_URI") 

if not all([USERNAME, PASSWORD, TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, MONGO_URI]):
    print("❌ Error: .env ဖိုင်ထဲတွင် အချက်အလက်များ ပြည့်စုံစွာ မပါဝင်ပါ။")
    exit()
  
bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# MongoDB Setup
db_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = db_client['bigwin_database'] 
history_collection = db['game_history'] 
predictions_collection = db['predictions'] 

# ==========================================
# 🔧 2. SYSTEM VARIABLES 
# ==========================================
CURRENT_TOKEN = ""
LAST_PROCESSED_ISSUE = ""
LAST_PREDICTED_ISSUE = ""
LAST_PREDICTED_RESULT = ""
MAIN_MESSAGE_ID = None # Message တစ်ခုတည်းကိုသာ Update လုပ်ရန်

BASE_HEADERS = {
    'authority': 'api.bigwinqaz.com',
    'accept': 'application/json, text/plain, */*',
    'content-type': 'application/json;charset=UTF-8',
    'origin': 'https://www.777bigwingame.app',
    'referer': 'https://www.777bigwingame.app/',
    'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36',
}

async def init_db():
    try:
        await history_collection.create_index("issue_number", unique=True)
        await predictions_collection.create_index("issue_number", unique=True)
        print("🗄 MongoDB ချိတ်ဆက်မှု အောင်မြင်ပါသည်။ (📊 Dynamic Graph Engine Enabled)")
    except Exception as e:
        pass

# ==========================================
# 🔑 3. ASYNC API FUNCTIONS
# ==========================================
async def fetch_with_retry(session, url, headers, json_data, retries=3):
    for attempt in range(retries):
        try:
            async with session.post(url, headers=headers, json=json_data, timeout=10) as response:
                return await response.json()
        except Exception:
            if attempt == retries - 1: return None
            await asyncio.sleep(1)

async def login_and_get_token(session: aiohttp.ClientSession):
    global CURRENT_TOKEN
    json_data = {
        'username': '959680090540',
        'pwd': 'Mitheint11',
        'phonetype': 1,
        'logintype': 'mobile',
        'packId': '',
        'deviceId': '51ed4ee0f338a1bb24063ffdfcd31ce6',
        'language': 7,
        'random': '452fa309995244de92103c0afbefbe9a',
        'signature': '202C655177E9187D427A26F3CDC00A52',
        'timestamp': 1773021618,
    }
    data = await fetch_with_retry(session, 'https://api.bigwinqaz.com/api/webapi/Login', BASE_HEADERS, json_data)
    if data and data.get('code') == 0:
        token_str = data.get('data', {}) if isinstance(data.get('data'), str) else data.get('data', {}).get('token', '')
        CURRENT_TOKEN = f"Bearer {token_str}"
        print("✅ Login အောင်မြင်ပါသည်။ Token အသစ် ရရှိပါပြီ。\n")
        return True
    return False

# ==========================================
# 🧠 4. MACHINE LEARNING
# ==========================================
def train_and_predict_ml(history_docs):
    if len(history_docs) < 30: return None
    docs = list(reversed(history_docs)) 
    X, y = [], []
    window_size = 5 
    def enc_size(s): return 1 if s == 'BIG' else 0
    def enc_par(p): return 1 if p == 'EVEN' else 0
    def enc_time(t): return {'MORNING':0, 'AFTERNOON':1, 'NIGHT':2, 'LATE_NIGHT':3}.get(t, 0)
    for i in range(len(docs) - window_size):
        window_docs = docs[i : i+window_size]
        target_doc = docs[i+window_size]
        features = []
        for doc in window_docs:
            features.extend([enc_size(doc.get('size', 'BIG')), int(doc.get('number', 0)), enc_par(doc.get('parity', 'EVEN')), enc_time(doc.get('time_context', 'MORNING'))])
        X.append(features)
        y.append(enc_size(target_doc.get('size', 'BIG')))
    if len(X) < 10: return None
    clf = RandomForestClassifier(n_estimators=100, max_depth=7, random_state=42)
    clf.fit(X, y)
    latest_features = []
    for doc in docs[-window_size:]:
        latest_features.extend([enc_size(doc.get('size', 'BIG')), int(doc.get('number', 0)), enc_par(doc.get('parity', 'EVEN')), enc_time(doc.get('time_context', 'MORNING'))])
    return "BIG" if clf.predict([latest_features])[0] == 1 else "SMALL"

# ==========================================
# 🎨 5. DYNAMIC GRAPH GENERATOR 
# ==========================================
def generate_winrate_chart(predictions):
    wins, losses = 0, 0
    history_wr, bar_colors = [], []
    
    # တွက်ချက်ခြင်း (အဟောင်းမှ အသစ်သို့)
    for p in reversed(predictions): 
        if 'WIN' in p.get('win_lose', ''):
            wins += 1
            bar_colors.append('#26a69a') # အစိမ်း
        else:
            losses += 1
            bar_colors.append('#ef5350') # အနီ
        total = wins + losses
        history_wr.append((wins / total) * 100 if total > 0 else 0)
        
    total_played = wins + losses
    win_rate = int((wins / total_played * 100)) if total_played > 0 else 0

    # ပုံဆွဲခြင်း
    fig, ax = plt.subplots(figsize=(8, 4.5), facecolor='#1e222d')
    ax.set_facecolor('#1e222d')
    
    if total_played > 0:
        x = np.arange(total_played)
        # အစိမ်း/အနီ တုံးများ
        ax.bar(x, [55]*total_played, color=bar_colors, width=0.9, bottom=0)
        # မျဉ်းကြောင်း
        ax.plot(x, history_wr, color='#2979ff', linewidth=3, marker='o', markersize=6, markerfacecolor='#1e222d', markeredgecolor='#2979ff', markeredgewidth=2)
    
    ax.set_ylim(0, 105)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels(['0%', '25%', '50%', '75%', '100%'], color='#787b86', fontsize=10)
    ax.set_xticks([])
    
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#363a45')
    ax.spines['bottom'].set_color('#363a45')
    ax.grid(axis='y', color='#363a45', linestyle='-', linewidth=0.5)
    
    # စာသားများ
    plt.suptitle("WINRATE TRACKING", color='white', fontsize=20, fontweight='bold', y=0.96)
    plt.figtext(0.5, 0.05, f"{win_rate}%", color='white', fontsize=26, fontweight='bold', ha='center')
    plt.figtext(0.38, 0.0, f"WINS: {wins}", color='#26a69a', fontsize=12, ha='center', fontweight='bold')
    plt.figtext(0.62, 0.0, f"LOSSES: {losses}", color='#ef5350', fontsize=12, ha='center', fontweight='bold')
    plt.figtext(0.5, -0.06, f"PREDICTION COUNT: {total_played}/20", color='#787b86', fontsize=10, ha='center')

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=100, facecolor='#1e222d')
    buf.seek(0)
    plt.close(fig)
    return buf

# ==========================================
# 🚀 6. MAIN LOGIC & UI UPDATER
# ==========================================
async def check_game_and_predict(session: aiohttp.ClientSession):
    global CURRENT_TOKEN, LAST_PROCESSED_ISSUE, LAST_PREDICTED_ISSUE, LAST_PREDICTED_RESULT, MAIN_MESSAGE_ID
    
    if not CURRENT_TOKEN:
        if not await login_and_get_token(session): return

    headers = BASE_HEADERS.copy()
    headers['authorization'] = CURRENT_TOKEN

    json_data = {
        'pageSize': 10, 'pageNo': 1, 'typeId': 30, 'language': 7,
        'random': '1ef0a7aca52b4c71975c031dda95150e', 'signature': '7D26EE375971781D1BC58B7039B409B7', 'timestamp': 1772985040,
    }

    data = await fetch_with_retry(session, 'https://api.bigwinqaz.com/api/webapi/GetNoaverageEmerdList', headers, json_data)
    if not data or data.get('code') != 0:
        if data and (data.get('code') == 401 or "token" in str(data.get('msg')).lower()): CURRENT_TOKEN = ""
        return

    records = data.get("data", {}).get("list", [])
    if not records: return
    
    latest_record = records[0]
    latest_issue = str(latest_record["issueNumber"])
    latest_number = int(latest_record["number"])
    latest_size = "BIG" if latest_number >= 5 else "SMALL"
    
    is_new_issue = (latest_issue != LAST_PROCESSED_ISSUE)
    
    if is_new_issue:
        LAST_PROCESSED_ISSUE = latest_issue
        
        await history_collection.update_one(
            {"issue_number": latest_issue}, 
            {"$setOnInsert": {
                "number": latest_number, "size": latest_size, 
                "parity": "EVEN" if latest_number % 2 == 0 else "ODD",
                "time_context": "MORNING" # Simplified for space
            }}, upsert=True
        )
        
        if LAST_PREDICTED_ISSUE == latest_issue:
            is_win = (LAST_PREDICTED_RESULT == latest_size)
            win_lose_status = "WIN ✅" if is_win else "LOSE ❌"
            await predictions_collection.update_one(
                {"issue_number": latest_issue}, 
                {"$set": {"actual_size": latest_size, "actual_number": latest_number, "win_lose": win_lose_status}}
            )

    next_issue = str(int(latest_issue) + 1)
    
    # 🧠 ခန့်မှန်းခြင်း
    cursor = history_collection.find().sort("issue_number", -1).limit(5000)
    history_docs = await cursor.to_list(length=5000)
    
    try:
        ml_pred = await asyncio.to_thread(train_and_predict_ml, history_docs)
        predicted = ml_pred if ml_pred else ("BIG" if history_docs[0].get('size') == 'SMALL' else "SMALL")
    except:
        predicted = "BIG"
        
    LAST_PREDICTED_ISSUE = next_issue
    LAST_PREDICTED_RESULT = predicted
    
    await predictions_collection.update_one({"issue_number": next_issue}, {"$setOnInsert": {"predicted_size": LAST_PREDICTED_RESULT}}, upsert=True)

    # 📊 Data ဆွဲထုတ်ခြင်း
    pred_cursor = predictions_collection.find({"win_lose": {"$ne": None}}).sort("issue_number", -1).limit(20)
    last_20_preds = await pred_cursor.to_list(length=20)
    
    # 🎨 ဇယား ဖန်တီးခြင်း (၁၀ ပွဲစာ)
    table_str = "<code>Period    | Result  | W/L\n"
    table_str += "----------|---------|----\n"
    for p in last_20_preds[:10]:
        iss = p.get('issue_number', '0000000')
        iss_short = f"{iss[:3]}**{iss[-4:]}" 
        act_size = p.get('actual_size', 'BIG')
        act_num = p.get('actual_number', 0)
        res_str = f"{act_num}-{act_size}"
        wl_str = "✅" if "WIN" in p.get("win_lose", "") else "❌"
        table_str += f"{iss_short:<10}| {res_str:<7} | {wl_str}\n"
    table_str += "</code>"

    # --- အချိန်မှတ်စက် ---
    seconds_left = 30 - (int(time.time()) % 30)
    
    # 🎯 Telegram Caption ဖန်တီးခြင်း
    tg_caption = (
        f"<b>WIN GO 30 SECONDS</b>\n"
        f"⏰ Next Result In: <b>{seconds_left}s</b>\n\n"
        f"{table_str}\n"
        f"🅿️ <b>Period:</b> {next_issue[:3]}**{next_issue[-4:]}\n"
        f"🎯 <b>Predict: {predicted}</b>\n"
        f"🤿 <b>Network:</b> Pure ML Engine"
    )
    
    # 🔄 ပုံနှင့်စာကို အလိုအလျောက် Update လုပ်ခြင်း
    try:
        if is_new_issue or not MAIN_MESSAGE_ID:
            # ပွဲစဉ်အသစ် ထွက်လာမှသာ ပုံကို အသစ်ပြန်ဆွဲမည် (API Limit မထိစေရန်)
            img_buf = await asyncio.to_thread(generate_winrate_chart, last_20_preds)
            photo = BufferedInputFile(img_buf.read(), filename="chart.png")
            
            if MAIN_MESSAGE_ID:
                media = InputMediaPhoto(media=photo, caption=tg_caption, parse_mode="HTML")
                await bot.edit_message_media(chat_id=TELEGRAM_CHANNEL_ID, message_id=MAIN_MESSAGE_ID, media=media)
            else:
                msg = await bot.send_photo(chat_id=TELEGRAM_CHANNEL_ID, photo=photo, caption=tg_caption)
                MAIN_MESSAGE_ID = msg.message_id
        else:
            # စက္ကန့်လျော့နေချိန်တွင် စာ (Caption) ကိုသာ ပြောင်းလဲမည်
            if MAIN_MESSAGE_ID:
                await bot.edit_message_caption(chat_id=TELEGRAM_CHANNEL_ID, message_id=MAIN_MESSAGE_ID, caption=tg_caption)
    except TelegramBadRequest as e:
        if "message to edit not found" in str(e):
            MAIN_MESSAGE_ID = None # ဖျက်ခံရပါက အသစ်ပြန်ပို့ရန်

# ==========================================
# 🔄 6. BACKGROUND TASK
# ==========================================
async def auto_broadcaster():
    await init_db() 
    async with aiohttp.ClientSession() as session:
        await login_and_get_token(session)
        while True:
            await check_game_and_predict(session)
            await asyncio.sleep(2)

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    await message.reply("👋 မင်္ဂလာပါ။ စနစ်က Channel ထဲတွင် Winrate Graph ပုံနှင့်တကွ Auto Update လုပ်ပေးနေပါမည်။")

async def main():
    print("🚀 Aiogram Bigwin Bot (Graphic UI Edition) စတင်နေပါပြီ...\n")
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(auto_broadcaster())
    await dp.start_polling(bot)

if __name__ == '__main__':
    try: asyncio.run(main())
    except KeyboardInterrupt: print("Bot ကို ရပ်တန့်လိုက်ပါသည်။")
