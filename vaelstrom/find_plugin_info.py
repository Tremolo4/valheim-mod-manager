import re


def read_strings(file_bytes: bytes, index: int):
    result: list = []

    length: int = 0

    try:
        while (
            (length := file_bytes[index]) != 0
            and length < 128
            and index + length <= len(file_bytes)
        ):
            result.append(file_bytes[index + 1 : index + 1 + length].decode("utf-8"))
            index += length + 1
    except:
        return []

    return result


def find_plugin_info(dll_path: str):
    matching_strings: list = []

    package_regex = r"^([a-zA-Z_][a-zA-Z0-9_]*)(\.([a-zA-Z_][a-zA-Z0-9_]*))+$"
    version_regex = r"^[0-9]+(\.[0-9]+)*$"

    with open(dll_path, "rb") as f:
        file_bytes: bytes = f.read()

        for i in range(len(file_bytes) - 2):
            if file_bytes[i] != 1 or file_bytes[i + 1] != 0:
                continue

            strings: list = read_strings(file_bytes, i + 2)

            if len(strings) != 3:
                continue

            if not re.match(package_regex, strings[0]):
                continue

            if not re.match(version_regex, strings[2]):
                continue

            matching_strings.append(strings)

    if len(matching_strings) != 1:
        return None

    return {
        "package": matching_strings[0][0],
        "title": matching_strings[0][1],
        "version": matching_strings[0][2],
    }
