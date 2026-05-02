"""
TRUTH & DARE BOT — PROFESSIONAL EDITION
Install: pip install python-telegram-bot==20.7
Run:     python bot.py
"""

import os, random, sys, threading
sys.path.insert(0, os.path.dirname(__file__))

from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from utils.database import (
    init_db, get_user, create_or_update_user, add_coins,
    update_streak, record_play, update_xp_level,
    check_and_award_badges, get_leaderboard, get_user_rank,
    BADGE_DEFINITIONS, get_user_badges
)
from data.questions import TRUTHS, DARES, COIN_EARN_MESSAGES, STREAK_MESSAGES

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
PORT = int(os.getenv("PORT", 8080))

COINS = {
    "truth_easy": 5,  "truth_medium": 10, "truth_hard": 15,
    "dare_easy": 10,  "dare_medium": 20,  "dare_hard": 35,
    "random_bonus": 5,
}

# ── HEALTH CHECK SERVER (Render ke liye) ──────────────────

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Truth & Dare Bot is alive! 🎮")
    def log_message(self, format, *args):
        pass  # Logs quiet rakhne ke liye

def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    server.serve_forever()

# ── KEYBOARDS ──────────────────────────────────────────────

def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Truth", callback_data="menu_truth"),
         InlineKeyboardButton("🔥 Dare",  callback_data="menu_dare")],
        [InlineKeyboardButton("🎲 Random",     callback_data="menu_random"),
         InlineKeyboardButton("📊 Profile",    callback_data="menu_profile")],
        [InlineKeyboardButton("🏆 Leaderboard",callback_data="menu_leaderboard"),
         InlineKeyboardButton("🎖️ Badges",     callback_data="menu_badges")],
        [InlineKeyboardButton("❓ Help",        callback_data="menu_help")],
    ])

def truth_diff_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Easy +5🪙",   callback_data="play_truth_easy"),
         InlineKeyboardButton("🟡 Medium +10🪙", callback_data="play_truth_medium"),
         InlineKeyboardButton("🔴 Hard +15🪙",   callback_data="play_truth_hard")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_main")],
    ])

def dare_diff_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Easy +10🪙",  callback_data="play_dare_easy"),
         InlineKeyboardButton("🟡 Medium +20🪙", callback_data="play_dare_medium"),
         InlineKeyboardButton("🔴 Hard +35🪙",   callback_data="play_dare_hard")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_main")],
    ])

def after_q_kb(qt, diff):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Complete! Coins Lo", callback_data=f"done_{qt}_{diff}"),
         InlineKeyboardButton("⏭️ Skip",               callback_data=f"skip_{qt}_{diff}")],
        [InlineKeyboardButton("🔄 Naya Question",      callback_data=f"play_{qt}_{diff}"),
         InlineKeyboardButton("🏠 Menu",               callback_data="back_main")],
    ])

def back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="back_main")]])

# ── HELPERS ────────────────────────────────────────────────

def get_q(qt, diff):
    pool = TRUTHS if qt == "truth" else DARES
    dp = pool.get(diff, pool["easy"])
    cat = random.choice(list(dp.keys()))
    return random.choice(dp[cat]), cat

def coin_msg(c): return random.choice(COIN_EARN_MESSAGES).format(coins=c)

def xp_bar(xp, level):
    needed = level * 100
    filled = int((xp % needed) / needed * 10)
    return f"[{'█'*filled}{'░'*(10-filled)}] {xp%needed}/{needed} XP"

DIFF_LABEL = {"easy":"🟢 Easy","medium":"🟡 Medium","hard":"🔴 Hard"}

# ── COMMANDS ───────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    create_or_update_user(u.id, u.username, u.first_name)
    nb = check_and_award_badges(u.id)
    if nb:
        bonus = sum(BADGE_DEFINITIONS[b]["coins"] for b in nb if b in BADGE_DEFINITIONS)
        if bonus: add_coins(u.id, bonus)
    await update.message.reply_text(
        f"🎮 *Aye {u.first_name}! Welcome to Truth & Dare Pro!* 🎮\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔍 *Truth* — Sacch bolna COMPULSORY!\n"
        "🔥 *Dare* — Jo bola jaaye KARNA PADEGA!\n"
        "🪙 *Coins* — Task complete = Coins!\n"
        "🏆 *Badges* — Milestones pe rewards!\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Hard difficulty = Zyada coins! 💰\n"
        "Roz khelo = Streak bonus! 🔥\n\n"
        "Shuru karo! 👇",
        parse_mode="Markdown", reply_markup=main_menu_kb()
    )

