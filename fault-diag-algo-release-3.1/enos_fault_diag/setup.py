#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author  : qi.cheng

from setuptools import find_packages, setup

setup(
    name='enos_fault_diag',
    version='1.0',
    packages=find_packages(),
    url='',
    license='',
    author='enos cloud',
    description='fault diagnostic framework',
    python_requires='>=3.6',
    platforms='any',
    install_requires=[
        'pandas',
        'numpy',
    ]
)
