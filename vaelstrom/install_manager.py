from enum import Enum, auto
from pathlib import Path
from dataclasses import dataclass
import json
import re
import shutil
from typing import List, Optional, Set, Tuple
import zipfile as zf
import tempfile
import httpx
from urllib.parse import ParseResult, parse_qsl, urlparse
import logging
import webbrowser
import asyncio

import marshmallow_dataclass as mmd

from vaelstrom import cfg
import vaelstrom.nexusmods as nm
import vaelstrom.thunderstore as ths
from vaelstrom.marshmallow_ext import BaseSchema, SetEncoder
from vaelstrom.find_plugin_info import find_plugin_info
from vaelstrom.util import (
    find_steam_install_path,
    pretty_date,
    thunderstore_date_to_ts,
    ts_to_text,
)


class ModType(Enum):
    Invalid = auto()
    NexusMod = auto()
    Thunderstore = auto()


@dataclass(frozen=True)
class ModKey:
    type: ModType
    nxm_id: int = 0
    ths_namespace: str = None  # type:ignore
    ths_name: str = None  # type:ignore

    def __repr__(self):
        if self.type == ModType.NexusMod:
            return f"nxm-{self.nxm_id}"
        if self.type == ModType.Thunderstore:
            return f"ths-{self.ths_namespace}-{self.ths_name}"

    def __hash__(self):
        return hash(repr(self))


ths_namespace, _, ths_name = cfg["Thunderstore"]["BepInEx_Package"].partition("/")
KEY_BEPINEX_PACK = ModKey(
    ModType.Thunderstore, ths_namespace=ths_namespace, ths_name=ths_name
)


@dataclass
class ThunderstoreModInstallState:
    namespace: str
    name: str


@dataclass
class NexusModInstallState:
    nxm_id: int


@dataclass
class ModInstallState:
    title: str
    version: str
    ts: int
    files: Set[Path]
    nxm_state: Optional[NexusModInstallState] = None
    ths_state: Optional[ThunderstoreModInstallState] = None
    _version: int = 1

    @property
    def mod_type(self):
        if self.nxm_state is not None:
            return ModType.NexusMod
        if self.ths_state is not None:
            return ModType.Thunderstore
        return ModType.Invalid

    def mod_key(self) -> ModKey:
        if self.nxm_state is not None:
            return ModKey(ModType.NexusMod, nxm_id=self.nxm_state.nxm_id)
        if self.ths_state is not None:
            return ModKey(
                ModType.Thunderstore,
                ths_namespace=self.ths_state.namespace,
                ths_name=self.ths_state.name,
            )
        raise ValueError("Invalid mod state")


@dataclass
class InstallState:
    app_version: Tuple[int, int, int]


state_schema = mmd.class_schema(InstallState, base_schema=BaseSchema)()
mod_state_schema = mmd.class_schema(ModInstallState, base_schema=BaseSchema)()


@dataclass
class ModItem:
    state: ModInstallState
    disabled: bool
    available_ts: Optional[int] = None
    available_version: Optional[str] = None

    def set_available_version(self, ts: int, version: str):
        self.available_ts = ts
        self.available_version = version


