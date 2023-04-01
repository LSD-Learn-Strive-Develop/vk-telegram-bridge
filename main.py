import time
import copy
import asyncio
import config

import pymongo
from pymongo import MongoClient

from aiogram import Bot, Dispatcher, executor, types
from aiogram.utils.executor import start_webhook
from aiogram.dispatcher.filters import Text

from aiogram.contrib.fsm_storage.mongo import MongoStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from loguru import logger

from start_script import start_script
from config import SINGLE_START, TIME_TO_SLEEP
from tools import prepare_temp_folder
from last_id import check_data, write_data, read_data
import messages
import buttons

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

client = MongoClient('localhost', 27017)
db = client[config.MONGO_DB_NAME]

bot = Bot(config.TG_BOT_TOKEN)


def get_general_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    row1 = [buttons.add_vk, buttons.add_tg]
    row2 = [buttons.del_vk, buttons.del_tg]
    row3 = [buttons.show]
    keyboard.add(*row1).add(*row2).add(*row3)

    return keyboard


def get_menu():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    row = [buttons.menu]
    keyboard.add(*row)

    return keyboard


def get_tg_channels_keyboard(msg):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for obj in db.links.find():
        if obj['owner_id'] == msg.from_user.id:
            but = [obj['channel_username']]
            keyboard.add(*but)
    but = [buttons.menu]
    keyboard.add(*but)

    return keyboard


def get_vk_groups_keyboard(channel):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for obj in db.links.find_one({'channel_username': channel})['links']:
        but = [obj['username']]
        keyboard.add(*but)
    but = [buttons.menu]
    keyboard.add(*but)

    return keyboard


def get_count_user_tg(msg):
    return db.links.count_documents({'owner_id': msg.from_user.id})


def get_count_user_vk(channel_username):
    return len(db.links.find_one({'channel_username': channel_username})['links'])


class RegisterActions(StatesGroup):
    waiting_for_forward_msg_from_channel = State()
    waiting_verification = State()
    
    waiting_for_select_tg_for_add_vk = State()
    waiting_for_add_vk_group = State()

    waiting_for_select_tg_for_delete = State()

    waiting_for_select_tg_for_delete_vk = State()
    waiting_for_select_vk = State()


async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)


async def on_shutdown(dp):
    await bot.delete_webhook()


@logger.catch
async def background_on_start():
    logger.info('background_on_start')
    global bot
    
    while True:
        logger.info('NEW ITERATION')

        count_sent_post = await start_script(bot, db)

        prepare_temp_folder()

        sent_posts = db.statistics.find_one()['sent_posts']
        db.statistics.update_one(
            {'sent_posts': sent_posts}, {'$set': {'sent_posts': sent_posts + count_sent_post}}
        )

        await asyncio.sleep(6*60)


async def on_bot_start_up(dp):
    #asyncio.create_task(on_startup())
    await on_startup(dp)
    #asyncio.create_task(background_on_start())
    asyncio.ensure_future(background_on_start())


async def start(msg: types.Message, state: FSMContext):
    print(msg)

    await msg.answer(messages.start, reply_markup=get_general_keyboard())
    await state.finish()


def beautiful_display(dict_item):
    text = (
        'status: ' + str(dict_item['status']) + '\n' +
        'owner_username: @' + str(dict_item['owner_username']) + '\n' +
        'owner_id: ' + str(dict_item['owner_id']) + '\n' +
        'links: ' + str(list(map(lambda x: 'vk.com/' + x['username'], dict_item['links'])))
    )

    return text


async def show(msg: types.Message, state: FSMContext):
    text = 'Ваши каналы и группы:\n'
    for obj in db.links.find():
        if obj['owner_id'] == msg.from_user.id:
            text = text + '@' + str(obj['channel_username']) + '\n' + beautiful_display(obj) + '\n\n'

    await msg.answer(text)


async def show_all(msg: types.Message, state: FSMContext):
    print(msg)

    statistics_text = 'Отправлено постов: ' + str(db.statistics.find_one()['sent_posts'])

    text = ''
    for obj in db.links.find():
        text = text + '@' + str(obj['channel_username']) + '\n' + beautiful_display(obj) + '\n\n'

    await msg.answer(statistics_text + '\n\nСписок групп:\n' + text)


async def go_to_menu(msg: types.Message, state: FSMContext):

    await msg.answer(messages.select_action, reply_markup=get_general_keyboard())
    await state.finish()


