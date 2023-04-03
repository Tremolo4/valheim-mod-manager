import asyncio
from typing import List, Optional, Tuple
import httpx as rq
from pathlib import Path
import json

from vaelstrom import cfg


THUNDERSTORE_URL = f'https://{cfg["Thunderstore"]["GameName"]}.thunderstore.io/api/'


def _rq(method: str, endpoint: str, **kwargs):
    p = Path(cfg["Thunderstore"]["SaveAPIResultsFolder"]) / Path(endpoint)
    if p.suffix != ".json":
        p = p.parent / (p.name + ".json")

    if cfg["Thunderstore"].getboolean("UseAPICache"):
        if p.exists():
            with p.open("r") as f:
                return json.load(f)

    res = rq.request(method, THUNDERSTORE_URL + endpoint, **kwargs)

    if cfg["Thunderstore"].getboolean("SaveAPIResults"):
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w") as f:
            json.dump(res.json(), f, indent=2)

    return res.json()


def package_info(namespace: str, name: str, version: Optional[str] = None):
    url = f"experimental/package/{namespace}/{name}/"
    if version is not None:
        url += f"{version}/"
    return _rq("GET", url)


async def package_info_async(session, namespace: str, name: str):
    url = f"experimental/package/{namespace}/{name}/"
    res = await session.get(THUNDERSTORE_URL + url)
    return res.json()


async def package_info_multiple(name_tuples: List[Tuple[str, str]]):
    async with rq.AsyncClient() as session:
        return await asyncio.gather(
            *[
                package_info_async(session, namespace, name)
                for (namespace, name) in name_tuples
            ]
        )
