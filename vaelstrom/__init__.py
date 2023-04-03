import configparser

# workaround for https://bugs.python.org/issue29288
# bug appears when using pyinstaller build
u"".encode("idna")

cfg = configparser.ConfigParser()
cfg.read("config.ini")
