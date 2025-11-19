#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بوت تلغرام لحفظ المحتوى (دعم حفظ ملفات/صور/نصوص) + تحقق اشتراك إجباري بقناتين
مطلوب: تعيين المتغير البيئي BOT_TOKEN فقط على Render لتشغيل البوت.

مكتوب باستخدام python-telegram-bot v20.7 (asynchronous). قاعدة بيانات sqlite محلية.
"""
import os
import logging
import sqlite3
from datetime import datetime
from functools import wraps

from telegram import (Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup,
                      InlineQueryResultArticle, InputTextMessageContent,
                      InlineQueryResultCachedPhoto, InlineQueryResultCachedDocument)
from telegram.ext import (Application, CommandHandler, MessageHandler, filters,
                          InlineQueryHandler, ContextTypes, CallbackQueryHandler)
from telegram.ext import CallbackContext

# ------- CONFIG -------
REQUIRED_CHANNELS = ["@Tepthon", "@TepthonHelp"]
# استخدام مسار مطلق للداتابيز علشان Render
DB_PATH = os.path.join(os.getcwd(), "saves.db")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("Please set BOT_TOKEN environment variable")

# ------- Logging -------
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ------- Database helpers -------

def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS saves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            file_id TEXT,
            file_type TEXT,
            caption TEXT,
            created_at TEXT
        )
        """
    )
    conn.commit()
    return conn

DB = init_db()


