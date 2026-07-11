module async_fifo_flat #(
    parameter data_width = 8,
    parameter ptr_width  = 8,
    parameter depth      = 256
)(
    input  logic                  wclk,
    input  logic                  rclk,
    input  logic                  w_rst_n,
    input  logic                  r_rst_n,
    input  logic                  w_en,
    input  logic                  r_en,
    input  logic [data_width-1:0] data_in,
    output logic [data_width-1:0] data_out,
    output logic                  full,
    output logic                  empty,
    output logic                  half_full,
    output logic                  half_empty
);
    logic [ptr_width:0] waddr, raddr;
    logic [ptr_width:0] wptr,  rptr;
    logic [ptr_width:0] wptr_sync, rptr_sync;

    w2rsync   #(ptr_width) u_w2r (rclk, r_rst_n, wptr, wptr_sync);
    r2wsync   #(ptr_width) u_r2w (wclk, w_rst_n, rptr, rptr_sync);
    write_ptr #(ptr_width) u_wp  (wclk, w_rst_n, w_en, rptr_sync,
                                   waddr, wptr, full);
    read_ptr  #(ptr_width) u_rp  (rclk, r_rst_n, r_en, wptr_sync,
                                   raddr, rptr, empty);
    fifo_mem  #(data_width, ptr_width, depth) u_mem (
        wclk, rclk, r_rst_n, w_rst_n,
        w_en, r_en, full, empty,
        data_in, waddr, raddr, data_out,
        rptr, wptr, half_full, half_empty
    );
endmodule