async def cmd_truth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    create_or_update_user(u.id, u.username, u.first_name)
    await update.message.reply_text(
        "🔍 *TRUTH* — Difficulty chuno!\nZyada mushkil = Zyada coins! 🪙",
        parse_mode="Markdown", reply_markup=truth_diff_kb()
    )

async def cmd_dare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    create_or_update_user(u.id, u.username, u.first_name)
    await update.message.reply_text(
        "🔥 *DARE* — Himmat hai toh choose karo!\nZyada dare = Zyada coins! 🪙",
        parse_mode="Markdown", reply_markup=dare_diff_kb()
    )

async def cmd_random(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    create_or_update_user(u.id, u.username, u.first_name)
    qt = random.choice(["truth", "dare"])
    diff = random.choice(["easy", "medium", "hard"])
    q, cat = get_q(qt, diff)
    emoji = "🔍" if qt == "truth" else "🔥"
    cv = COINS.get(f"{qt}_{diff}", 10) + COINS["random_bonus"]
    await update.message.reply_text(
        f"{emoji} *RANDOM — {qt.upper()}!*\n_{DIFF_LABEL[diff]} | {cat.title()}_\n\n"
        f"*{q}*\n\n🎲 Random bonus included!\nComplete = *+{cv}🪙*!",
        parse_mode="Markdown", reply_markup=after_q_kb(qt, diff)
    )

async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    create_or_update_user(u.id, u.username, u.first_name)
    du = get_user(u.id)
    rank = get_user_rank(u.id)
    bc = len(get_user_badges(u.id))
    await update.message.reply_text(
        f"👤 *{du['first_name']}'s Profile*\n━━━━━━━━━━━━━━━\n"
        f"🏅 Rank: #{rank}\n⭐ Level: {du['level']}\n"
        f"📊 {xp_bar(du['xp'], du['level'])}\n\n"
        f"🪙 Coins: *{du['coins']}*\n🔥 Streak: {du['streak']} din\n"
        f"🎮 Games: {du['total_played']}\n🔍 Truths: {du['truths_done']}\n"
        f"🔥 Dares: {du['dares_done']}\n🎖️ Badges: {bc}/16\n━━━━━━━━━━━━━━━",
        parse_mode="Markdown", reply_markup=back_kb()
    )

async def cmd_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_leaderboard(10)
    medals = ["🥇","🥈","🥉"] + ["🏅"]*7
    lines = ["🏆 *TOP 10 LEADERBOARD*\n━━━━━━━━━━━━━━━"]
    for i, r in enumerate(rows):
        lines.append(f"{medals[i]} {r['first_name']} — *{r['coins']}🪙* | Lv.{r['level']}")
    lines.append("━━━━━━━━━━━━━━━")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=back_kb())

async def cmd_badges(update: Update, context: ContextTypes.DEFAULT_TYPE):
    earned = get_user_badges(update.effective_user.id)
    lines = ["🎖️ *BADGES*\n━━━━━━━━━━━━━━━"]
    for bid, info in BADGE_DEFINITIONS.items():
        s = "✅" if bid in earned else "🔒"
        lines.append(f"{s} {info['name']} — _{info['desc']}_")
    lines.append(f"\n━━━━━━━━━━━━━━━\n🎯 {len(earned)}/16 earned!")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=back_kb())

