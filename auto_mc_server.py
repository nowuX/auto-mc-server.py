"""Main python script"""
import importlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from urllib.request import urlopen

import requests
from colorlog import ColoredFormatter

MOJANG_VERSIONS_MANIFEST = 'https://launchermeta.mojang.com/mc/game/version_manifest_v2.json'
CARPET_112 = 'https://gitlab.com/Xcom/carpetinstaller/uploads/24d0753d3f9a228e9b8bbd46ce672dbe/carpetInstaller.jar'
FABRIC_URL = 'https://maven.fabricmc.net/net/fabricmc/fabric-installer/0.11.0/fabric-installer-0.11.0.jar'
FORGE_URL = 'https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json'
FORGE_URL_2 = 'https://maven.minecraftforge.net/net/minecraftforge/forge/'
QUILT_URL = 'https://maven.quiltmc.org/repository/release/org/quiltmc/quilt-installer/latest/quilt-installer-latest.jar'
PAPER_URL = 'https://api.papermc.io/v2/projects/paper/'
MINECRAFT = ''
MCDR = 'mcdreforged'  # Global mcdr package name


class ScriptLogger(logging.Logger):
    """Main Class for script Logging"""

    def __init__(self):
        super().__init__('Script')
        self.input = 24
        logging.addLevelName(self.input, 'INPUT')
        formatter = ColoredFormatter(
            '%(log_color)s[%(name)s] %(levelname)-8s:%(reset)s %(message)s',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'bold_red',
                'INPUT': 'blue',
            },
            datefmt='%H:%M:%S',
            reset=True
        )
        self.console_handler = logging.StreamHandler()
        self.console_handler.setFormatter(formatter)
        self.console_handler.setLevel(logging.DEBUG)
        self.addHandler(self.console_handler)
        self.setLevel(logging.INFO)


def input_logger(msg: str):
    """Create a logger for user input

    :param msg: Message to display in console
    :return: 0
    """
    _input_logger = ScriptLogger()
    _input_logger.console_handler.terminator = ''
    _input_logger.setLevel('INPUT')
    _input_logger.log(_input_logger.input, msg)
    return 0


def subprocess_logger(args: list, stderr: bool = True, stdout: bool = True, exit_in_error: bool = True):
    """Create a logger to print all subprocess.Popen()

    :param args: Arguments to execute.
    :param stderr: Print stderr output. Defaults to True.
    :param stdout: Print stdout output. Defaults to True.
    :param exit_in_error: Error in subprocess cause a sys.exit(1). Defaults to True.
    :return: 0
    """
    sp_logger = ScriptLogger()
    sp_logger.name = '$'
    sp_logger.console_handler.setFormatter(
        ColoredFormatter('%(log_color)s%(name)s : %(reset)s%(message)s',
                         log_colors={'DEBUG': 'bold', 'ERROR': 'bold_red'},
                         reset=True))
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
        if stdout:
            with process.stdout as _stdout:
                for line in iter(_stdout.readline, b''):
                    sp_logger.debug(line.decode('utf-8').strip())
        if stderr:
            with process.stderr as _stderr:
                for line in iter(_stderr.readline, b''):
                    sp_logger.error(line.decode('utf-8').strip())
        process.wait()
        if process.returncode != 0 and exit_in_error:
            logger.error('Something failed in subprocess execution')
            return sys.exit(1)
    return 0


def check_environment() -> str:
    """Function to validate each script requirement

    :return: Python global command.
    """
    logger.debug('Check environment...')
    py_cmd: str
    match sys.platform:
        case 'win32':
            logger.debug('')
            py_cmd = 'python'
        case 'linux':
            py_cmd = 'python3'
        case _:
            logger.error('OS %s is currently not supported', sys.platform)
            return sys.exit(0)
    major_version, minor_version = sys.version_info.major, sys.version_info.minor
    if major_version < 3 or (major_version == 3 and minor_version < 10):
        logger.warning('Python 3.10+ is needed')
        return sys.exit(0)

    try:
        subprocess_logger(['java', '-version'], stderr=False)
    except FileNotFoundError:
        logger.warning('Java is needed')
        logger.error('System can\'t find java')
        return sys.exit(0)

    try:
        importlib.import_module(MCDR)
    except ImportError:
        logger.error('MCDReforged packaged not detected')
        logger.warning('Installing MCDReforged...')
        subprocess_logger([py_cmd, '-m', 'pip', 'install', MCDR])
    return py_cmd


