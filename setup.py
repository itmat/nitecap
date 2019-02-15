"""
Run this as:
python setup.py build_ext --in_place
"""

from distutils.core import Extension, setup
import numpy

total_delta = Extension("total_delta", sources=["total_delta.c"], include_dirs=[numpy.get_include()])


setup(ext_modules = [total_delta])
