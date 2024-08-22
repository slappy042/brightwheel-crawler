from dataclasses import dataclass
from datetime import datetime
import json
import logging
import os
import re
import time
from typing import Optional
from urllib.request import urlopen
from zoneinfo import ZoneInfo
import yaml
import argparse
import random
import sys

import undetected_chromedriver as uc

from selenium.common.exceptions import NoSuchElementException
from selenium import webdriver

from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from webdriver_manager.chrome import ChromeDriverManager

from PIL import Image

import piexif

"""I was saving pictures ad hoc through the brightwheel app, but got way behind
and didn't want to lose them if my kid changed schools or lost access to the app.
This uses selenium to crawl a BrightWheel (https://mybrightwheel.com/) profile
for images, find all of them, pass the cookies to requests, and then download
all images in bulk. Works with current site design as off 6/24/19"""

BASE_BRIGHTWHEEL_URL = "https://schools.mybrightwheel.com"

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

file_handler = logging.FileHandler("scraper.log")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

@dataclass
class Student:
    id: str
    name: str
class Config(yaml.YAMLObject):
    yaml_tag = u'!Config'
    yaml_loader=yaml.SafeLoader
    username:  str
    password: str
    guardian_id: str | None
    child_ids: list[Student] | None
    signin_url: str
    kidlist_url: str
    start_date: datetime
    end_date: datetime
    start_page:int | None
    page_size:int | None
    timezone: ZoneInfo | None

    def __init__(
            self, 
            bwuser, 
            bwpass, 
            guardianid, 
            childids, 
            bwsignin, 
            bwlist, 
            startdate, 
            enddate, 
            startpage = 0, 
            pagesize = 10, 
            timezone = "UTC",
    ) -> None:
        self.username = bwuser
        self.password = bwpass
        self.guardian_id = guardianid
        self.child_ids = childids
        self.signin_url = bwsignin
        self.kidlist_url = bwlist
        self.start_date = datetime.strptime(startdate, "%m/%d/%Y")
        self.end_date = datetime.strptime(enddate, "%m/%d/%Y")
        self.start_page = startpage
        self.page_size = pagesize
        self.timezone = ZoneInfo(timezone)

def config_parser() -> Config:
    """parse config file in config.yml if present"""

    try:
        with open("config.yml", "r") as bw_config:
            return yaml.safe_load(bw_config)
            
    except FileNotFoundError:
        logger.error("[!] No config file found, check config file!")
        raise SystemExit
    
    except KeyError:
        logger.error("[!] - Check config file, missing required values")
        raise SystemExit


def get_random_time():
    """Randomly wait before sending imput, some time under 4 seconds"""
    random_wait = random.randint(0, 2000)
    return random_wait / 1000


# Get the first URL and populate the fields
def signme_in(browser, config: Config):
    """Populate and send login info using U/P from config"""

    browser.get(config.signin_url)
    time.sleep(get_random_time())
    loginuser = browser.find_element(By.XPATH, '//input[@id="username"]')
    loginpass = browser.find_element(By.ID, "password")
    loginuser.click()
    time.sleep(get_random_time())
    loginuser.send_keys(config.username)
    loginpass.click()
    time.sleep(get_random_time())
    loginpass.send_keys(config.password)

    # Submit login, have to wait for page to change
    try:
        loginpass.submit()
        WebDriverWait(browser, 45).until(EC.url_changes(config.signin_url))
    except:
        logger.error("[!] - Unable to authenticate - Check credentials")
        raise SystemExit
    time.sleep(get_random_time() * 3)  # Change this to the amount of time you need to solve the captcha manually
    return browser

def get_json_from_session(session: webdriver.Chrome) -> dict:    
    try:
        json_container = session.find_element(By.TAG_NAME, 'pre')
        parsed_json = json.loads(json_container.text)
    except NoSuchElementException:
        logger.error("[!] - 'pre' element not found in response")
        raise SystemExit
    return parsed_json

def get_guardian_id(session: webdriver.Chrome, url: str = "/api/v1/users/me"):
    me_url = f"{BASE_BRIGHTWHEEL_URL}{url}"
    session.get(me_url)
    me = get_json_from_session(session=session)
    logger.info('me %s', me)
    guardian_id: str = me.get("object_id", None)
    if not guardian_id:
        logger.error("[!] - could not extract guardian id")
        raise SystemExit
    return guardian_id

def get_child_ids(session: webdriver.Chrome, id: str, index: Optional[int]):
    students_url = f"{BASE_BRIGHTWHEEL_URL}/api/v1/guardians/{id}/students?include[]=schools"
    session.get(students_url)
    students = get_json_from_session(session=session)
    logger.info('children %s', students)
    students_list: list[str] = students.get("students", [])
    if not students_list:
        logger.error("[!] - could not extract student ids")
        raise SystemExit
    if index:
        students_list = [students_list[index]]

    return [Student(id = student["student"]["object_id"], name = student["student"]["first_name"]) for student in students_list]

