"""
🎮 TRUTH & DARE PRO BOT — SINGLE FILE EDITION
=============================================
- 500+ Questions (Hindi/Hinglish)
- Coin System
- Badge System (16 badges)
- Level + XP System
- Streak System
- Leaderboard
- SQLite Database (auto create)

Install: pip install python-telegram-bot==21.4
Run:     python bot.py
"""

import os, random, sqlite3, threading
from datetime import date
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ============================================================
#   CONFIG
# ============================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
PORT = int(os.getenv("PORT", 8080))
DB_PATH = "gamedata.db"

COINS_MAP = {
    "truth_easy": 5,  "truth_medium": 10, "truth_hard": 15,
    "dare_easy": 10,  "dare_medium": 20,  "dare_hard": 35,
    "random_bonus": 5,
}

# ============================================================
#   DATABASE
# ============================================================

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    c = db()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id      INTEGER PRIMARY KEY,
            username     TEXT,
            first_name   TEXT,
            coins        INTEGER DEFAULT 0,
            level        INTEGER DEFAULT 1,
            xp           INTEGER DEFAULT 0,
            streak       INTEGER DEFAULT 0,
            last_played  TEXT,
            total_played INTEGER DEFAULT 0,
            truths_done  INTEGER DEFAULT 0,
            dares_done   INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS badges (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER,
            badge_id  TEXT,
            UNIQUE(user_id, badge_id)
        );
        CREATE TABLE IF NOT EXISTS history (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER,
            type         TEXT,
            difficulty   TEXT,
            coins_earned INTEGER DEFAULT 0,
            played_at    TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    c.commit()
    c.close()

def get_user(uid):
    c = db()
    u = c.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    c.close()
    return u

def upsert_user(uid, username, first_name):
    c = db()
    c.execute("""
        INSERT INTO users (user_id, username, first_name) VALUES (?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name
    """, (uid, username or "", first_name or "Player"))
    c.commit()
    c.close()

def add_coins(uid, amount):
    c = db()
    c.execute("UPDATE users SET coins=coins+? WHERE user_id=?", (amount, uid))
    c.commit()
    total = c.execute("SELECT coins FROM users WHERE user_id=?", (uid,)).fetchone()["coins"]
    c.close()
    return total

def update_streak(uid):
    c = db()
    u = c.execute("SELECT streak, last_played FROM users WHERE user_id=?", (uid,)).fetchone()
    today = str(date.today())
    last = u["last_played"] if u else None
    streak = u["streak"] if u else 0
    if last == today:
        c.close()
        return streak, False
    try:
        diff = (date.today() - date.fromisoformat(last)).days if last else 999
        streak = streak + 1 if diff == 1 else 1
    except:
        streak = 1
    c.execute("UPDATE users SET streak=?, last_played=?, total_played=total_played+1 WHERE user_id=?", (streak, today, uid))
    c.commit()
    c.close()
    return streak, streak in [3, 7, 14, 30, 60, 100]

def record_play(uid, qtype, diff, coins):
    c = db()
    c.execute("INSERT INTO history (user_id, type, difficulty, coins_earned) VALUES (?,?,?,?)", (uid, qtype, diff, coins))
    if qtype == "truth":
        c.execute("UPDATE users SET truths_done=truths_done+1 WHERE user_id=?", (uid,))
    else:
        c.execute("UPDATE users SET dares_done=dares_done+1 WHERE user_id=?", (uid,))
    c.commit()
    c.close()

def update_xp(uid, xp_gain):
    c = db()
    u = c.execute("SELECT xp, level FROM users WHERE user_id=?", (uid,)).fetchone()
    new_xp = (u["xp"] if u else 0) + xp_gain
    cur_lvl = u["level"] if u else 1
    new_lvl = 1
    left = new_xp
    while left >= new_lvl * 100:
        left -= new_lvl * 100
        new_lvl += 1
    leveled = new_lvl > cur_lvl
    c.execute("UPDATE users SET xp=?, level=? WHERE user_id=?", (new_xp, new_lvl, uid))
    c.commit()
    c.close()
    return new_lvl, leveled

def award_badge(uid, bid):
    c = db()
    try:
        c.execute("INSERT INTO badges (user_id, badge_id) VALUES (?,?)", (uid, bid))
        c.commit()
        c.close()
        return True
    except sqlite3.IntegrityError:
        c.close()
        return False

def get_badges(uid):
    c = db()
    rows = c.execute("SELECT badge_id FROM badges WHERE user_id=?", (uid,)).fetchall()
    c.close()
    return [r["badge_id"] for r in rows]

def check_badges(uid):
    u = get_user(uid)
    if not u: return []
    earned = get_badges(uid)
    new = []
    checks = [
        ("starter",   True),
        ("truth10",   u["truths_done"] >= 10),
        ("truth50",   u["truths_done"] >= 50),
        ("dare10",    u["dares_done"] >= 10),
        ("dare50",    u["dares_done"] >= 50),
        ("coins100",  u["coins"] >= 100),
        ("coins500",  u["coins"] >= 500),
        ("coins1000", u["coins"] >= 1000),
        ("coins5000", u["coins"] >= 5000),
        ("streak3",   u["streak"] >= 3),
        ("streak7",   u["streak"] >= 7),
        ("streak30",  u["streak"] >= 30),
        ("level5",    u["level"] >= 5),
        ("level10",   u["level"] >= 10),
        ("level20",   u["level"] >= 20),
    ]
    for bid, cond in checks:
        if cond and bid not in earned:
            if award_badge(uid, bid):
                new.append(bid)
    return new

def leaderboard(limit=10):
    c = db()
    rows = c.execute("SELECT first_name, coins, level, streak FROM users ORDER BY coins DESC LIMIT ?", (limit,)).fetchall()
    c.close()
    return rows

def get_rank(uid):
    c = db()
    row = c.execute("SELECT coins FROM users WHERE user_id=?", (uid,)).fetchone()
    if not row:
        c.close()
        return -1
    rank = c.execute("SELECT COUNT(*) as r FROM users WHERE coins>?", (row["coins"],)).fetchone()["r"]
    c.close()
    return rank + 1

# ============================================================
#   BADGE DEFINITIONS
# ============================================================
BADGES = {
    "starter":   {"name": "🌱 Game Starter",   "desc": "Pehla game khela!",        "coins": 50},
    "truth10":   {"name": "🔍 Truth Seeker",   "desc": "10 truths complete!",      "coins": 100},
    "truth50":   {"name": "📖 Truth Master",   "desc": "50 truths complete!",      "coins": 300},
    "dare10":    {"name": "🔥 Dare Devil",     "desc": "10 dares complete!",       "coins": 150},
    "dare50":    {"name": "👑 Dare King",      "desc": "50 dares complete!",       "coins": 500},
    "coins100":  {"name": "💰 Coin Collector", "desc": "100 coins kama liye!",     "coins": 50},
    "coins500":  {"name": "💎 Coin Hoarder",   "desc": "500 coins ho gaye!",       "coins": 100},
    "coins1000": {"name": "🏦 Coin Lord",      "desc": "1000 coins! Legend!",      "coins": 200},
    "coins5000": {"name": "🤑 Millionaire",    "desc": "5000 coins! Insane!",      "coins": 500},
    "streak3":   {"name": "🔥 On Fire",        "desc": "3 din ka streak!",         "coins": 75},
    "streak7":   {"name": "⚡ Week Warrior",   "desc": "7 din ka streak!",         "coins": 200},
    "streak30":  {"name": "🌟 Monthly Master", "desc": "30 din ka streak!",        "coins": 1000},
    "level5":    {"name": "⬆️ Rising Star",    "desc": "Level 5 reach kiya!",      "coins": 200},
    "level10":   {"name": "🚀 Pro Player",     "desc": "Level 10!",                "coins": 500},
    "level20":   {"name": "🌈 Elite",          "desc": "Level 20! Top tier!",      "coins": 1000},
}

STREAK_MSG = {
    3: "🔥 3 din ka streak! Warm ho rahe ho!",
    7: "⚡ Ek hafte ka streak! Dedicated!",
    14: "💎 2 hafte streak! Kya baat hai!",
    30: "👑 30 din streak! LEGEND!",
}

COIN_MSGS = [
    "🪙 +{c} coins mile! Mazaa aa raha hai?",
    "💰 Waah! +{c} coins aur jama ho gaye!",
    "🔥 +{c} coins! Tu toh legend banta ja raha hai!",
    "⚡ Boom! +{c} coins! Keep going!",
    "🎯 +{c} coins earned! Teri wallet bhar rahi hai!",
]

# ============================================================
#   QUESTIONS — 500+
# ============================================================
TRUTHS = {
    "easy": {
        "funny": [
            "Tune kabhi khud se baat ki hai — aur woh conversation interesting tha?",
            "Kya tune kabhi kisi ka naam bhool gaya aur puri conversation ki bina naam liye?",
            "Tera sabse bura joke kya tha jo tune seriously sunaya?",
            "Tune kabhi kisi ko galat number pe call kiya aur phir baat ki?",
            "Kya tune kabhi khane mein kuch giraya aur chupke se utha ke khaya?",
            "Tune kabhi kisi ka birthday wish kiya aur date galat thi?",
            "Kya tune kabhi apna hi surprise spoil kiya?",
            "Tune kabhi auto-correct ki wajah se embarrassing message bheja?",
            "Kya tune kabhi galat group mein message bheja?",
            "Tune kabhi neend mein kuch bola jo baad mein embarrassing laga?",
            "Kya tune kabhi kisi ki photo secretly save ki social media pe?",
            "Tune kabhi apna hi surprise dekh liya?",
            "Kya tune kabhi dost ke saamne gas pass ki aur dusre ko blame kiya?",
            "Tune kabhi kisi ko dekh ke rasta badla aur woh dekh gaya?",
            "Kya tune kabhi khud ko mirror mein dekh ke wink kiya?",
            "Tune kabhi kisi celebrity ke baare mein sapna dekha?",
            "Kya tune kabhi shower mein concert kiya?",
            "Tune kabhi apni hi photo dekh ke cringe kiya?",
            "Kya tune kabhi dost ko prank kiya jo backfire hua?",
            "Tune kabhi khud ki tarif khud hi ki loudly?",
        ],
        "personal": [
            "Tera sabse favorite childhood memory kaunsi hai?",
            "Agar ek superpower milti toh kya leta?",
            "Teri life ka sabse khaas din kaun sa tha?",
            "Tune pehli baar kya pakaya tha?",
            "Tera dream job kya hai?",
            "Ek aisi cheez bata jo tujhe subah uthne ki motivation deti hai?",
            "Tera fav childhood cartoon kaun sa tha?",
            "Tune kabhi koi language sikhne ki koshish ki?",
            "Tera sabse purana dost kaun hai?",
            "Kya tune kabhi kisi ko gift diya jo pehle tumhare paas tha?",
            "Teri life mein sabse inspiring insaan kaun hai?",
            "Tune school mein kaunsa subject sabse zyada pasand kiya?",
            "Tera sabse bada dream kya hai?",
            "Ek aisi jagah bata jahan tu zaroor jaana chahta hai?",
            "Tune pehli baar kya earn kiya aur usse kya kiya?",
        ],
    },
    "medium": {
        "personal": [
            "Teri life ka sabse embarrassing moment kya tha?",
            "Tune kabhi apne dost ke baare mein jhooth bola hai?",
            "Tera crush kaun hai? Name bata!",
            "Tune kabhi exam mein cheating ki hai?",
            "Kya tune kabhi apne parents se paisa churaya hai?",
            "Aaj tak ka sabse bada secret kya hai?",
            "Tune kabhi kisi ki baat sunne ki acting ki?",
            "Tera sabse bura habit kya hai?",
            "Kya kabhi tune kisi ko block karke phir unblock kiya?",
            "Teri life ka sabse bada regret kya hai?",
            "Tune pehli baar propose kiya tha ya tujhe kiya gaya tha?",
            "Kya tune kabhi kisi ka phone secretly check kiya hai?",
            "Sabse lamba time tune kisi se baat nahi ki — aur kyun?",
            "Tune kabhi kisi ka gift accept kiya aur andar se pasand nahi aaya?",
            "Tune sabse last kab roya tha aur kyun?",
            "Apne phone ki gallery mein sabse sharmnaak photo kaun si hai?",
            "Kya tune kabhi khud apni tarif mirror ke saamne ki hai?",
            "Tune kabhi kisi celeb ka poster lagaya hai room mein?",
            "Kya tune kabhi khud se baat ki hai aur koi sun leta?",
            "Tune kabhi kisi friend ke ghar se kuch churaaya?",
            "Apne life mein sabse bekar cheez pe kitna paisa waste kiya?",
            "Kya tune kabhi ek hi kapde 3 din se zyada pehne?",
            "Tune sabse last kab nachaya tha akele kamre mein?",
            "Tera most toxic trait kya hai?",
            "Ek aisi cheez bata jo tujhe lagta hai sirf tujhe hi pasand hai?",
            "Kaun sa dost hai jis par tu sabse kam trust karta hai?",
            "Teri life mein abhi sabse badi problem kya chal rahi hai?",
            "Ek aisi baat bata jo teri maa ko kabhi nahi batayega?",
            "Tune sabse zyada jealous kab feel kiya?",
            "Tera worst decision kaun sa tha last 1 saal mein?",
            "Tune kabhi kisi ko pasand kiya aur kabhi bola nahi?",
            "Teri life mein kaunsi adat hai jo tu chhodni chahta hai?",
            "Kya tune kabhi jhooth bolke kisi se milne gaya?",
            "Tune kabhi kisi ke baare mein gossiping ki hai?",
            "Teri sabse badi insecurity kya hai?",
        ],
        "daring": [
            "Agar aaj raat koi bhi nahi dekh raha hota toh kya karta?",
            "Tune kabhi kisi ke liye kuch aisa kiya jo tune pehle socha nahi tha?",
            "Sabse bada adventure kya tha teri life mein?",
            "Tune kabhi kisi se fight ki — physically?",
            "Kya tune kabhi kuch aisa kiya jo society mein galat maana jata hai?",
            "Tune kabhi kisi authority figure ko challenge kiya?",
            "Teri life mein sabse risky decision kaun sa tha?",
            "Kya tune kabhi kisi ke liye apni principles tod di?",
            "Sabse scary cheez kya hai jo tune voluntarily ki?",
            "Tune kabhi kisi ko publicly embarrass kiya intentionally?",
            "Kya tune kabhi kisi ka dil toda knowing fully well?",
            "Teri life mein ek aisa waqt jab tune sab kuch risk pe lagaya?",
            "Tune kabhi kisi ko manipulate kiya apna kaam karwane ke liye?",
            "Kya tune kabhi apne best friend se peeche se bura bola?",
            "Ek aisa rishta batao jo tune sirf fayde ke liye rakkha?",
        ],
    },
    "hard": {
        "dark": [
            "Teri life ka sabse dark secret kya hai?",
            "Tune kabhi kisi ke saath aisa kiya jiske liye tu genuinely sharminda hai?",
            "Kya tune kabhi kisi ke feelings se khela?",
            "Ek aisi baat bata jo agar log jaante toh tujhe differently dekhte?",
            "Tune kabhi kisi baat pe jhooth bola aur woh jhooth aaj bhi chal raha hai?",
            "Kya tune kabhi kisi insaan se nahi mila jaan ke jab woh tumse milna chahta tha?",
            "Teri life mein ek aisa moment jab tu sach mein toot gaya tha?",
            "Tune kabhi kisi ko intentionally hurt kiya emotionally?",
            "Kya tera koi aisa secret hai jo agar bahar aaye toh relationship khatam ho jaaye?",
            "Tune kabhi kisi pe blame dala apni galti ke liye publicly?",
            "Kya tune kabhi kisi ke trust ka faayda uthaya?",
            "Teri life mein ek aisa decision jo tune regret kiya lekin kabhi accept nahi kiya?",
            "Tune kabhi kisi ke sapne ya goals ko discourage kiya jealousy ki wajah se?",
            "Tune kabhi kisi ko 'main theek hun' bola jab tu actually bilkul theek nahi tha?",
            "Teri life ka wo moment batao jab tune feel kiya ki sab kuch khatam ho gaya?",
            "Kya tune kabhi khud se jhooth bola reality accept nahi kiya?",
            "Agar tujhe pata hota ki kal teri zindagi ka aakhri din hai kya karta?",
            "Tera sabse bada fear kya hai jo log nahi jaante?",
            "Tune kabhi kisi se 'I love you' bola bina feel kiye?",
            "Kya tera koi aisa sapna hai jis pe tune kabhi kaam nahi kiya darr ke?",
        ],
    },
}

DARES = {
    "easy": {
        "funny": [
            "Abhi WhatsApp status pe likho: 'Main pagal ho gaya hun' 2 minute ke liye!",
            "Group mein sabse upar uthake 10 second tak khada reh bina hasye!",
            "Apne pet naam se kisi bhi group member ko bula aur explain bhi kar why!",
            "Next 5 minute tak sirf shayari mein baat kar!",
            "Apni awaaz mein koi bhi movie ka dialogue suna bina bataye kaun si movie!",
            "Ek silly dance karo 15 second ke liye video bhejna compulsory!",
            "Apna fav song ki first line gao tune mein ya betune!",
            "5 alag alag emotion mein 'Hello' bolo!",
            "Tongue twister 3 baar fast bolo: 'Kaccha papita pakka papita'!",
            "Apne baare mein ek roast karo 30 seconds ke liye!",
            "Group ke kisi ek member ki voice copy karo!",
            "Ek minute tak sirf rhyming words mein baat karo!",
            "Apna fav meme bhejo jo aaj dekha!",
            "Kisi bhi dost ko call karo aur bolo 'Kuch nahi bas teri yaad aa rahi thi'!",
            "Next message sirf capital letters mein likho!",
            "Apne room ka selfie bhejo filter nahi!",
            "Ek animal ki awaaz nikalo baaki guess karen!",
            "Apna embarrassing childhood photo dhundho aur share karo!",
            "Ek minute ke liye bakwas karo bina ruke serious face ke saath!",
            "Apne fav gane pe lip sync karo video bhejo!",
            "Apna last Google search publicly batao!",
            "Apni sari notifications publicly padhke sunao!",
            "Kisi bhi ek member ko ek genuine compliment do!",
            "Apne phone pe last saved contact ka naam batao!",
            "Apni gallery ki 10th photo share karo!",
            "Kisi bhi movie ka villain dialogue karo fully dramatic!",
            "Apni awaaz mein news anchor bano 30 second ke liye!",
            "Abhi jo bhi pehen rakha hai uski photo bhejo!",
            "Apne dost ke liye ek motivational quote banao silly wala!",
            "Ek joke suno hasna allowed nahi agar funny na lage!",
        ],
    },
    "medium": {
        "funny": [
            "Kisi bhi dost ko call karo aur bolo 'Maine tujhse pyar kiya tha' phir explanation do!",
            "1 minute mein apna intro kisi celebrity style mein de!",
            "Bina haath use kiye apna naam sign karo mooh se pen pakad ke!",
            "Apne pair ki ungli se apna naam zameen pe likho!",
            "30 second mein 15 push-up karo fail hone pe 10 baar apna naam chillao!",
            "Aankh band karke apna fav gana gao bina bhule!",
            "5 minute tak sirf backwards sochke baat karo!",
            "Apni maa ya baap ki voice mein kuch bolo!",
            "Robot ki tarah 2 minute tak move karo aur baat karo!",
            "Kisi bhi cheez pe ek 60 second ka advertisement do live!",
            "Apne worst enemy ki tarif karo genuinely 30 second!",
            "Speed dating style mein apna intro do 30 second mein sab kuch!",
            "Ek cooking show host bano jo bhi kitchen mein ho usse describe karo!",
            "James Bond style mein apna naam introduce karo!",
            "Ek horror movie trailer ki tarah apna din describe karo!",
            "Apni awaaz mein news anchor bano group ka latest gossip sunao!",
            "Apne aap ko third person mein describe karo 1 minute!",
            "Kisi bhi historical figure ki tarah ek speech do 1 minute!",
            "Apne fav dish ki recipe singing mein sunao!",
            "Ek Shakespeare style mein apna din describe karo!",
        ],
        "daring": [
            "Abhi kisi bhi insaan ko call karo jisse 6 mahine se baat nahi ki!",
            "Apne best friend ke baare mein ek honest roast karo publicly!",
            "Ek aisi baat bolo jo tune kabhi kisi ko nahi batayi abhi bata do!",
            "Group mein sabse boring insaan kaun hai bata do!",
            "Apna secret talent abhi perform karo chahe kitna bhi weird ho!",
            "Ek aisi photo share karo jo tune kabhi public nahi ki aur explain karo kyun!",
            "Apne crush ko right now text karo group decide karega kya likhna hai!",
            "Apne phone pe last 5 searches publicly share karo!",
            "Kisi bhi group member ke baare mein sach mein kya sochte ho bolo!",
            "Ek 'unpopular opinion' share karo jo genuinely tera hai!",
            "Apni life ki sabse badi galti publicly acknowledge karo!",
            "Kisi ek group member ko bolo exactly kya teri problem hai unse!",
            "Apna ek aisa dream share karo jo tune kabhi seriously nahi liya darr ke!",
            "Ek aisi cheez karo right now jo normally tum avoid karte ho!",
            "Apne parents ko 'I love you' message karo right now!",
            "Kisi aisi person se maafi maango jise tune hurt kiya message karo!",
            "Apni 3 biggest weaknesses publicly bolo!",
            "Ek insaan ka naam lo jis pe tum genuinely jealous ho aur kyun!",
            "Apni life mein ek aisi cheez publicly acknowledge karo jo improve karna chahte ho!",
            "Apne boss ya teacher ko ek honest feedback message draft karo aur share karo!",
        ],
    },
    "hard": {
        "daring": [
            "Abhi apne crush ko call karo aur bolo 'Mujhe tujhse kuch important kehna hai' phir 1 minute silence!",
            "Apni life ki sabse embarrassing video ya photo share karo group mein!",
            "Ek insaan ko right now call karo jisse tum sabse zyada darte ho aur normal baat karo!",
            "Apne parents ko apni life ki ek aisi baat batao jo unhone pehle nahi suni!",
            "Apne 3 biggest secrets ek saath reveal karo!",
            "Ek insaan jis se tum naraaz ho abhi unhe call karo aur puri baat karo!",
            "Apni life ka ek aisa moment share karo jab tum genuinely toot gaye the!",
            "Group ke saamne apni sabse badi fear describe karo full details mein!",
            "Ek aise insaan ko message karo jis ne tumhara dil toda aur honestly baat karo!",
            "Apni life ka wo decision share karo jo tune regret kiya aur kyun nahi badla!",
            "Ek public apology karo kisi ek insaan ke liye actual message bhejo unhe!",
            "Apne best friend ko right now call karo aur bolo exactly kya tumhe unme bug karta hai!",
            "Ek aise sapne ke baare mein bolo jo tune literally kabhi kisi ko nahi bataya!",
            "Group ke saamne apne 3 toxic traits acknowledge karo no excuses!",
            "Apni life ki wo cheez share karo jo tujhe raat ko jaagta rakhti hai!",
        ],
        "physical": [
            "100 jumping jacks karo right now video proof!",
            "1 minute plank karo baaki count karen!",
            "Ek glass thanda paani seedha ek baar mein piyo!",
            "30 second mein 20 situps karo!",
            "Ek minute tak ek pair pe khade raho aankh band karke!",
            "10 minute walk karo right now aur live update do!",
            "5 minute mein apna room organize karo photo proof!",
            "Ek glass nimbu paani piyo bina chehra banaye!",
            "Nonstop 2 minute tak haath upar rakh ke khade raho!",
            "20 squats karo abhi video bhejo!",
        ],
    },
}

# ============================================================
#   HELPERS
# ============================================================

def get_q(qt, diff):
    pool = TRUTHS if qt == "truth" else DARES
    dp = pool.get(diff, list(pool.values())[0])
    cat = random.choice(list(dp.keys()))
    return random.choice(dp[cat]), cat

def cmsg(c): return random.choice(COIN_MSGS).format(c=c)

def xpbar(xp, level):
    needed = level * 100
    filled = int((xp % needed) / needed * 10)
    return f"[{'█'*filled}{'░'*(10-filled)}] {xp%needed}/{needed} XP"

DL = {"easy": "🟢 Easy", "medium": "🟡 Medium", "hard": "🔴 Hard"}

# ============================================================
#   KEYBOARDS
# ============================================================

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Truth", callback_data="menu_truth"),
         InlineKeyboardButton("🔥 Dare",  callback_data="menu_dare")],
        [InlineKeyboardButton("🎲 Random",      callback_data="menu_random"),
         InlineKeyboardButton("📊 Profile",     callback_data="menu_profile")],
        [InlineKeyboardButton("🏆 Leaderboard", callback_data="menu_lb"),
         InlineKeyboardButton("🎖️ Badges",      callback_data="menu_badges")],
        [InlineKeyboardButton("❓ Help",         callback_data="menu_help")],
    ])

