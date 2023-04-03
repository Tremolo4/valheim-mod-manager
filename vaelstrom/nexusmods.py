import httpx as rq
import asyncio
from typing import List
from pathlib import Path
import json
import logging

from vaelstrom import cfg

NEXUS_MODS_URL = "https://api.nexusmods.com/"
# TODO: don't cache the config like this?
NEXUS_MODS_GAME = cfg["NexusMods"]["GameName"]


def _rq(method: str, endpoint: str, **kwargs):
    kwargs.setdefault("headers", {})["apikey"] = cfg["NexusMods"]["APIKey"]
    p = Path(cfg["NexusMods"]["SaveAPIResultsFolder"]) / Path(endpoint)

    if cfg["NexusMods"].getboolean("UseAPICache"):
        if p.exists():
            with p.open("r") as f:
                return json.load(f)

    res = rq.request(method, NEXUS_MODS_URL + endpoint, **kwargs)

    if cfg["NexusMods"].getboolean("SaveAPIResults"):
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w") as f:
            json.dump(res.json(), f, indent=2)

    return res.json()


def mod_file_list(mod_id: int):
    url = f"v1/games/{NEXUS_MODS_GAME}/mods/{mod_id}/files.json"
    return _rq("GET", url)


def mod_info(mod_id: int):
    url = f"v1/games/{NEXUS_MODS_GAME}/mods/{mod_id}.json"
    return _rq("GET", url)


def mod_file_info(mod_id: int, file_id: int):
    url = f"v1/games/{NEXUS_MODS_GAME}/mods/{mod_id}/files/{file_id}.json"
    return _rq("GET", url)


def mod_dl_link(mod_id: int, file_id: int, key: str, expires: str):
    url = f"v1/games/{NEXUS_MODS_GAME}/mods/{mod_id}/files/{file_id}/download_link.json"
    params = {
        "key": key,
        "expires": expires,
    }
    return _rq("GET", url, params=params)


def get_download_page_url(mod_id: int, file_id: int):
    return f"https://www.nexusmods.com/{NEXUS_MODS_GAME}/mods/{mod_id}/?tab=files&file_id={file_id}&nmm=1"


def mod_file_info_newest(mod_id: int):
    res = mod_file_list(mod_id)
    if len(res["files"]) == 0:
        raise ValueError("mod has no files")
    newest = res["files"][-1]
    # TODO: is this needed? maybe we can rely on the last one being the newest one
    # TODO: need to check is_primary / category, e.g. for ImprovedBuildHud
    for file in res["files"]:
        if file["uploaded_timestamp"] > newest["uploaded_timestamp"]:
            newest = file
    return newest


async def mod_file_info_newest_multiple(mod_ids: List[int]):
    async with rq.AsyncClient() as session:
        ress = await asyncio.gather(
            *[mod_file_info_newest_async(session, mod_id) for mod_id in mod_ids]
        )
    return ress


async def mod_file_info_newest_async(session, mod_id: int):
    url = f"v1/games/{NEXUS_MODS_GAME}/mods/{mod_id}/files.json"
    res = await session.get(
        NEXUS_MODS_URL + url, headers={"apikey": cfg["NexusMods"]["APIKey"]}
    )
    res = res.json()
    if len(res["files"]) == 0:
        raise ValueError("mod has no files")
    newest = res["files"][-1]
    # TODO: is this needed? maybe we can rely on the last one being the newest one
    # TODO: need to check is_primary / category, e.g. for ImprovedBuildHud
    for file in res["files"]:
        if file["uploaded_timestamp"] > newest["uploaded_timestamp"]:
            newest = file
    return newest