def simple_yes_no(question: str, default_no=True) -> bool:
    """Make a simple yes or no question

    :param question: Question to display in console.
    :param default_no: Is the answer no by default?. Defaults to True.
    :return: Boolean.
    """
    while True:
        choices = ' [y/N]: ' if default_no else ' [Y/n]: '
        input_logger(question + choices)
        ans = input().lower().strip()
        match ans[:1]:
            case '':
                return not bool(default_no)
            case 'yes' | 'y':
                return True
            case 'no' | 'n':
                return False
            case _:
                logger.warning('%s is an invalid answer, please try again', ans)


def mk_folder():
    """Create a folder for server install

    :return: 0
    """
    input_logger('Enter the server folder name [minecraft_server]: ')
    folder: str = re.sub(r'\W', '', input().replace(' ', '_'))

    if not folder:
        folder = 'minecraft_server'
    if os.path.exists(folder):
        logger.warning('Folder already exists')
        return sys.exit(0)

    try:
        logger.info('Making folder: %s...', folder)
        os.mkdir(folder)
        os.chdir(folder)
        return 0
    except OSError:
        logger.error('Something failed while the folder was being created')
        return sys.exit(1)


def get_last_release() -> str:
    """Get last Minecraft Server Release

    :return: Last Release
    """
    with urlopen(MOJANG_VERSIONS_MANIFEST) as response:
        return json.loads(response.read())['latest']['release']


def vanilla_loader() -> str:
    """Function to install the Vanilla Loader

    :return: Server jar name.
    """
    logger.debug('Vanilla Loader setup')
    while True:
        input_logger('Which minecraft version do you want to use? [latest]: ')
        minecraft: str = input().strip()
        minecraft = get_last_release() if not minecraft else minecraft
        tmp = minecraft.split('.')
        major, minor = int(tmp[1]), int(tmp[2]) if len(tmp) == 3 else 0
        is_invalid = major < 2 or (major == 2 and minor < 5)
        if is_invalid:
            logger.warning('This version is currently unsupported by the script')
            return sys.exit(1)

        if re.match(r'[\d.]', minecraft):
            logger.info('Version selected: %s', minecraft)
            logger.info('Downloading vanilla loader...')
            try:
                with urlopen(MOJANG_VERSIONS_MANIFEST) as response:
                    versions_json = json.loads(response.read())['versions']
                for index, version in enumerate(versions_json):
                    if version['id'] == minecraft:
                        url = version['url']
                        with urlopen(url) as response:
                            version_json = json.loads(response.read())
                        server_url: str = version_json['downloads']['server']['url']
                        server_file = list(server_url.split('/'))[6]
                        response = requests.get(server_url, allow_redirects=True)
                        with open(server_file, 'wb') as file:
                            file.write(response.content)
                        globals()['MINECRAFT'] = minecraft
                        logger.info('Vanilla server installation complete')
                        return server_file.replace('.jar', '')
                    if index == (len(versions_json) - 1):
                        logger.warning('Version not found in Mojang manifest!')
                        break

            except requests.exceptions.RequestException as err:
                logger.error('Something failed: %s', err)
                return sys.exit(1)
        else:
            logger.warning('Version provided contain invalid characters')


def fabric_loader() -> str:
    """Function to install the Fabric Loader

    :return: Server jar name.
    """
    logger.debug('Fabric Loader setup')
    installer = str(list(FABRIC_URL.split('/'))[7])
    logger.info('Downloading fabric loader...')
    try:
        response = requests.get(FABRIC_URL, allow_redirects=True)
        with open(installer, 'wb') as file:
            file.write(response.content)
        while True:
            input_logger('Which version of Minecraft do you want to use? [latest]: ')
            minecraft: str = input().strip()
            input_logger('Which version of Fabric Loader do you want to use? [latest]: ')
            fabric_version: str = input().strip()

            if minecraft and bool(re.match(r'[^\d.]', minecraft)):
                logger.warning('Minecraft version provided contain invalid characters')
                continue
            if fabric_version and bool(re.match(r'[^\d.]', fabric_version)):
                logger.warning('Loader version provided contain invalid characters')
                continue
            break

        logger.info('Minecraft version selected: %s', 'latest' if not minecraft else minecraft)
        logger.info('Fabric loader version selected: %s', 'latest' if not fabric_version else fabric_version)
        logger.debug('Installing fabric server...')
        _download_mc: str = '-downloadMinecraft'
        if not minecraft and not fabric_version:
            subprocess_logger(
                ['java', '-jar', installer, 'server', _download_mc])
        elif minecraft and not fabric_version:
            subprocess_logger(
                ['java', '-jar', installer, 'server', '-mcversion', minecraft, _download_mc])
        elif not minecraft and fabric_version:
            subprocess_logger(
                ['java', '-jar', installer, 'server', '-loader', fabric_version, _download_mc])
        elif minecraft and fabric_version:
            subprocess_logger(
                ['java', '-jar', installer, 'server', '-mcversion', minecraft, '-loader', fabric_version, _download_mc])
        logger.info('Fabric server installation complete')
        os.remove(installer)
        globals()['MINECRAFT'] = minecraft
        return 'fabric-server-launch'
    except ValueError as err:
        logger.error('Something failed: %s', err)
        return sys.exit(1)
    except requests.exceptions.RequestException as err:
        logger.error('Something failed: %s', err)
        return sys.exit(1)