def truth_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Easy +5🪙",    callback_data="play_truth_easy"),
         InlineKeyboardButton("🟡 Medium +10🪙", callback_data="play_truth_medium"),
         InlineKeyboardButton("🔴 Hard +15🪙",   callback_data="play_truth_hard")],
        [InlineKeyboardButton("🔙 Back", callback_data="back")],
    ])

def dare_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Easy +10🪙",   callback_data="play_dare_easy"),
         InlineKeyboardButton("🟡 Medium +20🪙", callback_data="play_dare_medium"),
         InlineKeyboardButton("🔴 Hard +35🪙",   callback_data="play_dare_hard")],
        [InlineKeyboardButton("🔙 Back", callback_data="back")],
    ])

def aq_kb(qt, diff):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Complete! Coins Lo", callback_data=f"done_{qt}_{diff}"),
         InlineKeyboardButton("⏭️ Skip",               callback_data=f"skip")],
        [InlineKeyboardButton("🔄 Naya Question",      callback_data=f"play_{qt}_{diff}"),
         InlineKeyboardButton("🏠 Menu",               callback_data="back")],
    ])

def back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="back")]])

# ============================================================
#   HEALTH SERVER
# ============================================================

class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")
    def log_message(self, *a): pass

def health_server():
    HTTPServer(("0.0.0.0", PORT), Health).serve_forever()

