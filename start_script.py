from typing import Union

from loguru import logger
from aiogram import Bot, Dispatcher
from aiogram.utils import executor

import config
import asyncio
from api_requests import get_data_from_vk, get_group_name
from last_id import write_id, read_id
from parse_posts import parse_post
from send_posts import send_post
from tools import blacklist_check, whitelist_check, prepare_temp_folder


async def start_script(bot, links):
    count_sent_post = 0

    for channel_username in links.keys():
        if links[channel_username]['status'] == False:
            continue
        
        for vk_group_username, last_known_id in links[channel_username]['links'].items():
            # last_known_id = links[link]
            logger.info(f"Last known ID: {last_known_id}")

            items: Union[dict, None] = get_data_from_vk(
                config.VK_TOKEN,
                config.REQ_VERSION,
                vk_group_username,
                config.REQ_FILTER,
                config.REQ_COUNT,
            )
            if not items:
                continue

            if "is_pinned" in items[0]:
                items = items[1:]
            logger.info(f"Got a few posts with IDs: {items[-1]['id']} - {items[0]['id']}.")

            new_last_id: int = items[0]["id"]

            if new_last_id > last_known_id:
                if last_known_id != 0:
                    for item in items[::-1]:
                        item: dict
                        if item["id"] <= last_known_id:
                            continue
                        logger.info(f"Working with post with ID: {item['id']}.")
                        if blacklist_check(config.BLACKLIST, item["text"]):
                            continue
                        if whitelist_check(config.WHITELIST, item["text"]):
                            continue
                        if config.SKIP_ADS_POSTS and item["marked_as_ads"]:
                            logger.info("Post was skipped as an advertisement.")
                            continue
                        if config.SKIP_COPYRIGHTED_POST and "copyright" in item:
                            logger.info("Post was skipped as an copyrighted post.")
                            continue
                        if 'nopost' in item['text']:
                            continue

                        item_parts = {"post": item}
                        group_name = ""
                        if "copy_history" in item and not config.SKIP_REPOSTS:
                            item_parts["repost"] = item["copy_history"][0]
                            group_name = get_group_name(
                                config.VK_TOKEN,
                                config.REQ_VERSION,
                                abs(item_parts["repost"]["owner_id"]),
                            )
                            logger.info("Detected repost in the post.")

                        # for item_part in item_parts:
                        prepare_temp_folder()
                        # repost_exists: bool = True if len(item_parts) > 1 else False

                        logger.info(f"Starting parsing of the {'post'}")
                        parsed_post = parse_post(
                            item_parts['post'], False, 'post', group_name
                        )
                        if len(item_parts) > 1:
                            logger.info(f"Starting parsing of the {'repost'}")
                            parsed_repost = parse_post(
                                item_parts['repost'], True, 'repost', group_name
                            )

                            if len(parsed_post['text']) > 0:
                                parsed_post["text"] = parsed_post['text'] + '\n\n' + parsed_repost['text']
                            else:
                                parsed_post["text"] = parsed_repost['text']

                            parsed_post["photos"] = parsed_repost['photos']
                            parsed_post["docs"] = parsed_repost['docs']

                        vk_link = 'vk.com/wall' + str(item['owner_id']) + '_' + str(item['id'])
                        source = '<a href="' + vk_link + '">' + 'Источник' + '</a>'
                        print(source)
                        parsed_post["text"] = parsed_post["text"] + '\n\n' + source

                        logger.info(f"Starting sending of the post")
                        await send_post(
                            bot,
                            '@'+channel_username,
                            parsed_post["text"],
                            parsed_post["photos"],
                            parsed_post["docs"],
                        )
                        count_sent_post += 1
                        await asyncio.sleep(3)

                print('ids ', new_last_id, last_known_id)
                links[channel_username]['links'][vk_group_username] = new_last_id

            await asyncio.sleep(3)
    
    return count_sent_post