def get_user_usernames(msg):
    if msg.from_user.username:
        return msg.from_user.username, False
    else:
        return msg.from_user.first_name, True


def get_channel_usernames(msg):
    if msg.forward_from_chat.username:
        return msg.forward_from_chat.username, False
    else:
        return msg.forward_from_chat.title, True


async def forward_message(msg: types.Message, state: FSMContext):
    print(msg)
    user_username, err = get_user_usernames(msg)
    if err:
        await msg.answer(messages.not_public_user_username)
        return

    channel_username, err = get_channel_usernames(msg)
    if err:
        await msg.answer(messages.not_public_channel_username)
        return

    if not db.links.find_one({'channel_username': channel_username}):
        db.links.insert_one({
            'channel_username': channel_username,
            'status': True,
            'owner_username': user_username,
            'owner_id': msg.from_user.id,
            'links': []
        })

        await bot.send_message(config.MY_ID, '@' + user_username + ' @' + channel_username)
        # await msg.answer('Ожидайте верификации', reply_markup=types.ReplyKeyboardRemove())
        await msg.answer(messages.tg_added, reply_markup=get_general_keyboard())
        await state.finish()

    else:
        await msg.answer(messages.channel_already_added, reply_markup=get_general_keyboard())


# async def add_tg_channel(msg: types.Message, state: FSMContext):
#     logger.info('add_tg_channel')
#     print(msg)
#     if msg.from_user.id != config.MY_ID:
#         await msg.answer('У вас нет прав на это действие')
#         return

#     global links
#     global links_file

#     links = read_data(links_file)

#     link = msg.get_args().split('/')[-1]

#     if link in links:
#         if links[link]['status'] == False:
#             links[link]['status'] = True
#             await msg.answer('Канал верифицирован')
#             await bot.send_message(links[link]['owner_id'], 'Канал прошел верификацию! Вернитесь в главное меню и добавьте группы ВК', reply_markup=get_general_keyboard())
#             write_data(links, links_file)
#         else:
#             await msg.answer('Этот канал уже верифицирован')
#     else:
#         await msg.answer('Этого канала нет в системе')


async def select_tg_for_add_vk(msg: types.Message, state: FSMContext):
    if not db.links.find_one({'channel_username': msg.text}):
        await msg.answer(messages.channel_does_not_exist)
        return

    if get_count_user_vk(msg.text) > 10:
        await msg.answer(messages.limit_vk, reply_markup=get_general_keyboard())
        await state.finish()
        return

    await state.update_data(current_channel=msg.text)
    await msg.answer(messages.vk_link, reply_markup=get_menu())
    await state.set_state(RegisterActions.waiting_for_add_vk_group.state)


async def add_vk_group(msg: types.Message, state: FSMContext):
    print(msg)
    user_data = await state.get_data()

    if not 'current_channel' in user_data:
        await msg.answer('У вас нет привязанного канала', reply_markup=get_general_keyboard())
        await state.finish()
        return

    channel_username = user_data['current_channel']

    link = msg.text.split('/')[-1]

    channel = db.links.find_one({'channel_username': channel_username})
    print(channel['status'])
    if channel and channel['status'] == False:
        await msg.answer('Канал еще не верифицирован', reply_markup=get_general_keyboard())
        return

    groups_usernames = list(map(lambda x: x['username'], channel['links']))
    if link in groups_usernames:
        await msg.answer(messages.group_already_added)
    else:
        db.links.update_one(
            {'channel_username': channel_username}, {'$push': {'links': {'username': link, 'last_id': 0}}}
        )
        await msg.answer(messages.group_added, reply_markup=get_general_keyboard())
        await state.finish()


async def del_tg_channel(msg: types.Message, state: FSMContext):
    print(msg)
    
    # if msg.from_user.id != config.MY_ID:
    #     await msg.answer('У вас нет прав на это действие')
    #     return

    if not db.links.find_one({'channel_username': msg.text}):
        await msg.answer(messages.channel_does_not_exist)
        return

    link = msg.text

    db.links.delete_one({'channel_username': msg.text})
    await msg.answer(messages.channel_removed, reply_markup=get_general_keyboard())
    await state.finish()


async def del_vk_button(msg: types.Message, state: FSMContext):
    if not db.links.find_one({'channel_username': msg.text}):
        await msg.answer(messages.channel_does_not_exist)
        return

    await state.update_data(current_channel=msg.text)

    keyboard = get_vk_groups_keyboard(msg.text)
    await msg.answer(messages.select_group, reply_markup=keyboard)
    await state.set_state(RegisterActions.waiting_for_select_vk.state)