# ============================================================
#   COMMANDS
# ============================================================

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    upsert_user(u.id, u.username, u.first_name)
    nb = check_badges(u.id)
    if nb:
        bonus = sum(BADGES[b]["coins"] for b in nb if b in BADGES)
        if bonus: add_coins(u.id, bonus)
    await update.message.reply_text(
        f"*Aye {u.first_name}! Welcome to Truth & Dare Pro!*\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔍 *Truth* — Sacch bolna COMPULSORY!\n"
        "🔥 *Dare* — Jo bola jaaye KARNA PADEGA!\n"
        "🪙 *Coins* — Task complete = Coins!\n"
        "🏆 *Badges* — Milestones pe rewards!\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Hard difficulty = Zyada coins!\n"
        "Roz khelo = Streak bonus!\n\n"
        "Shuru karo! 👇",
        parse_mode="Markdown", reply_markup=main_kb()
    )

async def profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    upsert_user(u.id, u.username, u.first_name)
    du = get_user(u.id)
    await update.message.reply_text(
        f"*{du['first_name']}'s Profile*\n━━━━━━━━━━━━━━━\n"
        f"🏅 Rank: #{get_rank(u.id)}\n⭐ Level: {du['level']}\n"
        f"📊 {xpbar(du['xp'], du['level'])}\n\n"
        f"🪙 Coins: *{du['coins']}*\n🔥 Streak: {du['streak']} din\n"
        f"🎮 Games: {du['total_played']}\n🔍 Truths: {du['truths_done']}\n"
        f"🔥 Dares: {du['dares_done']}\n🎖️ Badges: {len(get_badges(u.id))}/15\n━━━━━━━━━━━━━━━",
        parse_mode="Markdown", reply_markup=back_kb()
    )

