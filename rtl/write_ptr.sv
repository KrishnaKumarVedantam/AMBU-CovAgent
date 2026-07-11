module write_ptr #(parameter ptr_width=8)(wclk, w_rst_n, w_en,  rptr_sync,  waddr, wptr, full);

input bit wclk, w_rst_n, w_en;
input logic [ptr_width:0] rptr_sync;

output bit full;
output logic [ptr_width:0] waddr, wptr;

logic wfull;
logic [ptr_width:0]waddr_next; 
logic [ptr_width:0]wptr_next;

assign waddr_next= waddr + (w_en & !full);
assign wptr_next= (waddr_next>>1)^waddr_next; 

always_ff@(posedge wclk or negedge w_rst_n)
begin
	if(!w_rst_n)
		begin
		waddr<='0;
		wptr<='0;
		end 
	else begin
		waddr<=waddr_next;
		wptr<=wptr_next;
	end
end

always_ff@(posedge wclk or negedge w_rst_n)
begin
if(!w_rst_n)
	full<=0;
else
	full<=wfull;
end
assign wfull= (wptr_next=={~rptr_sync[ptr_width:ptr_width-1],rptr_sync[ptr_width-2:0]});

	
endmodule















 