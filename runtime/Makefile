# CC = gcc -xc++
# AR = ar
CC = riscv64-unknown-elf-gcc -xc++
AR = riscv64-unknown-elf-ar
RM = rm -f

.PHONY: clean

all: libsysy.a

libsysy.a: sylib.o
	$(AR) rcs $@ $<

sylib.o: sylib.cc sylib.h
	$(CC) -O2 -c -o $@ $<

clean:
	$(RM) libsysy.a
	$(RM) sylib.o
