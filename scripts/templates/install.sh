#!/bin/bash

echo "Checking for required packages"

# python
if ! command -v python3 &>/dev/null; then
  REQUIRED_VERSION="3.9"
  echo "Required Python version: $REQUIRED_VERSION (or higher)"

  sudo apt-get install -y python3

#  echo "Fetching dependencies"
#  sudo apt-get install -y libncursesw5-dev libssl-dev libsqlite3-dev tk-dev libgdbm-dev libc6-dev libbz2-dev
#
#  echo "Downloading newer version"
#  PYTHON_URL="https://www.python.org/ftp/python/3.12.4/Python-3.12.4.tgz"
#  curl -O $PYTHON_URL
#
#  echo "Extracting"
#  tar -xzf Python-3.12.4.tgz
#  cd Python-3.12.4 || exit 1
#
#  echo "Installing"
#  ./configure --enable-optimizations
#  sudo make install
#
#  cd ..

  PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')
  echo "+ installed python $PYTHON_VERSION"

else
  echo "+ OK python "
fi

# rust
if ! command -v rustc &>/dev/null; then
  echo "- rust"
  sudo apt-get install -y rustc

  echo "+ installed rust"

else
  echo "+ OK rust"
fi

# not required -> only one package needed -> pip ssl error
# echo "Creating virtual environment"
# python3 -m venv .venv
# source .venv/bin/activate

python3 -c 'import asyncssh;' || {
  echo "Installing missing packages"
  sudo apt install -y python3-asyncssh
}

echo "Running script"
python3 - <<'EOF'
[[script]]
EOF

echo "Cleaning up"
# deactivate
# rm -rf .venv

echo "All done!"
