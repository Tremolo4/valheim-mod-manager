# type: ignore

import time
import logging
from multiprocessing.connection import Listener
from multiprocessing.connection import Client
from typing import Optional, Callable

from PySide2.QtGui import QColor
from PySide2.QtCore import (
    QThreadPool,
    QObject,
    QSize,
    Qt,
    QAbstractTableModel,
    QSortFilterProxyModel,
    Slot,
    Signal,
    QModelIndex,
    QRunnable,
)
from PySide2.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QMenu,
    QAction,
    QFrame,
    QTableView,
)

from vaelstrom.install_manager import InstallManager
from vaelstrom.util import pretty_date, ts_to_text


class QHLine(QFrame):
    def __init__(self):
        super(QHLine, self).__init__()
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Sunken)


class QVLine(QFrame):
    def __init__(self):
        super(QVLine, self).__init__()
        self.setFrameShape(QFrame.VLine)
        self.setFrameShadow(QFrame.Sunken)


class ModTableModel(QAbstractTableModel):
    COL_NAME = 0
    COL_VERSION = 1
    COL_VERSION_AVAIL = 2
    COL_TS_INSTALLED = 3
    COL_TS_AVAIL = 4
    COL_MAX = 5

    def __init__(self, man: InstallManager):
        super().__init__()
        self._man = man

    def get_mod_item(self, index: QModelIndex):
        return self._man.installed_mods[index.row()]

    def data(self, index: QModelIndex, role):
        item = self.get_mod_item(index)
        if role == Qt.DisplayRole:
            if index.column() == __class__.COL_NAME:
                return item.state.title
            elif index.column() == __class__.COL_VERSION:
                return item.state.version
            elif index.column() == __class__.COL_TS_INSTALLED:
                return pretty_date(item.state.ts)
            elif index.column() == __class__.COL_VERSION_AVAIL:
                return item.available_version or "unknown"
            elif index.column() == __class__.COL_TS_AVAIL:
                return pretty_date(item.available_ts)
        elif role == Qt.ToolTipRole:
            if index.column() == __class__.COL_TS_INSTALLED:
                return ts_to_text(item.state.ts)
            elif index.column() == __class__.COL_TS_AVAIL:
                return ts_to_text(item.available_ts)
            elif index.column() in (__class__.COL_VERSION, __class__.COL_VERSION_AVAIL):
                if item.available_ts is not None:
                    if item.available_ts > item.state.ts:
                        return "Newer version available, consider updating."
                    elif item.available_ts < item.state.ts:
                        return (
                            "Your installed version is newer than what is available online."
                            " Forcing update with Vaelstrom will downgrade."
                        )
                    else:
                        return "You currently have the newest available version."
                else:
                    return "To find out whether a newer version is available, check for updates."
        elif role == Qt.BackgroundRole:
            factor = 0.5 if item.disabled else 1
            if item.available_ts is not None:
                if item.available_ts > item.state.ts:
                    return QColor.fromHsv(350, 102 * factor, 255 * factor)  # red
                elif item.available_ts < item.state.ts:
                    return QColor.fromHsv(46, 153 * factor, 255 * factor)  # yellow
                else:
                    return QColor.fromHsv(100, 153 * factor, 255 * factor)  # green
            else:
                return QColor.fromHsv(0, 0, factor * 255)

    def headerData(self, section, orientation: Qt.Orientation, role):
        if orientation == Qt.Horizontal:
            if role == Qt.DisplayRole:
                return {
                    __class__.COL_NAME: "Title",
                    __class__.COL_VERSION: "Installed",
                    __class__.COL_TS_INSTALLED: "Age (Installed)",
                    __class__.COL_VERSION_AVAIL: "Available",
                    __class__.COL_TS_AVAIL: "Age (Available)",
                }[section]
            elif role == Qt.ToolTipRole:
                return {
                    __class__.COL_NAME: "Title of the mod",
                    __class__.COL_VERSION: "Installed version of the mod",
                    __class__.COL_TS_INSTALLED: "The date when the installed version was released",
                    __class__.COL_VERSION_AVAIL: "The newest available version of this mod",
                    __class__.COL_TS_AVAIL: "The date when the newest available version was released",
                }[section]

    def rowCount(self, index):
        return len(self._man.installed_mods)

    def columnCount(self, index):
        return __class__.COL_MAX


