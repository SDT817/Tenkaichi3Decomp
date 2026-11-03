Profile share codes use zlib's unchanged compress2/uncompress2 algorithms.
The local Windows adapter links E:/BT3-Wii-tools/mingw64/lib/libz.a statically;
no zlib DLL is required. Other builds must provide zlib headers and link -lz.
See LICENSE for the upstream license. No networking code uses this addition.
