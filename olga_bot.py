"""
WHIEDA — Телеграм бот Ольга
Установка:
  pip install python-telegram-bot anthropic

Запуск:
  python olga_bot.py

Переменные окружения:
  TG_TOKEN — токен от @BotFather
  ANTHROPIC_KEY — ключ Claude API
"""

import os
import asyncio
from anthropic import Anthropic
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TG_TOKEN = os.environ.get("TG_TOKEN", "ВАШ_ТОКЕН_ЗДЕСЬ")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY", "ВАШ_КЛЮЧ_ЗДЕСЬ")

client = Anthropic(api_key=ANTHROPIC_KEY)

# ── Системный промпт Ольги ────────────────────────────────────────
def build_system(day: int, replics_left: int) -> str:
    scenarios = {
        1: """СЦЕНАРИЙ ДНЯ 1 — Первый контакт.
ЦЕЛЬ: Утеплиться, узнать как дела, намекнуть что есть кое-что интересное, предложить посмотреть короткое видео.
НЕЛЬЗЯ: Называть компанию, говорить про деньги первой, давить.
ЗАВЕРШЕНИЕ: Когда человек сказал "ладно", "окей", "давай потом" или отказался — мягко попрощайся.""",

        2: """СЦЕНАРИЙ ДНЯ 2 — Второй контакт.
ЦЕЛЬ: Спросить посмотрел ли видео. Ответить на вопросы. Предложить Zoom с партнёром.
ФИШКА: Говори через себя — "я сам так думал", "мой знакомый теперь зарабатывает больше директора".
ЗАВЕРШЕНИЕ: Когда Zoom назначен или человек снова отказал.""",

        3: """СЦЕНАРИЙ ДНЯ 3 — Третий контакт.
ЦЕЛЬ: Пригласить на живую презентацию. Если отказывается — "последний раз, обещаю".
ФИШКА: "Там живые люди, реальные истории. Два часа — сам решишь."
ЗАВЕРШЕНИЕ: Когда человек согласился или жёстко отказал.""",

        4: """СЦЕНАРИЙ ДНЯ 4 — Утро презентации.
ЦЕЛЬ: Напомнить что сегодня. Убедиться что придёт. Максимум 3-4 реплики.
ЗАВЕРШЕНИЕ: После подтверждения или переноса.""",

        5: """СЦЕНАРИЙ ДНЯ 5 — Финал.
ЦЕЛЬ: Последний шанс. Если не согласился — открытая дверь, пусть сам звонит когда будет готов.
ТОНАЛЬНОСТЬ: Тепло, без обид, по-дружески."""
    }

    return f"""Ты — Антон, 34 года, лидер сетевого бизнеса. Пишешь старому знакомому в Телеграм.

КТО ТЫ:
- Тёплый, живой, пишешь как друг в WhatsApp
- 3 года в компании, сам прошёл путь от сомнений до результата
- Не давишь, не уговариваешь — рассказываешь и предлагаешь

КАК ПИШЕШЬ:
- Коротко: 1-3 предложения. Не монологи.
- Через себя: "я нашёл", "я сам так думал", "мой знакомый"
- Никогда не называешь компанию WHIEDA — говоришь "компания", "направление", "бизнес"
- Смайлики умеренно 😊
- Если человек грубит — спокойно: "окей, понимаю, не буду настаивать 😊"

ТЕХНИКИ:
- Бумеранг: "именно поэтому и написал — чтобы показать как это работает иначе"
- Открытая дверь: "окей, не настаиваю — если что изменится, ты знаешь где меня найти"
- Через третье лицо: "мой знакомый работал менеджером — через год вышел на доход х3"

ЖЁСТКОЕ ПРАВИЛО — КОНТЕКСТНЫЙ ФИЛЬТР:
Ты рекрутёр. Твоя задача — пригласить человека на встречу/презентацию.

Всегда задавай себе вопрос: "Этот вопрос помогает человеку принять решение — идти или нет?"

ЕСЛИ ДА — отвечай кратко:
Примеры: "это MLM?", "сколько можно заработать?", "нужно продавать?", "это законно?"
→ Отвечаешь в 1-2 предложения, без лекции

ЕСЛИ НЕТ — это выведывание информации вне контекста:
Примеры: "расскажи про активатор клеток", "объясни бинар пошагово", "как считается PV?"
→ Антон это чувствует. Мягко уходит от темы.

Примеры ответов на выведывание:
- "Активатор — отличная штука, но про продукт лучше на живой встрече, там дадут попробовать 😊 Сейчас давай про главное"
- "Про бинар можно часами говорить — это лучше на цифрах объяснять. Давай сначала поймём нужно ли тебе это вообще"
- "Слушай, я не хочу грузить тебя терминами в переписке — это всё станет понятно само когда увидишь живьём"

КЛЮЧЕВОЙ ПРИНЦИП:
Если вопрос уводит от решения "да/нет" — Антон мягко возвращает к теме рекрутинга.
Не грубо, не отказывает — просто переключает внимание.

СЕЙЧАС ДЕНЬ {day} из 5.
РЕПЛИК ОСТАЛОСЬ: {replics_left}
Если реплик мало — аккуратно подводи к завершению дня.

{scenarios.get(day, scenarios[5])}

ВАЖНО: Отвечай только как Антон-рекрутёр. Не выходи из роли. Не становись консультантом."""

