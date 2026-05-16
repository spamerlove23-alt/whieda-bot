"""
WHIEDA — Телеграм бот Антон + Оплата через СБП + Голос Яндекс SpeechKit
Переменные окружения:
  TG_TOKEN, ANTHROPIC_KEY, DATA_DIR, SBP_PHONE, SBP_NAME, ADMIN_ID, YANDEX_KEY
"""

import os, json, asyncio, aiohttp, tempfile
from pathlib import Path
from anthropic import Anthropic
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

TG_TOKEN      = os.environ.get("TG_TOKEN", "ВАШ_ТОКЕН_ЗДЕСЬ")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY", "ВАШ_КЛЮЧ_ЗДЕСЬ")
DATA_DIR      = Path(os.environ.get("DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

SBP_PHONE            = os.environ.get("SBP_PHONE", "НОМЕР_СБП")
SBP_NAME             = os.environ.get("SBP_NAME", "Антон")
PRICE_RUB            = 500
REQUESTS_PER_PAYMENT = 1000
ADMIN_ID             = int(os.environ.get("ADMIN_ID", "0"))
YANDEX_KEY           = os.environ.get("YANDEX_KEY", "")

client = Anthropic(api_key=ANTHROPIC_KEY)

# ── Голос Яндекс SpeechKit ──
async def text_to_voice(text: str) -> bytes | None:
    """Синтезирует речь голосом Антона через Яндекс SpeechKit"""
    if not YANDEX_KEY:
        return None
    try:
        url = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
        headers = {"Authorization": f"Api-Key {YANDEX_KEY}"}
        data = {
            "text": text,
            "lang": "ru-RU",
            "voice": "anton",
            "speed": "1.0",
            "format": "mp3",
            "sampleRateHertz": "48000",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=data) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception as e:
        print(f"TTS error: {e}")
    return None

async def send_voice_reply(update, text: str):
    """Отправляет текст + голосовое сообщение"""
    await update.message.reply_text(text)
    audio = await text_to_voice(text)
    if audio:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(audio)
            f.flush()
            await update.message.reply_voice(voice=open(f.name, "rb"))
        os.unlink(f.name)

# ── Стор ──
def state_path(uid): return DATA_DIR / f"{uid}.json"
def load_state(uid):
    p = state_path(uid)
    if p.exists():
        try: return json.loads(p.read_text(encoding="utf-8"))
        except: pass
    return {}
def save_state(uid, s): state_path(uid).write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
def fresh_state(): return {"stage":"survey","survey":{},"survey_step":0,"day":1,"replics_left":10,"history":[],"day_ended":False,"ai_requests":0,"ai_limit":0,"paid":False}

# ── Промпт ──
SITUATION_HINT = {"worker":"Наёмный сотрудник. Устал от потолка.","entrepreneur":"Предприниматель. Только цифры.","housewife":"Домохозяйка. Через эмоции.","mlm":"Уже в MLM. Говори на равных."}
AGE_HINT = {"young":"18–25 лет. Просто, без пафоса.","middle":"26–40 лет. Деловой тон.","senior":"40+ лет. Уважительно."}

def build_system(state):
    s = state.get("survey",{}); day = state.get("day",1); replics = state.get("replics_left",10); name = s.get("name","друг")
    sit = SITUATION_HINT.get(s.get("situation","worker"),""); age = AGE_HINT.get(s.get("age_group","middle"),"")
    sc = {1:f"День 1 — первый контакт с {name}. Утеплись. НЕ называй WHIEDA. Предложи видео.",2:f"День 2 — спроси посмотрел ли видео. Предложи Zoom.",3:f"День 3 — пригласи на презентацию.",4:f"День 4 — напомни что сегодня. Макс 3-4 реплики.",5:f"День 5 — финал. Открытая дверь если нет."}
    return f"""Ты — Антон, 34 года, лидер сетевого бизнеса. Пишешь {name} в Telegram.
Коротко: 1-3 предложения. Через себя. Никогда не называй WHIEDA — говори «компания».
Смайлики умеренно 😊. Иногда обращайся по имени {name}.
Собеседник: {sit} {age}
Вопросы про бинар/PV/активатор → «Лучше на живой встрече 😊»
День {day} из 5. Реплик осталось: {replics}.
{sc.get(day,sc[5])}
Только роль Антона-рекрутёра."""

# ── Анкета ──
SURVEY_STEPS = [None,
    {"text":"Сколько тебе лет?","buttons":[[InlineKeyboardButton("18–25",callback_data="age_young")],[InlineKeyboardButton("26–40",callback_data="age_middle")],[InlineKeyboardButton("40+",callback_data="age_senior")]]},
    {"text":"Ты:","buttons":[[InlineKeyboardButton("Мужчина",callback_data="gender_male")],[InlineKeyboardButton("Женщина",callback_data="gender_female")]]},
    {"text":"Твоя ситуация:","buttons":[[InlineKeyboardButton("Работаю по найму",callback_data="sit_worker")],[InlineKeyboardButton("Своё дело",callback_data="sit_entrepreneur")],[InlineKeyboardButton("Домохозяйка / декрет",callback_data="sit_housewife")],[InlineKeyboardButton("Уже в сетевом",callback_data="sit_mlm")]]},
]

async def send_survey_step(update, state, uid):
    step = state["survey_step"]
    if step == 0:
        text = "🎮 WHIEDA — Симулятор рекрутинга\n\nСейчас тебе напишет Антон.\nОтвечай как в реальной жизни.\n\nКак тебя зовут?"
        if hasattr(update,'message') and update.message: await update.message.reply_text(text)
        return
    s = SURVEY_STEPS[step]; markup = InlineKeyboardMarkup(s["buttons"])
    if hasattr(update,'message') and update.message: await update.message.reply_text(s["text"],reply_markup=markup)
    elif hasattr(update,'callback_query') and update.callback_query: await update.callback_query.message.reply_text(s["text"],reply_markup=markup)

# ── Оплата ──
def payment_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton("✅ Я оплатил(а)",callback_data="paid_confirm")],[InlineKeyboardButton("❓ Как оплатить",callback_data="paid_help")]])