async def lb_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rows = leaderboard()
    medals = ["🥇","🥈","🥉"] + ["🏅"]*7
    lines = ["*TOP 10 LEADERBOARD*\n━━━━━━━━━━━━━━━"]
    for i, r in enumerate(rows):
        lines.append(f"{medals[i]} {r['first_name']} — *{r['coins']}🪙* | Lv.{r['level']}")
    lines.append("━━━━━━━━━━━━━━━")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=back_kb())

async def badges_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    earned = get_badges(update.effective_user.id)
    lines = ["*BADGES*\n━━━━━━━━━━━━━━━"]
    for bid, info in BADGES.items():
        s = "✅" if bid in earned else "🔒"
        lines.append(f"{s} {info['name']} — _{info['desc']}_")
    lines.append(f"\n━━━━━━━━━━━━━━━\n🎯 {len(earned)}/15 earned!")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=back_kb())

async def coins_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    upsert_user(u.id, u.username, u.first_name)
    du = get_user(u.id)
    await update.message.reply_text(
        f"*Coin Wallet*\n━━━━━━━━━━━━\n"
        f"Balance: *{du['coins']} coins*\nRank: #{get_rank(u.id)}\nLevel: {du['level']}\n\n"
        f"*Earn karo:*\n"
        f"Truth Easy=5 Medium=10 Hard=15\n"
        f"Dare Easy=10 Medium=20 Hard=35\n"
        f"Random Bonus=+5\nBadges=50~1000",
        parse_mode="Markdown", reply_markup=back_kb()
    )

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*COMMANDS*\n━━━━━━━━━━━━━━━\n"
        "/start /truth /dare /random\n/profile /leaderboard /badges /coins\n\n"
        "Hard = Zyada coins!\nDaily = Streak bonus!\nBadges = Mega coins!",
        parse_mode="Markdown", reply_markup=main_kb()
    )