async def del_vk_group(msg: types.Message, state: FSMContext):
    print(msg)
    user_data = await state.get_data()
    
    if not 'current_channel' in user_data:
        await msg.answer('У вас нет привязанного канала', reply_markup=get_general_keyboard())
        await state.finish()
        return
    
    channel_username = user_data['current_channel'] 

    obj = db.links.find_one({'channel_username': channel_username})
    if obj['status'] == False:
        await msg.answer('Канал еще не верифицирован', reply_markup=get_general_keyboard())
        await state.finish()
        return

    groups_obj = list(filter(lambda x: x['username'] != msg.text, obj['links']))
    if len(groups_obj) != len(obj['links']):
        db.links.update_one(
            {'channel_username': channel_username}, {'$set': {'links': groups_obj}}
        )
        await msg.answer(messages.group_removed, reply_markup=get_general_keyboard())
        await state.finish()
    else:
        await msg.answer(messages.group_does_not_exist)


async def choosing_base_action(msg: types.Message, state: FSMContext):
    user_username, err = get_user_usernames(msg)
    await bot.send_message(config.MY_ID, '@' + user_username + ' ' + str(msg.from_user.id) + '\n' + msg.text)

    if msg.text == buttons.add_vk:
        keyboard = get_tg_channels_keyboard(msg)

        await msg.answer(messages.select_tg_for_add_vk, reply_markup=keyboard)
        await state.set_state(RegisterActions.waiting_for_select_tg_for_add_vk.state)

    elif msg.text == buttons.del_vk:
        keyboard = get_tg_channels_keyboard(msg)

        await msg.answer(messages.select_tg_for_delete_vk, reply_markup=keyboard)
        await state.set_state(RegisterActions.waiting_for_select_tg_for_delete_vk.state)

    elif msg.text == buttons.add_tg:
        if get_count_user_tg(msg) > 5:
            await msg.answer(messages.limit_tg, reply_markup=get_general_keyboard())
            return

        await msg.answer(messages.forward_msg_from_channel, reply_markup=get_menu())
        await state.set_state(RegisterActions.waiting_for_forward_msg_from_channel.state)

    elif msg.text == buttons.del_tg:
        keyboard = get_tg_channels_keyboard(msg)

        await msg.answer(messages.select_tg_for_delete, reply_markup=keyboard)
        await state.set_state(RegisterActions.waiting_for_select_tg_for_delete.state)
    
    else:
        await msg.answer(messages.no_such_action, reply_markup=get_general_keyboard())


def create_bot_factory():
    # dp = Dispatcher(bot, storage=MemoryStorage())
    storage = MongoStorage(host='localhost', port=27017, db_name='aiogram_fsm')
    dp = Dispatcher(bot, storage=storage)

    dp.register_message_handler(
        start,
        commands='start',
        state='*'
    )
    
    dp.register_message_handler(
        show_all,
        commands='show_all',
        state='*'
    )

    dp.register_message_handler(
        show,
        Text(equals=buttons.show, ignore_case=True),
        state='*'
    )

    dp.register_message_handler(
        go_to_menu,
        Text(equals=buttons.menu, ignore_case=True), 
        state='*'
    )

    # Добавление ТГ канала
    dp.register_message_handler(
        forward_message, 
        is_forwarded=True, 
        state=RegisterActions.waiting_for_forward_msg_from_channel
    )

    # dp.register_message_handler(
    #     add_tg_channel,
    #     commands='add_tg',
    #     state='*'
    # )

    # Добавиление ВК группы
    dp.register_message_handler(
        select_tg_for_add_vk,
        state=RegisterActions.waiting_for_select_tg_for_add_vk
    )

    dp.register_message_handler(
        add_vk_group,
        state=RegisterActions.waiting_for_add_vk_group
    )

    # Удаление ТГ канала
    dp.register_message_handler(
        del_tg_channel,
        state=RegisterActions.waiting_for_select_tg_for_delete
    )

    # Удаление ВК группы
    dp.register_message_handler(
        del_vk_button,
        state=RegisterActions.waiting_for_select_tg_for_delete_vk
    )

    dp.register_message_handler(
        del_vk_group,
        state=RegisterActions.waiting_for_select_vk
    )

    dp.register_message_handler(
        choosing_base_action, 
        state='*'
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