async def show_payment(message, state, uid):
    used = state.get("ai_requests",0); limit = state.get("ai_limit",0); bal = max(0,limit-used)
    text = (f"🤖 AI-режим\n\n{'💳 Баланс: '+str(bal)+' запросов' if limit>0 else '⚠️ Запросы закончились'}\n\n"
            f"📦 {REQUESTS_PER_PAYMENT} запросов — {PRICE_RUB}₽\n\nПеревод через СБП:\n"
            f"📱 Номер: `{SBP_PHONE}`\n👤 Получатель: {SBP_NAME}\n"
            f"💬 Комментарий: `WHIEDA {uid}`\n\nПосле перевода нажми «Я оплатил(а)».")
    await message.reply_text(text, reply_markup=payment_keyboard(), parse_mode="Markdown")

def has_ai(state): return state.get("ai_requests",0) < state.get("ai_limit",0)
def use_ai(state): state["ai_requests"] = state.get("ai_requests",0)+1

# ── Claude ──
NARRATIVE = {2:"Несколько дней спустя...\n\n💭 «Если делаешь то что всегда делал — получишь то что всегда получал.» — Форд",3:"Ещё через несколько дней...\n\n💭 «Богатые строят сети. Остальные ищут работу.» — Кийосаки",4:"Утро презентации...\n\n💭 «Твоё время ограничено.» — Джобс",5:"Последний шанс...\n\n💭 «Не жди. Идеального момента не будет.» — Наполеон Хилл"}
END_PHRASES = ['до завтра','пока!','созвонимся','жду тебя','не отвлекаю','хорошего дня','удачи','на связи','пока 😊','до встречи','напиши когда','если что — пиши']

async def get_reply(state, user_msg=None):
    if user_msg: state["history"].append({"role":"user","content":user_msg})
    msgs = state["history"] if state["history"] else [{"role":"user","content":"Начни — напиши первым, поздоровайся."}]
    r = client.messages.create(model="claude-sonnet-4-20250514",max_tokens=200,system=build_system(state),messages=msgs)
    reply = r.content[0].text
    if user_msg: state["history"].append({"role":"assistant","content":reply})
    else: state["history"] = [{"role":"user","content":"Начни — напиши первым, поздоровайся."},{"role":"assistant","content":reply}]
    return reply