class ModTableView(QTableView):
    def __init__(self, man: InstallManager):
        super().__init__()
        self._man = man

        # set up the model directly
        self.mod_model = ModTableModel(self._man)
        # proxy model is helpful for sorting rows independently of the actual model
        model_proxy = QSortFilterProxyModel()
        model_proxy.setSourceModel(self.mod_model)
        self.setSizeAdjustPolicy(QTableView.SizeAdjustPolicy.AdjustToContents)
        self.setModel(model_proxy)
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        # self.table.setSortingEnabled(True)
        self.resizeColumnsToContents()

    def get_selected_mods(self):
        rows = self.selectionModel().selectedRows()
        return [self._man.installed_mods[index.row()] for index in rows]

    # def contextMenuEvent(self, e):
    #     logging.debug("Context menu requested on table")


class MainWindow(QMainWindow):
    def __init__(self, man: InstallManager):
        super().__init__()
        self.man = man

        self.buttons = QHBoxLayout()
        self.button_update_selected = QPushButton("Check and update selected mods")
        self.buttons.addWidget(self.button_update_selected)
        self.button_update_selected.clicked.connect(self.update_selected)

        self.button_update_all = QPushButton("Check and update all mods")
        self.buttons.addWidget(self.button_update_all)
        self.button_update_all.clicked.connect(self.update_all)

        self.button_uninstall_selected = QPushButton("Uninstall selected mods")
        self.buttons.addWidget(self.button_uninstall_selected)
        self.button_uninstall_selected.clicked.connect(self.uninstall_selected)

        self.button_check_all = QPushButton("Check newest versions of all mods")
        self.buttons.addWidget(self.button_check_all)
        self.button_check_all.clicked.connect(self.check_all)

        # self.button_test = QPushButton("Refresh Test")
        # self.buttons.addWidget(self.button_test)
        # self.button_test.clicked.connect(self.test_clicked)

        self.table = ModTableView(self.man)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.table_custom_context_menu)

        self.setWindowTitle("Vaelstrom")
        layout = QVBoxLayout()
        layout.addLayout(self.buttons)
        layout.addWidget(QHLine())
        layout.addWidget(self.table)
        self.container = QWidget()
        self.container.setLayout(layout)
        self.setCentralWidget(self.container)

        self.pool = QThreadPool()
        worker = ListenerRunnable()
        worker.signals.url_received.connect(self.on_url_received)
        self.pool.start(worker)
        self.workers_currently_working = 0
        self.run_on_threadpool(self.man.find_installed_mods)

    def run_on_threadpool(self, function, *args, **kwargs):
        if self.workers_currently_working == 0:
            self.set_working()
        self.workers_currently_working += 1
        worker = FuncWorker(function, *args, **kwargs)
        worker.signals.done.connect(self.on_worker_done)
        self.pool.start(worker)

    @Slot(bool)
    def on_worker_done(self, failed: bool):
        if self.workers_currently_working < 0:
            logging.error("A worker has finished but no workers were pending.")
        else:
            self.workers_currently_working -= 1
        if self.workers_currently_working == 0:
            self.set_idle()
        if failed:
            logging.error("A worker task has failed")

    def set_working(self):
        logging.debug("First worker starting")
        for i in range(self.buttons.count()):
            self.buttons.itemAt(i).widget().setEnabled(False)
        self.table.mod_model.beginResetModel()

    def set_idle(self):
        logging.debug("Last worker finished")
        self.table.mod_model.endResetModel()
        self.table.resizeColumnsToContents()
        self.container.adjustSize()
        self.adjustSize()
        for i in range(self.buttons.count()):
            self.buttons.itemAt(i).widget().setEnabled(True)

    def is_working(self):
        return self.workers_currently_working > 0

    def test_clicked(self):
        self.run_on_threadpool(self.timer_test, 3, False)
        self.run_on_threadpool(self.timer_test, 2, False)
        self.run_on_threadpool(self.timer_test, 4, False)
        self.run_on_threadpool(self.timer_test, 3, False)
        self.run_on_threadpool(self.timer_test, 3.5, True)

    def table_custom_context_menu(self, pos):
        if self.is_working():
            return
        # change selection to be only the right-clicked mod
        idx = self.table.indexAt(pos)
        self.table.selectRow(idx.row())
        # create context menu
        context = QMenu(self)
        context.addAction(chk := QAction("Check for newer version", self))
        context.addAction(chk_upd := QAction("Check and update", self))
        context.addAction(upd := QAction("Force update (ignore version numbers)", self))
        context.addAction(rem := QAction("Uninstall this mod", self))
        context.addAction(on := QAction("Enable this mod", self))
        context.addAction(off := QAction("Disable this mod", self))
        # open it and await click
        action = context.exec_(self.table.viewport().mapToGlobal(pos))
        # act on clicked item
        if action == chk:
            self.check_selected()
        elif action == chk_upd:
            self.update_selected()
        elif action == upd:
            self.update_selected(force=True)
        elif action == rem:
            self.uninstall_selected()
        elif action == on:
            self.enable_selected()
        elif action == off:
            self.disable_selected()

    def update_selected(self, force=False):
        mods = self.table.get_selected_mods()
        for mod in mods:
            self.run_on_threadpool(self.man.update_mod, mod, force)

    def update_all(self, force=False):
        for mod in self.man.installed_mods:
            self.run_on_threadpool(self.man.update_mod, mod, force)

    def uninstall_selected(self):
        mods = self.table.get_selected_mods()
        for mod in mods:
            self.run_on_threadpool(self.man.uninstall_mod, mod.state.mod_key(), mod)

    def check_all(self):
        # TODO: in case any request fails, we currently ignore all of the results
        # maybe better to have a for-each like the functions above
        self.run_on_threadpool(self.man.check_for_updates)

    def check_selected(self):
        mods = self.table.get_selected_mods()
        self.run_on_threadpool(self.man.check_for_updates, mods)

    def enable_selected(self):
        mods = self.table.get_selected_mods()
        for mod in mods:
            self.run_on_threadpool(self.man.enable_mod, mod)

    def disable_selected(self):
        mods = self.table.get_selected_mods()
        for mod in mods:
            self.run_on_threadpool(self.man.disable_mod, mod)

    @Slot(str)
    def on_url_received(self, url: str):
        logging.debug(f"GUI Thread received url: {url}")

        # TODO: use run_on_threadpool instead of blocking gui thread
        # need to prevent installing the same mod twice in parallel
        # maybe use a single worker with a queue
        # self.run_on_threadpool(self.man.handle_url, url)

        row_count = len(self.man.installed_mods)
        self.table.mod_model.beginInsertRows(QModelIndex(), row_count, row_count)
        self.man.handle_url(url)
        self.table.mod_model.endInsertRows()

    def timer_test(self, seconds: float, crash: bool):
        logging.debug("timer started")
        time.sleep(seconds)
        logging.debug("timer done")
        if crash:
            logging.debug("crashing imminent")
            raise Exception("timer_test raising exception")