def save_item(user_id, file_id, file_type, caption=None):
    cur = DB.cursor()
    cur.execute("INSERT INTO saves (user_id, file_id, file_type, caption, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, file_id, file_type, caption or '', datetime.utcnow().isoformat()))
    DB.commit()
    return cur.lastrowid


def search_items(user_id, q=None, limit=20):
    cur = DB.cursor()
    if q:
        cur.execute("SELECT id, file_id, file_type, caption FROM saves WHERE user_id=? AND caption LIKE ? ORDER BY id DESC LIMIT ?",
                    (user_id, f"%{q}%", limit))
    else:
        cur.execute("SELECT id, file_id, file_type, caption FROM saves WHERE user_id=? ORDER BY id DESC LIMIT ?",
                    (user_id, limit))
    return cur.fetchall()

# ------- Subscription check decorator -------

def must_subscribed(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if user is None:
            return await func(update, context, *args, **kwargs)
        user_id = user.id
        bot: Bot = context.bot
        not_member = []
        for ch in REQUIRED_CHANNELS:
            try:
                member = await bot.get_chat_member(ch, user_id)
                if member.status in ('left', 'kicked'):
                    not_member.append(ch)
            except Exception as e:
                logger.warning(f"Error checking membership for {ch}: {e}")
                not_member.append(ch)
        if not_member:
            keyboard = [[InlineKeyboardButton("اشترك هنا " + ch, url=f"https://t.me/{ch.lstrip('@')}") for ch in not_member]]
            keyboard.append([InlineKeyboardButton("تحقق الآن", callback_data="verify")])
            if update.effective_message:
                await update.effective_message.reply_text(
                    "قبل ما تقدر تستخدم البوت لازم تشترك في القنوات التالية:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# ------- Helper to process a message (forwarded or replied) -------

async def process_message(msg, context: ContextTypes.DEFAULT_TYPE):
    if msg is None:
        return
    user = msg.from_user
    if user is None:
        return
    user_id = user.id
    # determine type
    file_id = None
    ftype = None
    caption = msg.caption if getattr(msg, 'caption', None) else (msg.text if getattr(msg, 'text', None) else '')

    if getattr(msg, 'document', None):
        file_id = msg.document.file_id
        ftype = 'document'
    elif getattr(msg, 'photo', None):
        file_id = msg.photo[-1].file_id
        ftype = 'photo'
    elif getattr(msg, 'video', None):
        file_id = msg.video.file_id
        ftype = 'video'
    elif getattr(msg, 'audio', None):
        file_id = msg.audio.file_id
        ftype = 'audio'
    elif getattr(msg, 'voice', None):
        file_id = msg.voice.file_id
        ftype = 'voice'
    elif getattr(msg, 'text', None):
        file_id = ''
        ftype = 'text'
    else:
        if getattr(msg, 'reply_text', None):
            await msg.reply_text('نوع المحتوى غير مدعوم للحفظ.')
        return

    if ftype == 'text':
        save_item(user_id, '', 'text', caption)
        await msg.reply_text('تم حفظ النص 📝')
        return

    sid = save_item(user_id, file_id, ftype, caption)
    await msg.reply_text('تم الحفظ بنجاح — رقم المرجع: #' + str(sid))

# ------- Handlers -------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = user.first_name if user and getattr(user, 'first_name', None) else 'صديق'
    text = f"- اهلا {name}\nانا بوت حفظ المحتوى — ابعث المحتوى دلوقتي 🖤"
    keyboard = [[InlineKeyboardButton("أنضم اولا 💌", callback_data='verify')]]
    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def verify_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user is None:
        return
    user_id = user.id
    bot: Bot = context.bot
    not_member = []
    for ch in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(ch, user_id)
            if member.status in ('left', 'kicked'):
                not_member.append(ch)
        except Exception as e:
            logger.warning(f"Error checking membership for {ch}: {e}")
            not_member.append(ch)
    if not_member:
        kb = [[InlineKeyboardButton("اشترك هنا " + ch, url=f"https://t.me/{ch.lstrip('@')}") for ch in not_member]]
        kb.append([InlineKeyboardButton("تحقق مرة اخرى", callback_data='verify')])
        if update.effective_message:
            await update.effective_message.reply_text("لسه باين إنك مش مشترك في:")
            await update.effective_message.reply_text('\n'.join(not_member), reply_markup=InlineKeyboardMarkup(kb))
    else:
        if update.effective_message:
            await update.effective_message.reply_text("تمام! تم التحقق — تقدر الآن تستخدم البوت 🖤.")


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    if query.data == 'verify':
        try:
            await query.answer()
        except Exception:
            pass
        await verify_cmd(update, context)


@must_subscribed
async def save_forwarded(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # هذا الهاندلر يتعامل مع أي رسالة عادية (مع تطبيق فحص الاشتراك بواسطة الديكوريتر)
    msg = update.message
    await process_message(msg, context)


@must_subscribed
async def save_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # حفظ عبر /save عند الرد على رسالة
    if not update.message or not update.message.reply_to_message:
        if update.message:
            await update.message.reply_text('رد على رسالة بها محتوى ثم اكتب /save')
        return
    # نستخدم نفس لوجيك الحفظ لكن على الرسالة المردودة
    await process_message(update.message.reply_to_message, context)


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query
    if not query:
        return
    user_id = query.from_user.id
    q = query.query.strip() if getattr(query, 'query', None) else ''

    bot = context.bot
    for ch in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(ch, user_id)
            if member.status in ('left', 'kicked'):
                r = InlineQueryResultArticle(
                    id='not_subscribed',
                    title='يجب أن تشترك أولاً',
                    input_message_content=InputTextMessageContent(
                        'رجاءً اشترك في القنوات المطلوبة ثم جرب مرة أخرى.'
                    )
                )
                await query.answer([r], cache_time=10)
                return
        except Exception:
            r = InlineQueryResultArticle(
                id='not_subscribed',
                title='يجب أن تشترك أولاً',
                input_message_content=InputTextMessageContent(
                    'رجاءً اشترك في القنوات المطلوبة ثم جرب مرة أخرى.'
                )
            )
            await query.answer([r], cache_time=10)
            return

    items = search_items(user_id, q=q, limit=20)
    results = []
    for row in items:
        _id, file_id, ftype, caption = row
        iid = f"item-{_id}"
        if ftype == 'photo' and file_id:
            try:
                results.append(InlineQueryResultCachedPhoto(id=iid, photo_file_id=file_id, title=caption or 'صورة'))
            except Exception:
                results.append(InlineQueryResultArticle(id=iid, title=caption or 'صورة', input_message_content=InputTextMessageContent(caption or 'صورة')))
        elif ftype == 'document' and file_id:
            try:
                results.append(InlineQueryResultCachedDocument(id=iid, title=caption or 'ملف', document_file_id=file_id))
            except Exception:
                results.append(InlineQueryResultArticle(id=iid, title=caption or 'ملف', input_message_content=InputTextMessageContent(caption or 'ملف')))
        else:
            txt = caption or f"محتوى محفوظ #{_id}"
            results.append(InlineQueryResultArticle(id=iid, title=txt[:30], input_message_content=InputTextMessageContent(txt)))
        if len(results) >= 20:
            break

    if not results:
        results = [InlineQueryResultArticle(id='empty', title='لا يوجد محتوى محفوظ', input_message_content=InputTextMessageContent('مافيش حاجه محفوظة لغاية دلوقتي.'))]

    await query.answer(results, cache_time=5)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)


def main():
    # استخدام Application بدلاً من Updater في الإصدار 20.x
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('verify', verify_cmd))
    application.add_handler(CommandHandler('save', save_command))

    application.add_handler(InlineQueryHandler(inline_query))

    application.add_handler(MessageHandler(
        filters.FORWARDED | filters.PHOTO | filters.Document.ALL |
        filters.VIDEO | filters.AUDIO | filters.VOICE | filters.TEXT,
        save_forwarded
    ))

    application.add_handler(CallbackQueryHandler(callback_query_handler))

    application.add_handler(MessageHandler(filters.COMMAND, lambda u, c: u.message.reply_text('غير معروف')))

    application.add_error_handler(error_handler)

    logger.info('Starting bot...')
    application.run_polling()


if __name__ == '__main__':
    main()
