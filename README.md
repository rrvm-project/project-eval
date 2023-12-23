# 大实验测试脚本

## 使用说明

预置条件：riscv64-unknown-elf工具链，python3

```sh
python test.py -t <testcase_folder>
```

请看`test.py`，修改`compiler_path`,`compiler_args`和`gcc_args`变量，改为你的编译器路径和参数选项。

例如
```Python
compiler_path = "./build/mycompiler"
compiler_args = "-O2"
```
此处`compiler_args`为提供给你的编译器的额外选项。

我们会以下面的命令模板调用你的编译器生成汇编代码
```bash
# {compiler_path} {compiler_args} xxx.sy -o xxx.s
./build/mycompiler -O2 xxx.sy -o xxx.s
```
如果你的编译器不支持这样的命令格式，请在`test`函数中的注释附近修改。

然后会带上`gcc_args`使用gcc来汇编上一步生成的代码并链接运行时库。

比如：
```Python
gcc_args = "-march=rv64gc -mabi=lp64f"
```

则会调用
```bash
# riscv64-unknown-elf-gcc {gcc_args} xxx.s runtime/libsysy.a -o xxx
riscv64-unknown-elf-gcc -march=rv64gc -mabi=lp64f xxx.s runtime/libsysy.a -o xxx
```

## 如果你的编译器后端架构不是riscv64

重新编译libsysy.a，到runtime目录下，修改Makefile

修改CC变量，将`-march=rv64gc -mabi=lp64f`改为你的架构

重新`make`

推荐32位的用`-march=rv32gc -mabi=ilp32f`

64位的用：`-march=rv64gc -mabi=lp64f`

## 已知问题

