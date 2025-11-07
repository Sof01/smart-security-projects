import os, zipfile, numpy as np

def load_test_zip(zip_path: str):
    files, contents = [], []
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if name.endswith("/") or name.endswith(".labels"):
                continue
            contents.append(z.read(name))    # <- Bytes
            files.append(name)
    return files, contents
