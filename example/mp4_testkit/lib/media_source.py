import os


def list_jpegs(folder_path):
    files = [
        f
        for f in os.listdir(folder_path)
        if f.lower().endswith(".jpeg") or f.lower().endswith(".jpg")
    ]
    files.sort()
    return [folder_path + "/" + f for f in files]


def compute_max_file_size(paths, default_bytes=64 * 1024):
    max_bytes = 0
    for p in paths:
        sz = os.stat(p)[6]
        if sz > max_bytes:
            max_bytes = sz
    return max_bytes if max_bytes > 0 else default_bytes