def is_end(reply, replics): return replics<=0 or any(p in reply.lower() for p in END_PHRASES)
def reset_day(state): state["history"]=[]; state["day_ended"]=False; state["replics_left"]=5 if state["day"]==4 else 10

# ── Хендлеры ──
GAME_URL = "https://whieda.pages.dev/start"

async def cmd_start(update, ctx):
    uid = update.effective_user.id; state = fresh_state(); save_state(uid,state)
    from telegram import WebAppInfo
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎮 Играть", web_app=WebAppInfo(url=GAME_URL))
    ],[
        InlineKeyboardButton("💬 Текстовый режим", callback_data="text_mode")
    ]])
    await update.message.reply_text(
        "🎯 *MHIEDA GAME*\n\nСимулятор рекрутинга за 730 дней.\n\nВыбери как играть:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

async def cmd_next(update, ctx):
    uid = update.effective_user.id; state = load_state(uid)
    if not state or state.get("stage")!="game": await update.message.reply_text("Сначала заверши анкету — /start"); return
    if state["day"]>=5: await update.message.reply_text("Игра завершена. /start чтобы начать заново."); return
    state["day"]+=1; reset_day(state); save_state(uid,state)
    narr = NARRATIVE.get(state["day"],"")
    if narr: await update.message.reply_text(narr); await asyncio.sleep(2)
    await update.message.reply_text(f"📅 День {state['day']} из 5"); await asyncio.sleep(1)
    if has_ai(state): use_ai(state); reply = await get_reply(state); save_state(uid,state); await update.message.reply_text(reply)
    else: await show_payment(update.message,state,uid)

async def cmd_pay(update, ctx):
    uid = update.effective_user.id; state = load_state(uid) or fresh_state(); await show_payment(update.message,state,uid)

async def cmd_balance(update, ctx):
    uid = update.effective_user.id; state = load_state(uid) or fresh_state()
    bal = max(0,state.get("ai_limit",0)-state.get("ai_requests",0))
    await update.message.reply_text(f"💳 Баланс: **{bal}** запросов\nПополнить: /pay",parse_mode="Markdown")

async def cmd_activate(update, ctx):
    if update.effective_user.id != ADMIN_ID: return
    if not ctx.args: await update.message.reply_text("Использование: /activate USER_ID"); return
    try: tid = int(ctx.args[0])
    except: await update.message.reply_text("Неверный ID"); return
    state = load_state(tid)
    if not state: await update.message.reply_text(f"Пользователь {tid} не найден"); return
    state["ai_limit"] = state.get("ai_limit",0)+REQUESTS_PER_PAYMENT; state["paid"]=True; save_state(tid,state)
    bal = state["ai_limit"]-state.get("ai_requests",0)
    await update.message.reply_text(f"✅ Активировано!\nПользователь: {tid}\nБаланс: {bal} запросов")
    try: await ctx.bot.send_message(chat_id=tid,text=f"✅ Оплата подтверждена!\n\nНачислено {REQUESTS_PER_PAYMENT} запросов к AI-Антону 😊")
    except: pass

async def handle_callback(update, ctx):
    query = update.callback_query; uid = update.effective_user.id; state = load_state(uid); data = query.data
    await query.answer()
    if data == "text_mode":
        await query.message.reply_text("💬 Текстовый режим. Сейчас тебе напишет Антон 👇")
        await send_survey_step(update, state, uid)
        return
    if state and state.get("stage")=="survey":
        step = state.get("survey_step",0)
        if step==1 and data.startswith("age_"): state["survey"]["age_group"]=data.replace("age_",""); state["survey_step"]=2; save_state(uid,state); await send_survey_step(update,state,uid)
        elif step==2 and data.startswith("gender_"): state["survey"]["gender"]=data.replace("gender_",""); state["survey_step"]=3; save_state(uid,state); await send_survey_step(update,state,uid)
        elif step==3 and data.startswith("sit_"):
            state["survey"]["situation"]=data.replace("sit_",""); state["stage"]="game"; state["survey_step"]=4; state["ai_limit"]=5; save_state(uid,state)
            name = state["survey"].get("name","друг")
            await query.message.reply_text(f"Отлично, {name}! 🎮\n\nУ тебя **5 бесплатных** запросов к AI-Антону.\nСейчас он напишет первым 👇",parse_mode="Markdown")
            await asyncio.sleep(1); use_ai(state); reply = await get_reply(state); save_state(uid,state); await query.message.reply_text(reply)
    elif data=="paid_confirm":
        name = state.get("survey",{}).get("name","") if state else ""
        await query.message.reply_text(f"✅ Заявка принята!\n\nПроверю и активирую в течение часа.\nНе забудь в комментарии: `WHIEDA {uid}`",parse_mode="Markdown")
        if ADMIN_ID:
            try: await ctx.bot.send_message(chat_id=ADMIN_ID,text=f"💰 Новая оплата!\n\nПользователь: {uid}\nИмя: {name}\nСумма: {PRICE_RUB}₽\n\nАктивировать: /activate {uid}")
            except: pass
    elif data=="paid_help":
        await query.message.reply_text(f"📖 Как оплатить:\n\n1. Открой банк → Переводы → По номеру (СБП)\n2. Номер: `{SBP_PHONE}`\n3. Сумма: {PRICE_RUB}₽\n4. Комментарий: `WHIEDA {uid}`\n5. Нажми «Я оплатил(а)»",parse_mode="Markdown")

async def handle_message(update, ctx):
    uid = update.effective_user.id; state = load_state(uid); text = update.message.text.strip()
    if not state: await update.message.reply_text("Напиши /start чтобы начать."); return
    if state.get("stage")=="survey" and state.get("survey_step")==0:
        state["survey"]["name"]=text[:30]; state["survey_step"]=1; save_state(uid,state); await send_survey_step(update,state,uid); return
    if state.get("stage")=="survey":
        step = state.get("survey_step",0); s = SURVEY_STEPS[step] if step<len(SURVEY_STEPS) else None
        if s: await update.message.reply_text("Выбери один из вариантов 👆",reply_markup=InlineKeyboardMarkup(s["buttons"]))
        return
    if state.get("day_ended"): await update.message.reply_text("День завершён 😊\n\nНапиши /next чтобы продолжить."); return
    if not has_ai(state): await show_payment(update.message,state,uid); return
    state["replics_left"]-=1; use_ai(state)
    try:
        reply = await get_reply(state,text); save_state(uid,state)
        await send_voice_reply(update, reply) if YANDEX_KEY else await update.message.reply_text(reply)
    except: await update.message.reply_text("Что-то пошло не так, попробуй ещё раз."); return
    bal = state.get("ai_limit",0)-state.get("ai_requests",0)
    if bal==10: await update.message.reply_text("⚠️ Осталось 10 запросов. Пополнить: /pay")
    if is_end(reply,state["replics_left"]):
        state["day_ended"]=True; save_state(uid,state); await asyncio.sleep(1)
        if state["day"]>=5:
            name=state["survey"].get("name","")
            await update.message.reply_text(f"🏁 Игра завершена, {name}!\n\nТы прошёл все 5 дней с Антоном.\n\n/start чтобы сыграть снова.")
        else: await update.message.reply_text(f"День {state['day']} завершён.\n\n/next чтобы продолжить.")

def main():
    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import json as json_lib

    class ProxyHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args): pass

        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()

        def do_POST(self):
            if self.path == '/api/chat':
                length = int(self.headers.get('Content-Length', 0))
                body = json_lib.loads(self.rfile.read(length))
                try:
                    resp = client.messages.create(
                        model=body.get('model', 'claude-sonnet-4-20250514'),
                        max_tokens=body.get('max_tokens', 200),
                        system=body.get('system', ''),
                        messages=body.get('messages', [])
                    )
                    result = {'content': [{'type': 'text', 'text': resp.content[0].text}]}
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json_lib.dumps(result).encode())
                except Exception as e:
                    self.send_response(500)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(str(e).encode())

    PORT = int(os.environ.get('PORT', 8080))
    server = HTTPServer(('0.0.0.0', PORT), ProxyHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f"Прокси запущен на порту {PORT}")

    app = Application.builder().token(TG_TOKEN).build()
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("next",     cmd_next))
    app.add_handler(CommandHandler("pay",      cmd_pay))
    app.add_handler(CommandHandler("balance",  cmd_balance))
    app.add_handler(CommandHandler("activate", cmd_activate))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print(f"Бот запущен. Данные: {DATA_DIR}")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
