```
# The B2 format is documented at https://winlink.org/sites/default/files/downloads/winlink_data_flow_and_data_packaging.pdf
#
# The first B2 block begins with this header:
#   SOH – byte with hex value 01
#   length – Single byte containing length of the message subject + number of bytes to store the offset value (as an ASCII value) + 2
#   subject – The subject of the message
#   NUL – byte with hex value 00
#   offset – If the message is starting at an interrupted point, this is the byte offset of the starting point. 
#     If the message is starting at the beginning, the offset is 0 (zero). The offset value is stored as an ASCII string.
#   NUL – byte with hex value 00
#   If the starting offset is not zero, this information field is added (omitted if offset is 0):
#     STX – byte with hex value 02
#     6 – byte with hex value 06
#     lead-bytes – First 6 bytes of the compressed image.
#
# After the B2 header information, the compressed message image is formatted into multiple
# blocks with each block having the following contents:
#   STX – byte with hex value 02
#   block-length – byte with the value 250 for a full block or a smaller number for the final, short block.
#   data – As many data bytes from the compressed message image as specified by block-
# length. Full blocks have 250 data bytes, the final block may have fewer.
# An end block is added after the required number of data blocks. The end block has this format:
#   EOT – byte with hex value 04
#   checksum – Simple checksum of the compressed data bytes in the block converted to a
# byte value using this VB.NET code:
# CByte(((intCheckSum And &HFF) * -1) And &HFF)
```


## The debug-323.b2f example

This upload from the client included two messages. 

```
162 bytes for the first message (Proposal 154 152)
    01    04                                    41         00     30                 00
    <SOH> <length of subject + offset + 2 = 4>  <subject>  <NUL>  <offset ASCII = 0> <NUL>
    02    98               98 ...
    <STX> <blocklen = 152> <data>
    04        20
    <EOT@160> <checksum@161>

followed by 161 bytes for the second message (Proposal 154 151)
    01        04                                    42         00     30                 00
    <SOH@162> <length of subject + offset + 2 = 4>  <subject>  <NUL>  <offset ASCII = 0> <NUL>
    02    97               88 ...
    <STX> <blocklen = 151> <data>
    04    C7
    <EOT> <checksum>
```

Once the blocks are extracted and concatenated, they have to be decompressed.

```
<CRC-16>  CRC
<LENGTH>  Four byte length field in little-endian format.  It gives the length in bytes of the decompressed message, as a check.
<COMPRESSED MESSAGE>
```


```
# Format of the message at this stage:
# Headers in ASCII, each line terminated by \r\n
#   <header1> <\r\n>
#   <header2> <\r\n>
#   ...
#   <\r\n>  The header has no blank lines, so searching for <\r\n\r\n> is safe
# Body is in ASCII and attachments are in binary
#   <body> (if any) <\r\n> The body does not use <\r> for line separation
#   <attachment1> (if any) <\r\n\r\n>
#   <attachment2> (if any) <\r\n\r\n>
#   ...
#   <\r\n\r\n>
```