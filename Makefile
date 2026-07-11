SIM             = verilator
TOPLEVEL_LANG   = verilog
VERILOG_SOURCES = $(shell pwd)/rtl/async_fifo_flat.sv \
                  $(shell pwd)/rtl/fifo_mem.sv \
                  $(shell pwd)/rtl/write_ptr.sv \
                  $(shell pwd)/rtl/read_ptr.sv \
                  $(shell pwd)/rtl/w2rsync.sv \
                  $(shell pwd)/rtl/r2wsync.sv
TOPLEVEL        = async_fifo_flat
MODULE          = tb.tb_fifo
EXTRA_ARGS     += --timing --threads 1 -Wno-WIDTHEXPAND
include $(shell cocotb-config --makefiles)/Makefile.sim
