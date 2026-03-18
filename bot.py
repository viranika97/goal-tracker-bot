# Updated: 2026-01-06 test4
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Goal Tracker Telegram Bot
Отслеживает прогресс обучения и постит отчёты в канал
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
import asyncio

from telegram import Bot
from telegram.error import TelegramError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Firebase
import firebase_admin
from firebase_admin import credentials, firestore

# ==================== КОНФИГУРАЦИЯ ====================

# Telegram
BOT_TOKEN = "8372871931:AAG5_MQypUetuzorBeluXJpWv54cr5PbUvg"
CHANNEL_ID = "@viranika97_12_weeks"

# Firebase
FIREBASE_PROJECT_ID = "goal-tracker-1ad42"
FIREBASE_COLLECTION = "users"
FIREBASE_USER_DOC = "veronika"

# Расписание (московское время UTC+3)
DAILY_REPORT_TIME = "21:01"      # Ежедневный отчёт
SHAME_CHECK_TIME = "23:01"       # Проверка на лоханье
WEEKLY_SUMMARY_TIME = "20:01"    # Еженедельные итоги (воскресенье)

# Дата старта работы бота (None = работает сразу)
# Формат: "YYYY-MM-DD" например "2026-01-10"
BOT_START_DATE = None  # Измените на нужную дату или оставьте None

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================

bot: Optional[Bot] = None
db: Optional[firestore.Client] = None
scheduler: Optional[AsyncIOScheduler] = None

# ==================== FIREBASE ====================

def init_firebase():
    """Инициализация Firebase"""
    global db
    
    try:
        if not firebase_admin._apps:
            # Читаем credentials из переменной окружения
            import json
            creds_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
            
            # ОТЛАДКА
            if creds_json:
                logger.info(f"📋 Переменная найдена, длина: {len(creds_json)} символов")
            else:
                logger.error("❌ Переменная GOOGLE_APPLICATION_CREDENTIALS_JSON пустая или не найдена!")
            
            if creds_json:
                # Парсим JSON из переменной окружения
                try:
                    creds_dict = json.loads(creds_json)
                    logger.info("✅ JSON успешно распарсен")
                    cred = credentials.Certificate(creds_dict)
                    firebase_admin.initialize_app(cred)
                    logger.info("✅ Firebase инициализирован с credentials из переменной окружения")
                except json.JSONDecodeError as je:
                    logger.error(f"❌ Ошибка парсинга JSON: {je}")
                    raise
            else:
                # Fallback - пробуем автоматические credentials
                firebase_admin.initialize_app(options={
                    'projectId': FIREBASE_PROJECT_ID,
                })
                logger.info("✅ Firebase инициализирован с автоматическими credentials")
        
        db = firestore.client()
        logger.info("✅ Firebase клиент создан")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации Firebase: {e}")
        return False

def get_user_data() -> Optional[Dict]:
    """Получить данные пользователя из Firebase"""
    try:
        doc_ref = db.collection(FIREBASE_COLLECTION).document(FIREBASE_USER_DOC)
        doc = doc_ref.get()
        
        if doc.exists:
            data = doc.to_dict()
            logger.info(f"📊 Данные загружены из Firebase")
            return data
        else:
            logger.warning("⚠️ Документ пользователя не найден в Firebase")
            return None
            
    except Exception as e:
        logger.error(f"❌ Ошибка чтения Firebase: {e}")
        return None

# ==================== ПРОВЕРКИ ====================

def is_bot_active() -> bool:
    """Проверить активен ли бот (дата старта наступила)"""
    if BOT_START_DATE is None:
        return True  # Работаем сразу
    
    try:
        start_date = datetime.strptime(BOT_START_DATE, '%Y-%m-%d').date()
        today = datetime.now().date()
        
        is_active = today >= start_date
        
        if not is_active:
            days_until = (start_date - today).days
            logger.info(f"⏳ Бот неактивен. До старта {days_until} дней (старт: {BOT_START_DATE})")
        
        return is_active
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки даты старта: {e}")
        return True  # При ошибке работаем

def get_today_key() -> str:
    """Получить ключ сегодняшнего дня (YYYY-MM-DD)"""
    return datetime.now().strftime('%Y-%m-%d')

def did_study_today(data: Dict) -> bool:
    """Проверить занималась ли сегодня"""
    today_key = get_today_key()
    study_days = data.get('studyDays', {})
    
    # Проверяем есть ли запись за сегодня
    return today_key in study_days and study_days[today_key] > 0

