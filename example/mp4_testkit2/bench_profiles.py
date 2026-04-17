import os

try:
    from lib.config_loader import load_config
    from lib.sdio_mount import mount_from_config
except Exception:
    load_config = None
    mount_from_config = None


def _exists(p):
    try:
        os.stat(p)
        return True
    except Exception:
        return False


def _find_mount_candidates():
    out = []
    for p in ("/sd", "/sdcard", "/SD", "/SDCARD"):
        if _exists(p):
            out.append(p)
    return out


def _try_import(name):
    try:
        return __import__(name)
    except Exception as e:
        print("import failed:", name, e)
        return None


def run():
    if load_config is not None and mount_from_config is not None:
        try:
            cfg = load_config()
            mp = mount_from_config(cfg)
            if mp:
                print("sd mounted:", mp)
        except Exception as e:
            print("sd mount skipped:", e)

    bench_fs = _try_import("bench_fs")
    bench_pack = _try_import("bench_pack")
    if bench_fs is None or bench_pack is None:
        return

    mounts = _find_mount_candidates()
    print("mounts:", mounts)

    cases = []
    cases.append(("flash folder", "fs", "/jpeg/background"))
    cases.append(("flash pack", "pack", "/jpeg/background.jpk"))
    for m in mounts:
        cases.append(("sd folder", "fs", m + "/background"))
        cases.append(("sd pack", "pack", m + "/background.jpk"))

    for title, kind, path in cases:
        print()
        print("==", title, "==")
        print("path:", path)
        if kind == "fs":
            try:
                bench_fs.main(path, loops=3)
            except Exception as e:
                print("bench_fs failed:", e)
        else:
            try:
                bench_pack.main(path, loops=3)
            except Exception as e:
                print("bench_pack failed:", e)


if __name__ == "__main__":
    run()
