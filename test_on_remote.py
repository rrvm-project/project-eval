from __future__ import annotations

import os
import json
import subprocess
import sys
import random
import shutil
import time
import uuid

from argparse import ArgumentParser
from enum import Enum, auto
from glob import glob
from typing import NamedTuple, Optional, Union
import re
import requests

from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

TEST_ROUND = 1
TIMEOUT = 120

# NOTE: 在这里修改你的编译器路径。
compiler_path = "../target/release/compiler"

# 调用gcc进行链接的参数
gcc_args_rv64 = "-march=rv64gc -mabi=lp64d"
gcc_args_rv32 = "-march=rv32gc -mabi=ilp32f"
gcc_args = gcc_args_rv64

rival_compiler = "gcc"
rival_time = None
rival_time_lock = Lock()
config: Config = None
remote_url = None

folder = str(uuid.uuid4())

class Config(NamedTuple):
    compiler: str
    testcases: str
    optimize_level: str
    tempdir: str
    parallel: bool
    timing: bool
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

# 计算算术平均数
def arithmetic_mean(numbers):
    if not numbers:
        return None

    return sum(numbers) / len(numbers)

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
    assembly: str,
    input: str,
    answer: str,
    timing: bool = False,
) -> Union[Result, float]:
    global folder
    name_body = os.path.basename(assembly).split('.')[0]
    name_body_without_suffix = os.path.basename(answer).split('.')[0]
    
    json_data = {
        "folder": folder,
        "name": name_body,
        "name_without_suffix": name_body_without_suffix
    }
    response = requests.post(remote_url + "run", json=json_data)
    if response.status_code != 200:
        json_result = response.json()
        if json_result["code"] == 1:
            return Result.LINKER_ERROR
        elif json_result["code"] == 2:
            return Result.WRONG_ANSWER
        else:
            return 0
    json_result = response.json()
    t = float(json_result["time"])
    if timing:
        return t
    else:
        return Result.PASSED

