SIM           ?= verilator
TOPLEVEL_LANG ?= verilog

# All three RTL files — bridge-top instantiates both submodules
VERILOG_SOURCES = $(shell pwd)/rtl/AHB_Slave_Interface.v \
                  $(shell pwd)/rtl/APB_Controller.v \
                  $(shell pwd)/rtl/bridge-top.v

TOPLEVEL      = Bridge_Top
MODULE        = tb.tb_ahb2apb

# Suppress RTL warnings (Hreadyout listed twice, width mismatches)
COMPILE_ARGS  += --public -Wno-MULTIDRIVEN -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC -Wno-LATCH

PYTHONPATH    = $(shell pwd):$(shell pwd)/../..
export PYTHONPATH

include $(shell cocotb-config --makefiles)/Makefile.sim
