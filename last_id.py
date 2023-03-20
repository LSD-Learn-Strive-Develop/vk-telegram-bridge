from loguru import logger
import pickle
import os


def read_id() -> int:
    try:
        return int(open("./last_id.txt", "r").read())
    except ValueError:
        logger.critical(
            "The value of the last identifier is incorrect. "
            "Please check the contents of the file 'last_id.txt'."
        )
        exit()


def write_id(new_id: int) -> None:
    open("./last_id.txt", "w").write(str(new_id))
    logger.info(f"New ID, written in the file: {new_id}")


def read_data(fi):
    with open(fi, 'rb') as f:
        data_new = pickle.load(f)

    return data_new


def write_data(d, fi):
    with open(fi, 'wb') as f:
        pickle.dump(d, f)


def check_data(obj, fi, empty=False):
    if not os.path.isfile(fi) or empty:
        write_data(obj, fi)
        return obj
    else:
        return read_data(fi)