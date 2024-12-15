import random
import time
import sys
import os.path
import argparse
import markdown
import zipfile
import shutil
import tarfile
import requests.exceptions
import src.frontend.resources  # Your IDE may tell you that this is an unused import statement, but that is WRONG!

from itertools import islice, chain
from threading import Event
from pathlib import Path
from io import TextIOWrapper
from hqporner_api.api import Sort as hq_Sort
from phub import consts
from base_api.modules import consts as bs_consts
from base_api.base import Core

from src.backend.shared_functions import *
from src.backend.shared_gui import *
from src.backend.class_help import *
from src.backend.log_config import setup_logging
from src.frontend.ui_form_license import Ui_SetupLicense
from src.frontend.ui_form_range_selector import Ui_PornFetchRangeSelector
from src.frontend.ui_form_desktop import Ui_PornFetch_Desktop
from src.frontend.ui_form_android import Ui_PornFetch_Android
from src.frontend.ui_form_install_dialog import Ui_SetupInstallDialog
from src.frontend.ui_form_keyboard_shortcuts import Ui_KeyboardShortcuts

from PySide6.QtCore import (QFile, QTextStream, Signal, QRunnable, QThreadPool, QObject, QSemaphore, Qt, QLocale,
                            QTranslator, QCoreApplication, QSize)
from PySide6.QtWidgets import QWidget, QApplication, QTreeWidgetItem, QButtonGroup, QFileDialog, QHeaderView
from PySide6.QtGui import QIcon, QFont, QFontDatabase, QPixmap, QShortcut

"""
Copyright (C) 2023-2024 Johannes Habel

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

Contact:

E-Mail: EchterAlsFake@proton.me
Discord: echteralsfake (faster response)
"""

__license__ = "GPL 3"
__version__ = "3.5"
__build__ = "desktop"  # android or desktop
__author__ = "Johannes Habel"
__next_release__ = "3.5"
total_segments = 0
downloaded_segments = 0
stop_flag = Event()

ffmpeg_features = True
ffmpeg_path = None
url_linux = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
url_windows = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
session_urls = []  # This list saves all URls used in the current session. Used for the URL export function
total_downloaded_videos = 0 # All videos that actually successfully downloaded
total_downloaded_videos_attempt = 0 # All videos the user tries to download
logger = setup_logging()


class Signals(QObject):
    """Signals for the Download class"""
    # Progress Signals
    progress_single = Signal(int)
    completed = Signal()
    progress = Signal(int, int)
    progress_hqporner = Signal(int, int)
    progress_eporner = Signal(int, int)
    progress_xnxx = Signal(int, int)
    progress_xvideos = Signal(int, int)
    progress_spankbang = Signal(int, int)
    total_progress = Signal(int, int)
    progress_video = Signal(object)
    ffmpeg_progress = Signal(int, int)
    internet_check = Signal(dict)

    # Ranges
    start_undefined_range = Signal() # Starts the loading animation
    stop_undefined_range = Signal() # Stops the loading animation
    data = Signal(list) # Data for the tree widget (I think)

    # Other (I don't remember)
    text_data = Signal(list) # Data returned from the AddToTreeWidget class
    install_finished = Signal(list)

    # URL Thread
    url_iterators = Signal(list, list, list)

    # Operations
    clear_signal = Signal()
    get_total = Signal(str, str)
    result = Signal(bool)

    # Errors
    error_signal = Signal(str)

    # Video Loader class
    loaded = Signal(object, str, str, object, str, bool, str)
    error = Signal(str)


class License(QWidget):
    """License class to display the GPL 3 License to the user.
       And handle the other UI popups"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_widget = None
        self.conf = ConfigParser()
        self.conf.read("config.ini")
        self.android_startup = None
        self.install_widget = None

        # Set up the UI for License widget
        self.ui = Ui_SetupLicense()
        self.ui.setupUi(self)
        self.ui.button_accept.clicked.connect(self.accept)
        self.ui.button_deny.clicked.connect(self.denied)

    def check_license_and_proceed(self):
        if self.conf["Setup"]["license_accepted"] == "true":
            self.show_android_startup_or_main() # License accepted, proceed with Android or main widget

        else:
            self.show() # License not accepted, show the license widget

    def accept(self):
        self.conf.set("Setup", "license_accepted", "true")
        with open("config.ini", "w") as config_file: # type: TextIOWrapper
            self.conf.write(config_file)
        self.show_android_startup_or_main()

    def denied(self):
        self.conf.set("Setup", "license_accepted", "false")
        with open("config.ini", "w") as config_file:  #type: TextIOWrapper
            self.conf.write(config_file)
        logger.error("License was denied, closing application")
        self.close()
        sys.exit(0)

    def show_android_startup_or_main(self):
        """ Check if running on Android and show the appropriate startup screen. """
        self.close()

        if __build__ == "android":
            pass # TODO

        else:
            self.show_install_dialog()

    def show_install_dialog(self):
        if self.conf["Setup"]["install"] == "unknown":
            self.install_widget = InstallDialog()
            self.install_widget.show()

        else:
            self.show_main()

    def show_main(self):
        self.main_widget = Porn_Fetch()
        self.main_widget.show()


class InstallDialog(QWidget):
    def __init__(self):
        super().__init__()
        self.conf = ConfigParser()
        self.conf.read("config.ini")
        self.main_widget = None

        self.ui = Ui_SetupInstallDialog()
        self.ui.setupUi(self)
        self.ui.button_install.clicked.connect(self.start_install)
        self.ui.button_portable.clicked.connect(self.start)

    def start_install(self):
        self.conf.set("Setup", "install", "installed")
        with open("config.ini", "w") as config: #type: TextIOWrapper
            self.conf.write(config)

        self.close()
        app_name = self.ui.lineedit_custom_app_name.text() or "Porn Fetch"
        logging.info(f"App Name: {app_name}")

        self.main_widget = Porn_Fetch(start_installation=True, app_name=app_name)
        self.main_widget.show()

    def start(self):
        self.conf.set("Setup", "install", "portable")
        with open("config.ini", "w") as config: #type: TextIOWrapper
            self.conf.write(config)

        self.close()
        self.main_widget = Porn_Fetch()
        self.main_widget.show()


class InstallThread(QRunnable):
    def __init__(self, app_name):
        super(InstallThread, self).__init__()
        self.app_name = app_name
        self.signals = Signals()

    def run(self):
        try:
            self.signals.start_undefined_range.emit()

            if sys.platform == "linux":
                filename = "PornFetch_Linux_GUI_x64.bin"
                destination_path_tmp = os.path.expanduser("~/.local/share/")
                destination_path_final = os.path.expanduser("~/.local/share/pornfetch/")
                destination_install = os.path.expanduser("~/.local/share/applications/")
                shortcut_path = os.path.join(destination_install, "pornfetch.desktop")

                if not os.path.exists(destination_path_tmp):
                    ui_popup(QCoreApplication.translate(context="main", key="""The path ~/.local/share/ does not exist. This path is typically used for installing applications and their settings
in a users local account. Since you don't have that, you can't install it. Probably because your Linux does not follow
the XDG Desktop Portal specifications. It's your own decision and I don't create the directory for you, or force you to
do that. If you still wish to install Porn Fetch, look Online how to setup XDK-Desktop-Portal on your Linux distribution,
head over to the setting and down there you will be able to try the installation again. Otherwise, you can just keep
using the portable version, which will work just fine.

If you believe, that this is a mistake, please report it on GitHub, so that I can fix it :)""", disambiguation=None))
                    return

                try:
                    os.makedirs(destination_path_final, exist_ok=True)

                except PermissionError:
                    ui_popup("""You do not have permissions to create the folder 'pornfetch' inside {destination_path_tmp}!
The installation process will stop now. You can either run Porn Fetch with elevated privileges, or use the portable
version.""")
                    return

                pornfetch_exe = os.path.join(destination_path_final, filename)
                if os.path.exists(pornfetch_exe):
                    os.remove(pornfetch_exe)

                shutil.move("PornFetch_Linux_GUI_x64.bin", dst=destination_path_final)
                logger.info(f"Moved the PornFetch binary to: {destination_path_final}")

                if not os.path.exists(os.path.join(destination_path_final, "config.ini")):
                    shutil.move("config.ini", dst=destination_path_final)
                    logger.info("Moved configuration file")

                logger.info(f"Downloading additional asset: icon")

                if not os.path.exists(os.path.join(destination_path_final, "Logo.png")):
                    img = requests.get(
                        "https://github.com/EchterAlsFake/Porn_Fetch/blob/master/src/frontend/graphics/android_app_icon.png?raw=true")
                    if not img.status_code == 200:
                        ui_popup("Couldn't download the Porn Fetch logo. Installation will still be successfully, but please"
                            "report this error on GitHub. Thank you.")

                    elif img.status_code == 200:
                        with open("Logo.png", "wb") as logo:
                            logo.write(img.content)
                            shutil.move("Logo.png", dst=destination_path_final)

                entry_content = f"""[Desktop Entry]
