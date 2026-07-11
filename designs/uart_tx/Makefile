SIM           ?= verilator
TOPLEVEL_LANG ?= verilog
VERILOG_SOURCES = $(shell pwd)/rtl/uart_tx.v
TOPLEVEL      = uart_tx
MODULE        = tb.tb_uart_tx

# Speed: 10 cycles/bit instead of default 5208
# BIT_RATE=1MHz, CLK_HZ=10MHz → CYCLES_PER_BIT=10
# One TX = 10 bits × 11 cycles = 110 cycles ≈ 1μs
COMPILE_ARGS  += --public -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC -GBIT_RATE=1000000 -GCLK_HZ=10000000

PYTHONPATH    = $(shell pwd):$(shell pwd)/../..
export PYTHONPATH

include $(shell cocotb-config --makefiles)/Makefile.sim
