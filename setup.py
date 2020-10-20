from setuptools import setup

with open('README.md') as f:
    long_description = f.read()

setup(
  name = 'gsmHat',
  packages = ['gsmHat'],
  version = '0.4.2',
  license='MIT',
  description = 'Using the Waveshare GSM/GPRS/GNSS Hat for Raspberry Pi with Python',
  long_description = long_description,
  long_description_content_type="text/markdown",
  author = 'Tarek Tounsi',
  author_email = 'software@tounsi.de',
  url = 'https://github.com/Civlo85/gsmHat',
  download_url = 'https://github.com/Civlo85/gsmHat/archive/v_04.tar.gz',
  keywords = ['Waveshare', 'GSM', 'GPS', 'Raspberry', 'Pi'],
  install_requires=[
          'serial',
          'datetime'
      ],
  classifiers=[
    'Development Status :: 3 - Alpha',      # Chose either "3 - Alpha", "4 - Beta" or "5 - Production/Stable" as the current state of your package
    'Intended Audience :: Developers',
    'Topic :: Software Development :: Build Tools',
    'License :: OSI Approved :: MIT License',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.4',
    'Programming Language :: Python :: 3.5',
    'Programming Language :: Python :: 3.6',
    'Programming Language :: Python :: 3.7',
  ],
)
