import asyncio
import json
import logging
import os
import subprocess
from types import SimpleNamespace

import psutil as psutil
from aiohttp import web
from serverhub_agent.utils.filesystem import TempFileManager

AGENT_PORT = os.getenv("PORT")
TIMEOUT = int(os.getenv("TIMEOUT"))
TESTS_PATH = "/home/student"
RESPONSE_LIMIT = 3_500_000


async def run(request: web.Request) -> web.Response:
    body = await request.json()
    files = [
        SimpleNamespace(name=f["name"], content=f["content"]) for f in body["files"]
    ]
    timeout = False
    stdout = b""
    stderr = b""
    return_code = 1
    oom_killed = False

    try:
        async with run_lock:
            with TempFileManager(directory=TESTS_PATH, files=files) as manager:
                try:
                    proc = subprocess.run(
                        (
                            f"cd {manager.directory} && chown -R student {manager.directory} "
                            f"&& su - student -c \"{body['command']}\""
                        ),
                        capture_output=True,
                        timeout=TIMEOUT,
                        shell=True,
                    )
                    stdout = proc.stdout
                    stderr = proc.stderr
                    return_code = proc.returncode

                    logging.info("Command: %s", body['command'])
                    logging.info("FILES %s", files)

                    with open(os.path.join(TESTS_PATH, "author_code.py")) as f:
                        result = f.read()
                        logging.info("author_code.py %s", result)
                    with open(os.path.join(TESTS_PATH, "user_code.py")) as f:
                        result = f.read()
                        logging.info("user_code.py %s", result)

                except subprocess.TimeoutExpired:
                    timeout = True

            # Убиваем все возможные процессы, которые мог запустить пользовательский код (через fork и т.п.)
            subprocess.call("killall -s 9 -u student", shell=True)

    except OSError as ex:
        # Пытаемся починить "OSError: [Errno 12] Cannot allocate memory"
        processes = "\n".join([f"{p.pid}\t{p.name()}\t{' '.join(p.cmdline())}" for p in psutil.process_iter()])
        memory_info = str(psutil.virtual_memory())
        student_files = "\n".join(get_dir_content(TESTS_PATH))
        logging.error(f"OSError. Memory: {memory_info}\n"
                      f"Processes:\n{processes}\n"
                      f"Files:\n{student_files}", exc_info=True)
        oom_killed = True
        if run_lock.locked():
            run_lock.release()

    # Для завершения сервиса в контейнере, при слишком большом количестве зомби-процессов, вероятно, пригодится:
    # raise GracefulExit()

    result = {
            "exit_code": return_code,
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
            "oom_killed": oom_killed,
            "timeout": timeout,
            "duration": 0,
    }

    response = web.json_response(result)

    if response.content_length > RESPONSE_LIMIT:
        try:
            lib_result = json.loads(result["stdout"])
            # Обрезать вывод stdout до ~ 0.5 МБ, т.к. далее возможна конвертация в UTF-8, увеличивающая ответ в 6 раз
            lib_result["stdout"] = lib_result["stdout"][:400_000]
            lib_result["error"] = {"id": "AssertionError.Truncated", "values": {}}  # Меняем ошибку
            result["stdout"] = json.dumps(lib_result)
        except json.JSONDecodeError as ex:
            logging.warning("json.loads exception. Probably picture", exc_info=True)
            result["stdout"] = result["stdout"][:400_000]  # Графика или другой вывод в stdout (не json)

        result["stderr"] = result["stderr"][:50_000]  # Обрезать вывод stderr - до ~ 0.05 МБ
        response = web.json_response(result)

    logging.info(result)
    return response


def get_dir_content(path: str) -> [str]:
    if not os.path.isdir(path):
        return ["Student directory doesn't exist"]

    result = []
    for file in os.listdir(path):
        full_name = os.path.join(path, file)
        if os.path.islink(full_name):
            result.append(f"link\t{os.path.getsize(full_name)}\t{full_name} -> {os.path.realpath(full_name)}")
        elif os.path.isfile(full_name):
            result.append(f"file\t{os.path.getsize(full_name)}\t{full_name}")
        elif os.path.isdir(full_name):
            result.append(f"dir\t{os.path.getsize(full_name)}\t{full_name}")
        else:
            result.append(f"other\t{os.path.getsize(full_name)}\t{full_name}")
    return result


def setup_routes(app: web.Application) -> None:
    app.router.add_post("/run/", run)


# Fix file permission
os.system("chmod a=rx /testlibs && chmod a=rx /testlibs/*")

app = web.Application()
run_lock = asyncio.Lock()
setup_routes(app)
logging.basicConfig(level=logging.DEBUG)


web.run_app(
    app,
    host="0.0.0.0",
    port=AGENT_PORT,
)