# ── Состояние пользователей ───────────────────────────────────────
user_states = {}

def get_state(user_id: int) -> dict:
    if user_id not in user_states:
        user_states[user_id] = {
            "day": 1,
            "replics_left": 10,
            "history": [],
            "day_ended": False
        }
    return user_states[user_id]

def reset_day(state: dict):
    state["history"] = []
    state["day_ended"] = False
    state["replics_left"] = 5 if state["day"] == 4 else 10

NARRATIVE = {
    2: "Несколько дней спустя...\n\nВидео так и лежит непросмотренным. Но разговор с Ольгой не выходит из головы.\n\n💭 «Если ты делаешь то, что всегда делал — получишь то, что всегда получал.» — Генри Форд",
    3: "Ещё через несколько дней...\n\nЖизнь идёт своим чередом. Ольга не писала — но ты знаешь что напишет.\n\n💭 «Богатые люди строят сети. Все остальные ищут работу.» — Роберт Кийосаки",
    4: "Утро дня презентации...\n\nСегодня та самая встреча. Ты ещё не решил — идти или нет.\n\n💭 «Твоё время ограничено. Не трать его на чужую жизнь.» — Стив Джобс",
    5: "Последний шанс...\n\nПрошло время. Ольга пишет последний раз.\n\n💭 «Не жди. Идеального момента не будет.» — Наполеон Хилл",
}

END_PHRASES = ['до завтра', 'пока!', 'созвонимся', 'жду тебя', 'не отвлекаю', 'хорошего дня', 'удачи', 'на связи', 'пока 😊', 'до встречи']

# ── Получить ответ Ольги ──────────────────────────────────────────
async def get_olga_reply(state: dict, user_msg: str = None) -> str:
    if user_msg:
        state["history"].append({"role": "user", "content": user_msg})

    messages = state["history"] if state["history"] else [
        {"role": "user", "content": "Начни — напиши первой, поздоровайся, спроси как дела."}
    ]

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        system=build_system(state["day"], state["replics_left"]),
        messages=messages
    )

    reply = response.content[0].text

    if user_msg:
        state["history"].append({"role": "assistant", "content": reply})
    else:
        state["history"] = [
            {"role": "user", "content": "Начни — напиши первой, поздоровайся, спроси как дела."},
            {"role": "assistant", "content": reply}
        ]

    return reply

def is_day_end(reply: str, replics_left: int) -> bool:
    if replics_left <= 0:
        return True
    return any(p in reply.lower() for p in END_PHRASES)

# ── Хендлеры ─────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_states[user_id] = {
        "day": 1,
        "replics_left": 10,
        "history": [],
        "day_ended": False
    }
    state = user_states[user_id]

    await update.message.reply_text(
        "🎮 WHIEDA — Живой диалог с Ольгой\n\n"
        "Сейчас тебе напишет знакомая. Отвечай как в реальной жизни.\n"
        "Можешь отказывать, возражать, задавать любые вопросы.\n\n"
        "5 дней. Ольга попытается пригласить тебя на встречу.\n\n"
        "Начинаем 👇"
    )

    await asyncio.sleep(1)

    reply = await get_olga_reply(state)
    await update.message.reply_text(reply)

async def cmd_next(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Перейти к следующему дню"""
    user_id = update.effective_user.id
    state = get_state(user_id)

    if state["day"] >= 5:
        await update.message.reply_text("Игра завершена. Напиши /start чтобы начать заново.")
        return

    state["day"] += 1
    reset_day(state)

    narr = NARRATIVE.get(state["day"], "")
    if narr:
        await update.message.reply_text(narr)
        await asyncio.sleep(2)

    await update.message.reply_text(f"📅 День {state['day']} из 5")
    await asyncio.sleep(1)

    reply = await get_olga_reply(state)
    await update.message.reply_text(reply)

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_state(user_id)
    text = update.message.text

    if state["day_ended"]:
        await update.message.reply_text(
            "День завершён 😊\n\nНапиши /next чтобы перейти к следующему дню."
        )
        return

    # Уменьшаем счётчик
    state["replics_left"] -= 1

    # Получаем ответ
    try:
        reply = await get_olga_reply(state, text)
        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text("Что-то пошло не так, попробуй ещё раз.")
        return

    # Проверяем конец дня
    if is_day_end(reply, state["replics_left"]):
        state["day_ended"] = True
        await asyncio.sleep(1)

        if state["day"] >= 5:
            await update.message.reply_text(
                "🏁 Игра завершена!\n\n"
                "Ты прошёл все 5 дней с Ольгой.\n"
                "Теперь ты знаешь как работает рекрутинг изнутри.\n\n"
                "Напиши /start чтобы сыграть снова."
            )
        else:
            await update.message.reply_text(
                f"День {state['day']} завершён.\n\n"
                f"Напиши /next когда будешь готов продолжить."
            )

# ── Запуск ────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TG_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("next", cmd_next))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