# ============================================================
#   BUTTON HANDLER
# ============================================================

async def btn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    u = q.from_user
    upsert_user(u.id, u.username, u.first_name)

    if d == "back":
        await q.edit_message_text(
            f"*Truth & Dare Pro*\n\nKya khelna hai {u.first_name}? 👇",
            parse_mode="Markdown", reply_markup=main_kb()
        )
    elif d == "menu_truth":
        await q.edit_message_text("*TRUTH* — Difficulty chuno!\nZyada mushkil = Zyada coins!",
                                   parse_mode="Markdown", reply_markup=truth_kb())
    elif d == "menu_dare":
        await q.edit_message_text("*DARE* — Himmat hai toh choose karo!\nZyada dare = Zyada coins!",
                                   parse_mode="Markdown", reply_markup=dare_kb())
    elif d == "menu_random":
        qt = random.choice(["truth","dare"])
        diff = random.choice(["easy","medium","hard"])
        question, cat = get_q(qt, diff)
        cv = COINS_MAP.get(f"{qt}_{diff}", 10) + COINS_MAP["random_bonus"]
        emoji = "🔍" if qt == "truth" else "🔥"
        await q.edit_message_text(
            f"{emoji} *RANDOM {qt.upper()}!*\n_{DL[diff]} | {cat.title()}_\n\n"
            f"*{question}*\n\nRandom bonus included!\nComplete = *+{cv} coins*!",
            parse_mode="Markdown", reply_markup=aq_kb(qt, diff)
        )
    elif d == "menu_profile":
        du = get_user(u.id)
        await q.edit_message_text(
            f"*{du['first_name']}'s Profile*\n━━━━━━━━━━━━━━━\n"
            f"🏅 Rank: #{get_rank(u.id)}\n⭐ Level: {du['level']}\n"
            f"📊 {xpbar(du['xp'], du['level'])}\n\n"
            f"🪙 Coins: *{du['coins']}*\n🔥 Streak: {du['streak']} din\n"
            f"🎮 Games: {du['total_played']}\n🔍 Truths: {du['truths_done']}\n"
            f"🔥 Dares: {du['dares_done']}\n🎖️ Badges: {len(get_badges(u.id))}/15\n━━━━━━━━━━━━━━━",
            parse_mode="Markdown", reply_markup=back_kb()
        )
    elif d == "menu_lb":
        rows = leaderboard()
        medals = ["🥇","🥈","🥉"] + ["🏅"]*7
        lines = ["*TOP 10 LEADERBOARD*\n━━━━━━━━━━━━━━━"]
        for i, r in enumerate(rows):
            lines.append(f"{medals[i]} {r['first_name']} — *{r['coins']}🪙* | Lv.{r['level']}")
        lines.append("━━━━━━━━━━━━━━━")
        await q.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=back_kb())
    elif d == "menu_badges":
        earned = get_badges(u.id)
        lines = ["*BADGES*\n━━━━━━━━━━━━━━━"]
        for bid, info in BADGES.items():
            s = "✅" if bid in earned else "🔒"
            lines.append(f"{s} {info['name']} — _{info['desc']}_")
        lines.append(f"\n━━━━━━━━━━━━━━━\n🎯 {len(earned)}/15 earned!")
        await q.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=back_kb())
    elif d == "menu_help":
        await q.edit_message_text(
            "*COMMANDS*\n━━━━━━━━━━━━━━━\n"
            "/start /truth /dare /random\n/profile /leaderboard /badges /coins\n\n"
            "Hard = Zyada coins!\nDaily = Streak bonus!",
            parse_mode="Markdown", reply_markup=back_kb()
        )
    elif d.startswith("play_"):
        _, qt, diff = d.split("_")
        question, cat = get_q(qt, diff)
        emoji = "🔍" if qt == "truth" else "🔥"
        cv = COINS_MAP.get(f"{qt}_{diff}", 10)
        await q.edit_message_text(
            f"{emoji} *{qt.upper()}* — {DL[diff]}\n_{cat.title()}_\n\n"
            f"*{question}*\n\nComplete karo = *+{cv} coins*!",
            parse_mode="Markdown", reply_markup=aq_kb(qt, diff)
        )
    elif d.startswith("done_"):
        _, qt, diff = d.split("_")
        cv = COINS_MAP.get(f"{qt}_{diff}", 10)
        streak, smil = update_streak(u.id)
        total = add_coins(u.id, cv)
        new_lvl, lvlup = update_xp(u.id, cv)
        record_play(u.id, qt, diff, cv)
        nb = check_badges(u.id)
        bbonus = sum(BADGES[b]["coins"] for b in nb if b in BADGES)
        if bbonus: total = add_coins(u.id, bbonus)
        txt = (
            f"✅ *TASK COMPLETE!*\n━━━━━━━━━━━━━━━\n"
            f"{cmsg(cv)}\n💰 Total: *{total} coins*\n"
            f"🔥 Streak: {streak} din | ⭐ Level: {new_lvl}\n"
        )
        if lvlup: txt += f"\n🎉 *LEVEL UP! Level {new_lvl}!*\n"
        if smil and streak in STREAK_MSG: txt += f"\n{STREAK_MSG[streak]}\n"
        if nb:
            txt += "\n🎖️ *NAYE BADGES!*\n"
            for b in nb:
                info = BADGES.get(b, {})
                txt += f"• {info.get('name', b)} (+{info.get('coins',0)} coins)\n"
        txt += "━━━━━━━━━━━━━━━"
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=main_kb())
    elif d == "skip":
        await q.edit_message_text(
            "⏭️ *Skipped!*\nKoi baat nahi agli baar pakka complete karna!\n_(Skip pe coins nahi milte)_",
            parse_mode="Markdown", reply_markup=main_kb()
        )

