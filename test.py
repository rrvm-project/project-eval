from __future__ import annotations

import os
import json
import subprocess
import sys
import random
import shutil
import time

from argparse import ArgumentParser
from enum import Enum, auto
from glob import glob
from typing import NamedTuple, Optional, Union
import re

from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

TEST_ROUND = 1
TIMEOUT = 120

# NOTE: 在这里修改你的编译器路径和参数。此处的默认值对应着gcc
compiler_path = "./tmp/compiler"
compiler_args = "-O2"
# compiler_args = "-O2 -march=rv32gc -mabi=ilp32f -xc++ -S -include ./runtime/sylib.h"

# 调用gcc进行链接的参数
cc = "riscv64-unknown-elf-gcc"
gcc_args_rv64 = "-march=rv64gc -mabi=lp64d"
gcc_args_rv32 = "-march=rv32gc -mabi=ilp32f"
gcc_args = gcc_args_rv64
rival_compiler = "riscv64-unknown-elf-gcc"
rival_time = None
rival_time_lock = Lock()
cur_testcases = None


class Config(NamedTuple):
    compiler: str
    testcases: str
    compiler_args: str
    tempdir: str
    parallel: bool
    timing: bool
    on_riscv: bool
    store_time: bool
    rival_compiler: str


class Result(Enum):
    LINKER_ERROR = auto()
    PASSED = auto()
    WRONG_ANSWER = auto()
    TIME_LIMIT_EXCEEDED = auto()
    GCC_ERROR = auto()


def geometric_mean(numbers):
    if not numbers:
        return None

    product = 1
    for number in numbers:
        product *= number

    return product ** (1.0 / len(numbers))

def get_config(argv: list[str]) -> Config:
    global cc
    global rival_compiler
    global rival_time
    global cur_testcases
    parser = ArgumentParser('simple-tester')
    parser.add_argument('-t', '--testcases',
                        metavar='<testcases>', required=True,
                        help='path to the directory containing testcases')
    parser.add_argument('-c', '--compiler',
                        metavar='<compiler>', required=True, default="riscv64-unknown-elf-gcc",
                        help='compiler to use for generating executable, on a riscv64 machine, it should just be gcc')
    parser.add_argument('-r', '--rival_compiler',
                        metavar='<rival_compiler>', required=True, default="riscv64-unknown-elf-gcc",
                        help='the name of the compiler to rival')
    parser.add_argument('-p', '--parallel', action='store_true', default=False, help='run parallely')
    parser.add_argument('-b', '--benchmark', action='store_true', default=False, help='benchmark time')
    parser.add_argument("--on_riscv", action='store_true', default=False, help='is on a riscv machine')
    parser.add_argument("--store_time", action='store_true', default=False, help='whether to store time result')
    index: int
    try:
        index = argv.index('--')
    except ValueError:
        index = len(argv)
    args = parser.parse_args(argv[:index])
    cc = args.compiler
    # 如果存在文件 ./args.compiler/args.compiler, 就将这个路径赋值给 cc
    path_to_rival = "./rivals/{}/{}".format(args.rival_compiler, args.rival_compiler)
    if os.path.exists(path_to_rival):
        rival_compiler = path_to_rival
    else:
        rival_compiler = args.rival_compiler
    path_to_rival_time = "./rivals/{}/{}.json".format(args.rival_compiler, args.rival_compiler)
    if not os.path.exists(path_to_rival_time):
        with open(path_to_rival_time, "w") as f:
            json.dump({}, f)
    
    cur_testcases = args.testcases
    if os.path.exists(path_to_rival_time):
        rival_time = json.load(open(path_to_rival_time, "r"))
        rival_time = rival_time.get(args.testcases)
    if rival_time is None:
        rival_time = {}
    return Config(compiler=compiler_path,
                  testcases=args.testcases,
                  compiler_args=compiler_args,
                  tempdir='build',
                  parallel=args.parallel,
                  timing=args.benchmark,
                  on_riscv=args.on_riscv,
                  store_time=args.store_time,
                  rival_compiler=args.rival_compiler
                  )


