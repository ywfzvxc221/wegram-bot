import json
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, Text
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import F
import sqlite3
import asyncio

bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()
conn = sqlite3.connect("quiz.db")
cursor = conn.cursor()

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

def load_ads():
    with open("ads.json", "r", encoding="utf-8") as f:
        return json.load(f)

ads = load_ads()

@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (user_id, balance, answered, ad_index) VALUES (?, 0, 0, 0)", (user_id,))
        conn.commit()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ابدأ الإجابة", callback_data="quiz_start")],
        [InlineKeyboardButton(text="الرصيد", callback_data="balance")],
        [InlineKeyboardButton(text="دعوة الأصدقاء", callback_data="referral")],
    ])
    if user_id == ADMIN_ID:
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="لوحة التحكم", callback_data="admin")])
    await message.answer("مرحبًا بك في بوت الربح من الإجابة على الأسئلة.", reply_markup=keyboard)

@dp.callback_query(Text("quiz_start"))
async def ask_question(callback: types.CallbackQuery):
    cursor.execute("SELECT * FROM questions ORDER BY RANDOM() LIMIT 1")
    row = cursor.fetchone()
    if not row:
        await callback.message.answer("لا توجد أسئلة متاحة حالياً.")
        return

    question_id, question, op1, op2, op3, op4, correct = row
    options = [op1, op2, op3, op4]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=opt, callback_data=f"answer_{i}")] for i, opt in enumerate(options)
    ])
    cursor.execute("UPDATE users SET question_id = ? WHERE user_id = ?", (question_id, callback.from_user.id))
    conn.commit()
    await callback.message.answer(question, reply_markup=keyboard)

@dp.callback_query(F.data.startswith("answer_"))
async def handle_answer(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    choice = int(callback.data.split("_")[1])

    cursor.execute("SELECT question_id FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    if not result:
        await callback.message.answer("حدث خطأ. يرجى البدء من جديد.")
        return

    question_id = result[0]
    cursor.execute("SELECT correct_option FROM questions WHERE id = ?", (question_id,))
    correct = cursor.fetchone()[0]

    if choice == correct:
        cursor.execute("UPDATE users SET balance = balance + 0.003, answered = answered + 1 WHERE user_id = ?", (user_id,))

        cursor.execute("SELECT referrer_id FROM users WHERE user_id = ?", (user_id,))
        ref = cursor.fetchone()
        if ref and ref[0]:
            cursor.execute("UPDATE users SET balance = balance + 0.0003 WHERE user_id = ?", (ref[0],))

        cursor.execute("SELECT answered, ad_index FROM users WHERE user_id = ?", (user_id,))
        answered, ad_index = cursor.fetchone()

        conn.commit()
        await callback.message.answer("إجابة صحيحة! تم إضافة $0.003 إلى رصيدك.")

        if answered % 4 == 0:
            ad = ads[ad_index % len(ads)]
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="زيارة الإعلان", url=ad["url"])],
                [InlineKeyboardButton(text="متابعة الأسئلة", callback_data="continue")]
            ])
            await callback.message.answer(ad["title"], reply_markup=markup)
            cursor.execute("UPDATE users SET ad_index = ad_index + 1 WHERE user_id = ?", (user_id,))
            conn.commit()
            return

        await ask_question(callback.message)
    else:
        await callback.message.answer("إجابة خاطئة! حاول مرة أخرى.")

    await callback.answer()

@dp.callback_query(Text("continue"))
async def continue_quiz(callback: types.CallbackQuery):
    await ask_question(callback.message)
    await callback.answer()

@dp.callback_query(Text("balance"))
async def balance(callback: types.CallbackQuery):
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (callback.from_user.id,))
    balance = cursor.fetchone()[0]
    await callback.message.answer(f"رصيدك الحالي: ${balance:.4f}")
    await callback.answer()

@dp.callback_query(Text("admin"))
async def admin_panel(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("غير مصرح لك.", show_alert=True)
        return
    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(balance) FROM users")
    total_paid = cursor.fetchone()[0] or 0
    await callback.message.answer(
        f"لوحة التحكم:
عدد المستخدمين: {users_count}
إجمالي الأرباح المدفوعة: ${total_paid:.4f}"
    )
    await callback.answer()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
