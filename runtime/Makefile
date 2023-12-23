CC = riscv64-unknown-elf-gcc -march=rv64gc -mabi=lp64f -xc++
AR = riscv64-unknown-elf-ar
CLEAN = rm -f

all: clean libsysy.a

libsysy.a: sylib.o
	$(AR) rcs $@ $<

sylib.o: sylib.c sylib.h
	$(CC) -O2 -c -o $@ $<

clean:
	$(CLEAN) libsysy.a
	$(CLEAN) sylib.o