def forge_loader() -> str:
    """Function to install the Forge Loader

    :return: Server jar name.
    """
    logger.debug('Forge Loader setup')
    logger.info('Downloading Forge Loader...')
    while True:
        input_logger('Which minecraft version do you want to use? [latest]: ')
        minecraft: str = input().strip()
        minecraft = get_last_release() if not minecraft else minecraft
        if not re.match(r'[\d.]', minecraft):
            logger.error('Version provided contain invalid characters')
            continue

        logger.info('Version selected: %s', minecraft)
        logger.info('Downloading forge loader...')
        try:
            with urlopen(FORGE_URL) as response:
                versions_json = json.loads(response.read())['promos']
            for index, version_raw in enumerate(versions_json):
                version_raw: str = version_raw.replace('-latest', '').replace('-recommended', '')
                if version_raw == minecraft:
                    if simple_yes_no('Do you want to use latest forge build?', default_no=False):
                        version = f'{version_raw}-latest'
                    else:
                        version = f'{version_raw}-recommended'
                    logger.debug('Using %s forge version', version)
                    build = versions_json[version]
                    version_build = f'{version_raw}-{build}'
                    server_file = f'forge-{version_build}-installer.jar'
                    server_url = f'{FORGE_URL_2}{version_build}/{server_file}'
                    response = requests.get(server_url, allow_redirects=True)
                    with open(server_file, 'wb') as file:
                        file.write(response.content)
                    subprocess_logger(['java', '-jar', server_file, '--installServer'])
                    os.remove(server_file)
                    os.remove(f'{server_file}.log')
                    globals()['MINECRAFT'] = minecraft

                    logger.info('Forge server installation complete')
                    return server_file.replace('.jar', '')
                if index == (len(versions_json) - 1):
                    logger.warning('Version not found in ForgeFiles!')
                    break
        except requests.exceptions.RequestException as err:
            logger.error('Something failed: %s', err)
            return sys.exit(1)
        except KeyError as err:
            logger.error('%s is a invalid build index!', err)


def quilt_loader() -> str:
    """Function to install the Quilt Loader

    :return: Server jar name.
    """
    logger.debug('Quilt Loader setup')
    installer = str(list(QUILT_URL.split('/'))[9])
    logger.info('Downloading quilt loader...')
    try:
        os.chdir('..')
        response = requests.get(QUILT_URL, allow_redirects=True)
        with open(installer, 'wb') as file:
            file.write(response.content)
        while True:
            input_logger('Which version of Minecraft do you want to use? [latest]: ')
            minecraft: str = input().strip()
            minecraft = get_last_release() if not minecraft else minecraft
            if bool(re.match(r'[^\d.]', minecraft)):
                logger.warning('Minecraft version provided contain invalid characters!')
                continue
            break

        logger.info('Minecraft version selected: %s', 'latest' if not minecraft else minecraft)
        logger.debug('Installing quilt server...')

        while True:
            subprocess_logger(
                ['java', '-jar', installer, 'install', 'server', minecraft, '--download-server'])
            if os.path.isfile(r'./server/server.jar'):
                break
            logger.warning('Server.jar not found, re-installing Quilt loader...')
        logger.info('Quilt server installation complete')
        os.remove(installer)
        os.chdir('server')
        globals()['MINECRAFT'] = minecraft
        return 'quilt-server-launch'
    except ValueError as err:
        logger.error('Something failed: %s', err)
        return sys.exit(1)
    except requests.exceptions.RequestException as err:
        logger.error('Something failed: %s', err)
        return sys.exit(1)