def get_days_since_last_activity(data: Dict) -> int:
    """Получить количество дней с последней активности"""
    study_days = data.get('studyDays', {})
    
    if not study_days:
        return 999  # Никогда не занималась
    
    # Находим последнюю дату
    last_date_str = max(study_days.keys())
    last_date = datetime.strptime(last_date_str, '%Y-%m-%d')
    
    days_diff = (datetime.now() - last_date).days
    return days_diff

# ==================== ФОРМАТИРОВАНИЕ ====================

def format_daily_report(data: Dict) -> str:
    """Форматировать ежедневный отчёт"""
    today_key = get_today_key()
    today_date = datetime.now().strftime('%d %B')
    
    minutes = data.get('studyDays', {}).get(today_key, 0)
    lessons = data.get('lessonsCompleted', 0)
    tasks = data.get('tasksCompleted', 0)
    streak = data.get('streak', 0)
    total_lessons = data.get('totalLessons', 41)
    progress_percent = int((lessons / total_lessons) * 100) if total_lessons > 0 else 0
    
    message = f"""🤖 Автоотчёт за {today_date}

✅ ЗАНИМАЛАСЬ!

📚 Уроков: {lessons}/{total_lessons}
⏱ Время сегодня: {minutes} минут
🔥 Streak: {streak} дней!

📊 Прогресс курса: {progress_percent}%

💪 Молодец! Так держать!"""
    
    return message

def format_shame_message(data: Dict) -> str:
    """Форматировать сообщение стыда"""
    today_date = datetime.now().strftime('%d %B')
    days_missed = get_days_since_last_activity(data)
    old_streak = data.get('streak', 0)
    
    # Дни до дедлайна
    deadline_str = data.get('deadlineDate')
    if deadline_str:
        deadline = datetime.fromisoformat(deadline_str.replace('Z', '+00:00'))
        days_left = (deadline.replace(tzinfo=None) - datetime.now()).days
    else:
        days_left = 0
    
    # Прогресс
    lessons = data.get('lessonsCompleted', 0)
    total_lessons = data.get('totalLessons', 41)
    remaining_lessons = total_lessons - lessons
    
    message = f"""🤖 Проверка за {today_date}

💀 НЕ ОТЧИТАЛАСЬ!

Последняя активность: {days_missed} дней назад
Пропущено подряд: {days_missed} дней

🔥 Streak потерян: {old_streak} → 0 😭

⚠️ СТАТУС: ЛОХАНУЛАСЬ

📊 Прогресс:
• Осталось уроков: {remaining_lessons}
• До дедлайна: {days_left} дней

Завтра ОБЯЗАТЕЛЬНО вернись! 💪"""
    
    return message

def format_reset_message(data: Dict) -> str:
    """Форматировать сообщение о сбросе"""
    reset_type = data.get('resetType', 'unknown')
    reset_date = data.get('resetDate', datetime.now().isoformat())
    
    try:
        reset_dt = datetime.fromisoformat(reset_date.replace('Z', '+00:00'))
        reset_date_str = reset_dt.strftime('%d %B %Y, %H:%M')
    except:
        reset_date_str = "недавно"
    
    if reset_type == 'progress':
        # Мягкий сброс
        start_date = data.get('startDate')
        deadline_date = data.get('deadlineDate')
        
        try:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            deadline_dt = datetime.fromisoformat(deadline_date.replace('Z', '+00:00'))
            start_str = start_dt.strftime('%d %B %Y')
            deadline_str = deadline_dt.strftime('%d %B %Y')
        except:
            start_str = "не указана"
            deadline_str = "не указан"
        
        message = f"""🤖 Обнаружен сброс прогресса

Время сброса: {reset_date_str}

Данные обнулены:
• Уроки → 0
• Задания → 0
• Streak → 0
• Время → 0

Даты курса сохранены:
• Старт: {start_str}
• Дедлайн: {deadline_str}

Начинаем заново! 💪"""
        
    elif reset_type == 'full':
        # Полный сброс
        message = f"""🤖 Полный сброс системы

Время сброса: {reset_date_str}

Все данные удалены.
Начинается новый цикл обучения!

Удачи в новом забеге! 🚀"""
        
    else:
        message = f"""🤖 Обнаружен сброс данных

Время: {reset_date_str}

Система перезапущена."""
    
    return message

