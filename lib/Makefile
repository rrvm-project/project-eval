CC = riscv64-unknown-elf-gcc
AR = riscv64-unknown-elf-ar

all: libsysy.a

libsysy.a: sylib.o
	$(AR) rcs $@ $<

sylib.o: sylib.c sylib.h
	$(CC) -O2 -c -o $@ $<
