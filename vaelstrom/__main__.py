import sys
import logging

from vaelstrom.install_manager import InstallManager
from vaelstrom.gui_qt import run_qt_app, ListenerRunnable

VALHEIM_DIR = None
# VALHEIM_DIR = Path("test_installation")

if len(sys.argv) > 1:
    # url protocol handler path
    # get url from first arg and use IPC to send it to main app, then exit
    ListenerRunnable.send(sys.argv[1])
    sys.exit()

# logger = logging.getLogger("vaelstrom")
# logger.setLevel(logging.DEBUG)
# fmt = logging.Formatter("[%(asctime)s] [%(levelname)8s] [%(name)s] %(message)s")
# fh = logging.FileHandler(filename="vaelstrom.log")
# sh = logging.StreamHandler(sys.stdout)
# fh.setFormatter(fmt)
# sh.setFormatter(fmt)
# logger.addHandler(fh)
# logger.addHandler(sh)
logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] [%(levelname)8s] [%(name)s] %(message)s",
    handlers=[
        logging.FileHandler(filename="vaelstrom.log"),
        logging.StreamHandler(sys.stdout),
    ],
)

man = InstallManager(VALHEIM_DIR)
exitcode = run_qt_app(man)
exit(exitcode)