def format_weekly_summary(data: Dict) -> str:
    """Форматировать еженедельные итоги"""
    # Текущая неделя
    today = datetime.now()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    
    week_str = f"{week_start.strftime('%d %b')} - {week_end.strftime('%d %b')}"
    
    # Подсчитываем активность за неделю
    study_days = data.get('studyDays', {})
    week_minutes = 0
    active_days = 0
    
    for i in range(7):
        day = week_start + timedelta(days=i)
        day_key = day.strftime('%Y-%m-%d')
        if day_key in study_days:
            minutes = study_days[day_key]
            if minutes > 0:
                week_minutes += minutes
                active_days += 1
    
    week_hours = week_minutes / 60
    
    # Общий прогресс
    lessons = data.get('lessonsCompleted', 0)
    tasks = data.get('tasksCompleted', 0)
    streak = data.get('streak', 0)
    
    # Оценка недели
    if active_days >= 6:
        rating = 10
        status = "ОТЛИЧНО! 🌟"
    elif active_days >= 5:
        rating = 9
        status = "МОЛОДЕЦ! 💪"
    elif active_days >= 4:
        rating = 7
        status = "Хорошо ✓"
    elif active_days >= 3:
        rating = 5
        status = "Средне ⚠️"
    else:
        rating = 3
        status = "Слабовато 😔"
    
    message = f"""🤖 Итоги недели | {week_str}

📊 Статистика:

Дней с занятиями: {active_days}/7
Времени потрачено: {week_hours:.1f} часов
Текущий streak: {streak} дней

📈 Общий прогресс:
• Уроков пройдено: {lessons}
• Заданий выполнено: {tasks}

🎯 Оценка недели: {rating}/10
Статус: {status}

{'Так держать! 🔥' if rating >= 7 else 'На следующей неделе постарайся лучше! 💪'}"""
    
    return message

# ==================== ОТПРАВКА СООБЩЕНИЙ ====================

async def send_to_channel(message: str):
    """Отправить сообщение в канал"""
    try:
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=message,
            parse_mode=None  # Без форматирования для избежания проблем
        )
        logger.info(f"✅ Сообщение отправлено в канал")
        return True
        
    except TelegramError as e:
        logger.error(f"❌ Ошибка отправки в Telegram: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка: {e}")
        return False

# ==================== ЗАДАЧИ ПО РАСПИСАНИЮ ====================

async def daily_report_task():
    """Ежедневный отчёт в 21:00"""
    logger.info("📊 Запуск задачи: ежедневный отчёт")
    
    # Проверяем активен ли бот
    if not is_bot_active():
        logger.info("⏸ Бот неактивен (дата старта не наступила)")
        return
    
    data = get_user_data()
    if not data:
        logger.error("❌ Не удалось загрузить данные")
        return
    
    # Проверяем занималась ли сегодня
    if did_study_today(data):
        message = format_daily_report(data)
        await send_to_channel(message)
        logger.info("✅ Отчёт о занятиях отправлен")
    else:
        logger.info("ℹ️ Сегодня не было занятий, ждём до 23:00")

async def shame_check_task():
    """Проверка на лоханье в 23:00"""
    logger.info("💀 Запуск задачи: проверка на лоханье")
    
    # Проверяем активен ли бот
    if not is_bot_active():
        logger.info("⏸ Бот неактивен (дата старта не наступила)")
        return
    
    data = get_user_data()
    if not data:
        logger.error("❌ Не удалось загрузить данные")
        return
    
    # Проверяем занималась ли сегодня
    if not did_study_today(data):
        message = format_shame_message(data)
        await send_to_channel(message)
        logger.info("💀 Сообщение стыда отправлено")
        
        # TODO: Обновить streak в Firebase (обнулить)
        # Это можно добавить позже если нужно
    else:
        logger.info("✅ Сегодня занималась, стыдить не нужно")

async def weekly_summary_task():
    """Еженедельные итоги в воскресенье 20:00"""
    logger.info("📈 Запуск задачи: еженедельные итоги")
    
    # Проверяем активен ли бот
    if not is_bot_active():
        logger.info("⏸ Бот неактивен (дата старта не наступила)")
        return
    
    data = get_user_data()
    if not data:
        logger.error("❌ Не удалось загрузить данные")
        return
    
    message = format_weekly_summary(data)
    await send_to_channel(message)
    logger.info("✅ Еженедельные итоги отправлены")

