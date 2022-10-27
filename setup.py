# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['sqladmin', 'sqladmin.backends', 'sqladmin.backends.gino', 'sqladmin.utils']

package_data = \
{'': ['*'],
 'sqladmin': ['statics/css/*',
              'statics/fontawesome/*',
              'statics/fontawesome/css/*',
              'statics/fontawesome/js/*',
              'statics/fontawesome/less/*',
              'statics/fontawesome/metadata/*',
              'statics/fontawesome/scss/*',
              'statics/fontawesome/sprites/*',
              'statics/fontawesome/svgs/brands/*',
              'statics/fontawesome/svgs/regular/*',
              'statics/fontawesome/svgs/solid/*',
              'statics/fontawesome/webfonts/*',
              'statics/iconfont/*',
              'statics/iconfont/fonts/*',
              'statics/js/*',
              'statics/webfonts/*',
              'templates/sqladmin/*',
              'templates/sqladmin/components/*',
              'templates/sqladmin/modals/*']}

install_requires = \
['Jinja2>=2.0,<3.0',
 'aiosqlite>=0.17.0,<0.18.0',
 'mypy==0.931',
 'pydantic>=1.8.2,<2.0.0',
 'python-multipart>=0.0.5,<0.0.6',
 'reform>=0.2,<0.3',
 'sqlalchemy==1.3.15',
 'starlette>=0.13.0,<0.14.0',
 'wtforms-appengine>=0.1,<0.2',
 'wtforms>=3,<4']

setup_kwargs = {
    'name': 'sqladmin',
    'version': '0.1.4',
    'description': 'Admin interface for SQLAlchemy and Gino',
    'long_description': None,
    'author': 'Amin Alaee',
    'author_email': 'mohammadamin.alaee@gmail.com',
    'maintainer': None,
    'maintainer_email': None,
    'url': None,
    'packages': packages,
    'package_data': package_data,
    'install_requires': install_requires,
    'python_requires': '>=3.7,<4.0',
}


setup(**setup_kwargs)

