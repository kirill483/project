import asyncio
import aio_pika
from aiogram import Bot, exceptions
from aiogram.types import Update
from .config import TELEGRAM_BOT_TOKEN

bot = Bot(token=TELEGRAM_BOT_TOKEN)

async def get_chat_id(username: str):
    try:
        user = await bot.get_chat(username)
        print(f"Найден chat_id {user.id} для {username}")
        return user.id
    except exceptions.TelegramBadRequest:
        print(f"{username} не найден через get_chat(). Проверяю getUpdates()...")

    try:
        updates = await bot.get_updates()
        for update in updates:
            if update.message and update.message.from_user.username == username.lstrip("@"):
                print(f" Найден chat_id {update.message.chat.id} через getUpdates()")
                return update.message.chat.id
    except Exception as e:
        print(f"Ошибка при получении getUpdates(): {e}")
    print(f"е удалось найти chat_id для {username}")
    return None


async def process_message(message: aio_pika.IncomingMessage):
    async with message.process():
        body = message.body.decode()
        print(f"Получено сообщение: {body}")
        try:
            user_id, telegram_username = body.split(",")
            text = f"Привет, {telegram_username}"
            chat_id = await get_chat_id(telegram_username)

            if chat_id:
                await bot.send_message(chat_id, text)
                print(f"Отправлено сообщение {telegram_username} (chat_id: {chat_id})")
            else:
                print(f"е удалось отправить сообщение {telegram_username}")

        except Exception as e:
            print(f"Ошибка: {e}")


async def main():
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()
    queue = await channel.declare_queue("telegram_queue")
    await queue.consume(process_message)
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
