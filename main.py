import time
import copy
import asyncio
import config

from aiogram import Bot, Dispatcher, executor, types
from aiogram.utils.executor import start_webhook
from aiogram.dispatcher.filters import Text
from loguru import logger

from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

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

statistics_file = 'statistics_data.pickle'
statistics = {
    'sent_posts': 0
}


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
    for channel, value in links.items():
        if value['owner_id'] == msg.from_user.id:
            but = [channel]
            keyboard.add(*but)
    but = [buttons.menu]
    keyboard.add(*but)

    return keyboard


def get_vk_groups_keyboard(channel):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for group, status in links[channel]['links'].items():
        but = [group]
        keyboard.add(*but)
    but = [buttons.menu]
    keyboard.add(*but)

    return keyboard


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
    global links
    global links_file
    global statistics
    global statistics_file

    # d = dict()
    links = check_data(links, links_file)
    statistics = check_data(statistics, statistics_file)
    
    while True:
        logger.info('NEW ITERATION')
        links = read_data(links_file)
        links_copy = copy.deepcopy(links)

        count_sent_post = await start_script(bot, links_copy)

        if links.keys() != links_copy.keys():
            for key in links.keys():
                if not key in links_copy.keys():
                    links_copy[key] = 0

        write_data(links_copy, links_file)
        prepare_temp_folder()

        statistics['sent_posts'] += count_sent_post
        write_data(statistics, statistics_file)

        await asyncio.sleep(6*60)
        # await asyncio.sleep(10)


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
        'links: ' + str(list(map(lambda x: 'vk.com/' + x, list(dict_item['links'].keys()))))
    )

    return text


async def show(msg: types.Message, state: FSMContext):
    text = 'Ваши каналы и группы:\n'
    for k, v in links.items():
        if v['owner_id'] == msg.from_user.id:
            text = text + '@' + str(k) + '\n' + beautiful_display(v) + '\n\n'

    await msg.answer(text)


async def show_all(msg: types.Message, state: FSMContext):
    print(msg)

    statistics_text = 'Отправлено постов: ' + str(statistics['sent_posts'])

    text = ''
    for k, v in links.items():
        text = text + '@' + str(k) + '\n' + beautiful_display(v) + '\n\n'

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
    global links
    global links_file

    links = read_data(links_file)

    user_username, err = get_user_usernames(msg)
    if err:
        await msg.answer(messages.not_public_user_username)
        return

    channel_username, err = get_channel_usernames(msg)
    if err:
        await msg.answer(messages.not_public_channel_username)
        return

    if not channel_username in links:
        links[channel_username] = {
            'status': True,
            'owner_username': user_username,
            'owner_id': msg.from_user.id,
            'links': {}
        }

        await bot.send_message(config.MY_ID, '@' + user_username + ' @' + channel_username)
        # await msg.answer('Ожидайте верификации', reply_markup=types.ReplyKeyboardRemove())
        await msg.answer(messages.tg_added, reply_markup=get_general_keyboard())
        await state.finish()

        write_data(links, links_file)
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
    if msg.text not in links:
        await msg.answer(messages.channel_does_not_exist)
        return

    await state.update_data(current_channel=msg.text)
    await msg.answer(messages.vk_link, reply_markup=get_menu())
    await state.set_state(RegisterActions.waiting_for_add_vk_group.state)


async def add_vk_group(msg: types.Message, state: FSMContext):
    print(msg)
    global links
    global links_file

    links = read_data(links_file)

    user_data = await state.get_data()
    # link = msg.get_args().split('/')[-1]

    if not 'current_channel' in user_data:
        await msg.answer('У вас нет привязанного канала', reply_markup=get_general_keyboard())
        await state.finish()
        return

    channel_username = user_data['current_channel']

    link = msg.text.split('/')[-1]

    if links[channel_username]['status'] == False:
        await msg.answer('Канал еще не верифицирован', reply_markup=get_general_keyboard())
        return

    if link in links[channel_username]['links']:
        await msg.answer(messages.group_already_added)
    else:
        links[channel_username]['links'][link] = 0
        await msg.answer(messages.group_added, reply_markup=get_general_keyboard())
        await state.finish()

    write_data(links, links_file)


async def del_tg_channel(msg: types.Message, state: FSMContext):
    print(msg)
    
    # if msg.from_user.id != config.MY_ID:
    #     await msg.answer('У вас нет прав на это действие')
    #     return

    global links
    global links_file

    if not msg.text in links:
        await msg.answer(messages.channel_does_not_exist)
        return

    links = read_data(links_file)
    
    # link = msg.get_args().split('/')[-1]
    link = msg.text

    if link in links:
        del links[link]
        await msg.answer(messages.channel_removed, reply_markup=get_general_keyboard())
        await state.finish()
    else:
        await msg.answer(messages.channel_does_not_exist)

    write_data(links, links_file)


async def del_vk_button(msg: types.Message, state: FSMContext):
    if not msg.text in links:
        await msg.answer(messages.channel_does_not_exist)
        return

    await state.update_data(current_channel=msg.text)

    keyboard = get_vk_groups_keyboard(msg.text)
    await msg.answer(messages.select_group, reply_markup=keyboard)
    await state.set_state(RegisterActions.waiting_for_select_vk.state)


async def del_vk_group(msg: types.Message, state: FSMContext):
    print(msg)
    global links
    global links_file

    links = read_data(links_file)

    # link = msg.get_args().split('/')[-1]
    user_data = await state.get_data()
    
    # for k, v in links.items():
    #     if v['owner_id'] == msg.from_user.id:
    #         channel_username = k
    
    if not 'current_channel' in user_data:
        await msg.answer('У вас нет привязанного канала', reply_markup=get_general_keyboard())
        await state.finish()
        return
    
    channel_username = user_data['current_channel'] 

    if links[channel_username]['status'] == False:
        await msg.answer('Канал еще не верифицирован', reply_markup=get_general_keyboard())
        await state.finish()
        return

    if msg.text in links[channel_username]['links']:
        del links[channel_username]['links'][msg.text]
        await msg.answer(messages.group_removed, reply_markup=get_general_keyboard())
        await state.finish()
    else:
        await msg.answer(messages.group_does_not_exist)

    write_data(links, links_file)


async def choosing_base_action(msg: types.Message, state: FSMContext):
    if msg.text == buttons.add_vk:
        keyboard = get_tg_channels_keyboard(msg)

        await msg.answer(messages.select_tg_for_add_vk, reply_markup=keyboard)
        await state.set_state(RegisterActions.waiting_for_select_tg_for_add_vk.state)

    elif msg.text == buttons.del_vk:
        keyboard = get_tg_channels_keyboard(msg)

        await msg.answer(messages.select_tg_for_delete_vk, reply_markup=keyboard)
        await state.set_state(RegisterActions.waiting_for_select_tg_for_delete_vk.state)

    elif msg.text == buttons.add_tg:
        await msg.answer(messages.forward_msg_from_channel, reply_markup=get_menu())
        await state.set_state(RegisterActions.waiting_for_forward_msg_from_channel.state)

    elif msg.text == buttons.del_tg:
        keyboard = get_tg_channels_keyboard(msg)

        await msg.answer(messages.select_tg_for_delete, reply_markup=keyboard)
        await state.set_state(RegisterActions.waiting_for_select_tg_for_delete.state)
    
    else:
        await msg.answer(messages.no_such_action, reply_markup=get_general_keyboard())


def create_bot_factory():
    dp = Dispatcher(bot, storage=MemoryStorage())

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