def test(config: Config, testcase: str, score_callback = None) -> str:
    global rival_time
    global rival_time_lock
    global gcc_args
    global remote_url
    source = os.path.join(config.testcases, f'{testcase}.sy')
    input = os.path.join(config.testcases, f'{testcase}.in')
    answer = os.path.join(config.testcases, f'{testcase}.out')

    ident = '%04d' % random.randint(0, 9999)
    assembly = os.path.join(config.tempdir, f'{testcase}-{ident}.s')
    gcc_assembly = os.path.join(config.tempdir, f'{testcase}-gcc.s')
    # NOTE: 你可以在这里修改调用你的编译器的方式
    command = (f'ulimit -s unlimited && {config.compiler} -O{config.optimize_level} {source}'
                f' -o {assembly}')
    proc = subprocess.Popen(command, shell=True)
    try:
        proc.wait(TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        print(testcase, '\033[0;31mCompiler TLE\033[0m', flush=True)
        return '\033[0;31mCompiler TLE\033[0m'
    if proc.returncode != 0:
        print(testcase, '\033[0;31mCompiler Error\033[0m', flush=True)
        return '\033[0;31mCompiler Error\033[0m'
    
    name_body = os.path.basename(assembly).split('.')[0]
    
    url = remote_url + f"upload?folder={folder}"
    asm = open(assembly, 'rb')
    files = {
        'asm': asm,
    }
    if os.path.exists(input):
        files["input"] = open(input, 'rb')
    if os.path.exists(answer):
        files["answer"] = open(answer, 'rb')
    requests.post(url=url, files=files)
    for f in files.values():
        f.close()
        
    result = run(assembly, input, answer, config.timing)
    if result == Result.LINKER_ERROR:
        print(testcase, '\033[0;31mLinker Error\033[0m', flush=True)
        return '\033[0;31mLinker Error\033[0m'
    elif result == Result.WRONG_ANSWER:
        print(testcase, '\033[0;31mWrong Answer\033[0m', flush=True)
        return '\033[0;31mWrong Answer\033[0m'
    elif result == Result.TIME_LIMIT_EXCEEDED:
        print(testcase, '\033[0;31mTime Limit Exceeded\033[0m', flush=True)
        return '\033[0;31mTime Limit Exceeded\033[0m'
    else:
        runtime = result
    # print(' ', end='')
    if not isinstance(runtime, float) or runtime == 0:
        print(testcase, '\033[0;32mPassed\033[0m', flush=True)
        return 'Passed'
    
    name_body = os.path.basename(gcc_assembly).split('.')[0]
    gcc_result = Result.GCC_ERROR
    if not config.store_time:
        rival_time_lock.acquire()
        gcc_result = rival_time.get(name_body)
        rival_time_lock.release()
        if gcc_result is None:
            asm_gen_command = f'{rival_compiler} -S -o {gcc_assembly} {source}'
            flag = False
            if 'gcc' == config.rival_compiler:        
                url = remote_url + f"upload?folder={folder}"
                source_file = open(source, 'rb')
                files = {
                    'source': source_file,
                }
                requests.post(url=url, files=files)
                source_file.close()
                files = {
                    "folder": folder,
                    "name": os.path.basename(source).split('.')[0],
                    "name_without_suffix": ""
                }
                resp = requests.post(remote_url + "compile", json=files)
                flag |= (resp.status_code == 200)
            else:
                flag |= os.system(asm_gen_command) == 0
                asm = open(gcc_assembly, 'rb')
                files = {
                    'asm': asm,
                }
                requests.post(url=url, files=files)
                for f in files.values():
                    f.close()
            gcc_result = run(gcc_assembly, input, answer, config.timing)
    else:
        asm_gen_command = f'{rival_compiler} -S -o {gcc_assembly} {source}'
        flag = False
        if 'gcc' == config.rival_compiler:        
            url = remote_url + f"upload?folder={folder}"
            source_file = open(source, 'rb')
            files = {
                'source': source_file,
            }
            requests.post(url=url, files=files)
            source_file.close()
            files = {
                "folder": folder,
                "name": os.path.basename(source).split('.')[0],
                "name_without_suffix": ""
            }
            resp = requests.post(remote_url + "compile", json=files)
            flag |= (resp.status_code == 200)
        else:
            flag |= os.system(asm_gen_command) == 0
            asm = open(gcc_assembly, 'rb')
            files = {
                'asm': asm,
            }
            requests.post(url=url, files=files)
            for f in files.values():
                f.close()
        gcc_result = run(gcc_assembly, input, answer, config.timing)
    
        
    if isinstance(gcc_result, Result):
        print(testcase, '\033[0;31mGCC Error\033[0m', flush=True, end=" ")
        if gcc_result == Result.LINKER_ERROR:
            print('\033[0;31mLinker Error\033[0m', flush=True)
        elif gcc_result == Result.WRONG_ANSWER:
            print('\033[0;31mWrong Answer\033[0m', flush=True)
        elif gcc_result == Result.TIME_LIMIT_EXCEEDED:
            print('\033[0;31mTime Limit Exceeded\033[0m', flush=True)
        return '\033[0;31mGCC Error\033[0m'
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
    return 'Passed'

def get_config(argv: list[str]) -> Config:
    global rival_compiler
    global rival_time
    global remote_url
    parser = ArgumentParser('simple-tester')
    parser.add_argument('-t', '--testcases',
                        metavar='<testcases>', required=True,
                        help='path to the directory containing testcases')
    parser.add_argument('-r', '--rival_compiler',
                        metavar='<rival_compiler>', required=True, default="gcc",
                        help='the name of the compiler to rival')
    parser.add_argument('--remote_address',
                        metavar='<remote_address>', required=True,
                        help='remote address for running executables')
    parser.add_argument('--remote_port',
                        metavar='<remote_port>', required=True,
                        help='remote port for running executables')
    parser.add_argument('-O', '--optimize_level', required=True, default="2", help='the optimize level of the compiler')
    parser.add_argument('-p', '--parallel', action='store_true', default=False, help='run parallely')
    parser.add_argument('-b', '--benchmark', action='store_true', default=False, help='benchmark time')
    parser.add_argument("--store_time", action='store_true', default=False, help='whether to store time result')
    index: int
    try:
        index = argv.index('--')
    except ValueError:
        index = len(argv)
    args = parser.parse_args(argv[:index])
    # 如果存在文件 ./args.compiler/args.compiler, 就将这个路径赋值给 rival_compiler
    path_to_rival = "./rivals/{}/{}".format(args.rival_compiler, args.rival_compiler)
    if os.path.exists(path_to_rival):
        rival_compiler = path_to_rival
    else:
        rival_compiler = args.rival_compiler
    path_to_rival_time = "./rivals/{}/{}.json".format(args.rival_compiler, args.rival_compiler)
    if not os.path.exists(path_to_rival_time):
        with open(path_to_rival_time, "w") as f:
            json.dump({}, f)
    
    if os.path.exists(path_to_rival_time):
        rival_time = json.load(open(path_to_rival_time, "r"))
        rival_time = rival_time.get(args.testcases)
    if rival_time is None:
        rival_time = {}
        
    remote_url = f"http://{args.remote_address}:{args.remote_port}/"
    return Config(compiler=compiler_path,
                  testcases=args.testcases,
                  optimize_level=args.optimize_level,
                  tempdir='build',
                  parallel=args.parallel,
                  timing=args.benchmark,
                  store_time=args.store_time,
                  rival_compiler=args.rival_compiler
                  )

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
                if ok != 'Passed':
                    failed.append('`' + testcase + "` " + ok)
        failed.sort()
    else:
        for testcase in testcases:
            result = test(config, testcase, score_callback)
            if result != 'Passed':
                failed.append('`' + testcase + "` " + result)
    if remote_url is not None:
        requests.post(remote_url + f"clean?folder={folder}")
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
            mean_score = arithmetic_mean([t[1] for t in score_info])
            print("final score:", mean_score, flush=True)
    else:
        for testcase in failed:
            print(info.format(f'{testcase}'), flush=True)
    assert not failed, "Test Fail"
