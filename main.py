import time
import copy
import asyncio
import config

from aiogram import Bot, Dispatcher, executor
from aiogram.utils.executor import start_webhook
from loguru import logger

from start_script import start_script
from config import SINGLE_START, TIME_TO_SLEEP
from tools import prepare_temp_folder
from last_id import check_data, write_data, read_data
import messages

logger.add(
    "./logs/debug.log",
    format="{time} {level} {message}",
    level="DEBUG",
    rotation="1 week",
    compression="zip",
)

logger.info("Script is started.")

WEBHOOK_HOST = 'https://pmpu.site'
WEBHOOK_PATH = '/pmpu_news_bot/'
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

WEBAPP_HOST = '127.0.0.1'
WEBAPP_PORT = 7786

bot = Bot(config.TG_BOT_TOKEN)
links_file = 'links_data.pickle'
# links = dict()
# {
#     'pmpu_news': 0,
#     'sspmpu': 0
# }
links = {
    #'amcp_feed': {
    # 'nethub_test_channel': {
    #     'status': True,
    #     'owner_username': 'romanychev',
    #     'owner_id': 248603604,
    #     'links': {
    #         'sciapmath': 0, 'stipkomsspmpu': 0, 'club158734605': 0, 'sspmpu': 0, 'pmpu_news': 0
    #         }
    # }
}


async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)


async def on_shutdown(dp):
    await bot.delete_webhook()


@logger.catch
async def background_on_start():
    global bot
    global links
    global links_file

    # d = dict()
    links = check_data(links, links_file)

    while True:
        print('new iter')
        links = read_data(links_file)
        links_copy = copy.deepcopy(links)

        await start_script(bot, links_copy)

        if links.keys() != links_copy.keys():
            for key in links.keys():
                if not key in links_copy.keys():
                    links_copy[key] = 0

        write_data(links_copy, links_file)
        prepare_temp_folder()

        await asyncio.sleep(6*60)


async def on_bot_start_up(dp):
    #asyncio.create_task(on_startup())
    await on_startup(dp)
    #asyncio.create_task(background_on_start())
    asyncio.ensure_future(background_on_start())


async def start(msg):
    print(msg)
    await msg.answer(messages.start)


def get_usernames(msg, forward=False):
    user_username = msg.from_user.first_name
    if msg.from_user.username != None:
        user_username = msg.from_user.username

    if forward:
        if msg.forward_from_chat.username != None:
            channel_username = msg.forward_from_chat.username
        else:
            channel_username = ''
        return user_username, channel_username
    else:
        return user_username


async def forward_message(msg):
    print(msg)
    global links
    global links_file

    links = read_data(links_file)

    user_username, channel_username = get_usernames(msg, forward=True)

    if not channel_username in links:
        links[channel_username] = {
            'status': False,
            'owner_username': user_username,
            'owner_id': msg.from_user.id,
            'links': {}
        }

        await bot.send_message(config.MY_ID, '@' + user_username + ' @' + channel_username)
        await msg.answer('Ожидайте верификации')

        write_data(links, links_file)
    else:
        await msg.answer('Этот канал уже привязан')


async def add_tg_channel(msg):
    print(msg)
    if msg.from_user.id != config.MY_ID:
        await msg.answer('У вас нет прав на это действие')
        return

    global links
    global links_file

    links = read_data(links_file)

    link = msg.get_args().split('/')[-1]

    if link in links:
        if links[link]['status'] == False:
            links[link]['status'] = True
            await msg.answer('Канал верифицирован')
            await bot.send_message(links[link]['owner_id'], 'Канал прошел верификацию!\n\n Для добавления групп вк используйте команду (нужно использовать именно юзернейм группы, а не ссылку):\n/add_vk vk_group_username\n\n'+
                                    'Для удаления групп вк используйте команду:\n/del_vk vk_group_username')
            write_data(links, links_file)
        else:
            await msg.answer('Этот канал уже верифицирован')
    else:
        await msg.answer('Этого канала нет в системе')


async def add_vk_group(msg):
    print(msg)
    global links
    global links_file

    links = read_data(links_file)

    link = msg.get_args().split('/')[-1]

    channel_username = ''   
    for k, v in links.items():
        if v['owner_id'] == msg.from_user.id:
            channel_username = k
    
    if channel_username == '':
        await msg.answer('У вас нет привязанного канала. Отправьте команду /start для привязки')
        return

    if links[channel_username]['status'] == False:
        await msg.answer('Канал еще не верифицирован')
        return

    if link in links[channel_username]['links']:
        await msg.answer('Такая группа уже привязана')
    else:
        links[channel_username]['links'][link] = 0
        await msg.answer('Группа добавлена')

    write_data(links, links_file)


async def del_tg_channel(msg):
    print(msg)
    if msg.from_user.id != config.MY_ID:
        await msg.answer('У вас нет прав на это действие')
        return

    global links
    global links_file

    links = read_data(links_file)
    
    link = msg.get_args().split('/')[-1]

    if link in links:
        del links[link]
        await msg.answer('Канал удален')
    else:
        await msg.answer('Нет такого канала')

    write_data(links, links_file)


async def del_vk_group(msg):
    print(msg)
    global links
    global links_file

    links = read_data(links_file)

    link = msg.get_args().split('/')[-1]

    channel_username = ''   
    for k, v in links.items():
        if v['owner_id'] == msg.from_user.id:
            channel_username = k
    
    if channel_username == '':
        await msg.answer('У вас нет привязанного канала. Отправьте команду /start для привязки')
        return

    if links[channel_username]['status'] == False:
        await msg.answer('Канал еще не верифицирован')
        return

    if link in links[channel_username]['links']:
        del links[channel_username]['links'][link]
    else:
        await msg.answer('Такой группы нет в списке')

    write_data(links, links_file)


async def show_links(msg):
    print(msg)
    await msg.answer('Список групп:\n' + str(links))


def create_bot_factory():
    dp = Dispatcher(bot)

    dp.register_message_handler(
        start,
        commands='start'
    )

    dp.register_message_handler(forward_message, is_forwarded=True)

    dp.register_message_handler(
        add_tg_channel,
        commands='add_tg'
    )

    dp.register_message_handler(
        add_vk_group,
        commands='add_vk'
    )

    dp.register_message_handler(
        del_tg_channel,
        commands='del_tg'
    )

    dp.register_message_handler(
        del_vk_group,
        commands='del_vk'
    )

    dp.register_message_handler(
        show_links,
        commands='show'
    )

    #await dp.start_polling()
    #executor.start_polling(dp, skip_updates=True, on_startup=on_bot_start_up)
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_bot_start_up,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
    )


if __name__ == '__main__':
    # asyncio.run(create_bot_factory())
    create_bot_factory()
