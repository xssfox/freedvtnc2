from cffi import FFI
ffibuilder = FFI()

# cdef() expects a single string declaring the C types, functions and
# globals needed to use the shared object. It must be in valid C syntax.
ffibuilder.cdef(open("freedv.h").read())

# set_source() gives the name of the python extension module to
# produce, and some C source code as a string.  This C code needs
# to make the declarated functions, types and globals available,
# so it is often just the "#include".
ffibuilder.set_source("_freedv_cffi",
"""
     #include "freedv_api.h"   // the C header of the library
     #include "modem_stats.h"   // the C header of the library
""",
     libraries=['codec2'],
     include_dirs = [ "/Users/mwheeler/src/codec2/src/"],
     library_dirs = ["/Users/mwheeler/src/codec2/build_linux/src/"]
     )   # library name, for the linker

if __name__ == "__main__":
    ffibuilder.compile(verbose=True)