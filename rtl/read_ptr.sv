module read_ptr #(parameter ptr_width=8)( rclk, r_rst_n, r_en,   wptr_sync,  raddr, rptr,  empty);

input bit rclk,r_rst_n, r_en;
input logic [ptr_width:0]  wptr_sync;
output bit empty;
output logic [ptr_width:0] raddr, rptr;

 logic rempty;
 logic emptyr;
 logic readempty;

logic [ptr_width:0]raddr_next;
logic [ptr_width:0]rptr_next;


assign raddr_next= raddr + (r_en & !empty);
assign rptr_next=(raddr_next>>1)^raddr_next;
assign rempty= (wptr_sync == rptr_next);

always_ff@(posedge rclk or negedge r_rst_n)
begin
	if(!r_rst_n)
		begin
		raddr<=0;
		rptr<=0;
		end 
	else begin
		raddr<=raddr_next;
		rptr<=rptr_next;
	end
end

always_ff@(posedge rclk or negedge r_rst_n)
begin
if(!r_rst_n)
	empty<=1;
else
	empty<=rempty;
	
end

endmodule












 