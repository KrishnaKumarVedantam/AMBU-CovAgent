module fifo_mem #(parameter data_width =  8, ptr_width =  8, depth =256)( wclk,rclk,r_rst_n,w_rst_n,w_en,r_en,full,empty, data_in,  waddr,raddr,  data_out,rptr,wptr,half_full,half_empty);

input bit wclk,rclk,r_rst_n,w_rst_n,w_en,r_en,full,empty;
input logic [ptr_width:0]  waddr, raddr, rptr,wptr;

input logic [data_width-1:0] data_in;
output logic [data_width-1:0]data_out;
output bit half_empty,half_full;

logic [data_width-1:0] fifo [0: depth-1];

assign half_empty = (raddr==8'b01011000)?1'b1:1'b0;
assign half_full = (waddr==8'b01011000)?1'b1:1'b0;

always_ff@(posedge wclk)
	begin
		if(w_en & !full)
			begin
				fifo[waddr[ptr_width-1:0]]<=data_in;
			end
	end
assign data_out=fifo[raddr[ptr_width-1:0]];
endmodule
