"""
Run this as:
pip install .
"""

#To rebuild the C extension, can run:
#python setup.py build_ext --inplace

from distutils.core import Extension, setup
from distutils.command.build_ext import build_ext

total_delta = Extension("nitecap.total_delta", sources=["nitecap/total_delta.c"])

class BuildNumpyExtCommand(build_ext):
    # Class that builds our C extension using the Numpy libraries but without
    # requiring that the numpy library be imported at the top level.
    # Fixes the case where the installer doesn't have numpy installed yet
    # But will when we runt he build_ext command since it's require'd
    # See  https://stackoverflow.com/questions/2379898/make-distutils-look-for-numpy-header-files-in-the-correct-place
    def run(self):
        import numpy
        # Add numpy header files directory to the build path
        self.include_dirs.append(numpy.get_include())
        build_ext.run(self)

install_requirements = ["numpy(>=1.15)"]
setup_args = dict(name="nitecap",
            cmdclass = {'build_ext': BuildNumpyExtCommand},
            version='0.1',
            description='Non-parametric Identification Tool Enabling of Circadian Analysis in Parallel',
            author='Thomas Brooks',
            author_email='tgbrooks@gmail.com',
            packages = ['nitecap'],
            install_requires=install_requirements # Need Numpy before we can build the ext
            )
try:
    # Setup plus build the extension module
    setup(ext_modules = [total_delta], **setup_args)
except SystemExit:
    # Had a problem compiling (eg: no compiler)
    # So just use the python implementation and forget the numpy extension step
    setup(**setup_args)
