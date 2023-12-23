# 大实验测试脚本

## 怎么使用

```
python test.py -t <testcase_folder>
```

请看`test.py`，修改`compiler_path`,`compiler_args`和`gcc_args`变量，改为你的编译器的位置，也可以加上你自己的选项。
比如如果你填写
```
compiler_path="./build/mycompiler -O2"
compiler_args="-O2"
```
这个`compiler_args`是给你的编译器的。

我们会以下面的命令调用你的编译器
```bash
# {compiler_path} {compiler_args} xxx.sy -o xxx.o
./build/mycompiler -O2 xxx.sy -o xxx.o
```

然后会带上`gcc_args`来链接大家的汇编。

比如：
```
gcc_args="-march=rv64gc -mabi=lp64f"
```
则会调用
```bash
# riscv64-unknown-elf-gcc {gcc_args} xxx.s runtime/libsysy.a -o xxx
riscv64-unknown-elf-gcc -march=rv64gc -mabi=lp64f xxx.s runtime/libsysy.a -o xxx
```

## 如果你使用的不是rv64

重新编译libsysy.a，到runtime目录下，修改Makefile

修改CC变量，将`-march=rv64gc -mabi=lp64f`改为你的架构

重新`make`

推荐32位的用`-march=rv32gc -mabi=ilp32f`

64位的用：`-march=rv64gc -mabi=lp64f`
