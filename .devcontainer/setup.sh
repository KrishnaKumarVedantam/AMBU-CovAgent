#!/bin/bash
set -e

echo "=== Installing build dependencies for Verilator ==="
sudo apt-get update
sudo apt-get install -y git help2man perl make autoconf g++ flex bison ccache \
  libgoogle-perftools-dev numactl libfl2 libfl-dev zlib1g zlib1g-dev

echo "=== Building Verilator v5.048 from source ==="
git clone https://github.com/verilator/verilator /tmp/verilator-src
cd /tmp/verilator-src
git checkout v5.048
autoconf
./configure
make -j "$(nproc)"
sudo make install
cd -

echo "=== Verilator version check ==="
verilator --version

echo "=== Installing pinned Python packages ==="
pip install -r requirements.txt

echo "=== Setup complete ==="
