from setuptools import setup, find_packages

setup(name='simpleLedger', version='0.0.1', packages=find_packages(),
    install_requires=[
        'peewee',
        'mako',
        'h2',
        'pytest'
    ])