Name={self.app_name}
Exec={destination_path_final}PornFetch_Linux_GUI_x64.bin %F
Icon={destination_path_final}Logo.png
Type=Application
Terminal=false
Categories=Utility;"""

                if os.path.exists(shortcut_path):
                    os.remove(shortcut_path)

                with open("pornfetch.desktop", "w") as entry_file:
                    entry_file.write(entry_content)

                shutil.move("pornfetch.desktop", shortcut_path)

                logger.info("Successfully installed Porn Fetch!")
                os.chmod(mode=0o755,
                         path=destination_path_final + "PornFetch_Linux_GUI_x64.bin")  # Setting executable permission

            elif sys.platform == "win32":
                import win32com.client  # Only available on Windows

                filename = "PornFetch_Windows_GUI_x64.exe"
                target_dir = os.path.join(os.getenv("LOCALAPPDATA"), "pornfetch")
                os.makedirs(target_dir, exist_ok=True)

                if os.path.exists(os.path.join(target_dir, filename)):
                    os.remove(os.path.join(target_dir, filename))

                # Move the executable to the target directory
                shutil.move(filename, target_dir)

                if not os.path.exists(os.path.join(target_dir, "config.ini")):
                    shutil.move("config.ini", target_dir)  # Prevent overriding the old configuration file

                # Define paths for the shortcut creation
                app_name = self.app_name
                app_exe_path = os.path.join(target_dir, filename)  # Full path to the executable
                start_menu_path = os.path.join(os.getenv("APPDATA"), "Microsoft", "Windows", "Start Menu", "Programs")
                shortcut_path = os.path.join(start_menu_path, f"{app_name}.lnk")

                # Create the shortcut
                shell = win32com.client.Dispatch("WScript.Shell")
                shortcut = shell.CreateShortcut(shortcut_path)
                shortcut.TargetPath = app_exe_path  # Path to the executable
                shortcut.WorkingDirectory = target_dir  # Set working directory to the target directory
                shortcut.IconLocation = app_exe_path
                shortcut.Save()

        except Exception as e:
            self.signals.install_finished.emit([False, e])
            self.signals.stop_undefined_range.emit()

        self.signals.stop_undefined_range.emit()
        self.signals.install_finished.emit([True, ""])
        # Porn Fetch installation is finished


class InternetCheck(QRunnable):
    def __init__(self):
        super(InternetCheck, self).__init__()

        self.headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.5",
        }

        self.websites = [
            "https://de.spankbang.com",
            "https://www.pornhub.com",
            "https://hqporner.com",
            "https://www.xvideos.com",
            "https://www.xnxx.com",
            # Append new URLs here
        ]

        self.website_results = {}
        self.signals = Signals()


    def run(self):
        for idx, website in enumerate(self.websites, start=1):
            logger.debug(f"[{idx}|{len(self.websites)}] Testing: {website}")

            try:
                logging.info(f"Testing Internet [{idx / len(self.websites)}] : {website}")
                status = requests.get(website, headers=self.headers)

                if status.status_code == 200:
                    self.website_results.update({website: "✔"})

                elif status.status_code == 404:
                        self.website_results.update({website: "Failed, website doesn't exist? Please report this error"})

                elif status.status_code == 403:
                    if not website == "https://de.spankbang.com": # I don't know why, but they block connection for no reason
                        self.website_results.update({website: "The website blocked access, please change your IP or wait"})

            except requests.exceptions.SSLError:
                self.website_results.update({website: "SSL Error, your ISP / Router / Firewall blocks access to the site"
                                                      " Are you at a university, school or in a public WiFi?"})

            except Exception as e:
                self.website_results.update({website: f"Unknown Error: {e}"})

        self.signals.internet_check.emit(self.website_results)


class CheckUpdates(QRunnable):
    def __init__(self):
        super(CheckUpdates, self).__init__()
        self.signals = Signals()

    def run(self):
        url = f"https://github.com/EchterAlsFake/Porn_Fetch/releases/tag/{__next_release__}"

        try:
            request = requests.get(url)

            if request.status_code == 200:
                logger.info("NEW UPDATE IS AVAILABLE!")
                self.signals.result.emit(True)

            else:
                logger.info("Checked for updates, no update is available.")
                self.signals.result.emit(False)

        except Exception as e:
            logger.error(f"Could not check for updates. Please report the following error on GitHub: {e}")


class AddToTreeWidget(QRunnable):
    def __init__(self, iterator, search_limit, data_mode, is_reverse, stop_flag, is_checked, last_index):
        super(AddToTreeWidget, self).__init__()
        self.signals = Signals() # Processing signals for progress and information
        self.iterator = iterator # The video iterator (Search or model object yk)
        self.search_limit = search_limit # The total number of videos displayed
        self.data_mode = data_mode # If the user wants only title or full data
        self.reverse = is_reverse # If the user wants to display the videos in reverse
        self.stop_flag = stop_flag # If the user pressed the stop process button
        self.is_checked = is_checked # If the "do not clear videos" checkbox is checked
        self.last_index = last_index # The last index (video) of the tree widget to maintain a correct order of numbers

    def process_video(self, video, index):
        try:
            if video is False:
                self.signals.error_signal.emit("Error: Video could not be processed due to an unknown issue.")
                return False

            session_urls.append(video.url)  # Append the URL for later use
            data = load_video_attributes(video, self.data_mode)  # Load video data

            # Defaults for disabled attributes
            title = data[0]
            disabled = QCoreApplication.translate("main", "Disabled", None)
            author = disabled
            duration = disabled
            thumbnail = disabled

            # Full data mode
            if self.data_mode == 1:
                try:
                    author = data[1]
                    duration = str(parse_length(data[2]))
                    thumbnail = str(data[5])
                except IndexError:
                    logger.warning(f"Warning: Some attributes are missing for video: {video.url}")

            print(
                f"\r\033[K[{Fore.LIGHTCYAN_EX}{index}/{self.search_limit}]{Fore.RESET}{str(title)} Successfully processed!",
                end='', flush=True
            )

            return [str(title), str(author), str(duration), str(index), video, thumbnail]

        except (errors.PremiumVideo, IndexError):
            logger.error(f"Warning: The video {video.url} is a Premium-only video and will be skipped.")
            self.signals.error_signal.emit(f"Premium-only video skipped: {video.url}")
            return False

        except errors.RegionBlocked:
            logger.error(f"Warning: The video {video.url} is region-blocked or private and will be skipped.")
            self.signals.error_signal.emit(f"Region-blocked video skipped: {video.url}")
            return False

        except Exception as e:
            logger.exception(f"Unexpected error while processing video: {e}")
            self.signals.error_signal.emit(f"Unexpected error occurred: {e}")
            return False


    def run(self):
        if not self.is_checked:
            self.signals.clear_signal.emit() # Clears the tree widget

        self.signals.start_undefined_range.emit() # Starts the progressbar, but with a loading animation

        if self.is_checked:
            index = self.last_index
            start = index
            self.search_limit += self.search_limit

        else:
            start = 1
            self.last_index = start

        try:
            logger.debug(f"Result Limit: {str(self.search_limit)}")

            if self.reverse:
                logger.debug("Reversing Videos. This may take some time...")

                # Use islice to limit the number of items fetched from the iterator
                videos = list(islice(self.iterator, self.search_limit)) # Can take A LOT of time (like really)
                videos.reverse()  # Reverse the list (to show videos in reverse order)

            else:
                videos = islice(self.iterator, self.search_limit)

            self.signals.stop_undefined_range.emit() # Stop the loading animation

            for i, video in enumerate(videos, start=start):
                if self.stop_flag.is_set():
                    return  # Stop processing if user pressed the stop button

                try_attempt = True
                while try_attempt:
                    try:
                        if i >= self.search_limit + 1:
                            break  # Respect search limit

                        text_data = self.process_video(video, i)
                        if text_data is False:
                            break  # Skip to the next video if processing failed

                        self.signals.progress.emit(self.search_limit, i)
                        self.signals.text_data.emit(text_data)
                        try_attempt = False  # Processing succeeded

                    except errors.RegexError as e:
                        logger.error(f"Regex error: {e}")
                        self.signals.error_signal.emit(f"Regex error: {e}. Please report this issue.")
                        continue

                    except (ConnectionError, ConnectionAbortedError, ConnectionResetError) as e:
                        logger.error(f"Connection error: {e}")
                        self.signals.error_signal.emit(f"Connection error: {e}. Retrying in 20 seconds...")
                        time.sleep(20)
                        continue


        except Exception as e:
            logger.exception(f"Fatal error in run: {e}")
            self.signals.error_signal.emit(f"Fatal error: {e}")

        finally:
            self.signals.stop_undefined_range.emit()


class DownloadThread(QRunnable):
    """Refactored threading class to download videos with improved performance and logic."""

    def __init__(self, video, quality, output_path, threading_mode, workers, timeout, stop_flag, skip_existing_files):
        super().__init__()
        self.video = video
        self.ffmpeg = None
        self.quality = quality
        self.output_path = output_path
        self.threading_mode = threading_mode
        self.signals = Signals()
        self.stop_flag = stop_flag
        self.skip_existing_files = skip_existing_files
        self.workers = int(workers)
        self.timeout = int(timeout)
        self.video_progress = {}
        self.last_update_time = 0
        self.progress_signals = {
            'pornhub': self.signals.progress,
            'hqporner': self.signals.progress_hqporner,
            'eporner': self.signals.progress_eporner,
            'xnxx': self.signals.progress_xnxx,
            'xvideos': self.signals.progress_xvideos,
            'spankbang': self.signals.progress_spankbang
        }

    def generic_callback(self, pos, total, signal, video_source, ffmpeg=False):
        """Generic callback function to emit progress signals with rate limiting."""
        current_time = time.time()
        if self.stop_flag.is_set():
            return

        if ffmpeg:
            self.update_ffmpeg_progress(pos, total)
            signal.emit(pos, total)

        else:
            # Emit signal for individual progress
            if video_source == "hqporner" or video_source == "eporner":

                # Check if the current time is at least 0.5 seconds greater than the last update time
                if current_time - self.last_update_time < 0.5:
                    # If not, do not update the progress and return immediately
                    return

                scaling_factor = 1024 * 1024
                pos = int(pos / scaling_factor)
                total = int(total / scaling_factor)

            signal.emit(pos, total)
            # Update total progress only if the video source uses segments
            if video_source not in ['hqporner', 'eporner']:
                self.update_total_progress(ffmpeg)

        # Update the last update time to the current time
        self.last_update_time = current_time

    def update_ffmpeg_progress(self, pos, total):
        """Update progress for ffmpeg downloads."""
        print(f"\r\033[KProgress: [{pos} / 100]", end='', flush=True)  # I don't know why, but this fixes the progress.
        video_title = self.video.title
        self.video_progress[
            video_title] = pos / total * 100  # video title as video id, to keep track which video has how much progress done
        total_progress = sum(self.video_progress.values()) / len(self.video_progress)
        self.signals.total_progress.emit(total_progress, 100)

    def update_total_progress(self, ffmpeg):
        """Update total download progress."""
        if not ffmpeg:
            global downloaded_segments
            downloaded_segments += 1
            self.signals.total_progress.emit(downloaded_segments, total_segments)

    def run(self):
        """Run the download in a thread, optimizing for different video sources and modes."""
        try:
            if os.path.isfile(self.output_path):
                if self.skip_existing_files:
                    logger.debug("The file already exists, skipping...")
                    self.signals.completed.emit()
                    return

                else:
                    logger.debug("The file already exists, appending random number...")
                    path = str(self.output_path).split(".")
                    path = path[0] + str(random.randint(0, 1000)) + ".mp4"
                    self.output_path = path

            logger.debug(f"Downloading Video to: {self.output_path}")
            if self.threading_mode == "FFMPEG" or self.threading_mode == download.FFMPEG:
                self.ffmpeg = True

            if isinstance(self.video, Video):  # Assuming 'Video' is the class for Pornhub
                self.threading_mode = resolve_threading_mode(workers=self.workers, timeout=
                self.timeout, mode=self.threading_mode, video=self.video)
                video_source = "pornhub"
                path = self.output_path
                logger.debug("Starting the Download!")
                try:
                    self.video.download(downloader=self.threading_mode, path=path, quality=self.quality,
                                        display=lambda pos, total: self.generic_callback(pos, total,
                                                                                         self.signals.progress,
                                                                                         video_source, self.ffmpeg))

                except TypeError:
                    self.video.download(downloader=self.threading_mode, path=path, quality=self.quality,
                                        display=lambda pos, total: self.generic_callback(pos, total,
                                                                                         self.signals.progress,
                                                                                         video_source, self.ffmpeg))

            # We need to specify the sources, so that it knows which individual progressbar to use
            elif isinstance(self.video, hq_Video):
                video_source = "hqporner"
                self.video.download(quality=self.quality, path=self.output_path, no_title=True,
                                    callback=lambda pos, total: self.generic_callback(pos, total,
                                                                                      self.signals.progress_hqporner,
                                                                                      video_source, self.ffmpeg))

            elif isinstance(self.video, ep_Video):
                video_source = "eporner"
                self.video.download(quality=self.quality, path=self.output_path,
                                    callback=lambda pos, total: self.generic_callback(pos, total,
                                                                                      self.signals.progress_eporner,
                                                                                      video_source, self.ffmpeg))

            elif isinstance(self.video, xn_Video):
                video_source = "xnxx"
                self.video.download(downloader=self.threading_mode, path=self.output_path, quality=self.quality,
                                    callback=lambda pos, total: self.generic_callback(pos, total,
                                                                                      self.signals.progress_xnxx,
                                                                                      video_source, self.ffmpeg))

            elif isinstance(self.video, xv_Video):
                video_source = "xvideos"
                self.video.download(downloader=self.threading_mode, path=self.output_path, quality=self.quality,
                                    callback=lambda pos, total: self.generic_callback(pos, total,
                                                                                      self.signals.progress_xvideos,
                                                                                      video_source, self.ffmpeg))
            elif isinstance(self.video, sp_Video):
                video_source = "spankbang"
                self.video.download(downloader=self.threading_mode, path=self.output_path, quality=self.quality,
                                    callback=lambda pos, total: self.generic_callback(pos, total,
                                                                                      self.signals.progress_spankbang,
                                                                                      video_source, self.ffmpeg),
                                    no_title=True, use_hls=True)

                # ... other video types ...

        finally:
            self.signals.completed.emit()


class ProcessVideoThread(QRunnable):
    """
    This class will be executed (if enabled by the user) to convert the final video into different formats and apply
    metadata to it.
    """

    def __init__(self, write_tags_, data, ffmpeg_path, format):
        super(ProcessVideoThread, self).__init__()
        self.signals = Signals()
        self.path = ffmpeg_path
        self.format = format
        self.write_tags_ = write_tags_
        self.data = data


    def run(self):
        os.rename(f"{self.path}", f"{self.path}_.tmp")
        logger.debug(f"FFMPEG PATH: {ffmpeg_path}")

        if self.format == "mp4":
            cmd = [ffmpeg_path, "-i", f"{self.path}_.tmp", "-c", "copy", self.path]

        else:
            self.path = str(self.path).replace(".mp4", f"{self.format}")
            cmd = [ffmpeg_path, '-i', f"{self.path}_.tmp", self.path]


        ff = FfmpegProgress(cmd)
        for progress in ff.run_command_with_progress():
            self.signals.ffmpeg_progress.emit(round(progress), 100)

        os.remove(f"{self.path}_.tmp")

        if self.write_tags_:
            write_tags(path=self.path, data=self.data)


class QTreeWidgetDownloadThread(QRunnable):
    """Threading class for the QTreeWidget (sends objects to the download class defined above)"""

    def __init__(self, treeWidget, threading_mode, semaphore, quality):
        super(QTreeWidgetDownloadThread, self).__init__()
        self.treeWidget = treeWidget
        self.signals = Signals()
        self.threading_mode = threading_mode
        self.semaphore = semaphore
        self.quality = quality

    def run(self):
        self.signals.start_undefined_range.emit()
        video_objects = []

        for i in range(self.treeWidget.topLevelItemCount()):
            item = self.treeWidget.topLevelItem(i)
            checkState = item.checkState(0)
            if checkState == Qt.Checked:
                video_objects.append(item.data(0, Qt.UserRole))

        if not self.threading_mode == "FFMPEG":
            logger.debug("Getting segments...")
            global total_segments, downloaded_segments
            total_segments += sum(
                [len(list(video.get_segments(quality=self.quality))) for video in video_objects if
                 hasattr(video, 'get_segments')])
            logger.debug("Got segments")
            # This basically looks how many segments exist in all videos together, so that we can calculate the total
            # progress

        else:
            logger.debug("Progress tracking: FFMPEG")
            # FFMPEG has always 0-100 as progress callback, that is why I specify 100 for each video instead of the
            # total segments

            counter = 0
            for _ in video_objects:
                counter += 100

            total_segments = counter

        downloaded_segments = 0
        self.signals.stop_undefined_range.emit()

        for video in video_objects:
            self.semaphore.acquire()  # Trying to start the download if the thread isn't locked
            if stop_flag.is_set():
                return
            logger.debug("Semaphore Acquired")
            self.signals.progress_video.emit(video)  # Now emits the video to the main class for further processing


class VideoLoader(QRunnable):
    def __init__(self, url, output_path, threading_mode, directory_system, quality, delay):
        super(VideoLoader, self).__init__()
        self.url = url
        self.output_path = output_path
        self.threading_mode = threading_mode
        self.directory_system = directory_system
        self.quality = quality
        self.signals = Signals()
        self.delay = delay

    def run(self):
        try:
            video = check_video(self.url, delay=self.delay)
            x = 1

            if x == 0:
                pass

            else:
                data = load_video_attributes(video, 1)
                title = data[0]
                author = data[1]
                output_path = Path(self.output_path)
                stripped_title = Core().strip_title(title)  # Strip the title so that videos with special chars can be
                # saved on windows. it would raise an OSError otherwise

                if self.directory_system:  # If the directory system is enabled, this will create an additional folder
                    author_path = output_path / author
                    author_path.mkdir(parents=True, exist_ok=True)
                    output_file_path = author_path / f"{stripped_title}.mp4"

                else:
                    output_file_path = output_path / f"{stripped_title}.mp4"

                # Emit the loaded signal with all the required information
                self.signals.loaded.emit(video, author, stripped_title, output_file_path, self.threading_mode,
                                         self.directory_system, self.quality)

        except Exception as e:
            self.signals.error.emit(str(e))


class FFMPEGDownload(QRunnable):
    """Downloads ffmpeg into the execution path of Porn Fetch"""

    def __init__(self, url, extract_path, mode):
        super().__init__()
        self.url = url
        self.extract_path = extract_path
        self.mode = mode
        self.signals = Signals()

    @staticmethod
    def delete_dir():
        files = os.listdir("./")
        for file in files:
            try:
                search = re.search(pattern=r'ffmpeg-(.*?)-', string=file)  # It's all about the version number
                if len(search.groups()) == 1:

                    if sys.platform == "win32":
                        shutil.rmtree(f"ffmpeg-{search.group(1)}-essentials_build")
                        return True

                    elif sys.platform == "linux" or sys.platform == "linux2":
                        shutil.rmtree(f"ffmpeg-{search.group(1)}-amd64-static")
                        return True

            except AttributeError:
                pass

        return False

    def run(self):
        # Download the file
        logger.debug(f"Downloading: {self.url}")
        logger.debug("FFMPEG: [1/4] Starting the download")
        with requests.get(self.url, stream=True) as r:
            r.raise_for_status()
            try:
                total_length = int(r.headers.get('content-length'))

            except Exception:
                total_length = 41313894

            self.signals.total_progress.emit(0, total_length)  # Initialize progress bar
            dl = 0
            filename = self.url.split('/')[-1]
            with open(filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:  # filter out keep-alive new chunks
                        f.write(chunk)
                        dl += len(chunk)
                        self.signals.total_progress.emit(dl, total_length)

        logger.debug("FFMPEG: [2/4] Starting file extraction")
        # Extract the file based on OS mode
        if self.mode == "linux" and filename.endswith(".tar.xz"):
            with tarfile.open(filename, "r:xz") as tar:
                total_members = len(tar.getmembers())

                for idx, member in enumerate(tar.getmembers()):
                    if 'ffmpeg' in member.name and (member.name.endswith('ffmpeg')):
                        tar.extract(member, self.extract_path, filter="data")
                        extracted_path = os.path.join(self.extract_path, member.path)
                        shutil.move(extracted_path, "./")

                    self.signals.total_progress.emit(idx, total_members)

        elif self.mode == "windows" and filename.endswith(".zip"):
            with zipfile.ZipFile(filename, 'r') as zip_ref:
                total = len(zip_ref.namelist())

                for idx, member in enumerate(zip_ref.namelist()):
                    if 'ffmpeg.exe' in member:
                        zip_ref.extract(member, self.extract_path)
                        extracted_path = os.path.join(self.extract_path, member)
                        shutil.move(extracted_path, ".")

                    self.signals.total_progress.emit(idx, total)
        logger.debug("FFMPEG: [3/4] Finished Extraction")
        # Finalize
        self.signals.total_progress.emit(total_length, total_length)  # Ensure progress bar reaches 100%
        os.remove(filename)  # Clean up downloaded archive

        if self.delete_dir():
            logger.debug("FFMPEG: [4/4] Cleaned Up")

        else:
            logger.error("The Regex for finding the FFmpeg version failed. Please report this on GitHub!, Thanks.")

        self.signals.finished.emit()


class AddUrls(QRunnable):
    """
    This class is used to add the URLs from the 'open file' function, because the UI doesn't respond until
    all URLs / Models / Search terms have been processed. This is why I made this threading class
    """

    def __init__(self, file, delay):
        super(AddUrls, self).__init__()
        self.signals = Signals()
        self.file = file
        self.delay = delay

    def run(self):
        iterator = []
        model_iterators = []
        search_iterators = []

        with open(self.file, "r") as url_file:
            content = url_file.read().splitlines()

        for idx, line in enumerate(content):
            if len(line) == 0:
                continue

            total = len(content)

            if line.startswith("model#"):
                line = line.split("#")[1]
                model_iterators.append(line)
                search_iterators.append(line)

            elif line.startswith("search#"):
                query = line.split("#")[1]
                site = line.split("#")[2]
                search_iterators.append({"website": site,
                                         "query": query})

            else:
                video = check_video(line, delay=self.delay)

                if video is not False:
                    iterator.append(video)


            self.signals.total_progress.emit(idx, total)

        self.signals.url_iterators.emit(iterator, model_iterators, search_iterators)


class Porn_Fetch(QWidget):
    def __init__(self, parent=None, start_installation=False, app_name="Porn Fetch"):
        super().__init__(parent)
        # Variable initialization:
        self.app_name = app_name

        # Threads
        self.install_thread = None
        self.thread = None
        self.internet_check_thread = None
        self.update_thread = None
        self.url_thread = None
        self.download_thread = None
        self.video_loader_thread = None

        # Button groups
        self.group_threading_mode = None
        self.group_quality = None
        self.group_radio_tree_data_mode = None
        self.group_ui_language = None
        self.group_directory_system = None
        self.group_radio_hqporner = None
        self.group_radio_model_videos = None
        self.group_radio_skip_existing_files = None

        # UI Stuff
        self.header = None
        self.widget = None
        self.range_ui = None
        self.keyboard_widget = None
        self.keyboard_widget_ = None

        # Settings mappings
        self.map_quality = None
        self.map_model_videos = None
        self.map_gui_language = None
        self.map_threading_mode = None

        self.internet_checks = None
        self.update_checks = None
        self._anonymous_mode = None
        self.enable_tor = None
        self.write_metadata = None
        self.convert_videos = None
        self.format = None
        self.semaphore_limit = None
        self.search_limit = None
        self.output_path = None
        self.gui_language = None
        self.quality = None
        self.threading_mode = None
        self.semaphore = None
        self.delay = None
        self.timeout = None
        self.workers = None
        self.max_retries = None
        self.skip_existing_files = None
        self.model_videos_type = None
        self.client = None
        self.downloader = None
        self.directory_system = None

        self.last_index = 0
        self.threadpool = QThreadPool()

        self.conf = ConfigParser()
        self.conf.read("config.ini")

        if __build__ == "android":
            self.ui = Ui_PornFetch_Android()
            self.ui.setupUi(self)

        else:
            self.ui = Ui_PornFetch_Desktop()
            self.ui.setupUi(self)

            if start_installation:
                self.install_pornfetch()
                ui_popup("Porn Fetch has been installed. The app will now close! Please start Porn Fetch from"
                         "your context menu again.")

                self.close()
                exit(0)

            self.default_max_height = self.ui.main_stacked_widget_top.maximumHeight()
            self.button_connectors()  # Connects the buttons to their functions
            self.button_groups()  # Groups the buttons, so that the Radio buttons are split from themselves (hard to explain)
            self.shortcuts() # Activates the keyboard shortcuts
            self.load_style()  # Loads all the User Interface stylesheets
            logger.debug("Startup: [3/5] Initialized the User Interface")
            self.settings_maps_initialization()
            self.load_user_settings()  # Loads the user settings and applies selected values to the UI
            logger.debug("Startup: [4/5] Loaded the user settings")
            self.switch_to_home()  # Switches Porn Fetch to the home widget

            if self.internet_checks:
                self.check_internet()

            if self.update_checks:
                self.check_for_updates()

            if self._anonymous_mode:
                self.anonymous_mode()

            if self.conf.get("Setup", "tor") == "true":
                logger.warning("You have enabled Tor! This feature is NOT implemented yet!")

            self.check_ffmpeg()  # Checks and sets up FFmpeg
            logger.debug("Startup: [5/5] ✔")


    def install_pornfetch(self):
        if __build__ == "desktop":
            self.install_thread = InstallThread(self.app_name)
            self.install_thread.signals.install_finished.connect(self.install_pornfetch_result)
            self.install_thread.signals.start_undefined_range.connect(self.start_undefined_range)
            self.install_thread.signals.stop_undefined_range.connect(self.stop_undefined_range)
            self.threadpool.start(self.install_thread)

        else:
            ui_popup(self.tr("You are running on Android! You can not install Porn Fetch", disambiguation=None))

    def install_pornfetch_result(self, result):
        if result[0]:
            ui_popup(self.tr("Porn Fetch installation successful!", disambiguation=None))

        else:
            ui_popup(self.tr(f"Porn Fetch installation failed, because of: {result[1]}", disambiguation=None))

    def anonymous_mode(self):
        """
        This mode will hide that you are using Porn Fetch by hiding video title names, hiding author names,
        hiding the window title and removing all placeholders from lineedits. May not be the most efficient approach,
         but it works.
        """
        self.setWindowTitle("Running in Anonymous mode...")


        self.ui.download_lineedit_url.setPlaceholderText(" ")
        self.ui.login_lineedit_password.setPlaceholderText(" ")
        self.ui.login_lineedit_username.setPlaceholderText(" ")
        self.ui.settings_label_pornhub_delay.setText("Delay (0 = Disabled) in seconds:")
        self.ui.settings_label_settings_videos_model.setText("Actors video types:")
        self.ui.settings_button_install_pornfetch.setText("Install Program")
        self.ui.settings_groupbox_system_pornfetch.setWindowTitle("System")
        self.ui.main_textbrowser_supported_websites.setText("Running in anonymous mode, please deactivate to display...")
        self.ui.download_lineedit_playlist_url.setPlaceholderText("Enter playlist URL")
        self.ui.download_radio_search_website_eporner.setText("4")
        self.ui.download_radio_search_website_hqporner.setText("2")
        self.ui.download_radio_search_website_pornhub.setText("1")
        self.ui.download_radio_search_website_xvideos.setText("3")
        self.ui.download_radio_search_website_xnxx.setText("5")
        self.ui.progress_label_pornhub.setText("1")
        self.ui.progress_label_hqporner.setText("2")
        self.ui.progress_label_eporner.setText("3")
        self.ui.progress_label_xnxx.setText("4")
        self.ui.progress_label_xvideos.setText("5")
        self.ui.progress_label_spankbang.setText("6")

    def button_groups(self):
        """
        The button groups are needed to tell the radio button which of them are in a group.
        If I don't do this, then you could check all redio buttons at the same time lol"""
        self.group_threading_mode = QButtonGroup()
        self.group_threading_mode.addButton(self.ui.settings_radio_threading_mode_ffmpeg)
        self.group_threading_mode.addButton(self.ui.settings_radio_threading_mode_default)
        self.group_threading_mode.addButton(self.ui.settings_radio_threading_mode_high_performance)

        self.group_quality = QButtonGroup()
        self.group_quality.addButton(self.ui.settings_radio_quality_worst)
        self.group_quality.addButton(self.ui.settings_radio_quality_half)
        self.group_quality.addButton(self.ui.settings_radio_quality_best)

        self.group_ui_language = QButtonGroup()
        self.group_ui_language.addButton(self.ui.settings_radio_ui_language_english)
        self.group_ui_language.addButton(self.ui.settings_radio_ui_language_german)
        self.group_ui_language.addButton(self.ui.settings_radio_ui_language_french)
        self.group_ui_language.addButton(self.ui.settings_radio_ui_language_system_default)
        self.group_ui_language.addButton(self.ui.settings_radio_ui_language_chinese_simplified)

        self.group_radio_hqporner = QButtonGroup()
        self.group_radio_hqporner.addButton(self.ui.tools_radio_top_porn_week)
        self.group_radio_hqporner.addButton(self.ui.tools_radio_top_porn_month)
        self.group_radio_hqporner.addButton(self.ui.tools_radio_top_porn_all_time)

        self.group_radio_model_videos = QButtonGroup()
        self.group_radio_model_videos.addButton(self.ui.settings_radio_model_both)
        self.group_radio_model_videos.addButton(self.ui.settings_radio_model_uploads)
        self.group_radio_model_videos.addButton(self.ui.settings_radio_model_featured)

        self.group_radio_tree_data_mode = QButtonGroup()
        self.group_radio_tree_data_mode.addButton(self.ui.main_radio_tree_show_title)
        self.group_radio_tree_data_mode.addButton(self.ui.main_radio_tree_show_all)

    def button_connectors(self):
        """a function to link the buttons to their functions"""
        # Menu Bar Switch Button Connections
        self.ui.main_button_switch_home.clicked.connect(self.switch_to_home)
        self.ui.main_button_switch_settings.clicked.connect(self.switch_to_settings)
        self.ui.main_button_switch_credits.clicked.connect(self.switch_to_credits)
        self.ui.main_button_switch_account.clicked.connect(self.switch_to_account)
        self.ui.main_button_switch_supported_websites.clicked.connect(self.switch_to_supported_websites)
        self.ui.main_button_view_progress_bars.clicked.connect(self.switch_to_all_progress_bars)

        # Video Download Button Connections
        self.ui.main_button_tree_download.clicked.connect(self.download_tree_widget)
        self.ui.download_button_download.clicked.connect(self.start_single_video)
        self.ui.download_button_model.clicked.connect(self.start_model)
        self.ui.download_button_playlist_get_videos.clicked.connect(self.start_playlist)

        # Help Buttons Connections
        self.ui.settings_button_semaphore_help.clicked.connect(button_semaphore_help)
        self.ui.settings_button_threading_mode_help.clicked.connect(button_threading_mode_help)
        self.ui.settings_button_directory_system_help.clicked.connect(button_directory_system_help)
        self.ui.settings_button_workers_help.clicked.connect(maximal_workers_help)
        self.ui.settings_button_timeout_help.clicked.connect(timeout_help)
        self.ui.settings_button_pornhub_delay_help.clicked.connect(pornhub_delay_help)
        self.ui.settings_button_result_limit_help.clicked.connect(result_limit_help)
        self.ui.download_button_help_file.clicked.connect(open_file_help)
        self.ui.settings_button_timeout_maximal_retries_help.clicked.connect(max_retries_help)
        self.ui.settings_button_help_skip_existing_files.clicked.connect(skip_existing_files_help)
        self.ui.settings_button_help_model_videos.clicked.connect(model_videos_help)

        # Settings
        self.ui.settings_button_apply.clicked.connect(self.save_user_settings)
        self.ui.settings_button_reset.clicked.connect(reset_pornfetch)
        self.ui.settings_button_install_pornfetch.clicked.connect(self.install_pornfetch)

        # Account
        self.ui.login_button_login.clicked.connect(self.login)
        self.ui.login_button_get_watched_videos.clicked.connect(self.get_watched_videos)
        self.ui.login_button_get_liked_videos.clicked.connect(self.get_liked_videos)
        self.ui.login_button_get_recommended_videos.clicked.connect(self.get_recommended_videos)

        # Search
        self.ui.button_search.clicked.connect(self.basic_search)

        # HQPorner
        self.ui.main_button_switch_tools.clicked.connect(self.switch_to_tools)
        self.ui.tools_button_hqporner_category_get_videos.clicked.connect(self.get_by_category_hqporner)
        self.ui.tools_button_top_porn_get_videos.clicked.connect(self.get_top_porn_hqporner)
        self.ui.tools_button_get_brazzers_videos.clicked.connect(self.get_brazzers_videos)
        self.ui.tools_button_list_categories.clicked.connect(self.list_categories_hqporner)
        self.ui.tools_button_get_random_videos.clicked.connect(self.get_random_video)

        # EPorner
        self.ui.tools_button_list_categories_eporner.clicked.connect(self.list_categories_eporner)
        self.ui.tools_button_eporner_category_get_videos.clicked.connect(self.get_by_category_eporner)

        # File Dialog
        self.ui.settings_button_output_path_select.clicked.connect(self.open_output_path_dialog)
        self.ui.download_button_open_file.clicked.connect(self.open_file_dialog)

        # Other stuff IDK
        self.ui.main_button_tree_stop.clicked.connect(switch_stop_state)
        self.ui.settings_button_download_ffmpeg.clicked.connect(self.download_ffmpeg)
        self.ui.main_button_tree_keyboard_shortcuts.clicked.connect(self.show_keyboard_shortcuts)
        self.ui.main_button_tree_automated_selection.clicked.connect(self.select_range_of_items)

    def shortcuts(self):
        quit_shortcut = QShortcut("Ctrl+Q", self)
        quit_shortcut.activated.connect(self.close)

        export_urls_shortcut = QShortcut("Ctrl+E", self)
        export_urls_shortcut.activated.connect(export_urls)

        download_tree_widget = QShortcut("Ctrl+T", self)
        download_tree_widget.activated.connect(self.download_tree_widget)

        enable_anonymous_mode = QShortcut("Ctrl+A", self)
        enable_anonymous_mode.activated.connect(self.anonymous_mode)

        save_settings = QShortcut("Ctrl+S", self)
        save_settings.activated.connect(self.save_user_settings)

        select_all_items = QShortcut("Ctrl+X", self)
        select_all_items.activated.connect(self.select_all_items)

        unselect_all_items = QShortcut("Ctrl+Z", self)
        unselect_all_items.activated.connect(self.unselect_all_items)

    def load_style(self):
        """Refactored function to load icons and stylesheets."""
        # Setting icons with a loop if applicable
        icons = {
            self.ui.main_button_switch_home: "download.svg",
            self.ui.main_button_switch_settings: "settings.svg",
            self.ui.main_button_switch_credits: "information.svg",
            self.ui.main_button_switch_account: "account.svg",
            self.ui.main_button_switch_tools: "tools.svg",
            self.ui.settings_button_workers_help: "faq.svg",
            self.ui.settings_button_pornhub_delay_help: "faq.svg",
            self.ui.settings_button_threading_mode_help: "faq.svg",
            self.ui.settings_button_semaphore_help: "faq.svg",
            self.ui.settings_button_timeout_help: "faq.svg",
            self.ui.settings_button_directory_system_help: "faq.svg",
            self.ui.settings_button_result_limit_help: "faq.svg",
            self.ui.settings_button_timeout_maximal_retries_help: "faq.svg",
            self.ui.download_button_help_file: "faq.svg",
            self.ui.main_button_view_progress_bars: "progressbars.svg",
            self.ui.settings_button_help_model_videos: "faq.svg",
            self.ui.settings_button_help_skip_existing_files: "faq.svg",
        }
        for button, icon_name in icons.items():
            if icon_name == "settings.svg" or icon_name == "tools.svg":
                button.setIconSize(QSize(24, 24))

            button.setIcon(QIcon(f":/images/graphics/{icon_name}"))

        self.setWindowIcon(QIcon(":/images/graphics/logo_transparent.ico"))
        # Stylesheets
        stylesheet_paths = {
            "stylesheet_menu_button_download": ":/style/stylesheets/menu_button_download.qss",
            "stylesheet_menu_button_account": ":/style/stylesheets/menu_button_account.qss",
            "stylesheet_menu_button_tools": ":/style/stylesheets/menu_button_tools.qss",
            "stylesheet_menu_button_credits": ":/style/stylesheets/menu_button_credits.qss",
            "stylesheet_menu_button_progress": ":/style/stylesheets/menu_button_progress.qss",
            "progressbar_pornhub": ":/style/stylesheets/progressbar_pornhub.qss",
            "progressbar_hqporner": ":/style/stylesheets/progressbar_hqporner.qss",
            "progressbar_eporner": ":/style/stylesheets/progressbar_eporner.qss",
            "progressbar_total": ":/style/stylesheets/progressbar_total.qss",
            "progressbar_xnxx": ":/style/stylesheets/progressbar_xnxx.qss",
            "progressbar_xvideos": ":/style/stylesheets/progressbar_xvideos.qss",
            "progressbar_spankbang": ":/style/stylesheets/progressbar_spankbang.qss",
            "progressbar_converting": ":/style/stylesheets/progressbar_converting.qss",
            "button_blue": ":/style/stylesheets/stylesheet_button_blue.qss",
            "button_orange": ":/style/stylesheets/stylesheet_button_orange.qss",
            "button_purple": ":/style/stylesheets/stylesheet_button_purple.qss",
            "button_green": ":/style/stylesheets/stylesheet_button_green.qss",
            "buttons_login": ":/style/stylesheets/stylesheet_buttons_login.qss",
            "button_reset": ":/style/stylesheets/stylesheet_button_reset.qss"
        }

        stylesheets = {key: load_stylesheet(path) for key, path in stylesheet_paths.items()}

        # Applying stylesheets to specific buttons
        # Simplify this part based on actual UI structure and naming



        # Applying top buttons
        self.ui.login_button_login.setStyleSheet(stylesheets["button_green"])
        self.ui.progressbar_pornhub.setStyleSheet(stylesheets["progressbar_pornhub"])
        self.ui.main_progressbar_total.setStyleSheet(stylesheets["progressbar_total"])
        self.ui.progressbar_xnxx.setStyleSheet(stylesheets["progressbar_xnxx"])
        self.ui.progressbar_eporner.setStyleSheet(stylesheets["progressbar_eporner"])
        self.ui.progressbar_hqporner.setStyleSheet(stylesheets["progressbar_hqporner"])
        self.ui.progressbar_xvideos.setStyleSheet(stylesheets["progressbar_xvideos"])
        self.ui.progressbar_spankbang.setStyleSheet(stylesheets["progressbar_spankbang"])
        self.ui.main_progressbar_converting.setStyleSheet(stylesheets["progressbar_converting"])
        self.ui.download_button_model.setStyleSheet(stylesheets["button_purple"])
        self.ui.button_search.setStyleSheet(stylesheets["button_purple"])
        self.ui.download_button_download.setStyleSheet(stylesheets["button_purple"])
        self.ui.settings_button_threading_mode_help.setStyleSheet(stylesheets["button_green"])
        self.ui.settings_button_directory_system_help.setStyleSheet(stylesheets["button_green"])
        self.ui.settings_button_semaphore_help.setStyleSheet(stylesheets["button_green"])
        self.ui.main_button_tree_download.setStyleSheet(stylesheets["button_purple"])
        self.ui.settings_button_output_path_select.setStyleSheet(stylesheets["button_blue"])
        self.ui.login_button_login.setStyleSheet(stylesheets["button_blue"])
        self.ui.settings_button_apply.setStyleSheet(stylesheets["button_blue"])
        self.ui.tools_button_get_random_videos.setStyleSheet(stylesheets["button_purple"])
        self.ui.tools_button_get_brazzers_videos.setStyleSheet(stylesheets["button_purple"])
        self.ui.tools_button_list_categories.setStyleSheet(stylesheets["button_purple"])
        self.ui.download_button_open_file.setStyleSheet(stylesheets["button_purple"])
        self.ui.main_button_switch_supported_websites.setStyleSheet(stylesheets["button_blue"])
        self.ui.tools_button_hqporner_category_get_videos.setStyleSheet(stylesheets["button_purple"])
        self.ui.tools_button_top_porn_get_videos.setStyleSheet(stylesheets["button_purple"])
        self.ui.login_button_get_watched_videos.setStyleSheet(stylesheets["buttons_login"])
        self.ui.login_button_get_liked_videos.setStyleSheet(stylesheets["buttons_login"])
        self.ui.login_button_get_recommended_videos.setStyleSheet(stylesheets["buttons_login"])
        self.ui.settings_button_timeout_help.setStyleSheet(stylesheets["button_green"])
        self.ui.settings_button_workers_help.setStyleSheet(stylesheets["button_green"])
        self.ui.settings_button_pornhub_delay_help.setStyleSheet(stylesheets["button_green"])
        self.ui.settings_button_result_limit_help.setStyleSheet(stylesheets["button_green"])
        self.ui.settings_button_reset.setStyleSheet(stylesheets["button_reset"])
        self.ui.download_button_playlist_get_videos.setStyleSheet(stylesheets["button_purple"])
        self.ui.main_button_tree_stop.setStyleSheet(stylesheets["button_reset"])

        self.ui.settings_button_timeout_maximal_retries_help.setStyleSheet(stylesheets["button_green"])
        self.ui.download_button_help_file.setStyleSheet(stylesheets["button_green"])
        self.ui.settings_button_download_ffmpeg.setStyleSheet(stylesheets["button_purple"])
        self.ui.tools_button_list_categories_eporner.setStyleSheet(stylesheets["button_purple"])
        self.ui.button_help_write_metadata_tags.setStyleSheet(stylesheets["button_green"])
        self.ui.settings_button_help_model_videos.setStyleSheet(stylesheets["button_green"])
        self.ui.settings_button_help_skip_existing_files.setStyleSheet(stylesheets["button_green"])
        self.ui.settings_button_install_pornfetch.setStyleSheet(stylesheets["button_green"])
        self.ui.settings_button_help_tor.setStyleSheet(stylesheets["button_green"])
        self.ui.settings_button_help_anonymous_mode.setStyleSheet(stylesheets["button_green"])
        self.ui.main_button_tree_automated_selection.setStyleSheet(stylesheets["button_purple"])
        self.ui.main_button_tree_keyboard_shortcuts.setStyleSheet(stylesheets["button_blue"])

        self.ui.main_button_switch_home.setStyleSheet(stylesheets["stylesheet_menu_button_download"])
        self.ui.main_button_switch_account.setStyleSheet(stylesheets["stylesheet_menu_button_account"])
        self.ui.main_button_switch_tools.setStyleSheet(stylesheets["stylesheet_menu_button_tools"])
        self.ui.main_button_switch_credits.setStyleSheet(stylesheets["stylesheet_menu_button_credits"])
        self.ui.main_button_view_progress_bars.setStyleSheet(stylesheets["stylesheet_menu_button_progress"])

        self.header = self.ui.treeWidget.header()
        self.header.resizeSection(0, 300)
        self.header.resizeSection(1, 150)
        self.header.resizeSection(2, 50)
        self.header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.ui.treeWidget.setColumnWidth(3, 150)
        self.header.sortIndicatorChanged.connect(self.reindex) # This does not make any sense and I need to refactor it!
        self.ui.treeWidget.itemClicked.connect(self.set_thumbnail)

        # Sort by the 'Length' column in ascending order
        self.ui.treeWidget.sortByColumn(2, Qt.AscendingOrder)
        self.ui.main_radio_tree_show_title.setChecked(True)

    def settings_maps_initialization(self):
        # Maps for settings and corresponding UI elements
        self.map_quality = {
            "best": self.ui.settings_radio_quality_best,
            "half": self.ui.settings_radio_quality_half,
            "worst": self.ui.settings_radio_quality_worst
        }

        self.map_threading_mode = {
            "threaded": self.ui.settings_radio_threading_mode_high_performance,
            "FFMPEG": self.ui.settings_radio_threading_mode_ffmpeg,
            "default": self.ui.settings_radio_threading_mode_default
        }

        self.map_gui_language = {
            "en": self.ui.settings_radio_ui_language_english,
            "de_DE": self.ui.settings_radio_ui_language_german,
            "fr": self.ui.settings_radio_ui_language_french,
            "zh_CN": self.ui.settings_radio_ui_language_chinese_simplified,
            "system": self.ui.settings_radio_ui_language_system_default
        }

        self.map_model_videos = {
            "both": self.ui.settings_radio_model_both,
            "uploads": self.ui.settings_radio_model_uploads,
            "featured": self.ui.settings_radio_model_featured
        }

    def load_user_settings(self):
        """Loads the user settings from the configuration file and applies them."""

        # Apply settings
        self.map_quality.get(self.conf.get("Video", "quality")).setChecked(True)
        self.map_threading_mode.get(self.conf.get("Performance", "threading_mode")).setChecked(True)
        self.map_gui_language.get(self.conf.get("UI", "language")).setChecked(True)
        self.map_model_videos.get(self.conf.get("Video", "model_videos")).setChecked(True)
        self.ui.settings_spinbox_semaphore.setValue(int(self.conf.get("Performance", "semaphore")))
        self.ui.settings_spinbox_treewidget_limit.setValue(int(self.conf.get("Video", "search_limit")))
        self.ui.settings_lineedit_output_path.setText(self.conf.get("Video", "output_path"))
        self.internet_checks = self.conf.get("Setup", "internet_checks") == "true"
        self.ui.settings_checkbox_internet_checks.setChecked(self.internet_checks)

        self.update_checks = self.conf.get("Setup", "update_checks") == "true"
        self.ui.settings_checkbox_system_update_checks.setChecked(self.update_checks)

        self._anonymous_mode = self.conf.get("Setup", "anonymous_mode") == "true"
        self.ui.settings_checkbox_system_anonymous_mode.setChecked(self._anonymous_mode)

        self.enable_tor = self.conf.get("Setup", "tor") == "true"
        self.ui.settings_checkbox_system_enable_tor.setChecked(self.enable_tor)

        self.skip_existing_files = self.conf.get("Video", "skip_existing_files") == "true"
        self.ui.settings_checkbox_videos_skip_existing_files.setChecked(self.skip_existing_files)

        self.directory_system = self.conf.get("Video", "directory_system") == "true"
        self.ui.settings_checkbox_videos_use_directory_system.setChecked(self.directory_system)

        if self.conf["PostProcessing"]["write_metadata"] == "true":
            self.write_metadata = True
            self.ui.checkbox_settings_post_processing_write_metadata_tags.setChecked(True) if self.conf.get("PostProcessing","write_metadata") == "true" else self.ui.checkbox_settings_post_processing_write_metadata_tags.setChecked(False)

        if self.conf["PostProcessing"]["convert"] == "true":
            self.format = self.conf["PostProcessing"]["format"]
            self.convert_videos = True
            self.ui.radio_settings_post_processing_use_custom_format.setChecked(True)
            self.ui.lineedit_settings_post_processing_use_custom_format.setText(str(self.format))

        else:
            self.ui.radio_settings_post_processing_do_not_convert.setChecked(True)
            self.convert_videos = False

        self.semaphore_limit = self.conf.get("Performance", "semaphore")
        self.search_limit = int(self.conf.get("Video", "search_limit"))
        self.output_path = self.conf.get("Video", "output_path")

        self.gui_language = self.conf.get("UI", "language")
        self.quality = self.conf["Video"]["quality"]
        self.threading_mode = self.conf["Performance"]["threading_mode"]
        self.semaphore = QSemaphore(int(self.semaphore_limit))
        self.delay = int(self.conf["Video"]["delay"])
        self.timeout = int(self.conf["Performance"]["timeout"])
        self.workers = int(self.conf["Performance"]["workers"])
        self.max_retries = int(self.conf["Performance"]["retries"])
        self.model_videos_type = self.conf["Video"]["model_videos"]
        self.ui.settings_spinbox_maximal_timeout.setValue(int(self.timeout))
        self.ui.settings_spinbox_maximal_workers.setValue(int(self.workers))
        self.ui.settings_spinbox_pornhub_delay.setValue(int(self.delay))
        consts.MAX_CALL_RETRIES = self.max_retries
        bs_consts.REQUEST_DELAY = self.delay
        bs_consts.MAX_RETRIES = self.max_retries
        bs_consts.FFMPEG_PATH = ffmpeg_path
        consts.FFMPEG_EXECUTABLE = ffmpeg_path
        self.client = Client(delay=self.delay)

    def save_user_settings(self):
        """Saves the user settings to the configuration file based on the UI state."""
        # Save quality setting
        for quality, radio_button in self.map_quality.items():
            if radio_button.isChecked():
                self.conf.set("Video", "quality", quality)

        # Save threading mode
        for mode, radio_button in self.map_threading_mode.items():
            if radio_button.isChecked():
                self.conf.set("Performance", "threading_mode", mode)

        for language, radio_button in self.map_gui_language.items():
            if radio_button.isChecked():
                self.conf.set("UI", "language", language)

        for model_video_type, radio_button in self.map_model_videos.items():
            if radio_button.isChecked():
                self.conf.set("Video", "model_videos", model_video_type)

        # Save other settings
        self.conf.set("Performance", "semaphore", str(self.ui.settings_spinbox_semaphore.value()))
        self.conf.set("Video", "search_limit", str(self.ui.settings_spinbox_treewidget_limit.value()))
        self.conf.set("Video", "output_path", self.ui.settings_lineedit_output_path.text())
        self.conf.set("Performance", "timeout", str(self.ui.settings_spinbox_maximal_timeout.value()))
        self.conf.set("Performance", "workers", str(self.ui.settings_spinbox_maximal_workers.value()))
        self.conf.set("Video", "delay", str(self.ui.settings_spinbox_pornhub_delay.value()))
        self.conf.set("Performance", "retries", str(self.ui.settings_spinbox_maximal_retries.value()))
        self.conf.set("Setup", "update_checks", "true" if self.ui.settings_checkbox_system_update_checks.isChecked() else "false")
        self.conf.set("Setup", "internet_checks", "true" if self.ui.settings_checkbox_internet_checks.isChecked() else "false")
        self.conf.set("Setup", "anonymous_mode", "true" if self.ui.settings_checkbox_system_anonymous_mode.isChecked() else "false")
        self.conf.set("Setup", "tor", "true" if self.ui.settings_checkbox_system_enable_tor.isChecked() else "false")
        self.conf.set("PostProcessing", "write_metadata", "true" if self.ui.checkbox_settings_post_processing_write_metadata_tags.isChecked() else "false")
        self.conf.set("Video", "skip_existing_files", "true" if self.ui.settings_checkbox_videos_skip_existing_files.isChecked() else "false")
        self.conf.set("Video", "directory_system", "true" if self.ui.settings_checkbox_videos_use_directory_system.isChecked() else "false")

        if self.ui.radio_settings_post_processing_do_not_convert.isChecked():
            self.conf.set("PostProcessing", "convert", "false")

        elif self.ui.radio_settings_post_processing_use_custom_format.isChecked():
            self.conf.set("PostProcessing", "convert", "true")
            self.conf.set("PostProcessing", "format", str(self.ui.lineedit_settings_post_processing_use_custom_format.text()))

        with open("config.ini", "w") as config_file: # type: TextIOWrapper
            self.conf.write(config_file)

        ui_popup(self.tr("Saved User Settings, please restart Porn Fetch!", None))
        logger.debug("Saved User Settings, please restart Porn Fetch.")

    def check_for_updates(self):
        """Checks for updates in a thread, so that the main UI isn't blocked, until update checks are done"""
        self.update_thread = CheckUpdates()
        self.update_thread.signals.result.connect(check_for_updates_result)
        self.threadpool.start(self.update_thread)

    def check_internet(self):
        """Checks if the porn sites are accessible"""
        self.internet_check_thread = InternetCheck()
        self.internet_check_thread.signals.internet_check.connect(self.internet_check_result)
        self.threadpool.start(self.internet_check_thread)

    def internet_check_result(self, results: dict):
        show = False
        formatted_results = ""

        for website, status in results.items():
            if status != "✔":
                formatted_results += f"{website} -->: {status}\n\n"
                show = True

        if show:
            ui_popup(self.tr(f"""
! Warning !
Some websites couldn't be accessed. Here's a detailed report:
------------------------------------------------------------
{formatted_results}"""))

    def check_ffmpeg(self):
        # Check if ffmpeg is available in the system PATH
        global ffmpeg_path
        ffmpeg_path = shutil.which("ffmpeg")

        if ffmpeg_path is None:
            # If ffmpeg is not in PATH, check the current directory for ffmpeg binaries
            ffmpeg_binary = "ffmpeg.exe" if os.path.isfile("ffmpeg.exe") else "ffmpeg" if os.path.isfile(
                "ffmpeg") else None

            if ffmpeg_binary is None:
                # If ffmpeg binaries are not found in the current directory, display warning and disable features
                if self.conf.get("Performance", "ffmpeg_warning") == "true":
                    ffmpeg_warning_message = self.tr(
                        """
FFmpeg isn't installed on your system... Some features won't be available:

- The FFmpeg threading mode
- Converting videos into a valid .mp4 format
- Writing tags / metadata into the videos

These features aren't necessary for Porn Fetch, but can be useful for some people.

To automatically install ffmpeg, just head over to the settings and press the magical button, or install ffmpeg in your
local PATH (e.g, through your linux package manager, or through the Windows PATH)

This warning won't be shown again.
                        """, None)
                    ui_popup(ffmpeg_warning_message)
                    self.conf.set("Performance", "ffmpeg_warning", "false")
                    with open("config.ini", "w") as config_file: #type: TextIOWrapper
                        self.conf.write(config_file)

                self.ui.settings_radio_threading_mode_ffmpeg.setDisabled(True)
                global ffmpeg_features
                ffmpeg_features = False
                logger.error("FFMPEG features have been disabled, because ffmpeg wasn't found on your system.")
            else:
                # If ffmpeg binary is found in the current directory, set it as the ffmpeg path
                ffmpeg_path = os.path.abspath(ffmpeg_binary)

        else:
            # If ffmpeg is found in system PATH, use it directly
            ffmpeg_path = shutil.which("ffmpeg")
            consts.FFMPEG_EXECUTABLE = ffmpeg_path
            bs_consts.FFMPEG_PATH = ffmpeg_path
            logger.debug(f"FFMPEG: {ffmpeg_path}")

    def download_ffmpeg(self):
        if sys.platform == "linux":
            if not os.path.isfile("ffmpeg"):
                self.downloader = FFMPEGDownload(url=url_linux, extract_path=".", mode="linux")

        elif sys.platform == "win32":
            if not os.path.isfile("ffmpeg.exe"):
                self.downloader = FFMPEGDownload(url=url_windows, extract_path=".", mode="windows")

        self.downloader.signals.total_progress.connect(self.update_total_progressbar)
        self.downloader.signals.finished.connect(ffmpeg_finished)
        self.threadpool.start(self.downloader)

    def switch_to_home(self):
        self.ui.main_stacked_widget_main.setCurrentIndex(0)
        self.ui.main_stacked_widget_top.setCurrentIndex(0)
        self.ui.main_stacked_widget_top.setMaximumHeight(260)

    def switch_to_account(self):
        self.ui.main_stacked_widget_top.setCurrentIndex(1)
        self.ui.main_stacked_widget_main.setCurrentIndex(0)
        self.ui.main_stacked_widget_top.setMaximumHeight(220)

    def switch_to_tools(self):
        self.ui.main_stacked_widget_main.setCurrentIndex(0)
        self.ui.main_stacked_widget_top.setCurrentIndex(3)

    def switch_to_settings(self):
        self.ui.main_stacked_widget_main.setCurrentIndex(1)

    def switch_to_credits(self):
        self.ui.main_stacked_widget_main.setCurrentIndex(2)
        self.show_credits()

    def switch_to_supported_websites(self):
        self.ui.main_stacked_widget_main.setCurrentIndex(3)

    def switch_to_all_progress_bars(self):
        self.ui.main_stacked_widget_top.setCurrentIndex(2)
        self.ui.main_stacked_widget_main.setCurrentIndex(0)
        self.ui.main_stacked_widget_top.setMaximumHeight(280)

    """
    The following functions are related to the tree widget    
    """

    def add_to_tree_widget_thread(self, iterator):
        search_limit = self.search_limit
        data_mode = 0 if self.ui.main_radio_tree_show_title.isChecked() else 1
        is_reverse = self.ui.main_checkbox_tree_show_videos_reversed.isChecked()
        is_checked = self.ui.main_checkbox_tree_do_not_clear_videos.isChecked()

        self.thread = AddToTreeWidget(iterator=iterator, search_limit=search_limit, data_mode=data_mode,
                                      is_reverse=is_reverse, is_checked=is_checked, last_index=self.last_index,
                                      stop_flag=stop_flag)
        self.thread.signals.text_data.connect(self.add_to_tree_widget_signal)
        self.thread.signals.progress.connect(self.progress_tree_widget)
        self.thread.signals.clear_signal.connect(self.clear_tree_widget)
        self.thread.signals.start_undefined_range.connect(self.start_undefined_range)
        self.thread.signals.stop_undefined_range.connect(self.stop_undefined_range)
        self.thread.signals.error_signal.connect(self.on_video_load_error)
        self.threadpool.start(self.thread)

    def add_to_tree_widget_signal(self, data):
        """
        This is the signal for the Tree Widget thread. It receives the data and applies it to the GUI
        """
        self.last_index += 1
        title = data[0]
        author = data[1]
        try:
            duration = float(data[2])  # Ensure duration is a float

        except ValueError:
            duration = parse_length(data[2])

        index = data[3]
        video = data[4]
        thumbnail = data[5]

        item = QTreeWidgetItem(self.ui.treeWidget)
        item.setText(0, f"{index}) {title}")
        item.setText(1, author)

        # Determine how many zeros are needed based on the type and value of duration
        if isinstance(duration, float):
            formatted_duration = f"{int(duration):05d}"
            # Handle the decimal part separately if needed
            decimal_part = str(duration).split('.')[1]
            if decimal_part != '0':
                formatted_duration += '.' + decimal_part

        else:
            formatted_duration = f"{duration:05d}"

        duration = round(duration)
        duration = str(duration).strip("0").strip(".")
        item.setCheckState(0, Qt.Unchecked)
        item.setData(0, Qt.UserRole, video)
        item.setData(1, Qt.UserRole, author)
        item.setText(2, duration)  # Set the text as the zero-padded number or float
        item.setData(2, Qt.UserRole, formatted_duration)  # Store the original duration for sorting
        item.setData(3, Qt.UserRole, thumbnail)

    def download_tree_widget(self):
        """
        Starts the thread for downloading the tree widget (All selected videos)
        """
        treeWidget = self.ui.treeWidget
        download_tree_thread = QTreeWidgetDownloadThread(treeWidget=treeWidget, quality=self.quality,
                                                         semaphore=self.semaphore, threading_mode=self.threading_mode)
        download_tree_thread.signals.progress_video.connect(self.tree_widget_receive_video)
        download_tree_thread.signals.start_undefined_range.connect(self.start_undefined_range)
        download_tree_thread.signals.stop_undefined_range.connect(self.stop_undefined_range)
        self.threadpool.start(download_tree_thread)
        self.threadpool.releaseThread()

    def clear_tree_widget(self):
        """
        This (like the name says) clears the tree widget.
        """
        if not self.ui.main_checkbox_tree_do_not_clear_videos.isChecked():
            self.ui.treeWidget.clear()

    def reindex(self):
        ascending = self.ui.treeWidget.header().sortIndicatorOrder() == Qt.AscendingOrder
        count = self.ui.treeWidget.topLevelItemCount()
        for i in range(count):
            if ascending:
                # When sorting in ascending order, start indexes at 1 and increment
                new_index = i + 1
            else:
                # When sorting in descending order, start indexes at the count and decrement
                new_index = count - i

            item = self.ui.treeWidget.topLevelItem(i)
            current_text = item.text(0)
            original_title = current_text.split(') ', 1)[1] if ') ' in current_text else current_text
            item.setText(0, f"{new_index}) {original_title}")

    def progress_tree_widget(self, total, current):
        """This tracks the progress of the tree widget data"""
        self.ui.main_progressbar_total.setMaximum(total)
        self.ui.main_progressbar_total.setValue(current)

    def tree_widget_receive_video(self, video):
        """
        This emits the video. If the semaphore is released, this function is called, so that the next video can be
        downloaded.
        """
        self.load_video(video)

    def unselect_all_items(self):
        """Unselects all items from the tree widget"""
        root = self.ui.treeWidget.invisibleRootItem()
        item_count = root.childCount()
        for i in range(item_count):
            item = root.child(i)
            item.setCheckState(0, Qt.Unchecked)

    def select_range_of_items(self):
        # Create an instance of the UI form widget
        self.widget = QWidget()
        self.range_ui = Ui_PornFetchRangeSelector()
        self.range_ui.setupUi(self.widget)
        root = self.ui.treeWidget.invisibleRootItem()
        item_count = root.childCount()
        self.range_ui.spinbox_range_end.setMaximum(item_count)
        self.range_ui.button_range_apply_index.clicked.connect(self.process_range_of_items_selection_index)
        self.range_ui.button_range_apply_time.clicked.connect(self.process_range_of_items_selection_time)
        self.range_ui.button_range_apply_author.clicked.connect(self.process_range_of_items_author)

        # Show the new widget
        self.widget.show()

    def select_all_items(self):
        """Selects all items from the tree widget"""
        root = self.ui.treeWidget.invisibleRootItem()
        item_count = root.childCount()
        for i in range(item_count):
            item = root.child(i)
            item.setCheckState(0, Qt.Checked)

        try:
            self.widget.deleteLater()

        except AttributeError:
            pass # This is expected when using the Keyboard shortcuts

    def process_range_of_items_selection_index(self):
        start = self.range_ui.spinbox_range_start.value()
        end = self.range_ui.spinbox_range_end.value()
        root = self.ui.treeWidget.invisibleRootItem()

        # Adjust start and end indices to match tree widget indexing
        start -= 1
        end -= 1

        for i in range(start, end + 1):  # Adjust the range to be inclusive of the end
            item = root.child(i)
            item.setCheckState(0, Qt.Checked)

        self.widget.deleteLater()

    def process_range_of_items_selection_time(self):
        start_time = int(self.range_ui.lineedit_range_start.text())
        end_time = int(self.range_ui.lineedit_range_end.text())
        root = self.ui.treeWidget.invisibleRootItem()

        # Loop through all items in the QTreeWidget
        for i in range(root.childCount()):
            item = root.child(i)

            # Retrieve the duration from the item, assuming it's stored as an integer in UserRole
            duration = int(item.data(2, Qt.UserRole))

            # Check if the duration is within the specified start and end times
            if start_time <= duration <= end_time:
                item.setCheckState(0, Qt.Checked)

        # Assuming this is meant to close the widget, but it might be better to handle this outside this function
        self.widget.deleteLater()

    def process_range_of_items_author(self):
        name = str(self.range_ui.lineedit_range_author.text())
        root = self.ui.treeWidget.invisibleRootItem()

        for i in range(root.childCount()):
            item = root.child(i)
            author = str(item.data(1, Qt.UserRole))
            if str(author).lower() == str(name).lower():
                item.setCheckState(0, Qt.Checked)

        self.widget.deleteLater()

    def start_single_video(self):
        """
        Starts the download of a single video.
        This still uses the tree widget because this makes it easier to track the total progress, as I've already
        implemented this feature into the tree widget and I don't want to write code 2 times
        """
        url = self.ui.download_lineedit_url.text()
        one_time_iterator = []

        try:
            video = check_video(url=url, delay=self.delay)

        except errors.PremiumVideo:
            ui_popup(self.tr("The video can not be downloaded, because it's a PornHub Premium video"))
            return

        except errors.RegionBlocked:
            ui_popup(self.tr("The video can not be downloaded, because it's either blocked in your region, or set private by the uploader"))
            return

        one_time_iterator.append(video)
        self.add_to_tree_widget_thread(iterator=one_time_iterator)

    def start_model(self, url=None):
        """Starts the model downloads"""
        if isinstance(url, str):
            model = url

        else:
            model = self.ui.download_lineedit_model_url.text()

        if pornhub_pattern.match(model):
            if not isinstance(self.client, Client):
                client = Client(delay=self.delay)

            else:
                client = self.client

            model_object = client.get_user(model)
            videos = model_object.videos
            uploads = model_object.uploads

            if self.model_videos_type == "both":
                videos = chain(uploads, videos)

            elif self.model_videos_type == "featured":
                videos = videos

            elif self.model_videos_type == "uploads":
                videos = uploads

        elif hqporner_pattern.match(model):
            videos = hq_Client().get_videos_by_actress(name=model)

        elif eporner_pattern.match(model):
            videos = ep_Client.get_pornstar(url=model, enable_html_scraping=True).videos()

        elif xnxx_pattern.match(model):
            videos = xn_Client.get_user(url=model).videos

        elif xvideos_pattern.match(model):
            videos = xv_Client().get_pornstar(url=model).videos

        self.add_to_tree_widget_thread(videos)

    def start_playlist(self):
        url = self.ui.download_lineedit_playlist_url.text()
        playlist = self.client.get_playlist(url)
        videos = playlist.sample()
        self.add_to_tree_widget_thread(iterator=videos)

    def load_video(self, url):
        """This starts the thread to load a video"""

        self.video_loader_thread = VideoLoader(url=url, output_path=self.output_path, quality=self.quality,
                                               directory_system=self.directory_system, delay=self.delay,
                                               threading_mode=self.threading_mode)
        # Connect signals to your slots
        self.video_loader_thread.signals.loaded.connect(self.on_video_loaded)
        self.video_loader_thread.signals.error.connect(self.on_video_load_error)
        self.threadpool.start(self.video_loader_thread)


    def on_video_loaded(self, video, output_file_path, threading_mode, quality):
        # Handle the loaded video and start download
        self.stop_undefined_range()
        self.process_video_thread(video=video, output_path=output_file_path, threading_mode=threading_mode,
                                  quality=quality)

    def on_video_load_error(self, error_message):
        # Handle errors and show a message to user
        logger.debug(f"Error loading video: {error_message}")
        ui_popup(self.tr( f"Some error occurred in loading a video. Please report this: {error_message}",
                                       None))

    def set_thumbnail(self, item, column):
        """Set the thumbnail for the selected video."""
        self.ui.main_label_tree_show_thumbnail.setScaledContents(False)  # Ensure manual scaling
        self.ui.main_label_tree_show_thumbnail.setFixedWidth(500)
        self.ui.main_label_tree_show_thumbnail.setFixedHeight(281.25)

        if item is None:  # Handle no selection
            return

        if self._anonymous_mode:
            self.ui.main_label_tree_show_thumbnail.setText(self.tr("Can't show thumbnail, due to your privacy settings ;)",
                                                                   disambiguation=None))
            return

        thumbnail = item.data(3, Qt.UserRole)  # Retrieve the thumbnail URL

        if not thumbnail:
            self.ui.main_label_tree_show_thumbnail.setText(
                self.tr("No thumbnail available", disambiguation=None)
            )
        else:
            # Load the thumbnail image dynamically
            try:
                pixmap = QPixmap()
                pixmap.loadFromData(requests.get(thumbnail).content)

                # Scale the pixmap to fit the fixed QLabel size while maintaining the aspect ratio
                scaled_pixmap = pixmap.scaled(
                    self.ui.main_label_tree_show_thumbnail.width(),
                    self.ui.main_label_tree_show_thumbnail.height(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.ui.main_label_tree_show_thumbnail.setPixmap(scaled_pixmap)
            except Exception as e:
                self.ui.main_label_tree_show_thumbnail.setText(f"Failed to load image: {e}")


    def process_video_thread(self, output_path, video, threading_mode, quality):
        """Checks which of the three types of threading the user selected and handles them."""
        self.download_thread = DownloadThread(video=video, output_path=output_path, quality=self.quality,
                                              threading_mode=threading_mode, workers=self.workers, timeout=self.timeout,
                                              stop_flag=stop_flag, skip_existing_files=self.skip_existing_files)
        self.download_thread.signals.progress.connect(self.update_progressbar)
        self.download_thread.signals.total_progress.connect(self.update_total_progressbar)
        self.download_thread.signals.progress_hqporner.connect(self.update_progressbar_hqporner)
        self.download_thread.signals.progress_eporner.connect(self.update_progressbar_eporner)
        self.download_thread.signals.progress_xnxx.connect(self.update_progressbar_xnxx)
        self.download_thread.signals.progress_xvideos.connect(self.update_progressbar_xvideos)
        self.download_thread.signals.progress_spankbang.connect(self.update_progressbar_spankbang)
        self.download_thread.signals.ffmpeg_progress.connect(self.update_converting)
        # ADAPTION
        self.download_thread.signals.completed.connect(self.download_completed)
        self.threadpool.start(self.download_thread)
        logger.debug("Started Download Thread!")

    """
    The following functions are used to connect data between Threads and the Main UI
    """

    def update_total_progressbar(self, value, maximum):
        """This updates the total progressbar"""
        self.ui.main_progressbar_total.setMaximum(maximum)
        self.ui.main_progressbar_total.setValue(value)

    def update_converting(self, value, maximum):
        """This updates the converting progressbar"""
        self.ui.main_progressbar_converting.setMaximum(maximum)
        self.ui.main_progressbar_converting.setValue(value)

    def update_progressbar(self, value, maximum):
        """This updates the PornHub progressbar"""
        self.ui.progressbar_pornhub.setMaximum(maximum)
        self.ui.progressbar_pornhub.setValue(value)

    def update_progressbar_hqporner(self, value, maximum):
        """This updates the HQPorner progressbar"""
        self.ui.progressbar_hqporner.setMaximum(maximum)
        self.ui.progressbar_hqporner.setValue(value)

    def update_progressbar_eporner(self, value, maximum):
        """This updates the eporner progressbar"""
        self.ui.progressbar_eporner.setMaximum(maximum)
        self.ui.progressbar_eporner.setValue(value)

    def update_progressbar_xnxx(self, value, maximum):
        """This updates the xnxx progressbar"""
        self.ui.progressbar_xnxx.setMaximum(maximum)
        self.ui.progressbar_xnxx.setValue(value)

    def update_progressbar_xvideos(self, value, maximum):
        """This updates the xvideos progressbar"""
        self.ui.progressbar_xvideos.setMaximum(maximum)
        self.ui.progressbar_xvideos.setValue(value)

    def update_progressbar_spankbang(self, value, maximum):
        self.ui.progressbar_spankbang.setMaximum(maximum)
        self.ui.progressbar_spankbang.setValue(value)

    # ADAPTION
    def download_completed(self):
        """If a video is downloaded, the semaphore is released"""
        logger.debug("Download Completed!")
        global total_downloaded_videos
        total_downloaded_videos += 1
        self.ui.progress_lineedit_download_info.setText(f"Downloaded: {total_downloaded_videos} video(s) this session.")
        self.ui.main_progressbar_total.setMaximum(100)
        self.ui.progressbar_hqporner.setValue(0)
        self.ui.progressbar_eporner.setValue(0)


        self.semaphore.release()


    def start_undefined_range(self):
        """This starts the undefined range (loading animation) of the total progressbar"""
        self.ui.main_progressbar_total.setRange(0, 0)

    def stop_undefined_range(self):
        """This stops the undefined range (loading animation) of the total progressbar"""
        self.ui.main_progressbar_total.setMinimum(0)
        self.ui.main_progressbar_total.setMaximum(100)
        self.ui.main_progressbar_total.setValue(0)

    """
    The following functions are used for opening files / directories with the QFileDialog
    """

    def open_output_path_dialog(self):
        """This handles the output path from the settings widget"""
        dialog = QFileDialog()
        path = dialog.getExistingDirectory()
        self.ui.settings_lineedit_output_path.setText(str(path))
        self.output_path = path
        self.save_user_settings()

    def open_file_dialog(self):
        """This opens and processes urls in the file"""
        dialog = QFileDialog()
        file, types = dialog.getOpenFileName()
        self.ui.download_lineedit_file.setText(file)
        self.start_file_processing()

    def start_file_processing(self):
        file = self.ui.download_lineedit_file.text()
        self.url_thread = AddUrls(file, delay=self.delay)
        self.url_thread.signals.total_progress.connect(self.update_total_progressbar)
        self.url_thread.signals.url_iterators.connect(self.receive_url_result)
        self.threadpool.start(self.url_thread)

    def receive_url_result(self, iterator, model_iterator, search_iterator):
        logger.debug(f"Received Video Iterator ({len(iterator)} videos)")
        logger.debug(f"Received Model Iterator ({len(model_iterator)} urls)")
        logger.debug(f"Received Search Iterator ({len(search_iterator)} keywords)")

        logger.debug("Processing Videos...")
        self.add_to_tree_widget_thread(iterator)
        logger.debug("Processing Models...")
        for url in model_iterator:
            self.start_model(url)

        logger.debug("Processing Search queries....")
        for search in search_iterator:
            query = search.get("query")
            website = search.get("website")

            if website == "hqporner":
                self.ui.download_radio_search_website_hqporner.setChecked(True)

            elif website == "xvideos":
                self.ui.download_radio_search_website_xvideos.setChecked(True)

            elif website == "pornhub":
                self.ui.download_radio_search_website_pornhub.setChecked(True)

            elif website == "xnxx":
                self.ui.download_radio_search_website_xnxx.setChecked(True)

            elif website == "eporner":
                self.ui.download_radio_search_website_eporner.setChecked(True)

            else:
                ui_popup(self.tr(f"Information: The Website {website} specified in the URL file isn't valid.", None))
                return

            self.ui.download_lineedit_search_query.setText(query)
            self.basic_search()

        self.ui.download_lineedit_search_query.clear()

    def login(self):
        """
        This handles logging in into the users PornHub accounts
        I need to update this to support more websites
        """
        # TODO

        username = self.ui.login_lineedit_username.text()
        password = self.ui.login_lineedit_password.text()
        if len(username) <= 2 or len(password) <= 2:
            ui_popup(self.tr("Those credentials don't seem to be valid...", None))
            return

        try:
            self.client = Client(username, password, delay=self.delay)
            logger.debug("Login Successful!")
            ui_popup(self.tr( "Login Successful!", None))
            self.switch_login_button_state()

        except errors.LoginFailed:
            ui_popup(self.tr("Login Failed, please check your credentials and try again!", None))

        except errors.ClientAlreadyLogged:
            ui_popup(self.tr("You are already logged in!", None))

    def switch_login_button_state(self):
        """If the user is logged in, I'll change the stylesheets of the buttons"""
        file = QFile(":/style/stylesheets/stylesheet_switch_buttons_login_state.qss")
        file.open(QFile.ReadOnly | QFile.Text)
        stream = QTextStream(file)
        stylesheet = stream.readAll()

        self.ui.login_button_get_liked_videos.setStyleSheet(stylesheet)
        self.ui.login_button_get_watched_videos.setStyleSheet(stylesheet)
        self.ui.login_button_get_recommended_videos.setStyleSheet(stylesheet)

    def check_login(self):
        """Checks if the user is logged in, so that no errors are threw if not"""
        if self.client.logged:
            return True

        elif not self.client.logged:
            self.login()
            if not self.client.logged:
                text = self.tr("There's a problem with the login. Please make sure you login first and then "
                               "you try to get videos based on your account.", None)
                ui_popup(text)
                return False

            else:
                return True

    def get_watched_videos(self):
        """Returns the videos watched by the user"""
        if self.check_login():
            watched = self.client.account.watched
            self.add_to_tree_widget_thread(watched)

    def get_liked_videos(self):
        """Returns the videos liked by the user"""
        if self.check_login():
            liked = self.client.account.liked
            self.add_to_tree_widget_thread(liked)

    def get_recommended_videos(self):
        """Returns the videos recommended for the user"""
        if self.check_login():
            recommended = self.client.account.recommended
            self.add_to_tree_widget_thread(recommended)

    """
    The following functions are related to the search functionality
    """

    def basic_search(self):
        """Does a simple search for videos without filters on selected website"""
        query = self.ui.download_lineedit_search_query.text()

        if self.ui.download_radio_search_website_pornhub.isChecked():
            videos = Client().search(query)

        elif self.ui.download_radio_search_website_xvideos.isChecked():
            videos = xv_Client.search(query)

        elif self.ui.download_radio_search_website_hqporner.isChecked():
            videos = hq_Client.search_videos(query)

        elif self.ui.download_radio_search_website_eporner.isChecked():
            videos = ep_Client().search_videos(query, sorting_gay="", sorting_order="", sorting_low_quality="", page=1,
                                               per_page=self.search_limit, enable_html_scraping=True)

        elif self.ui.download_radio_search_website_xnxx.isChecked():
            videos = xn_Client().search(query).videos

        self.add_to_tree_widget_thread(videos)

    def get_top_porn_hqporner(self):
        if self.ui.tools_radio_top_porn_week.isChecked():
            sort = hq_Sort.WEEK

        elif self.ui.tools_radio_top_porn_month.isChecked():
            sort = hq_Sort.MONTH

        elif self.ui.tools_radio_top_porn_all_time:
            sort = hq_Sort.ALL_TIME

        else:
            sort = None

        videos = hq_Client().get_top_porn(sort_by=sort)
        self.add_to_tree_widget_thread(iterator=videos)

    def get_by_category_hqporner(self):
        """Returns video by category from HQPorner. I want to add support for EPorner"""  # TODO
        category_name = self.ui.tools_lineedit_hqporner_category.text()
        all_categories = hq_Client().get_all_categories()

        if not category_name in all_categories:
            ui_popup(self.tr("Invalid Category. Press 'list categories' to see all "
                                                  "possible ones.", None))

        else:
            videos = hq_Client().get_videos_by_category(category=category_name)
            self.add_to_tree_widget_thread(videos)

    def get_by_category_eporner(self):
        """Returns video by category from EPorner"""
        category_name = self.ui.tools_lineedit_videos_by_category_eporner.text()

        if not category_name in self.all_cateogories_eporner:
            ui_popup(self.tr("Invalid Category. Press 'list categories' to see all "
                                                  "possible ones.", None))

        else:
            videos = ep_Client().get_videos_by_category(category=category_name, enable_html_scraping=True)
            self.add_to_tree_widget_thread(iterator=videos)

    def list_categories_eporner(self):
        """Lists all video categories from EPorner"""
        all_categories = ",".join([getattr(ep_Category, category) for category in dir(ep_Category) if
                                   not callable(getattr(ep_Category, category)) and not category.startswith("__")])

        self.all_cateogories_eporner = all_categories  # Need this list to verify the category later
        ui_popup(all_categories)

    def get_brazzers_videos(self):
        """Get brazzers videos from HQPorner"""
        videos = hq_Client().get_brazzers_videos()
        self.add_to_tree_widget_thread(videos)

    @classmethod
    def list_categories_hqporner(cls):
        """Get all available categories. I want to also extend that for EPorner (and maybe even more sites)"""
        categories_ = hq_Client().get_all_categories()
        categories = ",".join(categories_)
        ui_popup(categories)

    def get_random_video(self):
        """Gets a random video from HQPorner"""
        video = hq_Client().get_random_video()
        print(video.title)
        some_list = [video]
        self.add_to_tree_widget_thread(some_list)

    def show_credits(self):
        """Loads the credits from the CREDITS.md.  Credits need to be recompiled in the resource file every time"""
        if self.ui.settings_checkbox_system_anonymous_mode.isChecked():
            self.ui.main_textbrowser_credits.setText("Running in anonymous mode...")

        else:
            self.ui.main_textbrowser_credits.setOpenExternalLinks(True)
            file = QFile(":/credits/README/CREDITS.md")
            file.open(QFile.ReadOnly | QFile.Text)
            stream = QTextStream(file)
            self.ui.main_textbrowser_credits.setHtml(markdown.markdown(stream.readAll()))

    def show_keyboard_shortcuts(self):
        self.keyboard_widget = QWidget()
        self.keyboard_widget_ = Ui_KeyboardShortcuts()
        self.keyboard_widget_.setupUi(self.keyboard_widget)
        self.keyboard_widget.show()


def main():
    setup_config_file()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    conf = ConfigParser()
    conf.read("config.ini")
    language = conf["UI"]["language"]

    if language == "system":
        # Get the system's locale
        locale = QLocale.system()
        language_code = locale.name()

    else:
        language_code = language

    # Try loading the specific regional translation
    path = f":/translations/translations/{language_code}.qm"
    translator = QTranslator(app)
    if translator.load(path):
        logger.debug(f"Startup: [1/5] {language_code} translation loaded")

    else:
        # Try loading a more general translation if specific one fails
        general_language_code = language_code.split('_')[0]
        path = f":/translations/translations/{general_language_code}.qm"
        if translator.load(path):
            logger.debug(f"{general_language_code} translation loaded as fallback")
        else:
            logger.debug(f"Failed to load {language_code} translation")

    app.installTranslator(translator)

    file = QFile(":/style/stylesheets/stylesheet.qss")
    file.open(QFile.ReadOnly | QFile.Text)
    stream = QTextStream(file)
    app.setStyleSheet(stream.readAll())

    if __build__ == "android":
        font = QFont("arial", 12)
        app.setFont(font)

    if conf["UI"]["custom_font"] == "true":
        font_id = QFontDatabase.addApplicationFont(":/fonts/graphics/JetBrainsMono-Regular.ttf")
        if font_id == -1:
            print("Failed to load font, please report") # TODO
        else:

            # Get the family name of the loaded font
            font_family = QFontDatabase.applicationFontFamilies(font_id)[0]
            logger.info(f"Using custom font -->: {font_family}")
            app.setFont(QFont(font_family))

    widget = License()  # Starts License widget and checks if license was accepted.
    widget.check_license_and_proceed()
    """
    The following exceptions are just general exceptions to handle some basic errors. They are not so relevant for
    most cases.
    """

    sys.exit(app.exec())


if __name__ == "__main__":
    """
    These functions are static functions which I won't need while coding.
    These just exist for some reason, but I don't want to scroll through endless lines of code,
    which is why I placed them here.
    """

    def load_stylesheet(path):
        """Load stylesheet from a given path with explicit open and close."""
        file = QFile(path)
        if not file.open(QFile.ReadOnly | QFile.Text):
            logger.debug(f"Failed to open {path}")
            return ""
        stylesheet = QTextStream(file).readAll()
        file.close()
        return stylesheet


    def reset_pornfetch():
        setup_config_file(force=True)
        ui_popup(QCoreApplication.translate("main", "Done! Please restart.", None))


    def switch_stop_state_2():
        global stop_flag
        stop_flag = Event()


    def switch_stop_state():
        stop_flag.set()
        time.sleep(1)
        switch_stop_state_2()


    def export_urls():
        # TODO
        if not len(session_urls) == 0:
            file, type = QFileDialog().getOpenFileName()
            with open(file, "w") as url_export_file:
                for url in session_urls:
                    url_export_file.write(f"{url}\n")

            ui_popup(f"Success! Saved: {len(session_urls)} URLs")

        else:
            ui_popup(QCoreApplication.translate("main", "No URLs in the current session...", None))

    def ffmpeg_finished():
        ui_popup(QCoreApplication.translate("main", "FFmpeg has been installed. Please restart Porn Fetch :)", None))


    def check_for_updates_result(value):
        """Receives the Update result from the thread"""
        if value:
            logger.debug(f"Next release v{__next_release__} found!")
            try:
                changelog = (requests.get(f"https://github.com/EchterAlsFake/Porn_Fetch/tree/master/README/Changelog/"
                                          f"{__next_release__}/Changelog.md").text)

            except Exception as e:
                logger.error(f"Couldn't fetch changelog of version: {__next_release__}")
                changelog = f"Unknown Error: {e}"

            ui_popup(QCoreApplication.translate("main", f"""
            Information: A new version of Porn Fetch (v{__next_release__}) is out. I recommend you to update Porn Fetch. 
            Go to: https://github.com/EchterAlsFake/Porn_Fetch/releases/tag/ {__next_release__}

            Changelog:
            {markdown.markdown(changelog)}

            """, None))

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--version", help="Shows the version information", action="store_true")
    args = parser.parse_args()

    if args.version:
        print(__version__)
    main()

