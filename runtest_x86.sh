cd runtime
make clean
make
cd ..
python test.py -c riscv64-unknown-elf-gcc -r riscv64-unknown-elf-gcc -b -t $1
