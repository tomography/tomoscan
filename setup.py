from setuptools import setup, find_packages
from setuptools.command.install import install
import os

class PostInstallCommand(install):
    """Post-installation for installation mode."""
    def run(self):        
        install.run(self)
        from tomoscan.auto_complete import create_complete_scan
        import pathlib
        create_complete_scan.run(str(pathlib.Path.home())+'/complete_tomo.sh')
        print('For autocomplete please run: \n\n $ source '+str(pathlib.Path.home())+'/complete_tomo.sh\n'     )

setup(
    name='tomoscan',
    version=open('VERSION').read().strip(),
    #version=__version__,
    author='Mark Rivers, Francesco De Carlo',
    author_email='rivers@cars.uchicago.edu',
    url='https://github.com/tomography/tomoscan.git',
    packages=find_packages(),
    include_package_data = True,
    #scripts=['bin/tomo'],
    description='Classes to run tomography scans',
    zip_safe=False,
    #cmdclass={'install': PostInstallCommand},
)