def get_testcases(config: Config) -> list[str]:
    testcases = [os.path.splitext(os.path.basename(file))[0]
                 for file in glob(os.path.join(config.testcases, '*.sy'))]
    testcases.sort()
    return testcases


def get_answer(file: str) -> tuple[list[str], int]:
    content = [line.strip() for line in open(file).read().splitlines()]
    return content[:-1], int(content[-1])


def get_time(file: str) -> Optional[int]:
    content = open(file).read().splitlines()
    if not content:
        return None
    content = content[-1]
    pattern = r'TOTAL:\s*(\d+)H-(\d+)M-(\d+)S-(\d+)us'
    matches = re.match(pattern, content)
    h, m, s, us = map(int, (matches.group(1), matches.group(2), matches.group(3), matches.group(4)))
    return ((h * 60 + m) * 60 + s) * 1_000_000 + us


def run(
    workdir: str,
    assembly: str,
    input: str,
    answer: str,
    round: int = 1,
    timing: bool = False,
    on_riscv: bool = False
) -> Union[Result, float]:
    name_body = os.path.basename(assembly).split('.')[0]
    executable = os.path.join(workdir, name_body + '.exec')
    output = os.path.join(workdir, name_body + '.stdout')
    outerr = os.path.join(workdir, name_body + '.stderr')
    print(f'{cc} {gcc_args} {assembly} runtime/libsysy.a'
                 f' -o {executable}')
    if os.system(f'{cc} {gcc_args} {assembly} runtime/libsysy.a'
                 f' -o {executable}') != 0:
        return Result.LINKER_ERROR
    print(f'{cc} {gcc_args} {assembly} runtime/libsysy.a'
                 f' -o {executable}')
    answer_content, answer_exitcode = get_answer(answer)
    total_time = 0
    for _ in range(round):
        start_time = time.time()
        proc = subprocess.Popen(
            [executable] if on_riscv else ["qemu-riscv64", executable],
            stdin=open(input) if os.path.exists(input) else None,
            stdout=open(output, 'w'), stderr=open(outerr, 'w'))
        try:
            proc.wait(TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            return Result.TIME_LIMIT_EXCEEDED
        end_time = time.time()
        output_content = [line.strip()
                          for line in open(output).read().splitlines()]
        if proc.returncode != answer_exitcode \
                or output_content != answer_content:
            print(proc.returncode, " ", answer_exitcode, flush=True)
            return Result.WRONG_ANSWER
        # if round > 1:
        #     print('.', end='', flush=True)
        t = end_time - start_time
        if t is None:
            timing = False
        else:
            total_time += t
    if timing:
        return total_time * 1_000 / round
    else:
        return Result.PASSED


def test(config: Config, testcase: str, score_callback = None) -> bool:
    global rival_time
    global rival_time_lock
    source = os.path.join(config.testcases, f'{testcase}.sy')
    input = os.path.join(config.testcases, f'{testcase}.in')
    answer = os.path.join(config.testcases, f'{testcase}.out')

    ident = '%04d' % random.randint(0, 9999)
    assembly = os.path.join(config.tempdir, f'{testcase}-{ident}.s')
    gcc_assembly = os.path.join(config.tempdir, f'{testcase}-gcc.s')
    # NOTE: 你可以在这里修改调用你的编译器的方式
    command = (f'ulimit -s unlimited && {config.compiler} {config.compiler_args} {source}'
                f' -o {assembly}')
    proc = subprocess.Popen(command, shell=True)
    try:
        proc.wait(TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        print(testcase, '\033[0;31mCompiler TLE\033[0m', flush=True)
        return False
    if proc.returncode != 0:
        print(testcase, '\033[0;31mCompiler Error\033[0m', flush=True)
        return False
    result = run(config.tempdir, assembly, input, answer, TEST_ROUND, config.timing, config.on_riscv)
    if result == Result.LINKER_ERROR:
        print(testcase, '\033[0;31mLinker Error\033[0m', flush=True)
        return False
    elif result == Result.WRONG_ANSWER:
        print(testcase, '\033[0;31mWrong Answer\033[0m', flush=True)
        return False
    elif result == Result.TIME_LIMIT_EXCEEDED:
        print(testcase, '\033[0;31mTime Limit Exceeded\033[0m', flush=True)
        return False
    else:
        runtime = result
    # print(' ', end='')
    if not isinstance(runtime, float) or runtime == 0:
        print(testcase, '\033[0;32mPassed\033[0m', flush=True)
        return True
    asm_gen_command = f'{rival_compiler} -xc++ -O2 -S {gcc_args} -include runtime/sylib.h {source} -o {gcc_assembly} '
    if 'gcc' not in config.rival_compiler:
        # 即使用来对比的编译器不是 gcc，这里的变量名也还是 gcc_assembly。别问，问就是懒得改了 :(
        asm_gen_command = f'{rival_compiler} -S -o {gcc_assembly} {source}'
    print(asm_gen_command)
    gcc_result = Result.GCC_ERROR
    name_body = os.path.basename(gcc_assembly).split('.')[0]
    if os.system(asm_gen_command) == 0:
        if not config.store_time:
            rival_time_lock.acquire()
            gcc_result = rival_time.get(name_body)
            rival_time_lock.release()
            if gcc_result is None:
                gcc_result = run(config.tempdir, gcc_assembly, input, answer, TEST_ROUND, config.timing, config.on_riscv)
        else:
            gcc_result = run(config.tempdir, gcc_assembly, input, answer, TEST_ROUND, config.timing, config.on_riscv)
        
    if isinstance(gcc_result, Result):
        print(testcase, '\033[0;31mGCC Error\033[0m', flush=True)
    else:
        if config.store_time:
            rival_time_lock.acquire()
            rival_time[name_body] = gcc_result
            rival_time_lock.release()
        print(testcase, f'\033[0;32m{runtime :.3f}ms / {gcc_result :.3f}ms'
                f' => {gcc_result / runtime :.2%}\033[0m', flush=True)
        
        score = min(gcc_result / runtime * 100, 100)
        if score_callback is not None:
            score_callback(testcase, score)
    return True


if __name__ == '__main__':
    config = get_config(sys.argv[1:])
    testcases = get_testcases(config)

    if os.path.exists(config.tempdir):
        shutil.rmtree(config.tempdir)
    os.mkdir(config.tempdir)

    score_info = []
    scores_lock = Lock()
    def add_score(testcase, score):
        scores_lock.acquire()
        score_info.append((testcase, score))
        scores_lock.release()
    score_callback = add_score if config.timing else None

    failed = []
    if config.parallel:
        futures = []
        f = lambda t: (t, test(config, t, score_callback))
        with ThreadPoolExecutor() as executor:
            for testcase in testcases:
                futures.append(executor.submit(f, testcase))
            for future in as_completed(futures):
                testcase, ok = future.result()
                if not ok:
                    failed.append(testcase)
        failed.sort()
    else:
        for testcase in testcases:
            if not test(config, testcase, score_callback):
                failed.append(testcase)
    info = '\033[0;34m[info]\033[0m {}'
    if config.store_time:
        with open(f'./rivals/{config.rival_compiler}/{config.rival_compiler}.json', 'r') as f:
            rival_times = json.load(f)
        if rival_time is None:
            rival_time = {}
        with open(f'./rivals/{config.rival_compiler}/{config.rival_compiler}.json', 'w') as f:
            rival_times[config.testcases] = rival_time
            json.dump(rival_times, f)
    if not failed:
        print(info.format('All Passed'), flush=True)

        if config.timing:
            mean_score = geometric_mean([t[1] for t in score_info])
            print("final score:", mean_score, flush=True)
    else:
        for testcase in failed:
            print(info.format(f'`{testcase}` Failed'), flush=True)
    assert not failed, "Test Fail"
