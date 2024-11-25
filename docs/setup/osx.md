# Development Setup for OSX

A guide to setting up your OSX environment for developing on the Mac

### Requirements

    Docker -> https://www.docker.com/ (download, create a docker account and login)
    XCode -> install from app store (make sure you open and agree to licence)
    Brew -> /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install.sh)"
    pyenv -> https://github.com/pyenv/pyenv
    pyenv-virtualenv -> https://github.com/pyenv/pyenv-virtualenv


### Dependencies

    brew install postgresql
    brew install unixodbc


### Python

    pyenv init
    pyenv install 3.9.0
    pyenv global 3.9.0
    pyenv virtualenv 3.9.0 trrf-dev
    pyenv shell trrf-dev
    pip install --upgrade pip



### Installing modules for local development

    pip install -r requirements/requirements.txt
    pip install -r requirements/dev-requirements.txt
    pip install -r requirements/test-requirements.txt
