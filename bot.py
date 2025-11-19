#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بوت تلغرام لحفظ المحتوى (دعم حفظ ملفات/صور/نصوص) + تحقق اشتراك إجباري بقناتين
مطلوب: تعيين المتغير البيئي BOT_TOKEN فقط على Render لتشغيل البوت.

مكتوب باستخدام python-telegram-bot v13 (synchronous). قاعدة بيانات sqlite محلية.
"""
import os
import logging
import sqlite3
from datetime import datetime
from functools import wraps

from telegram import (Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup,
                      InlineQueryResultArticle, InputTextMessageContent,
                      InlineQueryResultCachedPhoto, InlineQueryResultCachedDocument)
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters,
                          InlineQueryHandler, CallbackContext, CallbackQueryHandler)

# ------- CONFIG -------
REQUIRED_CHANNELS = ["@Tepthon", "@TepthonHelp"]
DB_PATH = os.environ.get("DB_PATH", "saves.db")
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
    def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        bot: Bot = context.bot
        not_member = []
        for ch in REQUIRED_CHANNELS:
            try:
                member = bot.get_chat_member(ch, user_id)
                if member.status in ('left', 'kicked'):
                    not_member.append(ch)
            except Exception as e:
                logger.warning(f"Error checking membership for {ch}: {e}")
                not_member.append(ch)
        if not_member:
            keyboard = [[InlineKeyboardButton("اشترك هنا " + ch, url=f"https://t.me/{ch.lstrip('@')}") for ch in not_member]]
            keyboard.append([InlineKeyboardButton("تحقق الآن", callback_data="verify")])
            update.effective_message.reply_text(
                "قبل ما تقدر تستخدم البوت لازم تشترك في القنوات التالية:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        return func(update, context, *args, **kwargs)
    return wrapper

# ------- Helper to process a message (forwarded or replied) -------

def process_message(msg, context: CallbackContext):
    user_id = msg.from_user.id
    # determine type
    file_id = None
    ftype = None
    caption = msg.caption if msg.caption else (msg.text if msg.text else '')

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
        msg.reply_text('نوع المحتوى غير مدعوم للحفظ.')
        return

    if ftype == 'text':
        save_item(user_id, '', 'text', caption)
        msg.reply_text('تم حفظ النص 📝')
        return

    sid = save_item(user_id, file_id, ftype, caption)
    msg.reply_text('تم الحفظ بنجاح — رقم المرجع: #' + str(sid))

# ------- Handlers -------

def start(update: Update, context: CallbackContext):
    user = update.effective_user
    text = f"- اهلا {user.first_name}\nانا بوت حفظ المحتوى — ابعث المحتوى دلوقتي 🖤"
    keyboard = [[InlineKeyboardButton("أنضم اولا 💌", callback_data='verify')]]
    update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


def verify_cmd(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    bot: Bot = context.bot
    not_member = []
    for ch in REQUIRED_CHANNELS:
        try:
            member = bot.get_chat_member(ch, user_id)
            if member.status in ('left', 'kicked'):
                not_member.append(ch)
        except Exception as e:
            logger.warning(f"Error checking membership for {ch}: {e}")
            not_member.append(ch)
    if not_member:
        kb = [[InlineKeyboardButton("اشترك هنا " + ch, url=f"https://t.me/{ch.lstrip('@')}") for ch in not_member]]
        kb.append([InlineKeyboardButton("تحقق مرة اخرى", callback_data='verify')])
        update.effective_message.reply_text("لسه باين إنك مش مشترك في:")
        update.effective_message.reply_text('\n'.join(not_member), reply_markup=InlineKeyboardMarkup(kb))
    else:
        update.effective_message.reply_text("تمام! تم التحقق — تقدر الآن تستخدم البوت 🖤.")


def callback_query_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    if query.data == 'verify':
        query.answer()
        verify_cmd(update, context)


@must_subscribed
def save_forwarded(update: Update, context: CallbackContext):
    # هذا الهاندلر يتعامل مع أي رسالة عادية (مع تطبيق فحص الاشتراك بواسطة الديكوريتر)
    msg = update.message
    process_message(msg, context)


@must_subscribed
def save_command(update: Update, context: CallbackContext):
    # حفظ عبر /save عند الرد على رسالة
    if not update.message.reply_to_message:
        update.message.reply_text('رد على رسالة بها محتوى ثم اكتب /save')
        return
    # نستخدم نفس لوجيك الحفظ لكن على الرسالة المردودة
    process_message(update.message.reply_to_message, context)


def inline_query(update: Update, context: CallbackContext):
    query = update.inline_query
    user_id = query.from_user.id
    q = query.query.strip()

    bot = context.bot
    for ch in REQUIRED_CHANNELS:
        try:
            member = bot.get_chat_member(ch, user_id)
            if member.status in ('left', 'kicked'):
                r = InlineQueryResultArticle(
                    id='not_subscribed',
                    title='يجب أن تشترك أولاً',
                    input_message_content=InputTextMessageContent(
                        'رجاءً اشترك في القنوات المطلوبة ثم جرب مرة أخرى.'
                    )
                )
                query.answer([r], cache_time=10)
                return
        except Exception:
            r = InlineQueryResultArticle(
                id='not_subscribed',
                title='يجب أن تشترك أولاً',
                input_message_content=InputTextMessageContent(
                    'رجاءً اشترك في القنوات المطلوبة ثم جرب مرة أخرى.'
                )
            )
            query.answer([r], cache_time=10)
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

    query.answer(results, cache_time=5)


def error_handler(update: object, context: CallbackContext):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)


def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CommandHandler('verify', verify_cmd))
    dp.add_handler(CommandHandler('save', save_command))

    dp.add_handler(InlineQueryHandler(inline_query))

    dp.add_handler(MessageHandler(Filters.forwarded | Filters.photo | Filters.document | Filters.video | Filters.audio | Filters.voice | Filters.text, save_forwarded))

    dp.add_handler(MessageHandler(Filters.command, lambda u, c: u.message.reply_text('غير معروف')))

    dp.add_handler(CallbackQueryHandler(callback_query_handler))

    dp.add_error_handler(error_handler)

    logger.info('Starting bot...')
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()def init_db():
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
    def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        bot: Bot = context.bot
        not_member = []
        for ch in REQUIRED_CHANNELS:
            try:
                member = bot.get_chat_member(ch, user_id)
                # statuses: 'creator', 'administrator', 'member', 'restricted', 'left', 'kicked'
                if member.status in ('left', 'kicked'):
                    not_member.append(ch)
            except Exception as e:
                # إذا حدث خطأ (مثل بوت غير مشترك بالقناة)، سنعتبر المستخدم غير مشترك
                logger.warning(f"Error checking membership for {ch}: {e}")
                not_member.append(ch)
        if not_member:
            # رسالة ودية بالعربية تطلب الاشتراك
            keyboard = [[InlineKeyboardButton("اشترك هنا " + ch, url=f"https://t.me/{ch.lstrip('@')}") for ch in not_member]]
            keyboard.append([InlineKeyboardButton("تحقق الآن", callback_data="verify")])
            update.effective_message.reply_text(
                "قبل ما تقدر تستخدم البوت لازم تشترك في القنوات التالية:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        return func(update, context, *args, **kwargs)
    return wrapper

# ------- Handlers -------

def start(update: Update, context: CallbackContext):
    user = update.effective_user
    text = (f"- اهـلا {user.first_name}/nانا بوت حفظ المحتوي المقيد أرسل رابط الان 🖤.")
    keyboard = [[InlineKeyboardButton("أنضـم اولا 💌", callback_data='verify')]]
    update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


def verify_cmd(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    bot: Bot = context.bot
    not_member = []
    for ch in REQUIRED_CHANNELS:
        try:
            member = bot.get_chat_member(ch, user_id)
            if member.status in ('left', 'kicked'):
                not_member.append(ch)
        except Exception as e:
            logger.warning(f"Error checking membership for {ch}: {e}")
            not_member.append(ch)
    if not_member:
        kb = [[InlineKeyboardButton("اشترك هنا " + ch, url=f"https://t.me/{ch.lstrip('@')}") for ch in not_member]]
        kb.append([InlineKeyboardButton("تحقق مرة اخرى", callback_data='verify')])
        update.effective_message.reply_text("لسه باين إنك مش مشترك في:")
        update.effective_message.reply_text('\n'.join(not_member), reply_markup=InlineKeyboardMarkup(kb))
    else:
        update.effective_message.reply_text("تمام! تم التحقق — تقدر الآن تستخدم البوت 🖤.")


def callback_query_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    if query.data == 'verify':
        query.answer()
        verify_cmd(update, context)


@must_subscribed
def save_forwarded(update: Update, context: CallbackContext):
    msg = update.message
    user_id = msg.from_user.id
    # تحديد نوع الملف وfile_id
    file_id = None
    ftype = None
    caption = msg.caption if msg.caption else (msg.text if msg.text else '')

    if msg.document:
        file_id = msg.document.file_id
        ftype = 'document'
    elif msg.photo:
        # photo قائمة وبنأخذ أعلى جودة
        file_id = msg.photo[-1].file_id
        ftype = 'photo'
    elif msg.video:
        file_id = msg.video.file_id
        ftype = 'video'
    elif msg.audio:
        file_id = msg.audio.file_id
        ftype = 'audio'
    elif msg.voice:
        file_id = msg.voice.file_id
        ftype = 'voice'
    elif msg.text:
        file_id = None
        ftype = 'text'
    else:
        update.message.reply_text('نوع المحتوى غير مدعوم للحفظ.')
        return

    if ftype == 'text':
        # نحفظ النص كاملاً كـ caption
        save_item(user_id, '', 'text', caption)
        update.message.reply_text('تم حفظ النص 📝')
        return

    sid = save_item(user_id, file_id, ftype, caption)
    update.message.reply_text('تم الحفظ بنجاح — رقم المرجع: #' + str(sid))


@must_subscribed
def save_command(update: Update, context: CallbackContext):
    # حفظ عبر /save عند الرد على رسالة
    if not update.message.reply_to_message:
        update.message.reply_text('رد على رسالة بها محتوى ثم اكتب /save')
        return
    # محاكاة نفس المنطق
    update.message.reply_to_message.forward(chat_id=update.effective_chat.id)
    # لكن أبسط: اعادة استخدام نفس المعالج
    save_forwarded(update, context)


def inline_query(update: Update, context: CallbackContext):
    query = update.inline_query
    user_id = query.from_user.id
    q = query.query.strip()

    # تحقق اشتراك (هنا نتحقق سريعا بنهج مشابه)
    bot = context.bot
    for ch in REQUIRED_CHANNELS:
        try:
            member = bot.get_chat_member(ch, user_id)
            if member.status in ('left', 'kicked'):
                # نُعيد نتيجة تحمل تسجيلاً يطلب الاشتراك
                r = InlineQueryResultArticle(
                    id='not_subscribed',
                    title='يجب أن تشترك أولاً',
                    input_message_content=InputTextMessageContent(
                        'رجاءً اشترك في القنوات المطلوبة ثم جرب مرة أخرى.'
                    )
                )
                query.answer([r], cache_time=10)
                return
        except Exception:
            r = InlineQueryResultArticle(
                id='not_subscribed',
                title='يجب أن تشترك أولاً',
                input_message_content=InputTextMessageContent(
                    'رجاءً اشترك في القنوات المطلوبة ثم جرب مرة أخرى.'
                )
            )
            query.answer([r], cache_time=10)
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
                # fallback to article
                results.append(InlineQueryResultArticle(id=iid, title=caption or 'صورة', input_message_content=InputTextMessageContent(caption or 'صورة')))
        elif ftype == 'document' and file_id:
            try:
                results.append(InlineQueryResultCachedDocument(id=iid, title=caption or 'ملف', document_file_id=file_id))
            except Exception:
                results.append(InlineQueryResultArticle(id=iid, title=caption or 'ملف', input_message_content=InputTextMessageContent(caption or 'ملف')))
        else:
            # نص أو غير معروف
            txt = caption or f"محتوى محفوظ #{_id}"
            results.append(InlineQueryResultArticle(id=iid, title=txt[:30], input_message_content=InputTextMessageContent(txt)))
        if len(results) >= 20:
            break

    if not results:
        results = [InlineQueryResultArticle(id='empty', title='لا يوجد محتوى محفوظ', input_message_content=InputTextMessageContent('مافيش حاجه محفوظة لغاية دلوقتي.'))]

    query.answer(results, cache_time=5)


def error_handler(update: object, context: CallbackContext):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)


def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CommandHandler('verify', verify_cmd))
    dp.add_handler(CommandHandler('save', save_command))

    dp.add_handler(InlineQueryHandler(inline_query))

    dp.add_handler(MessageHandler(Filters.forwarded | Filters.photo | Filters.document | Filters.video | Filters.audio | Filters.voice | Filters.text, save_forwarded))

    dp.add_handler(MessageHandler(Filters.command, lambda u, c: u.message.reply_text('غير معروف')))

    dp.add_handler(MessageHandler(Filters.callback_query, callback_query_handler))

    dp.add_error_handler(error_handler)

    logger.info('Starting bot...')
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