async def cmd_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    create_or_update_user(u.id, u.username, u.first_name)
    du = get_user(u.id)
    await update.message.reply_text(
        f"🪙 *Coin Wallet*\n━━━━━━━━━━━━\n"
        f"Balance: *{du['coins']} coins*\nRank: #{get_user_rank(u.id)}\nLevel: {du['level']}\n\n"
        f"💡 *Earn karo:*\n"
        f"• Truth Easy=5🪙 Medium=10🪙 Hard=15🪙\n"
        f"• Dare Easy=10🪙 Medium=20🪙 Hard=35🪙\n"
        f"• Random Bonus=+5🪙\n• Badges=50~2000🪙",
        parse_mode="Markdown", reply_markup=back_kb()
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *COMMANDS*\n━━━━━━━━━━━━━━━\n"
        "/start — Welcome\n/truth — Truth question\n/dare — Dare\n"
        "/random — Random Truth/Dare\n/profile — Tera profile\n"
        "/leaderboard — Top players\n/badges — Achievements\n"
        "/coins — Wallet\n/help — Ye menu\n\n"
        "💡 Hard = Zyada coins!\n🔥 Daily streak = Bonus!\n🎖️ Badges = Mega bonus!",
        parse_mode="Markdown", reply_markup=main_menu_kb()
    )

# ── CALLBACK ───────────────────────────────────────────────

