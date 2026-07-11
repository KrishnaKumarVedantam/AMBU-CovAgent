module r2wsync #(parameter ptr_width=8)( wclk, w_rst_n, rptr,  rptr_sync);

input bit wclk, w_rst_n;
input logic [ptr_width:0]  rptr;
output logic [ptr_width:0]rptr_sync;

logic [ptr_width:0] q1;
  always_ff@(posedge wclk) begin
    if(!w_rst_n) begin
      q1 <= 0;
      rptr_sync <= 0;
    end
    else begin
      q1 <= rptr;
      rptr_sync <= q1;
    end
  end
endmodule