# 大实验测试脚本

## 预置条件

qemu-user, riscv64-unknown-elf工具链，python3

git-lfs:
```
sudo apt install git-lfs
git lfs install
```
> 原因：performance/03_sort2.in 和 performance/shuffle2.in 大小超过了 100MB，需要使用 git 的 lfs 插件进行版本控制

## 使用说明

### 本地测试

```sh
python test.py -t <testcase_folder> [-p] [-b] -c <riscv64-unknown-elf-gcc> -r <rival_compiler> [--on_riscv] [--store_time]
```

其中`-t`选项指定了存放测例的路径。`-b`和`-p`是可选项，使用`-b`将启用性能评测记录程序运行时间, 设置`-p`将开启并行评测（不建议在最终评测性能时启用）。

-c：表示用于链接动态库的编译器，一般用 riscv64-unknown-elf-gcc

-r：全写是 --rival，表示用来对比性能的编译器，以下称之为对手编译器。

如果是 gcc 或 riscv64-unknown-elf-gcc ，则编译命令为
```
[riscv64-unknown-elf-]gcc -xc++ -O2 -S {gcc_args} -include runtime/sylib.h {source} -o {gcc_assembly}
```
如果是其它编译器，则它需要被放置在 `./rivals/{rival_compiler}/{rival_compiler}`。并且根据比赛要求，编译命令为
```
{rival_compiler} -S -o {gcc_assembly} {source}
```

--on_riscv：可选项，表示本地机器架构是否是 riscv 架构，如果是，则需要将用于链接的编译器（-c 选项）改成 gcc，并且测试程序不会再使用 qemu 运行可执行文件

--store_time：可选项，表示是否存储对手编译器的运行时间。如果是，则会将对手编译器的运行存储到 ./rivals/{rival_compiler}{rival_compiler}.json, 如果已有旧结果，则会覆盖; 如果否，则会尝试寻找旧有结果，如果有就用，没有就重新测量

json 文件格式：
```
{
    "测试文件夹": {
        "测例所生成的汇编代码文件名称": 时间
    }
}
```
例：
```
{
    "./testcases/functional/": {
        "00_main-gcc": 2.4352073669433594,
    }
}
```

### 将编译好的汇编上传到 riscv 开发板上测试


```sh
python test_on_remote.py -t <testcase_folder> [-p] [-b] -r <riscv64-unknown-elf-gcc> [--store_time] --remote_address <ip_address> --remote_port <port>
```

我们假设 riscv 开发板上已经运行了一个后端，它和 [sysyc_tester](https://github.com/rrvm-project/sysyc_tester) 一样有上传文件和运行测试的同名接口。你需要通过 --remote_address 和 --remote_port 指定后端服务器的地址和端口

其余选项同本地测试

由于此时已知运行环境的架构，故用于链接的编译器被指定为 gcc, 并且删去了 --on_riscv 选项


## 测试你的编译器

（以下对 test_on_remote.py 同理）

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