async def btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    u = q.from_user
    create_or_update_user(u.id, u.username, u.first_name)

    if d == "back_main":
        await q.edit_message_text(
            f"🎮 *Truth & Dare Pro*\n\nKya khelna hai {u.first_name}? 👇",
            parse_mode="Markdown", reply_markup=main_menu_kb()
        )
    elif d == "menu_truth":
        await q.edit_message_text("🔍 *TRUTH* — Difficulty chuno!\nZyada mushkil = Zyada coins! 🪙",
                                   parse_mode="Markdown", reply_markup=truth_diff_kb())
    elif d == "menu_dare":
        await q.edit_message_text("🔥 *DARE* — Himmat hai toh choose karo!\nZyada dare = Zyada coins! 🪙",
                                   parse_mode="Markdown", reply_markup=dare_diff_kb())
    elif d == "menu_random":
        qt = random.choice(["truth","dare"])
        diff = random.choice(["easy","medium","hard"])
        question, cat = get_q(qt, diff)
        emoji = "🔍" if qt == "truth" else "🔥"
        cv = COINS.get(f"{qt}_{diff}", 10) + COINS["random_bonus"]
        await q.edit_message_text(
            f"{emoji} *RANDOM — {qt.upper()}!*\n_{DIFF_LABEL[diff]} | {cat.title()}_\n\n"
            f"*{question}*\n\n🎲 Random bonus included!\nComplete = *+{cv}🪙*!",
            parse_mode="Markdown", reply_markup=after_q_kb(qt, diff)
        )
    elif d == "menu_profile":
        du = get_user(u.id)
        rank = get_user_rank(u.id)
        bc = len(get_user_badges(u.id))
        await q.edit_message_text(
            f"👤 *{du['first_name']}'s Profile*\n━━━━━━━━━━━━━━━\n"
            f"🏅 Rank: #{rank}\n⭐ Level: {du['level']}\n"
            f"📊 {xp_bar(du['xp'], du['level'])}\n\n"
            f"🪙 Coins: *{du['coins']}*\n🔥 Streak: {du['streak']} din\n"
            f"🎮 Games: {du['total_played']}\n🔍 Truths: {du['truths_done']}\n"
            f"🔥 Dares: {du['dares_done']}\n🎖️ Badges: {bc}/16\n━━━━━━━━━━━━━━━",
            parse_mode="Markdown", reply_markup=back_kb()
        )
    elif d == "menu_leaderboard":
        rows = get_leaderboard(10)
        medals = ["🥇","🥈","🥉"] + ["🏅"]*7
        lines = ["🏆 *TOP 10 LEADERBOARD*\n━━━━━━━━━━━━━━━"]
        for i, r in enumerate(rows):
            lines.append(f"{medals[i]} {r['first_name']} — *{r['coins']}🪙* | Lv.{r['level']}")
        lines.append("━━━━━━━━━━━━━━━")
        await q.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=back_kb())
    elif d == "menu_badges":
        earned = get_user_badges(u.id)
        lines = ["🎖️ *BADGES*\n━━━━━━━━━━━━━━━"]
        for bid, info in BADGE_DEFINITIONS.items():
            s = "✅" if bid in earned else "🔒"
            lines.append(f"{s} {info['name']} — _{info['desc']}_")
        lines.append(f"\n━━━━━━━━━━━━━━━\n🎯 {len(earned)}/16 earned!")
        await q.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=back_kb())
    elif d == "menu_help":
        await q.edit_message_text(
            "📖 *COMMANDS*\n━━━━━━━━━━━━━━━\n"
            "/truth /dare /random /profile\n/leaderboard /badges /coins /help\n\n"
            "💡 Hard = Zyada coins!\n🔥 Daily = Streak bonus!\n🎖️ Badges = Mega coins!",
            parse_mode="Markdown", reply_markup=back_kb()
        )
    elif d.startswith("play_"):
        _, qt, diff = d.split("_")
        question, cat = get_q(qt, diff)
        emoji = "🔍" if qt == "truth" else "🔥"
        cv = COINS.get(f"{qt}_{diff}", 10)
        await q.edit_message_text(
            f"{emoji} *{qt.upper()}* — {DIFF_LABEL[diff]}\n_{cat.title()}_\n\n"
            f"*{question}*\n\n✅ Complete karo = *+{cv}🪙*!",
            parse_mode="Markdown", reply_markup=after_q_kb(qt, diff)
        )
    elif d.startswith("done_"):
        _, qt, diff = d.split("_")
        cv = COINS.get(f"{qt}_{diff}", 10)
        streak, s_milestone = update_streak(u.id)
        total = add_coins(u.id, cv)
        new_level, lvl_up = update_xp_level(u.id, cv)
        record_play(u.id, q.message.chat_id, qt, diff, "general", "completed", cv)
        nb = check_and_award_badges(u.id)
        badge_bonus = sum(BADGE_DEFINITIONS[b]["coins"] for b in nb if b in BADGE_DEFINITIONS)
        if badge_bonus: total = add_coins(u.id, badge_bonus)

        txt = (
            f"✅ *TASK COMPLETE!*\n━━━━━━━━━━━━━━━\n"
            f"{coin_msg(cv)}\n💰 Total: *{total}🪙*\n"
            f"🔥 Streak: {streak} din | ⭐ Level: {new_level}\n"
        )
        if lvl_up: txt += f"\n🎉 *LEVEL UP! Level {new_level}!* 🚀\n"
        if s_milestone and streak in STREAK_MESSAGES: txt += f"\n{STREAK_MESSAGES[streak]}\n"
        if nb:
            txt += "\n🎖️ *NAYE BADGES!*\n"
            for b in nb:
                info = BADGE_DEFINITIONS.get(b, {})
                txt += f"• {info.get('name', b)} (+{info.get('coins',0)}🪙)\n"
        txt += "━━━━━━━━━━━━━━━"
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=main_menu_kb())
    elif d.startswith("skip_"):
        await q.edit_message_text(
            "⏭️ *Skipped!*\nKoi baat nahi — agli baar pakka complete karna! 💪\n_(Skip pe coins nahi milte 😅)_",
            parse_mode="Markdown", reply_markup=main_menu_kb()
        )

# ── MAIN ───────────────────────────────────────────────────

def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ BOT_TOKEN set nahi hai!")
        return

    print("🚀 Truth & Dare Pro Bot starting...")
    init_db()
    print("✅ Database ready!")

    # Health check server background mein chalaao
    t = threading.Thread(target=run_health_server, daemon=True)
    t.start()
    print(f"✅ Health server port {PORT} pe live!")

    app = Application.builder().token(BOT_TOKEN).build()
    for cmd, handler in [
        ("start", cmd_start), ("truth", cmd_truth), ("dare", cmd_dare),
        ("random", cmd_random), ("profile", cmd_profile),
        ("leaderboard", cmd_leaderboard), ("badges", cmd_badges),
        ("coins", cmd_coins), ("help", cmd_help),
    ]:
        app.add_handler(CommandHandler(cmd, handler))
    app.add_handler(CallbackQueryHandler(btn))
    print("✅ Bot live! CTRL+C se band karo.\n")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
