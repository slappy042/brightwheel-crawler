from datetime import datetime
import logging
import os
import re
import time
from typing import Optional
from zoneinfo import ZoneInfo
import yaml
import argparse
import random
import sys

import requests
import undetected_chromedriver as uc

from selenium.common.exceptions import ElementNotVisibleException
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from webdriver_manager.chrome import ChromeDriverManager

"""I was saving pictures ad hoc through the brightwheel app, but got way behind
and didn't want to lose them if my kid changed schools or lost access to the app.
This uses selenium to crawl a BrightWheel (https://mybrightwheel.com/) profile
for images, find all of them, pass the cookies to requests, and then download
all images in bulk. Works with current site design as off 6/24/19"""

UTC = ZoneInfo("UTC")

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

class Config(yaml.YAMLObject):
    yaml_tag = u'!Config'
    yaml_loader=yaml.SafeLoader
    username:  str
    password: str
    guardian_id: str | None
    child_ids: list[str] | None
    signin_url: str
    kidlist_url: str
    start_date: datetime
    end_date: datetime
    start_page:int | None
    page_size:int | None
    timezone: str | None

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
        self.timezone = timezone

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

    return config


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


def pic_finder(browser, kidlist_url, startdate, enddate, args):
    """This is the core logic of the script, navigate through the site, find
    the page with photos, scroll to the bottom to load them all, load them all
    in a specified date range, and create an iterable list of image URLs"""

    browser.get(kidlist_url)

    time.sleep(get_random_time())

    # This xpath is generic enough to find any student listed.
    # You need to iterate through a list you create if you have more than one
    try:
        students = browser.find_elements(By.XPATH, "//a[contains(@href, '/students/')]")
        logger.info("got students")
        if not students:
            raise Exception("No student URLs found")
        if args.student_number:
            profile_url = students[args.student_number - 1].get_property("href")
        else:
            try:
                logger.info("Select a student:")
                for i, student in enumerate(students):
                    logger.info(f"{i}. {student.text}")
                selection = int(input("Enter a number: "))
                profile_url = students[selection].get_property("href")
                # Replace last part of url path with feed
            except Exception as e:
                logger.error(f"[!] - Unable to find student: {e}")
                raise SystemExit

    except Exception as e:
        logger.error(f"[!] - Unable to find profile page: {e}")
        raise SystemExit

    feed_url = profile_url.rsplit("/", 1)[0] + "/feed"

    time.sleep(get_random_time())

    # Get to feed, this is where the pictures are
    # Open the feed_url
    browser.get(feed_url)
    time.sleep(3)

    # Populate the selector for date range to load all images
    start_date = browser.find_element(By.NAME, "start_date")
    start_date.send_keys(startdate)
    end_date = browser.find_element(By.NAME, "end_date")
    end_date.send_keys(enddate)
    select = browser.find_element(By.ID, "select-input-2")
    select.send_keys("Photo")
    select.send_keys(Keys.ENTER)

    # This is the XPATH for the Apply button.
    browser.find_element(By.XPATH, '//*[@id="main"]/div/div/div[2]/div/form/button').click()
    logger.info("[-] - Applied date range")
    try:
        last_height = browser.execute_script("return document.body.scrollHeight")
        counter = 0
        state = True
        while state is True:
            try:
                button = WebDriverWait(browser, 7).until(EC.presence_of_element_located((By.XPATH, '//button[text()="Load more"]')))
                button.click()
            except:
                if counter == 1:
                    logger.info("[-] No Loading button found, there may not be many pictures")
                else:
                    logger.error("[!] No loading button found")
            browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            counter += 1

            # Wait to load the page.
            time.sleep(2)

            # Calculate new scroll height and compare with last scroll height.
            new_height = browser.execute_script("return document.body.scrollHeight")

            if new_height == last_height:
                logger.info("[!] Page fully loaded, finding images...")
                state = False

            last_height = new_height

    except ElementNotVisibleException:
        logger.info("none")


    matches = re.findall(r'<img\s+src="([^"]+)"', browser.page_source,)
    count_matches = len(matches)
    if count_matches == 0:
        logger.error("[!] No Images found to download! Check the source target page")
    else:
        logger.info("[!] Found {} files to download...".format(count_matches))

    return browser, matches


def get_images(browser, matches):
    """Brightwheel moved their image storage to a CDN with signed urls, so we dont need to use
    cookies anymore. I'm eaving this code in case that behavior ever comes back
    
    Since Selenium doesn't handle saving images well, requests
    can do this for us, but we need to pass it the cookies"""
    # Check if the ./pics/ directory exists, create it if it doesn't
    if not os.path.exists('./pics/'):
        os.makedirs('./pics/')

    # cookies = browser.get_cookies()
    # session = requests.Session()
    # for cookie in cookies:
    #     session.cookies.set(cookie["name"], cookie["value"])
    # for match in matches:
    #     try:
    #         filename = match.split("/")[-1].split("?")[0].split("%2F")[-1]
    #         request = session.get(match)
    #         open("./pics/" + filename, "wb").write(request.content)
    #         logger.info("[-] - Downloading {}".format(filename))
    #     except:
    #         logger.error("[!] - Failed to save {}".format(match))
    # try:
    #     session.cookies.clear()
    #     browser.delete_all_cookies()
    #     logger.info("[-] - Cleared cookies")
    # except:
    #     logger.error("[!] - Failed to clear cookies")

    for match in matches:
        try:
            filename = match.split("/")[-1].split("?")[0].split("%2F")[-1]
            request = requests.get(match)
            open("./pics/" + filename, "wb").write(request.content)
            logger.info("[-] - Downloading {}".format(filename))
        except:
            logger.error("[!] - Failed to save {}".format(match))


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

    config = config_parser()

    session = signme_in(browser, config=config)

    session, matches = pic_finder(session, kidlist_url, startdate, enddate, args)

    get_images(session, matches)


if __name__ == "__main__":
    main()
