#! /bin/sh
CC=riscv64-unknown-elf-gcc
GCC_ARGS="-march=rv64gc -mabi=lp64d"
on_riscv=0
asm=""

# 使用 getopt 解析选项, 注意，即使没有段选项，也要写上 -o "", 否则好像识别不了长选项
ARGS=$(getopt -o "" --long asm:,on_riscv -n 'run_riscv.sh' -- "$@")
if [ $? != 0 ]; then
  echo "Terminating..." >&2
  exit 1
fi

# 将解析结果重新设置到位置参数
eval set -- "$ARGS"

# 处理选项
while true; do
  case "$1" in
    --asm )
      asm=$2
      echo "Asm file: $asm"
      shift 2
      ;;
    --on_riscv )
      on_riscv=1
      echo "Run on riscv"
      shift
      ;;
    -- )
      shift
      break
      ;;
    * )
      break
      ;;
  esac
done

if [ -z "$asm" ]; then
  echo "Usage: $0 --asm <asm_file> [--on_riscv]"
  exit 1
fi

asm_prefix=$(echo "$asm" | sed 's/\.s.*//')

echo "Running $CC $GCC_ARGS $asm runtime/libsysy.a -o $asm_prefix.exec"
$CC $GCC_ARGS $asm runtime/libsysy.a -o $asm_prefix.exec


if [ $on_riscv -eq 0 ]; then
  qemu-riscv64 $asm_prefix.exec
else
  $asm_prefix.exec
fi

echo "Exit code: $?"