class ListenerSignals(QObject):
    url_received = Signal(str)


class ListenerRunnable(QRunnable):
    def __init__(self):
        super().__init__()
        self.signals = ListenerSignals()

    def run(self):
        listener = Listener(("localhost", 58238))
        while True:
            with listener.accept() as conn:
                logging.debug(
                    f"Listener: connection accepted from {listener.last_accepted}"
                )
                msg = conn.recv_bytes().decode("utf-16-le")
                if msg == "stop":
                    break
                logging.debug(f"Listener: Signalling URL: {msg}")
                self.signals.url_received.emit(msg)
        logging.debug("Listener: shut down.")

    @staticmethod
    def send(msg: str):
        conn = Client(("localhost", 58238))
        conn.send_bytes(msg.encode("utf-16-le"))
        conn.close()

    @staticmethod
    def stop():
        # TODO: check if still running first
        ListenerRunnable.send("stop")


class FuncWorkerSignals(QObject):
    done = Signal(bool)


class FuncWorker(QRunnable):
    def __init__(self, function: Callable, *args, **kwargs):
        super().__init__()
        self.signals = FuncWorkerSignals()
        self.function = function
        self.args = args
        self.kwargs = kwargs

    def run(self):
        # run the provided function
        # always call the done signal
        # if the function threw an exception, error will be True
        error = True
        try:
            self.function(*self.args, **self.kwargs)
            error = False
        finally:
            self.signals.done.emit(error)


def run_qt_app(man: InstallManager):
    app = QApplication([])
    window = MainWindow(man)
    window.show()
    try:
        exitcode = app.exec_()
    finally:
        ListenerRunnable.stop()
    return exitcode
