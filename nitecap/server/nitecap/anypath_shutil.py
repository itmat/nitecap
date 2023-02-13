'''
Functionality from shutil that is compatibile with both Path and CloudPath, i.e. as an AnyPath
'''

import shutil
from pathlib import Path
from cloudpathlib import CloudPath, AnyPath

def rmtree(path: AnyPath) -> None:
    if isinstance(path, Path):
        return shutil.rmtree(path)
    elif isinstance(path, CloudPath):
        return path.rmtree()
    else:
        raise NotImplementedError()

def copytree(source: AnyPath, dest: AnyPath) -> None:
    if isinstance(source, Path) and isinstance(dest, Path):
        return shutil.copytree(source, dest)
    elif isinstance(source, CloudPath) and isinstance(dest, CloudPath):
        return source.copytree(dest)
    else:
        raise NotImplementedError()