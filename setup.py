from setuptools import setup, find_packages

setup(
    name="ossnake",
    version="0.1.0",
    packages=find_packages(include=['driver', 'driver.*', 'tests', 'tests.*']),
    install_requires=[
        'boto3',
        'oss2',
        'minio',
        'pytest',
        'pytest-html',
        'pytest-cov'
    ],
) 