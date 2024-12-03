import setuptools

install_requires = open('requirements.txt').read().splitlines()

setuptools.setup(
    name="chubbcord",
    version="1.0",
    packages=setuptools.find_packages(),
    install_requires=install_requires,
    entry_points={
        'console_scripts': [
            'chubbcord=src.main:main',
        ]
    },
    include_package_data=True,
)