def carpet112_setup() -> str:
    """Function to install and setup Carpet112

    :return: Server jar name.
    """
    logger.debug('Carpet 1.12 loader setup')
    globals()['MINECRAFT'] = '1.12.2'
    try:
        logger.info('Downloading carpet112...')
        response = requests.get(CARPET_112, allow_redirects=True)
        carpet_installer: str = CARPET_112.split('/')[7]
        with open(carpet_installer, 'wb') as file:
            file.write(response.content)
        subprocess_logger(['java', '-jar', carpet_installer])
        os.chdir('update')
        carpet_name: str = ''
        for file in os.listdir(os.getcwd()):
            if file.endswith('.zip'):
                carpet_name = file.replace('zip', 'jar')
        shutil.move(carpet_name, '..')
        os.chdir('..')
        os.rename(carpet_name, 'server.jar')
        os.remove(carpet_installer)
        shutil.rmtree('update')
        logger.info('Carpet112 server installation complete')
        return 'server'
    except requests.exceptions.RequestException as err:
        logger.error('Something failed: %s', err)
        return sys.exit(1)
    except OSError as err:
        logger.error('Something failed: %s', err)
        return sys.exit(1)


def paper_loader() -> str:
    """Function to install the Paper Loader

    :return: Server jar name.
    """
    logger.debug('Paper Loader setup')
    while True:
        input_logger('Which minecraft version do you want to use? [latest]: ')
        minecraft: str = input().strip()
        minecraft = get_last_release() if not minecraft else minecraft
        if re.match(r'[\d.]', minecraft):
            logger.info('Version selected: %s', minecraft)
            logger.info('Downloading paper loader...')
            try:
                with urlopen(PAPER_URL) as response:
                    versions_json = json.loads(response.read())['versions']
                for index, version in enumerate(versions_json):
                    if version == minecraft:
                        logger.debug('Version found')
                        temp_url = f'{PAPER_URL}versions/{minecraft}/builds/'
                        with urlopen(temp_url) as response:
                            version_json = json.loads(response.read())
                        build: str = version_json['builds'][-1]['build']
                        server_file: str = version_json['builds'][-1]['downloads']['application']['name']
                        server_url = f'{temp_url}{build}/downloads/{server_file}/'
                        response = requests.get(server_url, allow_redirects=True)
                        with open(server_file, 'wb') as file:
                            file.write(response.content)
                        globals()['MINECRAFT'] = minecraft
                        logger.info('Paper server installation complete')
                        return server_file.replace('.jar', '')
                    if index == (len(versions_json) - 1):
                        logger.warning('Version not found in PaperMC!')
                        break
            except requests.exceptions.RequestException as err:
                logger.error('Something failed: %s', err)
                return sys.exit(1)
        else:
            logger.warning('Version provided contain invalid characters')


def loader_setup(loader: int) -> str:
    """Run function to each loader

    :param loader: Server loader.
    :return: Server loader jar name.
    """
    server_file: str
    match loader:
        case 1:
            server_file = vanilla_loader()
        case 2:
            server_file = fabric_loader()
        # case 3:
        #     server_file = forge_loader()
        case 4:
            server_file = quilt_loader()
        case 5:
            server_file = carpet112_setup()
        case 6:
            server_file = paper_loader()
        case _:
            logger.error('Invalid loader option %s', loader)
            return sys.exit(1)
    return server_file


def launch_scripts(cmd: str):
    """Create server launch scripts to Windows and Linux systems

    :param cmd: Command to put in the launch script.
    :return: 0
    """
    logger.info('Creating launch scripts...')
    try:
        with open('start.bat', 'w', encoding='utf-8') as file:
            file.write(f'@echo off\n{cmd}\n')
        with open('start.sh', 'w', encoding='utf-8') as file:
            file.write(f'#!\\bin\\bash\n{cmd}\n')
        if sys.platform == 'linux':
            subprocess_logger(['chmod', '+x', 'start.sh'])
        return 0
    except FileNotFoundError as err:
        logger.error('Something failed while generating the scripts: %s', err)
        return sys.exit(1)


def mcdr_setup(loader: int, py_cmd: str):
    """Function to install and configure MCDReforged

    :param loader: Server loader.
    :param py_cmd: Python global command.
    :return: 0
    """
    logger.debug('MCDR setup')
    logger.info('Using MCDR!')
    subprocess_logger([py_cmd, '-m', MCDR, 'init'])
    os.chdir('server')
    jar_name = loader_setup(loader)
    os.chdir('..')
    try:
        with open('config.yml', 'r', encoding='utf-8') as file:
            data = file.readlines()
            data[19] = f'start_command: {start_command(jar_name)}\n'
        with open('config.yml', 'w', encoding='utf-8') as file:
            file.writelines(data)
        input_logger('Set the nickname of the server owner? [Skip]: ')
        nickname: str = input().strip()
        if nickname:
            logger.info('Nickname to set: %s', nickname)
            with open('permission.yml', 'r', encoding='utf-8') as file:
                data = file.readlines()
                data[13] = f'- {nickname}\n'
            with open('permission.yml', 'w', encoding='utf-8') as file:
                file.writelines(data)
        return 0
    except FileNotFoundError as err:
        logger.error('Something failed: %s', err)
        return sys.exit(1)