class InstallManager:
    def __init__(self, game_directory: Optional[Path]):
        if game_directory:
            self.dir = game_directory
        elif dir := find_steam_install_path(cfg["General"]["Steam_AppId"]):
            self.dir = dir
        else:
            raise RuntimeError("Could not find the game installation directory")
        # we are not currently using this state at all
        # self.state = self._load_state()
        self.state = {}
        self.installed_mods: List[ModItem] = []

    def find_installed_mods(self):
        logging.info("Loading installed mods")
        for disabled in (False, True):
            self._find_installed_mods_in_folder(self._get_basedir(disabled), disabled)

    def _get_basedir(self, disabled: bool):
        if disabled:
            return self.dir / "BepInEx_vaelstrom_disabled"
        else:
            return self.dir / "BepInEx"

    def _find_installed_mods_in_folder(self, basedir: Path, disabled: bool):
        for file in basedir.rglob("vaelstrom_manifest.json"):
            with file.open("r") as f:
                read_json = json.load(f)
            state: ModInstallState = mod_state_schema.load(read_json)  # type: ignore
            # add manifest file so that it will also be deleted when uninstalling this mod
            state.files.add(file.relative_to(self.dir))
            item = ModItem(state, disabled)
            # bepinex pack shall be at the top
            if state.mod_key() == KEY_BEPINEX_PACK:
                self.installed_mods.insert(0, item)
            else:
                self.installed_mods.append(item)

    def handle_url(self, url_str: str):
        logging.debug(f"Received URL: {url_str}")
        url = urlparse(url_str)
        if url.scheme == "nxm":
            self._handle_url_nexus(url)
        elif url.scheme == "ror2mm":
            self._handle_url_thunderstore(url)
        else:
            raise ValueError("received unsupported url")

    def _handle_url_nexus(self, url: ParseResult):
        if url.netloc != cfg["NexusMods"]["GameName"]:
            raise ValueError(f'Not a {cfg["NexusMods"]["GameName"]} mod')
        qs = dict(parse_qsl(url.query))
        if "key" not in qs or "expires" not in qs:
            raise ValueError("missing `key` or `expires` param from received url")
        m = re.match(r"/mods/(\d+)/files/(\d+)", url.path)
        if m is None:
            raise ValueError("could not find mod_id and file_id in received url")
        # notification(f"Downloading new mod")
        mod_id = int(m.group(1))
        file_id = int(m.group(2))
        res = nm.mod_dl_link(mod_id, file_id, qs["key"], qs["expires"])
        dl_link = res[0]["URI"]
        key = ModKey(ModType.NexusMod, nxm_id=mod_id)
        is_update = False
        for info in self.installed_mods:
            if info.state.mod_key() == key:
                is_update = True
                # TODO: only uninstall after download succeeded
                logging.debug("Mod already installed, uninstalling old version first")
                self.uninstall_mod(key, info)
                break
        mod_item = self._download_and_install(key, dl_link, file_id)
        if is_update:
            logging.info(f"Updated {mod_item.state.title}")
        else:
            logging.info(f"Installed {mod_item.state.title}")

    def _handle_url_thunderstore(self, url: ParseResult):
        # ror2mm://v1/install/valheim.thunderstore.io/denikson/BepInExPack_Valheim/5.4.1001/
        parts = url.path.strip("/").split("/")
        if (
            url.netloc != "v1"
            or len(parts) != 5
            or parts[0] != "install"
            or parts[1] != cfg["Thunderstore"]["GameName"] + ".thunderstore.io"
        ):
            return ValueError("Unsupported Thunderstore URL format")
        namespace, name, version = parts[2:5]
        key = ModKey(ModType.Thunderstore, ths_namespace=namespace, ths_name=name)
        self._do_install_thunderstore(key, version)

    def update_mod(self, mod_item: ModItem, force=False):
        """opens download page for newest version of mod in web browser (nexusmods)
        or directly updates (thunderstore)."""
        key = mod_item.state.mod_key()
        if key.type == ModType.NexusMod:
            res = nm.mod_file_info_newest(key.nxm_id)
            mod_item.set_available_version(res["uploaded_timestamp"], res["version"])
            if not force and mod_item.available_ts <= mod_item.state.ts:
                logging.info(
                    f"Not updating {mod_item.state.title}. Same or newer version already installed."
                )
            else:
                logging.info(
                    f"Opening Nexusmods download page for {mod_item.state.title}"
                )
                # TODO: make use of premium-only direct download api
                url = nm.get_download_page_url(key.nxm_id, res["file_id"])
                webbrowser.open(url)
        elif key.type == ModType.Thunderstore:
            self._do_install_thunderstore(key, force_update=force)

    def _do_install_thunderstore(
        self, key: ModKey, version: Optional[str] = None, force_update=False
    ):
        """download and install a mod from thunderstore.
        if version is None, use the latest version"""
        is_update = False
        res = ths.package_info(key.ths_namespace, key.ths_name, version)
        for item in self.installed_mods:
            if item.state.mod_key() == key:
                is_update = True
                item.set_available_version(
                    thunderstore_date_to_ts(res["latest"]["date_created"]),
                    res["latest"]["version_number"],
                )
                if not force_update and item.available_ts <= item.state.ts:
                    logging.info(
                        f"Not updating {item.state.title}. Same or newer version already installed."
                    )
                    return
                # TODO: only uninstall if download succeeded
                logging.debug("Mod already installed, uninstalling old version first")
                self.uninstall_mod(key, item)
                break
        if version is None:
            version = res["latest"]["version_number"]
            ts = thunderstore_date_to_ts(res["latest"]["date_created"])
        else:
            ts = thunderstore_date_to_ts(res["date_created"])
        dl_link = (
            f'https://{cfg["Thunderstore"]["GameName"]}.thunderstore.io/package/download/'
            f"{key.ths_namespace}/{key.ths_name}/{version}/"
        )
        mod_item = self._download_and_install(key, dl_link, ts)

        if is_update:
            logging.info(f"Updated {mod_item.state.title}")
        else:
            logging.info(f"Installed {mod_item.state.title}")

    def check_for_updates(self, mod_items: Optional[List[ModItem]] = None):
        if mod_items is None:
            logging.debug("Checking for updates on all installed mods")
            mod_items = self.installed_mods
        nxm_ids = []
        name_tuples = []
        for item in mod_items:
            if item.state.nxm_state is not None:
                nxm_ids.append(item.state.nxm_state.nxm_id)
            elif item.state.ths_state is not None:
                name_tuples.append(
                    (item.state.ths_state.namespace, item.state.ths_state.name)
                )
        ress_nxm, ress_ths = asyncio.run(
            self._updatecheck_helper_async(nxm_ids, name_tuples)
        )

        idx_nxm = 0
        idx_ths = 0
        for item in mod_items:
            if item.state.nxm_state is not None:
                res = ress_nxm[idx_nxm]
                item.set_available_version(res["uploaded_timestamp"], res["version"])
                idx_nxm += 1
            elif item.state.ths_state is not None:
                res = ress_ths[idx_ths]
                item.set_available_version(
                    thunderstore_date_to_ts(res["latest"]["date_created"]),
                    res["latest"]["version_number"],
                )
                idx_ths += 1

    async def _updatecheck_helper_async(
        self, nxm_ids: List[int], name_tuples: List[Tuple[str, str]]
    ):
        return await asyncio.gather(
            nm.mod_file_info_newest_multiple(nxm_ids),
            ths.package_info_multiple(name_tuples),
        )

    def _load_state(self) -> InstallState:
        file = self._get_state_file_path()
        logging.debug(f"Loading state from {str(file)}")
        try:
            with file.open("r") as f:
                read_json = json.load(f)
        except FileNotFoundError:
            logging.info(
                f"Could not find state file at {str(file)}. Initializing empty state"
            )
            return InstallState(app_version=(0, 0, 1))
        return state_schema.load(read_json)  # type: ignore

    def _save_state(self):
        file = self._get_state_file_path()
        logging.debug(f"Saving state to {str(file)}")
        state_dict = state_schema.dump(self.state)
        text = json.dumps(state_dict, cls=SetEncoder, indent=2)
        with self._get_state_file_path().open("w") as f:
            f.write(text)

    def _save_mod_state(self, key: ModKey, mod_state: ModInstallState):
        """Saves the given mod state into a manifest file inside the mod's installation folder. Returns path to the newly-created manifest file."""
        if key == KEY_BEPINEX_PACK:
            outdir = self.dir / Path("BepInEx/")
        else:
            outdir = self._get_mod_install_path(key)
        outfile = outdir / Path("vaelstrom_manifest.json")
        logging.debug(f"Saving mod state to {str(outfile)}")
        state_dict = mod_state_schema.dump(mod_state)
        text = json.dumps(state_dict, cls=SetEncoder, indent=2)
        with outfile.open("w") as f:
            f.write(text)
        return outfile

    def _get_state_file_path(self) -> Path:
        return self.dir / Path("vaelstrom_state.json")

    def uninstall_mod(self, key: ModKey, mod_item: ModItem):
        mod_install_path = self._get_mod_install_path(key)
        for rp in mod_item.state.files:
            p = self.dir / rp
            if p.is_file():
                p.unlink(missing_ok=True)
            else:
                try:
                    p.rmdir()
                except OSError:
                    # TODO: only ignore "directory not empty", not any type of OSError
                    pass

            # delete parents if empty
            rp = p.relative_to(mod_install_path)
            for dir in rp.parents:
                try:
                    (mod_install_path / dir).rmdir()
                except OSError:
                    # TODO: only ignore "directory not empty", not any type of OSError
                    pass
        self.installed_mods.remove(mod_item)

    def disable_mod(self, mod_item: ModItem):
        if mod_item.disabled:
            logging.error(f"Mod {mod_item.state.title} is already disabled.")
        else:
            self._enable_disable_helper(mod_item, True)
            mod_item.disabled = True

    def enable_mod(self, mod_item: ModItem):
        if not mod_item.disabled:
            logging.error(f"Mod {mod_item.state.title} is already enabled.")
        else:
            self._enable_disable_helper(mod_item, False)
            mod_item.disabled = False

    def _enable_disable_helper(self, mod_item: ModItem, disable: bool):
        # TODO: this is untested
        key = mod_item.state.mod_key()
        if key == KEY_BEPINEX_PACK:
            raise NotImplementedError("Dis-/enabling BepInEx Pack is not supported")
        # move folder
        mod_path_source = self._get_mod_install_path(key, not disable)
        mod_path_target = self._get_mod_install_path(key, disable)
        self._get_basedir(not disable).mkdir(parents=True, exist_ok=True)
        logging.debug(
            f"Moving folder: from {str(mod_path_source)} to {str(mod_path_target)}"
        )
        shutil.move(str(mod_path_source), mod_path_target)
        # adjust file paths in state json
        files = set()
        for p in mod_item.state.files:
            files.add(mod_path_target / p.relative_to(mod_path_source))
        mod_item.state.files = files
        self._save_mod_state(key, mod_item.state)

    def _download_and_install(
        self, key: ModKey, download_link: str, file_id_or_ts: int = 0
    ):
        tempdir = Path(tempfile.mkdtemp())
        url = urlparse(download_link)
        if url.scheme != "https":
            raise ValueError("download link does not use https")
        mod_zip = tempdir / Path(str(key) + ".zip")
        with httpx.stream("GET", download_link, follow_redirects=True) as r:
            r.raise_for_status()
            with mod_zip.open("wb") as f:
                for chunk in r.iter_bytes(chunk_size=8192):
                    f.write(chunk)
        if key.type == ModType.NexusMod:
            res = nm.mod_file_info(key.nxm_id, file_id_or_ts)
            ts = int(res["uploaded_timestamp"])
            version = res["version"]
            mod_state = ModInstallState(
                res["name"],
                version,
                ts,
                self._install_mod(mod_zip, key),
                nxm_state=NexusModInstallState(key.nxm_id),
            )
        elif key.type == ModType.Thunderstore:
            parts = url.path.strip("/").split("/")
            ts = file_id_or_ts
            version = parts[4]
            mod_state = ModInstallState(
                key.ths_name,
                version,
                ts,
                self._install_mod(mod_zip, key),
                ths_state=ThunderstoreModInstallState(key.ths_namespace, key.ths_name),
            )
        else:
            raise ValueError("Unsupported mod type")

        manifest = self._save_mod_state(key, mod_state)
        mod_state.files.add(manifest.relative_to(self.dir))
        # bepinex pack shall be at the top
        mod_item = ModItem(mod_state, False, ts, version)
        if mod_state.mod_key() == KEY_BEPINEX_PACK:
            self.installed_mods.insert(0, mod_item)
        else:
            self.installed_mods.append(mod_item)
        return mod_item

    def _get_mod_install_path(self, key: ModKey, disabled: bool = False):
        if key == KEY_BEPINEX_PACK:
            # special case: bepinex pack is installed into game root folder
            return self.dir
        elif key.type == ModType.NexusMod:
            folder = Path(f"nexusmod_{key.nxm_id}")
        elif key.type == ModType.Thunderstore:
            folder = Path(f"thunderstore_{key.ths_namespace}_{key.ths_name}")
        else:
            raise ValueError("unsupported mod type")

        return self._get_basedir(disabled) / "plugins" / folder

    def _install_mod(self, mod_zip: Path, key: ModKey) -> Set[Path]:
        files = set()

        if not zf.is_zipfile(mod_zip):
            raise ValueError("Not a zipfile:", str(mod_zip))

        # (if no dll, stop) (TODO)
        # if is bepinex pack, only extract BepInExPack_Valheim/ to game root
        # if BepInEx/plugins, only extract contents of that
        # if plugins/, only extract contents of that
        # TODO: support things that go into patchers/, scripts/, or config/
        # TODO: but take care of conflicts
        # else extract everything
        # always extract into mod-specific subfolder

        mod_install_path = self._get_mod_install_path(key)

        with zf.ZipFile(mod_zip) as myzip:
            prefix = None
            if key == KEY_BEPINEX_PACK:
                prefix = KEY_BEPINEX_PACK.ths_name
                # error = True
                # for name in myzip.namelist():
                #     if name.startswith(prefix):
                #         error = False
                #         break
            if not prefix:
                for name in myzip.namelist():
                    if name.startswith("BepInEx/plugins/"):
                        prefix = "BepInEx/plugins/"
                        break
            if not prefix:
                for name in myzip.namelist():
                    if name.startswith("plugins/"):
                        prefix = "plugins/"
                        break
            if prefix:
                for info in myzip.infolist():
                    if info.filename.startswith(prefix) and not info.filename == prefix:
                        info.filename = info.filename[len(prefix) :]
                        files.add(
                            Path(
                                myzip.extract(info, path=mod_install_path)
                            ).relative_to(self.dir)
                        )
            else:
                for info in myzip.infolist():
                    files.add(
                        Path(myzip.extract(info, path=mod_install_path)).relative_to(
                            self.dir
                        )
                    )

        if len(files) == 0:
            logging.error(
                "Extracted zero files when installing mod. "
                "The downloaded zip has an unexpected structure or is simply empty."
            )

        return files

    def _path_belongs_to_mod_install(self, path: Path):
        try:
            relpath = path.relative_to(self.dir)
        except ValueError:
            logging.debug(
                "path_belongs_to_mod_install: "
                "path in question is not even inside valheim directory: "
                f"{str(path)}"
            )
        else:
            for mod_info in self.installed_mods:
                for entry in mod_info.state.files:
                    # TODO: is there a better way? except is_relative_to from py 3.9
                    if str(entry).startswith(str(relpath)):
                        return True
        return False

    def discover_existing_mods(self) -> List[ModInstallState]:
        # TODO: this is WIP
        # TODO: move discovered mods directly to nexusmod_<id> folder
        # this makes updating & uninstalling easier because more consistent
        # also important: skip a mod if we can't reliably determine its nexus ID
        # (there is not much sense in listing a mod if we can't update it)

        discovered_mods = []
        for p in (self.dir / Path("BepInEx/plugins/")).iterdir():
            files = set()
            mod_id = None
            mod_name = None
            mod_version = None
            if p.is_file() and p.suffix == ".dll":
                logging.debug(f"Discovered dll: {str(p)}")
                if self._path_belongs_to_mod_install(p):
                    logging.debug(
                        "Discovered dll already belongs to mod install, skipping"
                    )
                elif dll_info := find_plugin_info(str(p)):
                    logging.debug(f"Discovered info in dll: {dll_info} in {str(p)}")
                    mod_name = dll_info["title"]
                    mod_version = dll_info["version"]
                    # files = {p.relative_to(self.dir)}
                    discovered_mods.append(
                        ModInstallState(
                            mod_name, mod_version, 0, {p.relative_to(self.dir)}
                        )
                    )
                else:
                    logging.debug("No info discovered in dll, skipping")

            # find dangling nexusmod_<id> folders
            # if p.is_dir():
            #     if self.path_belongs_to_mod_install(p):
            #         logging.debug(
            #             "Discovered folder already belongs to mod install, skipping"
            #         )
            #     elif m := re.match(r"nexusmod_(\d+)", p.name):
            #         mod_id = int(m.group(1))
            #         logging.debug(
            #             f"Discovered unknown folder 'nexusmod_{mod_id}'. "
            #             f"Assuming that this is a mod with id {mod_id}."
            #         )
            #         files = set(p.glob("**/*"))

            # if len(files) == 0:
            #     logging.debug("Discovered folder is actually empty, ignoring.")
            # else:
            #     mod_info = NexusMod(
            #         mod_id=mod_id,
            #         name=mod_name,
            #         installed_version=str_ver(mod_version),
            #         files=files,
            #     )

        # TODO: make persistent? create manifest.json or add to state.json?
        for mod in discovered_mods:
            self.installed_mods.append(mod)

        return discovered_mods
