import os
import subprocess
import sys

from argparse import ArgumentParser
from enum import Enum, auto
from glob import glob
from tempfile import TemporaryDirectory
from typing import NamedTuple, Optional, Union
import re

TEST_ROUND = 1
TIMEOUT = 120

compiler_path = "riscv64-unknown-elf-gcc"
compiler_args = "-march=rv64gc -mabi=lp64f -xc++ -S -include ./runtime/sylib.h"

gcc_args = "-march=rv64gc -mabi=lp64f"

class Config(NamedTuple):
    compiler: str
    testcases: str
    compiler_args: str


class Result(Enum):
    LINKER_ERROR = auto()
    PASSED = auto()
    WRONG_ANSWER = auto()
    TIME_LIMIT_EXCEEDED = auto()
    GCC_ERROR = auto()

def get_config(argv: list[str]) -> Config:
    parser = ArgumentParser('simple-tester')
    parser.add_argument('-t', '--testcases',
                        metavar='<testcases>', required=True,
                        help='path to the directory containing testcases')
    index: int
    try:
        index = argv.index('--')
    except ValueError:
        index = len(argv)
    args = parser.parse_args(argv[:index])
    return Config(compiler=compiler_path,
                  testcases=args.testcases,
                  compiler_args=compiler_args)


def get_testcases(config: Config) -> list[str]:
    testcases = [os.path.splitext(os.path.basename(file))[0]
                 for file in glob(os.path.join(config.testcases, '*.sy'))]
    testcases.sort()
    return testcases


def get_answer(file: str) -> tuple[list[str], int]:
    content = [line.strip() for line in open(file).read().strip().splitlines()]
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
    assemble: str,
    input: str,
    answer: str,
    round: int
) -> Union[Result, float]:
    executable = os.path.join(workdir, 'main')
    output = os.path.join(workdir, 'output')
    time = os.path.join(workdir, 'time')
    if os.system(f'riscv64-unknown-elf-gcc {gcc_args} {assemble} runtime/libsysy.a'
                 f' -o {executable}') != 0:
        return Result.LINKER_ERROR
    answer_content, answer_exitcode = get_answer(answer)
    average_time = 0
    timing = True
    for _ in range(round):
        proc = subprocess.Popen(
            executable,
            stdin=open(input) if os.path.exists(input) else None,
            stdout=open(output, 'w'), stderr=open(time, 'w'))
        try:
            proc.wait(TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            return Result.TIME_LIMIT_EXCEEDED
        output_content = [line.strip()
                          for line in open(output).read().strip().splitlines()]
        if proc.returncode != answer_exitcode \
                or output_content != answer_content:
            return Result.WRONG_ANSWER
        if round > 1:
            print('.', end='', flush=True)
        t = get_time(time)
        if t is None:
            timing = False
        else:
            average_time += t
    if timing:
        return average_time / 1_000 / TEST_ROUND
    else:
        return Result.PASSED


def test(config: Config, testcase: str) -> bool:
    if os.path.exists("./tmp"):
        os.system("rm -r ./tmp")
    os.mkdir("./tmp")
    tempdir = "./tmp"
    print(testcase, end=': ', flush=True)
    source = os.path.join(config.testcases, f'{testcase}.sy')
    input = os.path.join(config.testcases, f'{testcase}.in')
    answer = os.path.join(config.testcases, f'{testcase}.out')
    assemble = os.path.join(tempdir, 'asm.s')
    command = (f'{config.compiler} {config.compiler_args} {source}'
                f' -o {assemble}')
    proc = subprocess.Popen(command, shell=True)
    try:
        proc.wait(TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        print('\033[0;31mCompiler TLE\033[0m')
        return False
    if proc.returncode != 0:
        print('\033[0;31mCompiler Error\033[0m')
        return False
    result = run(tempdir, assemble, input, answer, TEST_ROUND)
    if result == Result.LINKER_ERROR:
        print('\033[0;31mLinker Error\033[0m')
        return False
    elif result == Result.WRONG_ANSWER:
        print('\033[0;31mWrong Answer\033[0m')
        return False
    elif result == Result.TIME_LIMIT_EXCEEDED:
        print('\033[0;31mTime Limit Exceeded\033[0m')
        return False
    else:
        runtime = result
    print(' ', end='')
    if not isinstance(runtime, float) or runtime == 0:
        print('\033[0;32mPassed\033[0m')
        return True
    result = Result.GCC_ERROR \
        if os.system(
            f'riscv64-unknown-elf-gcc -xc++ -O2 -S {gcc_args}'
            f' -include runtime/sylib.h {source} -o {assemble} ') != 0 \
        and os.system(
            f'riscv64-unknown-elf-gcc -xc++ -O2 -S {gcc_args}'
            f' -include runtime/sylib.h {source} -o {assemble}') != 0 \
        else run(tempdir, assemble, input, answer, 1)
    if isinstance(result, Result):
        print('\033[0;31mGCC Error\033[0m')
    else:
        print(f'\033[0;32m{runtime :.3f}ms / {result :.3f}ms'
                f' = {result / runtime :.2%}\033[0m')
    return True


if __name__ == '__main__':
    config = get_config(sys.argv[1:])
    testcases = get_testcases(config)
    failed = []
    for testcase in testcases:
        if not test(config, testcase):
            failed.append(testcase)
    info = '\033[0;34m[info]\033[0m {}'
    if not failed:
        print(info.format('All Passed'))
    else:
        for testcase in failed:
            print(info.format(f'`{testcase}` Failed'))