import argparse
import os
import struct


def _list_jpegs(folder):
    names = [n for n in os.listdir(folder) if n.lower().endswith(".jpg") or n.lower().endswith(".jpeg")]
    names.sort()
    return [os.path.join(folder, n) for n in names]


def pack_folder(in_dir, out_file):
    paths = _list_jpegs(in_dir)
    if not paths:
        raise SystemExit("no jpg/jpeg in: " + in_dir)

    max_size = 0
    for p in paths:
        sz = os.stat(p).st_size
        if sz > max_size:
            max_size = sz

    with open(out_file, "wb") as out:
        out.write(b"JPK1")
        out.write(struct.pack("<III", len(paths), max_size, 0))
        for p in paths:
            sz = os.stat(p).st_size
            out.write(struct.pack("<I", sz))
            with open(p, "rb") as f:
                while True:
                    b = f.read(4096)
                    if not b:
                        break
                    out.write(b)

    return len(paths), max_size


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_dir", required=True)
    ap.add_argument("--out", dest="out_file", required=True)
    args = ap.parse_args(argv)

    cnt, max_size = pack_folder(args.in_dir, args.out_file)
    print("packed:", cnt, "max_jpeg_bytes:", max_size)
    print("out:", args.out_file)


if __name__ == "__main__":
    main()
