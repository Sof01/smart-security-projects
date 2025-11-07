import os, zipfile, numpy as np

def load_train_zip(zip_path: str):
    contents, labels, names = [], [], []
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if name.endswith("/") or name.endswith(".labels"):
                continue
            base = os.path.basename(name)
            if not (base.endswith(".0") or base.endswith(".1")):
                continue
            lab = int(base.rsplit(".", 1)[1])
            buf = z.read(name)               # <- Bytes, kein decode
            contents.append(buf)
            labels.append(lab)
            names.append(name)
    return names, contents, np.asarray(labels, dtype=int)

def load_test_zip(zip_path: str):
    files, contents = [], []
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if name.endswith("/") or name.endswith(".labels"):
                continue
            contents.append(z.read(name))    # <- Bytes
            files.append(name)
    return files, contents