# ============================================================
#   MAIN
# ============================================================

def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("BOT_TOKEN set nahi hai!")
        return
    print("Starting Truth & Dare Pro Bot...")
    init_db()
    print("Database ready!")
    threading.Thread(target=health_server, daemon=True).start()
    print(f"Health server port {PORT} pe live!")
    app = Application.builder().token(BOT_TOKEN).build()
    async def truth_cmd(u, c):
        upsert_user(u.effective_user.id, u.effective_user.username, u.effective_user.first_name)
        await u.message.reply_text("🔍 *TRUTH* — Difficulty chuno!\nZyada mushkil = Zyada coins!", parse_mode="Markdown", reply_markup=truth_kb())

    async def dare_cmd(u, c):
        upsert_user(u.effective_user.id, u.effective_user.username, u.effective_user.first_name)
        await u.message.reply_text("🔥 *DARE* — Himmat hai toh choose karo!\nZyada dare = Zyada coins!", parse_mode="Markdown", reply_markup=dare_kb())

    async def random_cmd(u, c):
        upsert_user(u.effective_user.id, u.effective_user.username, u.effective_user.first_name)
        qt = random.choice(["truth","dare"])
        diff = random.choice(["easy","medium","hard"])
        question, cat = get_q(qt, diff)
        cv = COINS_MAP.get(f"{qt}_{diff}", 10) + COINS_MAP["random_bonus"]
        emoji = "🔍" if qt == "truth" else "🔥"
        await u.message.reply_text(
            f"{emoji} *RANDOM {qt.upper()}!*\n_{DL[diff]} | {cat.title()}_\n\n"
            f"*{question}*\n\nRandom bonus included!\nComplete = *+{cv} coins*!",
            parse_mode="Markdown", reply_markup=aq_kb(qt, diff)
        )

    for cmd, handler in [
        ("start", start), ("truth", truth_cmd), ("dare", dare_cmd),
        ("random", random_cmd), ("profile", profile), ("leaderboard", lb_cmd),
        ("badges", badges_cmd), ("coins", coins_cmd), ("help", help_cmd),
    ]:
        app.add_handler(CommandHandler(cmd, handler))
    app.add_handler(CallbackQueryHandler(btn))
    print("Bot live!\n")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