async def check_reset_task():
    """Проверка на сброс данных (каждый час)"""
    logger.info("🔄 Проверка на сброс данных")
    
    data = get_user_data()
    if not data:
        return
    
    # Проверяем есть ли свежий сброс (за последний час)
    reset_date = data.get('resetDate')
    if reset_date:
        try:
            reset_dt = datetime.fromisoformat(reset_date.replace('Z', '+00:00'))
            time_diff = datetime.now() - reset_dt.replace(tzinfo=None)
            
            # Если сброс был меньше часа назад
            if time_diff.total_seconds() < 3600:
                message = format_reset_message(data)
                await send_to_channel(message)
                logger.info("✅ Сообщение о сбросе отправлено")
        except:
            pass

# ==================== ИНИЦИАЛИЗАЦИЯ ====================

async def init_bot():
    """Инициализация бота"""
    global bot, scheduler
    
    logger.info("🤖 Инициализация бота...")
    
    # Инициализация Telegram бота
    bot = Bot(token=BOT_TOKEN)
    
    # Проверка подключения
    try:
        bot_info = await bot.get_me()
        logger.info(f"✅ Бот подключен: @{bot_info.username}")
    except Exception as e:
        logger.error(f"❌ Ошибка подключения бота: {e}")
        return False
    
    # Инициализация Firebase
    if not init_firebase():
        logger.error("❌ Не удалось инициализировать Firebase")
        return False
    
    # Инициализация планировщика
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    
    # Добавляем задачи
    hour, minute = DAILY_REPORT_TIME.split(':')
    scheduler.add_job(
        daily_report_task,
        trigger=CronTrigger(hour=int(hour), minute=int(minute)),
        id='daily_report',
        name='Ежедневный отчёт'
    )
    
    hour, minute = SHAME_CHECK_TIME.split(':')
    scheduler.add_job(
        shame_check_task,
        trigger=CronTrigger(hour=int(hour), minute=int(minute)),
        id='shame_check',
        name='Проверка на лоханье'
    )
    
    hour, minute = WEEKLY_SUMMARY_TIME.split(':')
    scheduler.add_job(
        weekly_summary_task,
        trigger=CronTrigger(day_of_week='sun', hour=int(hour), minute=int(minute)),
        id='weekly_summary',
        name='Еженедельные итоги'
    )
    
    # Проверка на сброс каждый час
    scheduler.add_job(
        check_reset_task,
        trigger=CronTrigger(minute=0),
        id='reset_check',
        name='Проверка на сброс'
    )
    
    scheduler.start()
    logger.info("✅ Планировщик запущен")
    logger.info(f"📅 Расписание:")
    logger.info(f"  • Ежедневный отчёт: {DAILY_REPORT_TIME}")
    logger.info(f"  • Проверка на лоханье: {SHAME_CHECK_TIME}")
    logger.info(f"  • Еженедельные итоги: воскресенье {WEEKLY_SUMMARY_TIME}")
    logger.info(f"  • Проверка на сброс: каждый час")
    
    return True

# ==================== ОСНОВНОЙ ЦИКЛ ====================

async def main():
    """Главная функция"""
    logger.info("=" * 50)
    logger.info("🚀 Запуск Goal Tracker Bot")
    logger.info("=" * 50)
    
    # Инициализация
    if not await init_bot():
        logger.error("❌ Ошибка инициализации, выход")
        return
        # Инициализация Firebase
    logger.info("🔥 Инициализация Firebase...")
    if not init_firebase():
        logger.error("❌ Не удалось инициализировать Firebase, выход")
        return
    logger.info("✅ Firebase готов к работе")
    
    # Тестовое сообщение
    logger.info("📤 Отправка тестового сообщения...")
    test_message = """🤖 Goal Tracker Bot запущен!

Бот готов к работе и будет следить за вашим прогрессом.

Расписание:
• 21:00 - Ежедневный отчёт (если занимались)
• 23:00 - Проверка (если не занимались)
• Воскресенье 20:00 - Итоги недели

Удачи в обучении! 💪"""
    
    await send_to_channel(test_message)
    
    logger.info("✅ Бот работает, ожидание задач по расписанию...")
    logger.info("Press Ctrl+C to stop")
    
    # Бесконечный цикл
    try:
        while True:
            await asyncio.sleep(60)  # Проверка каждую минуту
    except KeyboardInterrupt:
        logger.info("⏹ Получен сигнал остановки")
    finally:
        if scheduler:
            scheduler.shutdown()
        logger.info("👋 Бот остановлен")

if __name__ == "__main__":
    asyncio.run(main())
    