def start_command(jar_name: str) -> str:
    """Return a string with the launch command

    :param jar_name: Server jar name.
    :return: String with launch command.
    """
    return f'java -Xms1G -Xmx2G -jar {jar_name}.jar nogui'


def post_setup(is_mcdr: bool = False, python: str = None, jar_file: str = None):
    """Create server launch scripts, version filter and try to start the server

    :param is_mcdr: Check if is a MCDR environment. Defaults to False.
    :param python: Python global command. Defaults to None.
    :param jar_file: Server jar name. Defaults to None.
    :return: 0
    """
    if is_mcdr:
        launch_scripts(f'{python} -m mcdreforged start')
    else:
        launch_scripts(start_command(jar_file))

    tmp = MINECRAFT.split('.')
    major, minor = int(tmp[1]), int(tmp[2]) if len(tmp) == 3 else 0
    is_invalid = major < 7 or (major == 7 and minor < 10)
    if is_invalid:
        logger.warning('Minecraft version too old, EULA does not exists')
        return 0

    if simple_yes_no('Do you want to start the server and set EULA=true?'):
        logger.info('Starting the server for the first time')
        logger.info('May take some time...')
        try:
            if is_mcdr:
                with open('config.yml', 'r', encoding='utf-8') as file:
                    data = file.readlines()
                    data[77] = 'disable_console_thread: true\n'
                with open('config.yml', 'w', encoding='utf-8') as file:
                    file.writelines(data)
            match sys.platform:
                case 'win32':
                    subprocess_logger([r'start.bat'])
                case 'linux':
                    subprocess_logger([r'./start.sh'])
            logger.info('First time server start complete')
            if is_mcdr:
                with open('config.yml', 'r', encoding='utf-8') as file:
                    data = file.readlines()
                    data[77] = 'disable_console_thread: false\n'
                with open('config.yml', 'w', encoding='utf-8') as file:
                    file.writelines(data)
                os.chdir('server')
            with open('eula.txt', 'r', encoding='utf-8') as file:
                data = file.readlines()
                data[2] = 'eula=true\n'
            with open('eula.txt', 'w', encoding='utf-8') as file:
                file.writelines(data)
            logger.info('EULA set to true complete')
        except FileNotFoundError as err:
            logger.error('Something failed: %s', err)
            return sys.exit(1)
    return 0


def server_loader() -> int:
    """Function to choose the server loader

    :return: Server loader.
    """
    logger.info('Which loader do you want to use?')
    logger.info(' 1 | Vanilla')
    logger.info(' 2 | Fabric')
    logger.info(' 3 | Forge')
    logger.info(' 4 | Quilt')
    logger.info(' 5 | Carpet112 (Carpet 1.12)')
    logger.info(' 6 | Paper')
    logger.info(' 7 | Close script')
    while True:
        input_logger('Select a option: ')
        option = input().lower().strip()
        loader_index: int
        match option:
            case '1' | 'vanilla':
                loader_index = 1
            case '2' | 'fabric':
                loader_index = 2
            case '3' | 'forge':
                loader_index = 3
            case '4' | 'quilt':
                loader_index = 4
            case '5' | 'carpet112':
                loader_index = 5
            case '6' | 'paper':
                loader_index = 6
            case '7' | 'exit':
                logger.info('Closing script...')
                return sys.exit(0)
            case _:
                logger.warning('Input is not within the options')
                continue
        return loader_index


def main():
    """Main script function"""
    logger.info('Auto server script is starting up')
    python = check_environment()
    mk_folder()
    loader = server_loader()
    if simple_yes_no('Do you want to use MCDR?') and loader != 3:
        mcdr_setup(loader, python)
        post_setup(is_mcdr=True, python=python)
    else:
        if loader == 3:
            logger.warning('Forge loader detected for stability some features of the script are disable')
        minecraft_jar: str = loader_setup(loader)
        if loader != 3:
            post_setup(python=python, jar_file=minecraft_jar)
    logger.info('Script done')
    return 0


if __name__ == '__main__':
    logger = ScriptLogger()  # Create global logger
    sys.exit(main())
