from setuptools import setup, find_packages
# pylint: disable=no-name-in-module,F0401,W0232,C0111,R0201
import fermenator

def readme():
    "Returns the contents of the README.rst file"
    with open("README.rst") as f:
        return f.read()

setup(
    name='fermenator',
    version=fermenator.__version__,
    description='Fermentation monitoring software',
    long_description=readme(),
    author='Prairie Dog Brewing CANADA Inc',
    author_email='gerad@prairiedogbrewing.ca',
    url='http://github.com/prairiedogbeer/fermenator',
    packages=find_packages(),
    install_requires=[
        'setuptools',
        'docopt',
        'PyYAML',
        #'RPi.GPIO',
        #'py-gaugette',
        #'Adafruit_Python_LED_Backpack',
    ],
    #scripts=[
    #    'bin/controller-v3',
    #    'bin/mini-controller-v3',
    #    'bin/probe-probe',
    #    'bin/prototype',
    #    'bin/bitwave'
    #],
    test_suite="nose.collector",
)
