from setuptools import setup

import freedvtnc2.freedv_build as freedv_build


def build(a):
    setup(
        ext_modules=[freedv_build.ffibuilder.distutils_extension()],
    )
