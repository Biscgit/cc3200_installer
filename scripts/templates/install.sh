#!/bin/bash

echo "Checking for required packages"

# python
if ! command -v python3 &>/dev/null; then
  echo "- missing python"
  sudo apt install -y python3 python3-pip python3-venv

  echo "+ installed python"
else
  echo "+ OK python"
fi

# rust
if ! command -v rustc &>/dev/null; then
  echo "- rust"

  # curl
  if ! command -v curl &>/dev/null; then
    echo "- curl"
    sudo apt install -y curl
    echo "+ installed curl"
  else
    echo "+ OK curl"
  fi

  curl https://sh.rustup.rs -sSf | sh -s -- -y
  # ToDo extra steps required here

  echo "+ installed rust"
else
  echo "+ OK rust"
fi

echo "Creating virtual environment"
python3 -m venv .venv
source .venv/bin/activate

echo "Installing packages"
pip3 install --upgrade pip
pip3 install asyncssh

echo "Running script"
python3 - <<'EOF'
[[script]]
EOF

echo "Cleaning up"
deactivate
rm -rf .venv

echo "All done!"