def get_activities(session: webdriver.Chrome, id: str, page: int, page_size: int, start: str, end: str,):
    activities_url = f"{BASE_BRIGHTWHEEL_URL}/api/v1/students/{id}/activities?page={page}&page_size={page_size}&start_date={start}&end_date={end}&action_type=ac_photo&include_parent_actions=true"
    session.get(activities_url)
    activities = get_json_from_session(session=session)
    logger.info('activities %s', activities)
    activity_list: list[dict] = activities.get("activities", None)
    if not activity_list:
        logger.error("[!] - could not extract activities")
        raise SystemExit
    return activity_list

def generate_exif_data(activity: dict, config: Config):    
    created_date_str = activity["created_at"]        
    created_date = datetime.strptime(created_date_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=config.timezone)    
    formatted_created_date = created_date.astimezone(tz=config.timezone).strftime('%Y:%m:%d %H:%M:%S')    
    actor: dict = activity["actor"]
    teacher_name: str = ""
    if actor:
        first_name: str = actor.get("first_name", "")
        last_name: str = actor.get("last_name", "")
        teacher_name: str = f"{first_name} {last_name}"
    note: str = activity.get("note", "")    
    zeroth_ifd = {
        piexif.ImageIFD.Artist: teacher_name.encode("utf-8", errors="ignore") if teacher_name else "",
        piexif.ImageIFD.ImageDescription: note.encode("utf-8", errors="ignore") if note else "",
        piexif.ImageIFD.DateTime: formatted_created_date,
    }
    exif_ifd = {
        piexif.ExifIFD.DateTimeOriginal: formatted_created_date,
    }
    exif_dict = {"0th": zeroth_ifd, "Exif": exif_ifd}
    exif_bytes = piexif.dump(exif_dict)
    return exif_bytes

def use_chrome_selenium(version: Optional[int] = 127) -> uc.Chrome:
    """Use undetected chrome driver

    Args:
        version (Optional[int], optional): Specify Chrome driver version if you are having issues. Defaults to 127.

    Returns:
        uc.Chrome: Controls the ChromeDriver and allows you to drive the browser.

    Notes:
        I had issues with the version, resolved using this post: https://stackoverflow.com/questions/29858752/error-message-chromedriver-executable-needs-to-be-available-in-the-path/52878725#52878725
    """

    browser = uc.Chrome(
        service=ChromeService(ChromeDriverManager().install()), 
        version_main=version
        )
    return browser


def use_existing_chrome_session():
    # Check if chrome is listening on port 9222
    # If not, start it
    try:
        chrome_options = webdriver.ChromeOptions()
        chrome_options.debugger_address = "127.0.0.1:9222"
        browser = webdriver.Chrome(
            options=chrome_options, 
            service=ChromeService(ChromeDriverManager().install())
        )
        return browser
    except Exception as e:
        logger.error(f"An error occurred: {e} - Please ensure Chrome is listening on port 9222")
        sys.exit(1)


def main():   
    parser = argparse.ArgumentParser(description="Brightwheel Scraper")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-c", "--chrome_selenium", action="store_true", help="Use existing Chrome session to login to Brightwheel")
    group.add_argument("-e", "--chrome_session", action="store_true", help="Use existing Chrome session to login to Brightwheel")
    parser.add_argument(
        "-n", "--student-number", type=int, help="Select a student by number, indexed starting at 0. Look at the student list and count in order"
    )
    args = parser.parse_args()

    if args.chrome_selenium:
        browser = use_chrome_selenium()
    elif args.chrome_session:
        browser = use_existing_chrome_session()
    else:
        logger.error("[!] - No browser selected, exiting")

     # Check if the ./pics/ directory exists, create it if it doesn't
    if not os.path.exists('./pics/'):
        os.makedirs('./pics/')
        
    config = config_parser()

    session = signme_in(browser, config=config)

    if not config.guardian_id:
        config.guardian_id=get_guardian_id(session)

    if not config.child_ids:
        config.child_ids = get_child_ids(session)

    start_date_tz = config.start_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    end_date_tz = config.end_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")    
    # Begin fetching and saving images for each child
    for child in config.child_ids:
        page = config.start_page
        while True:
            activities = get_activities(
                session=session, 
                id=child.id, 
                page=page, 
                page_size=config.page_size, 
                start=start_date_tz, 
                end=end_date_tz
            )
            for activity in activities:

                event_date_str = activity["event_date"]                
                event_date = datetime.strptime(event_date_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=config.timezone)    
                formatted_event_date = event_date.astimezone(tz=config.timezone).strftime("%Y%m%d")
                
                media = activity["media"]

                exif = generate_exif_data(activity, config=config)           

                filename = f"{child.name}_{formatted_event_date}_{media['object_id']}.jpg"

                with Image.open(urlopen(media["image_url"])) as img:
                    img.save("./pics/" + filename, exif=exif)

if __name__ == "__main__":
    main()
