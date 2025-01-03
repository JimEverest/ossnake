from setuptools import setup, find_packages

with open("readme.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="ossnake",
    version="0.1.1",
    author="Jim Everest",
    author_email="your.email@example.com",
    description="A unified object storage browser supporting multiple cloud storage services",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/jimeverest/ossnake",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    python_requires=">=3.8",
    install_requires=[
        "boto3>=1.26.0",
        "oss2>=2.16.0",
        "minio>=7.1.0",
        "Pillow>=9.0.0",
        "requests>=2.28.0",
    ],
    entry_points={
        'console_scripts': [
            'ossnake=ossnake.main:main',
        ],
    },
    include_package_data=True,
) 