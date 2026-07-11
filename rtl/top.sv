module top #(parameter depth=256, data_width=8,ptr_width=8) (intfc in );

w2rsync #(ptr_width) w2rsync_inst(in.rclk,  in.r_rst_n,  in.wptr ,  in.wptr_sync );
r2wsync #(ptr_width) r2wsync_inst(in.wclk,  in.w_rst_n, in.rptr,  in.rptr_sync );

write_ptr #(ptr_width) write_ptr_inst (in.wclk, in.w_rst_n, in.w_en,  in.rptr_sync,  in.waddr, in.wptr, in.full);

read_ptr #(ptr_width) read_ptr_inst (in.rclk, in.r_rst_n, in.r_en,   in.wptr_sync,  in.raddr, in.rptr,  in.empty);

fifo_mem #(data_width,ptr_width,depth) fifo_mem_inst (in.wclk,in.rclk,in.r_rst_n,in.w_rst_n,in.w_en,in.r_en,in.full,in.empty, in.data_in,  in.waddr,in.raddr,  in.data_out, in.rptr, in.wptr, in.half_full, in.half_empty);

endmodule